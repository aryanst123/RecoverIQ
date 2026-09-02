import pytest
from datetime import datetime, timezone, timedelta

from domain.models import RecoveryCase, Customer, Payment
from domain.enums import CaseState, PaymentStatus, CustomerSegment, ExecutionStatus
from integrations.razorpay.config import RazorpayConfig
from integrations.razorpay.client import MockRazorpayGateway
from integrations.razorpay.payment_links import RazorpayPaymentLinkAdapter
from integrations.razorpay.reconciliation import RazorpayLiveReconciliationAdapter
from integrations.razorpay.errors import (
    ProductionEnvironmentForbiddenError,
    RazorpayTimeoutError,
)

@pytest.fixture
def test_config():
    return RazorpayConfig(
        environment="test",
        key_id="rzp_test_mock_key",
        key_secret="mock_secret",
        webhook_secret="mock_wh_secret",
    )

@pytest.fixture
def mock_gateway():
    return MockRazorpayGateway()

@pytest.fixture
def recovery_case():
    now = datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc)
    return RecoveryCase(
        case_id="case_rzp_test_01",
        payment_id="pay_rzp_01",
        customer_id="cust_rzp_01",
        amount_due=4200.0,
        residual_amount=4200.0,
        created_at=now,
        last_updated_at=now,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        automated_action_count=0,
    )

@pytest.fixture
def test_customer():
    return Customer(
        customer_id="cust_rzp_01",
        segment=CustomerSegment.STANDARD,
    )

@pytest.fixture
def test_payment(recovery_case):
    return Payment(
        payment_id=recovery_case.payment_id,
        customer_id=recovery_case.customer_id,
        amount=recovery_case.amount_due,
        created_at=recovery_case.created_at,
        status=PaymentStatus.FAILED,
    )

def test_production_credentials_fail_closed():
    """Verifies that live key prefixes or production environment fail closed immediately."""
    with pytest.raises(ProductionEnvironmentForbiddenError):
        RazorpayConfig(environment="production", key_id="rzp_test_123")

    with pytest.raises(ProductionEnvironmentForbiddenError):
        RazorpayConfig(environment="test", key_id="rzp_live_abc12345678")

def test_payment_link_creation_success(mock_gateway, recovery_case, test_customer):
    """Tests successful creation of Razorpay Test-Mode payment link with correct amount and reference ID."""
    adapter = RazorpayPaymentLinkAdapter(client=mock_gateway)
    status, link_id, err = adapter.create_recovery_link(
        case=recovery_case,
        customer=test_customer,
        idempotency_key="idem_key_01",
        policy_version="recoveriq-v1",
    )

    assert status == ExecutionStatus.SUCCESS
    assert link_id is not None
    assert link_id.startswith("plink_mock_")
    assert err is None

    # Verify link in gateway
    link_obj = mock_gateway.fetch_payment_link(link_id)
    assert link_obj.amount == 4200.0
    assert link_obj.reference_id == f"riq_{recovery_case.case_id}_1"

def test_payment_link_idempotency_duplicate_prevention(mock_gateway, recovery_case, test_customer):
    """Tests that duplicate creation calls with the same logical case reference return identical link without creating duplicates."""
    adapter = RazorpayPaymentLinkAdapter(client=mock_gateway)

    # First attempt
    status1, link_id1, _ = adapter.create_recovery_link(recovery_case, test_customer, "idem_1", "v1")
    # Second attempt (e.g. process retry)
    status2, link_id2, _ = adapter.create_recovery_link(recovery_case, test_customer, "idem_1", "v1")

    assert status1 == ExecutionStatus.SUCCESS
    assert status2 == ExecutionStatus.SUCCESS
    assert link_id1 == link_id2
    assert len(mock_gateway.payment_links) == 1

def test_gateway_timeout_maps_to_execution_unknown(mock_gateway, recovery_case, test_customer):
    """Verifies that gateway network timeouts return EXECUTION_UNKNOWN rather than failing or creating blind duplicates."""
    mock_gateway.simulate_timeout = True
    adapter = RazorpayPaymentLinkAdapter(client=mock_gateway)

    status, link_id, err = adapter.create_recovery_link(recovery_case, test_customer, "idem_timeout", "v1")

    assert status == ExecutionStatus.UNKNOWN
    assert link_id is None
    assert "GATEWAY_TIMEOUT" in err

def test_amount_integrity_rejects_invalid_amount(mock_gateway, recovery_case, test_customer):
    """Verifies that non-positive residual amounts are rejected at the execution boundary."""
    recovery_case.residual_amount = 0.0
    adapter = RazorpayPaymentLinkAdapter(client=mock_gateway)

    status, link_id, err = adapter.create_recovery_link(recovery_case, test_customer, "idem_zero", "v1")
    assert status == ExecutionStatus.FAILED
    assert err == "INVALID_RESIDUAL_AMOUNT"

def test_live_reconciliation_halts_outreach_if_already_captured(mock_gateway, recovery_case, test_payment):
    """Verifies that live reconciliation halts execution if Razorpay shows payment already captured."""
    # Register payment as captured in Razorpay
    mock_gateway.register_test_payment(
        payment_id=test_payment.payment_id,
        amount=test_payment.amount,
        status="captured",
    )

    recon_adapter = RazorpayLiveReconciliationAdapter(client=mock_gateway)
    is_safe, reason = recon_adapter.reconcile_case_before_execution(recovery_case, test_payment)

    assert is_safe is False
    assert "ALREADY_CAPTURED" in reason
    assert recovery_case.current_state == CaseState.RECOVERED
    assert recovery_case.residual_amount == 0.0
    assert test_payment.status == PaymentStatus.CAPTURED

def test_live_reconciliation_allows_outreach_if_payment_still_failed(mock_gateway, recovery_case, test_payment):
    """Verifies that live reconciliation confirms outreach when payment is verified failed."""
    mock_gateway.register_test_payment(
        payment_id=test_payment.payment_id,
        amount=test_payment.amount,
        status="failed",
    )

    recon_adapter = RazorpayLiveReconciliationAdapter(client=mock_gateway)
    is_safe, reason = recon_adapter.reconcile_case_before_execution(recovery_case, test_payment)

    assert is_safe is True
    assert reason is None

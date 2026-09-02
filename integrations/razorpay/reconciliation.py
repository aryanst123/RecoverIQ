import logging
from typing import Tuple, Optional

from domain.models import RecoveryCase, Payment
from domain.enums import CaseState, PaymentStatus
from integrations.razorpay.client import RazorpayClientInterface
from integrations.razorpay.errors import RazorpayIntegrationError

logger = logging.getLogger(__name__)

class RazorpayLiveReconciliationAdapter:
    """
    LIVE RECONCILIATION ADAPTER.
    Queries Razorpay Test-Mode API immediately before critical recovery execution.
    Never trusts stale webhook events as the sole source of truth for payment state.
    """
    def __init__(self, client: RazorpayClientInterface):
        self.client = client

    def reconcile_case_before_execution(
        self,
        case: RecoveryCase,
        payment: Payment,
    ) -> Tuple[bool, Optional[str]]:
        """
        Queries Razorpay to verify live payment status before executing an outreach action.
        Returns: (is_safe_to_execute, rejection_reason_or_none)
        """
        # 1. Internal terminal check first
        if case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
            return False, f"CASE_ALREADY_TERMINAL_{case.current_state.value}"

        if case.residual_amount <= 0.0:
            return False, "RESIDUAL_AMOUNT_ZERO_OR_NEGATIVE"

        # 2. Live Provider Verification
        try:
            rzp_payment = self.client.fetch_payment(payment.payment_id)
            status_str = rzp_payment.status.lower()

            if status_str in ["captured", "paid"]:
                # MONOTONIC TERMINAL PROTECTION: Payment succeeded on provider side
                logger.warning(
                    f"Live reconciliation halt: payment {payment.payment_id} is already '{status_str}' on Razorpay"
                )
                case.current_state = CaseState.RECOVERED
                case.residual_amount = 0.0
                payment.status = PaymentStatus.CAPTURED
                return False, "PAYMENT_ALREADY_CAPTURED_ON_RAZORPAY"

            if status_str in ["authorized"]:
                # Payment is in progress / pending capture
                return False, "PAYMENT_IN_PROGRESS_AUTHORIZED"

            # Payment confirmed still failed / unpaid
            return True, None

        except RazorpayIntegrationError as err:
            logger.error(f"Live reconciliation failed for payment {payment.payment_id}: {err}")
            # Ambiguity guard: If provider check fails, fail closed to MANUAL_REVIEW_REQUIRED
            return False, f"GATEWAY_RECONCILIATION_UNAVAILABLE: {str(err)}"

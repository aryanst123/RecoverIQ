import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

from domain.models import RecoveryCase, Customer, Execution
from domain.enums import ExecutionStatus, ActionType
from integrations.razorpay.client import RazorpayClientInterface
from integrations.razorpay.models import RazorpayPaymentLinkResponse
from integrations.razorpay.errors import (
    RazorpayTimeoutError,
    RazorpayApiError,
    AmbiguousExecutionError,
    InvalidRequestError,
)

logger = logging.getLogger(__name__)

class RazorpayPaymentLinkAdapter:
    """
    BOUNDED RAZORPAY PAYMENT LINK ADAPTER.
    Operates strictly within Razorpay TEST MODE.
    Enforces amount integrity: amount MUST derive from trusted RecoveryCase.residual_amount.
    Enforces idempotency: reference_id derived deterministically from case and sequence.
    Handles network timeouts safely via EXECUTION_UNKNOWN rather than blind retries.
    """
    def __init__(self, client: RazorpayClientInterface):
        self.client = client

    def create_recovery_link(
        self,
        case: RecoveryCase,
        customer: Customer,
        idempotency_key: str,
        policy_version: str,
        expire_hours: float = 72.0,
        accept_partial: bool = False,
    ) -> Tuple[ExecutionStatus, Optional[str], Optional[str]]:
        """
        Creates a Razorpay Test-Mode Payment Link.
        Returns: (ExecutionStatus, provider_link_id_or_none, error_message_or_none)
        """
        # 1. Financial Amount Integrity Validation
        # Amount MUST come strictly from internal case.residual_amount
        trusted_amount = case.residual_amount
        if trusted_amount <= 0.0:
            logger.error(f"Cannot create payment link for non-positive residual amount: {trusted_amount}")
            return ExecutionStatus.FAILED, None, "INVALID_RESIDUAL_AMOUNT"

        # 2. Expiry Timestamp
        now = datetime.now(timezone.utc)
        expire_dt = now + timedelta(hours=expire_hours)

        # 3. Stable reference_id (merchant idempotency token)
        ref_id = f"riq_{case.case_id}_{case.automated_action_count + 1}"

        # 4. Safe Customer contact details
        phone = getattr(customer, "phone", "") or "+919876543210"

        notes = {
            "case_id": case.case_id,
            "policy_version": policy_version,
            "idempotency_key": idempotency_key,
            "system": "RecoverIQ",
        }

        try:
            resp = self.client.create_payment_link(
                amount=trusted_amount,
                reference_id=ref_id,
                customer_phone=phone,
                description=f"RecoverIQ Payment for {case.case_id}",
                notes=notes,
                expire_by=expire_dt,
                accept_partial=accept_partial,
            )
            return ExecutionStatus.SUCCESS, resp.link_id, None

        except RazorpayTimeoutError as timeout_err:
            # CRITICAL SAFETY: Gateway timeout does NOT equal failure or success.
            # Must be recorded as UNKNOWN to trigger reconciliation.
            logger.warning(f"Payment Link creation timed out for case {case.case_id}: {timeout_err}")
            return ExecutionStatus.UNKNOWN, None, f"GATEWAY_TIMEOUT: {str(timeout_err)}"

        except RazorpayApiError as api_err:
            logger.error(f"Razorpay API error creating link for case {case.case_id}: {api_err}")
            return ExecutionStatus.FAILED, None, f"API_ERROR_{api_err.error_code}: {api_err.description}"

        except Exception as e:
            logger.exception(f"Unexpected error creating payment link for case {case.case_id}: {e}")
            return ExecutionStatus.UNKNOWN, None, f"UNEXPECTED_ERROR: {str(e)}"

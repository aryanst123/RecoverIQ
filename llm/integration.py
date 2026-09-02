from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from domain.enums import ActionType, PromiseState
from domain.models import ObservableCaseState, PolicyDecision
from policy.adaptive import RecoverIQAdaptivePolicy
from llm.extractor import LLMContextExtractor
from llm.schema import (
    RecoveryContextExtraction,
    CustomerIntent,
    AmbiguityState,
)

class LLMAugmentedPolicy:
    """
    RECOVERIQ + LLM CONTEXT AUGMENTED DECISION PIPELINE.
    Converts unstructured customer messages into auditable structured context,
    then delegates financial decisioning to RecoverIQ's economic engine.
    
    STRICT BARRIER:
    - Zero execution privileges
    - Cannot declare payments recovered
    - Cannot modify payment balances
    - Cannot override safety constraints
    """
    POLICY_VERSION = "recoveriq-llm-v1"

    def __init__(
        self,
        base_policy: RecoverIQAdaptivePolicy,
        extractor: Optional[LLMContextExtractor] = None,
        enable_p2p_only: bool = False,
    ):
        self.base_policy = base_policy
        self.extractor = extractor or LLMContextExtractor()
        self.enable_p2p_only = enable_p2p_only
        self.stats = {
            "messages_processed": 0,
            "decisions_changed": 0,
            "promises_registered": 0,
            "opt_outs_honored": 0,
            "disputes_noted": 0,
            "fallbacks": 0,
        }

    def process_customer_message(
        self,
        state: ObservableCaseState,
        customer_message: Optional[str],
        current_time: Optional[datetime] = None,
    ) -> ObservableCaseState:
        """
        Extracts structured context from customer message and returns an updated ObservableCaseState.
        Never modifies actual payment status or amount due.
        """
        if not customer_message:
            return state

        self.stats["messages_processed"] += 1
        ref_dt = current_time or datetime.now(timezone.utc)
        extraction = self.extractor.extract_context(customer_message, reference_time=ref_dt)

        if extraction.is_fallback:
            self.stats["fallbacks"] += 1
            return state

        updated_fields = {}

        # 1. Opt-out intent
        if extraction.intent == CustomerIntent.STOP_REQUEST:
            if not self.enable_p2p_only:
                updated_fields["customer_opt_out"] = True
                self.stats["opt_outs_honored"] += 1

        # 2. Promise-to-Pay intent
        if extraction.promise_exists and extraction.promised_date is not None:
            if extraction.ambiguity_state in [AmbiguityState.CONFIRMED, AmbiguityState.TENTATIVE]:
                # Calculate promised due hours from now
                prom_dt = datetime.combine(extraction.promised_date, datetime.min.time(), tzinfo=timezone.utc)
                due_hours = max(1.0, (prom_dt - ref_dt).total_seconds() / 3600.0)
                
                # Active promise accepted state pauses automated outreach
                updated_fields["active_promise_status"] = PromiseState.PROMISE_ACCEPTED
                updated_fields["active_promise_due_hours"] = due_hours
                self.stats["promises_registered"] += 1

        if not updated_fields:
            return state

        return state.model_copy(update=updated_fields)

    def evaluate_case(
        self,
        state: ObservableCaseState,
        customer_message: Optional[str] = None,
        decision_time: Optional[datetime] = None,
    ) -> PolicyDecision:
        """
        Evaluates recovery case:
        1. Context enrichment via LLM extraction
        2. Economic decisioning via base RecoverIQAdaptivePolicy
        """
        current_time = decision_time or datetime.now(timezone.utc)

        # Baseline decision without message (for counterfactual ablation tracking)
        counterfactual_unaugmented_decision = self.base_policy.evaluate_case(state, current_time)

        # Apply LLM structured extraction to observable state
        augmented_state = self.process_customer_message(state, customer_message, current_time)

        # Execute base policy on augmented state
        decision = self.base_policy.evaluate_case(augmented_state, current_time)

        # Check if LLM context altered the selected action
        if decision.selected_action != counterfactual_unaugmented_decision.selected_action:
            self.stats["decisions_changed"] += 1

        return decision

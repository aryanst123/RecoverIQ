import uuid
from datetime import datetime, timezone
from typing import List

from domain.enums import ActionType
from domain.models import ObservableCaseState, PolicyDecision
from policy.eligibility import CandidateActionService

class ControlPolicy:
    """
    ARM A — CONTROL POLICY
    Represents the counterfactual world with zero automated recovery intervention.
    Always selects STOP.
    Allows natural payment recovery to proceed unhindered in the environment.
    """
    def __init__(self, eligibility_service: CandidateActionService = None):
        self.version = "control-v1"
        self.eligibility_service = eligibility_service or CandidateActionService()

    def evaluate(self, state: ObservableCaseState, current_time: datetime = None) -> PolicyDecision:
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"Control policy only accepts ObservableCaseState, got {type(state)}")

        # Query shared eligibility for symmetry verification
        candidate_actions = self.eligibility_service.get_eligible_actions(state)

        return PolicyDecision(
            decision_id=f"dec_ctrl_{uuid.uuid4().hex[:10]}",
            case_id=state.case_id,
            candidate_actions=candidate_actions,
            selected_action=ActionType.STOP,
            model_version="none",
            policy_version=self.version,
            confidence=1.0,
            expected_incremental_recovery=0.0,
            expected_cost=0.0,
            expected_friction_cost=0.0,
            net_expected_value=0.0,
            decision_reason="CONTROL_ARM: No automated recovery outreach permitted.",
        )

class PlaceholderRecoverIQPolicy:
    """
    ARM C — PLACEHOLDER RECOVERIQ POLICY (PHASE 3 ONLY)
    Structural placeholder for the adaptive incremental recovery agent.
    Strictly adheres to the Phase 3 gate: NO adaptive intelligence, NO LLM, NO learned models yet.
    Plugs into the runner so the 3-arm evaluation infrastructure is 100% verified.
    """
    def __init__(self, eligibility_service: CandidateActionService = None):
        self.version = "recoveriq-v0-placeholder"
        self.eligibility_service = eligibility_service or CandidateActionService()

    def evaluate(self, state: ObservableCaseState, current_time: datetime = None) -> PolicyDecision:
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"RecoverIQ placeholder only accepts ObservableCaseState, got {type(state)}")

        # Must query identical shared eligibility service
        candidate_actions = self.eligibility_service.get_eligible_actions(state)

        return PolicyDecision(
            decision_id=f"dec_riq_{uuid.uuid4().hex[:10]}",
            case_id=state.case_id,
            candidate_actions=candidate_actions,
            selected_action=ActionType.STOP,
            model_version="placeholder_none",
            policy_version=self.version,
            confidence=0.0,
            expected_incremental_recovery=0.0,
            expected_cost=0.0,
            expected_friction_cost=0.0,
            net_expected_value=0.0,
            decision_reason="RECOVERIQ_PHASE3_PLACEHOLDER: Awaiting Phase 5 & 6 implementation.",
        )

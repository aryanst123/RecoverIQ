from typing import List, Optional
from domain.enums import ActionType, PaymentStatus, PromiseState, CaseState
from domain.models import ObservableCaseState

class CandidateActionService:
    """
    SHARED ACTION ELIGIBILITY CONTRACT.
    Ensures all policy arms (Baseline, RecoverIQ, Control) see the exact same set
    of eligible candidate actions under identical technical, safety, timing,
    and economic feasibility constraints.
    """
    def __init__(
        self,
        max_automated_actions: int = 3,
        recovery_window_hours: float = 720.0,
        min_cooldown_hours: float = 12.0,
        min_amount_for_p2p: float = 250.0,
        min_amount_for_escalate: float = 1500.0,
        cost_reminder: float = 2.0,
        cost_payment_link: float = 3.0,
        cost_promise_to_pay: float = 5.0,
        cost_escalate: float = 100.0,
        friction_per_action: float = 5.0,
        friction_cap: float = 25.0,
    ):
        self.max_automated_actions = max_automated_actions
        self.recovery_window_hours = recovery_window_hours
        self.min_cooldown_hours = min_cooldown_hours
        self.min_amount_for_p2p = min_amount_for_p2p
        self.min_amount_for_escalate = min_amount_for_escalate
        self.cost_reminder = cost_reminder
        self.cost_payment_link = cost_payment_link
        self.cost_promise_to_pay = cost_promise_to_pay
        self.cost_escalate = cost_escalate
        self.friction_per_action = friction_per_action
        self.friction_cap = friction_cap

    def calculate_friction(self, automated_action_count: int) -> float:
        return min(automated_action_count * self.friction_per_action, self.friction_cap)

    def get_eligible_actions(self, state: ObservableCaseState) -> List[ActionType]:
        """
        Computes universally eligible actions for an observable state.
        Guarantees strict symmetry across evaluation arms.
        """
        # Always includes STOP
        eligible: List[ActionType] = [ActionType.STOP]

        # 1. Hard Safety & Stopping Gates
        if state.customer_opt_out:
            return eligible
        if state.payment_status == PaymentStatus.CAPTURED or state.current_state == CaseState.RECOVERED:
            return eligible
        if state.is_terminal:
            return eligible
        if state.automated_action_count >= self.max_automated_actions:
            return eligible
        if state.hours_since_failure > self.recovery_window_hours:
            return eligible
        if state.last_action_hours_ago is not None and state.last_action_hours_ago < self.min_cooldown_hours:
            return eligible
        if state.active_promise_status in [PromiseState.PROMISE_PROPOSED, PromiseState.PROMISE_ACCEPTED, PromiseState.PROMISE_DUE]:
            return eligible

        # 2. Economic Headroom Checks
        friction = self.calculate_friction(state.automated_action_count)

        # REMINDER
        if state.residual_amount > (self.cost_reminder + friction):
            eligible.append(ActionType.REMINDER)

        # PAYMENT_LINK
        if state.residual_amount > (self.cost_payment_link + friction):
            eligible.append(ActionType.PAYMENT_LINK)

        # PROMISE_TO_PAY: Symmetric availability
        has_active_p2p = state.active_promise_status in [
            PromiseState.PROMISE_PROPOSED,
            PromiseState.PROMISE_ACCEPTED,
            PromiseState.PROMISE_DUE,
        ]
        if (not has_active_p2p) and (state.residual_amount >= self.min_amount_for_p2p):
            if state.residual_amount > (self.cost_promise_to_pay + friction):
                eligible.append(ActionType.PROMISE_TO_PAY)

        # ESCALATE: Symmetric availability
        if state.residual_amount >= self.min_amount_for_escalate:
            if state.residual_amount > (self.cost_escalate + friction):
                eligible.append(ActionType.ESCALATE)

        return eligible

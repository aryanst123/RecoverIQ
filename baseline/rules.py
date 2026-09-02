from typing import Tuple, Optional, List
from domain.enums import ActionType, FailureCode, PaymentStatus, PromiseState, CaseState
from domain.models import ObservableCaseState
from baseline.config import BaselineConfig

def check_stopping_rules(
    state: ObservableCaseState,
    config: BaselineConfig,
) -> Tuple[bool, Optional[str]]:
    """
    Evaluates hard stopping constraints.
    Returns (should_stop, reason)
    """
    # 1. Customer Opt-Out
    if state.customer_opt_out:
        return True, "STOP: Customer has opted out of automated outreach"

    # 2. Already Paid / Recovered
    if state.payment_status == PaymentStatus.CAPTURED or state.current_state == CaseState.RECOVERED:
        return True, "STOP: Payment has already been captured and recovered"

    # 3. Terminal Case State
    if state.is_terminal:
        return True, f"STOP: Case is in terminal state ({state.current_state.value})"

    # 4. Action Count Limit
    if state.automated_action_count >= config.max_automated_actions:
        return True, f"STOP: Automated action limit reached ({state.automated_action_count}/{config.max_automated_actions})"

    # 5. Recovery Window Expiry
    if state.hours_since_failure > config.recovery_window_hours:
        return True, f"STOP: Case age ({state.hours_since_failure:.1f}h) exceeds recovery window ({config.recovery_window_hours:.1f}h)"

    # 6. Active Cooldown between actions
    if state.last_action_hours_ago is not None and state.last_action_hours_ago < config.min_cooldown_hours:
        return True, f"STOP: Cooldown active ({state.last_action_hours_ago:.1f}h since last action < {config.min_cooldown_hours}h required)"

    # 7. Active Promise-to-Pay in progress
    if state.active_promise_status in [PromiseState.PROMISE_PROPOSED, PromiseState.PROMISE_ACCEPTED, PromiseState.PROMISE_DUE]:
        return True, f"STOP: Active promise to pay pending fulfillment ({state.active_promise_status.value})"

    return False, None

def evaluate_action_eligibility(
    state: ObservableCaseState,
    config: BaselineConfig,
) -> List[ActionType]:
    """
    Determines which actions are technically and economically eligible for this case.
    Ensures complete symmetry with any adaptive model.
    """
    eligible = [ActionType.STOP]
    actions_left = config.max_automated_actions - state.automated_action_count

    if actions_left <= 0 or state.customer_opt_out or state.is_terminal:
        return eligible

    friction = config.calculate_friction(state.automated_action_count)

    # REMINDER eligibility:
    cost_rem = config.get_action_cost(ActionType.REMINDER) + friction
    if state.residual_amount > cost_rem:
        eligible.append(ActionType.REMINDER)

    # PAYMENT_LINK eligibility:
    cost_link = config.get_action_cost(ActionType.PAYMENT_LINK) + friction
    if state.residual_amount > cost_link:
        eligible.append(ActionType.PAYMENT_LINK)

    # PROMISE_TO_PAY eligibility:
    # Symmetrical: Available if no active promise and ticket amount meets minimum threshold
    cost_p2p = config.get_action_cost(ActionType.PROMISE_TO_PAY) + friction
    has_active_p2p = state.active_promise_status in [
        PromiseState.PROMISE_PROPOSED,
        PromiseState.PROMISE_ACCEPTED,
        PromiseState.PROMISE_DUE,
    ]
    if (not has_active_p2p) and (state.residual_amount >= config.min_amount_for_p2p) and (state.residual_amount > cost_p2p):
        eligible.append(ActionType.PROMISE_TO_PAY)

    # ESCALATE eligibility:
    # Escalation costs ₹100; only eligible if ticket justifies high-touch outreach and residual balance covers it
    cost_esc = config.get_action_cost(ActionType.ESCALATE) + friction
    if (state.residual_amount >= config.min_amount_for_escalate) and (state.residual_amount > cost_esc):
        eligible.append(ActionType.ESCALATE)

    return eligible

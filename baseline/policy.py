import uuid
from datetime import datetime, timezone
from typing import List

from domain.enums import ActionType, FailureCode, CaseState, PaymentStatus
from domain.models import ObservableCaseState, PolicyDecision
from baseline.config import BaselineConfig, load_baseline_config
from baseline.rules import check_stopping_rules, evaluate_action_eligibility
from baseline.explanations import BaselineDecisionExplanation

class DeterministicBaselinePolicy:
    """
    Strong, transparent, versioned, rule-based recovery policy.
    Operates strictly on ObservableCaseState with zero access to hidden simulator truth.
    Features symmetric access to all recovery actions, including PROMISE_TO_PAY.
    """
    def __init__(self, config: BaselineConfig = None):
        self.config = config or load_baseline_config()
        self.version = self.config.version
        self.checksum = self.config.get_checksum()

    def evaluate(
        self,
        state: ObservableCaseState,
        current_time: datetime = None,
    ) -> PolicyDecision:
        """
        Evaluates observable state and deterministically selects the recovery action.
        """
        if not isinstance(state, ObservableCaseState):
            raise TypeError(f"Baseline policy only accepts ObservableCaseState, got {type(state)}")

        eval_time = current_time or datetime.now(timezone.utc)
        rules_triggered: List[str] = []
        rules_rejected: List[str] = []

        # 1. Evaluate Hard Stopping Rules
        should_stop, stop_reason = check_stopping_rules(state, self.config)
        if should_stop:
            rules_triggered.append(stop_reason)
            explanation = BaselineDecisionExplanation(
                selected_action=ActionType.STOP,
                rules_triggered=rules_triggered,
                rules_rejected=rules_rejected,
                policy_version=self.version,
                config_checksum=self.checksum,
                decision_reason=stop_reason,
            )
            return self._build_decision(
                state=state,
                selected_action=ActionType.STOP,
                candidate_actions=[ActionType.STOP],
                explanation=explanation,
                expected_cost=0.0,
                friction_cost=0.0,
            )

        # 2. Evaluate Eligible Candidate Actions
        candidate_actions = evaluate_action_eligibility(state, self.config)
        friction_cost = self.config.calculate_friction(state.automated_action_count)

        if len(candidate_actions) == 1 and candidate_actions[0] == ActionType.STOP:
            reason = "STOP: No automated recovery action is currently eligible"
            rules_triggered.append(reason)
            explanation = BaselineDecisionExplanation(
                selected_action=ActionType.STOP,
                rules_triggered=rules_triggered,
                rules_rejected=rules_rejected,
                policy_version=self.version,
                config_checksum=self.checksum,
                decision_reason=reason,
            )
            return self._build_decision(
                state=state,
                selected_action=ActionType.STOP,
                candidate_actions=candidate_actions,
                explanation=explanation,
                expected_cost=0.0,
                friction_cost=0.0,
            )

        # 3. Context-Specific Deterministic Action Selection
        selected_action: ActionType = ActionType.STOP
        decision_reason: str = ""

        # Case 3A: High-value case with failed prior automated outreach -> ESCALATE
        if (
            state.residual_amount >= self.config.min_amount_for_escalate
            and state.automated_action_count >= 2
            and ActionType.ESCALATE in candidate_actions
        ):
            selected_action = ActionType.ESCALATE
            decision_reason = (
                f"RuleEscalateHighValue: High ticket value (₹{state.residual_amount:.2f}) "
                f"and {state.automated_action_count} prior automated attempts failed. Routing to human recovery."
            )
            rules_triggered.append(decision_reason)

        # Case 3B: CARD_EXPIRED -> Requires new card / instrument, so PAYMENT_LINK
        elif state.failure_code == FailureCode.CARD_EXPIRED:
            if ActionType.PAYMENT_LINK in candidate_actions:
                selected_action = ActionType.PAYMENT_LINK
                decision_reason = (
                    "RuleCardExpired: Expired card cannot retry identical instrument. "
                    "Sending fresh Payment Link for alternative card/UPI entry."
                )
                rules_triggered.append(decision_reason)
            elif ActionType.ESCALATE in candidate_actions:
                selected_action = ActionType.ESCALATE
                decision_reason = "RuleCardExpiredEscalate: Payment link ineligible; escalating high-value expired card."
                rules_triggered.append(decision_reason)
            else:
                selected_action = ActionType.STOP
                decision_reason = "RuleCardExpiredStop: No alternative card entry action eligible."
                rules_triggered.append(decision_reason)

        # Case 3C: INSUFFICIENT_FUNDS -> Symmetric availability of PROMISE_TO_PAY
        elif state.failure_code == FailureCode.INSUFFICIENT_FUNDS:
            if ActionType.PROMISE_TO_PAY in candidate_actions:
                selected_action = ActionType.PROMISE_TO_PAY
                decision_reason = (
                    f"RuleInsufficientFundsP2P: Account balance delay detected. "
                    f"Offering Promise-to-Pay window for delayed fulfillment."
                )
                rules_triggered.append(decision_reason)
            elif state.automated_action_count >= 1 and ActionType.PAYMENT_LINK in candidate_actions:
                selected_action = ActionType.PAYMENT_LINK
                decision_reason = "RuleInsufficientFundsLink: P2P unavailable; sending payment link retry."
                rules_triggered.append(decision_reason)
            elif ActionType.REMINDER in candidate_actions:
                selected_action = ActionType.REMINDER
                decision_reason = "RuleInsufficientFundsReminder: Sending low-cost balance top-up reminder."
                rules_triggered.append(decision_reason)
            else:
                selected_action = ActionType.STOP
                decision_reason = "RuleInsufficientFundsStop: No viable payment action eligible."
                rules_triggered.append(decision_reason)

        # Case 3D: GATEWAY_DOWNTIME or NETWORK_TIMEOUT -> Transient infrastructure failure
        elif state.failure_code in [FailureCode.GATEWAY_DOWNTIME, FailureCode.NETWORK_TIMEOUT]:
            if state.automated_action_count == 0 and ActionType.REMINDER in candidate_actions:
                selected_action = ActionType.REMINDER
                decision_reason = (
                    f"RuleTransientFailureReminder: Transient gateway failure ({state.failure_code.value}). "
                    "Sending soft reminder to retry once network stabilizes."
                )
                rules_triggered.append(decision_reason)
            elif ActionType.PAYMENT_LINK in candidate_actions:
                selected_action = ActionType.PAYMENT_LINK
                decision_reason = (
                    f"RuleTransientFailureLink: Re-attempt after transient failure ({state.failure_code.value}). "
                    "Issuing direct Payment Link with fresh gateway session."
                )
                rules_triggered.append(decision_reason)
            else:
                selected_action = ActionType.STOP
                decision_reason = "RuleTransientFailureStop: No eligible retry action."
                rules_triggered.append(decision_reason)

        # Case 3E: AUTHENTICATION_FAILED or USER_DROPPED -> Customer engagement friction
        elif state.failure_code in [FailureCode.AUTHENTICATION_FAILED, FailureCode.USER_DROPPED]:
            if state.automated_action_count == 0 and ActionType.REMINDER in candidate_actions:
                selected_action = ActionType.REMINDER
                decision_reason = (
                    f"RuleEngagementReminder: Customer authentication/checkout friction ({state.failure_code.value}). "
                    "Triggering instant reminder."
                )
                rules_triggered.append(decision_reason)
            elif state.automated_action_count == 1 and ActionType.PAYMENT_LINK in candidate_actions:
                selected_action = ActionType.PAYMENT_LINK
                decision_reason = (
                    f"RuleEngagementLink: Reminder did not convert. "
                    "Escalating intervention to direct Payment Link."
                )
                rules_triggered.append(decision_reason)
            elif (
                state.automated_action_count == 2
                and ActionType.PROMISE_TO_PAY in candidate_actions
            ):
                selected_action = ActionType.PROMISE_TO_PAY
                decision_reason = "RuleEngagementP2P: Final automated attempt offering Promise-to-Pay arrangement."
                rules_triggered.append(decision_reason)
            else:
                selected_action = ActionType.STOP
                decision_reason = "RuleEngagementStop: Action limit reached or no candidate available."
                rules_triggered.append(decision_reason)

        # Case 3F: General Fallback
        else:
            if ActionType.PAYMENT_LINK in candidate_actions:
                selected_action = ActionType.PAYMENT_LINK
                decision_reason = "RuleFallbackLink: General recovery default to direct Payment Link."
                rules_triggered.append(decision_reason)
            elif ActionType.REMINDER in candidate_actions:
                selected_action = ActionType.REMINDER
                decision_reason = "RuleFallbackReminder: General recovery fallback to Reminder."
                rules_triggered.append(decision_reason)
            else:
                selected_action = ActionType.STOP
                decision_reason = "RuleFallbackStop: No eligible fallback action."
                rules_triggered.append(decision_reason)

        # 4. Construct Explanation and Decision
        action_cost = self.config.get_action_cost(selected_action)
        explanation = BaselineDecisionExplanation(
            selected_action=selected_action,
            rules_triggered=rules_triggered,
            rules_rejected=rules_rejected,
            policy_version=self.version,
            config_checksum=self.checksum,
            decision_reason=decision_reason,
        )

        return self._build_decision(
            state=state,
            selected_action=selected_action,
            candidate_actions=candidate_actions,
            explanation=explanation,
            expected_cost=action_cost,
            friction_cost=friction_cost,
        )

    def _build_decision(
        self,
        state: ObservableCaseState,
        selected_action: ActionType,
        candidate_actions: List[ActionType],
        explanation: BaselineDecisionExplanation,
        expected_cost: float,
        friction_cost: float,
    ) -> PolicyDecision:
        # Expected incremental recovery for baseline is a transparent heuristic:
        # Baseline does NOT claim learned counterfactual probabilities.
        # Heuristic: 0.0 for STOP, or residual_amount for active interventions
        expected_inc_recovery = state.residual_amount if selected_action != ActionType.STOP else 0.0
        net_val = expected_inc_recovery - expected_cost - friction_cost

        return PolicyDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            case_id=state.case_id,
            candidate_actions=candidate_actions,
            selected_action=selected_action,
            model_version="deterministic_rule_engine",
            policy_version=self.version,
            confidence=1.0, # Deterministic rule match confidence
            expected_incremental_recovery=expected_inc_recovery,
            expected_cost=expected_cost,
            expected_friction_cost=friction_cost,
            net_expected_value=net_val,
            decision_reason=explanation.decision_reason,
        )

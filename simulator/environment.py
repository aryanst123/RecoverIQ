from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
import numpy as np
import yaml

from domain.enums import (
    ActionType,
    CaseState,
    ExecutionStatus,
    RecoveryStatus,
    PaymentStatus,
    PromiseState,
)
from domain.models import (
    Customer,
    Payment,
    PaymentAttempt,
    RecoveryCase,
    RecoveryAction,
    Promise,
    Execution,
    RecoveryOutcome,
    AuditRecord,
    PotentialOutcome,
    ObservableCaseState,
)
from domain.state_machine import CaseStateMachine
from simulator.scenarios import ScenarioConfig, get_scenario

class SimulationEnvironment:
    """
    Stateful simulation environment for failed payment recovery.
    Enforces a strict barrier: agents can ONLY access observable state.
    """
    def __init__(
        self,
        scenario_id: str = "S1_HIGH_NATURAL_RECOVERY",
        costs_config_path: str = "configs/costs.yaml",
        seed: int = 42,
    ):
        self.scenario: ScenarioConfig = get_scenario(scenario_id)
        self.rng = np.random.default_rng(seed)
        self._load_costs(costs_config_path)

        # Internal repositories
        self._customers: Dict[str, Customer] = {}
        self._payments: Dict[str, Payment] = {}
        self._attempts: Dict[str, List[PaymentAttempt]] = {}
        self._cases: Dict[str, RecoveryCase] = {}
        self._actions: Dict[str, List[RecoveryAction]] = {}
        self._promises: Dict[str, List[Promise]] = {}
        self._executions: Dict[str, List[Execution]] = {}
        self._outcomes: Dict[str, RecoveryOutcome] = {}
        self._audits: Dict[str, List[AuditRecord]] = {}

        # STRICTLY HIDDEN SIMULATION TRUTH: NEVER ACCESSIBLE VIA AGENT APIS
        self._hidden_potential_outcomes: Dict[str, PotentialOutcome] = {}

    def _load_costs(self, path: str):
        try:
            with open(path, "r") as f:
                cfg = yaml.safe_load(f)
            self.action_costs = {
                ActionType(k): float(v) for k, v in cfg.get("action_costs", {}).items()
            }
            fric = cfg.get("friction_costs", {})
            self.friction_per_action = float(fric.get("per_previous_automated_action", 5.0))
            self.friction_cap = float(fric.get("cap", 25.0))
        except Exception:
            # Safe defaults if file missing during scratch testing
            self.action_costs = {
                ActionType.REMINDER: 2.0,
                ActionType.PAYMENT_LINK: 3.0,
                ActionType.PROMISE_TO_PAY: 5.0,
                ActionType.ESCALATE: 100.0,
                ActionType.STOP: 0.0,
            }
            self.friction_per_action = 5.0
            self.friction_cap = 25.0

    def register_case(
        self,
        customer: Customer,
        payment: Payment,
        attempt: PaymentAttempt,
        case: RecoveryCase,
        hidden_outcome: PotentialOutcome,
    ):
        """Registers a case and stores the hidden potential outcome in isolated memory."""
        self._customers[customer.customer_id] = customer
        self._payments[payment.payment_id] = payment
        self._attempts[case.case_id] = [attempt]
        self._cases[case.case_id] = case
        self._actions[case.case_id] = []
        self._promises[case.case_id] = []
        self._executions[case.case_id] = []
        self._audits[case.case_id] = []
        self._hidden_potential_outcomes[case.case_id] = hidden_outcome

        # Default outcome record (unrecovered)
        self._outcomes[case.case_id] = RecoveryOutcome(
            case_id=case.case_id,
            recovered_amount=0.0,
            recovery_status=RecoveryStatus.UNRECOVERED,
            is_attributed=False,
        )

    def get_observable_state(self, case_id: str, current_time: Optional[datetime] = None) -> ObservableCaseState:
        """
        STRICT BARRIER METHOD: Returns ONLY observable features.
        Zero leakage of potential outcomes or latent simulation parameters.
        """
        case = self._cases[case_id]
        customer = self._customers[case.customer_id]
        payment = self._payments[case.payment_id]
        attempts = self._attempts[case_id]
        latest_attempt = attempts[-1]
        actions = self._actions.get(case_id, [])

        eval_time = current_time or case.last_updated_at
        hours_since_failure = max(0.0, (eval_time - case.created_at).total_seconds() / 3600.0)

        last_action_type = actions[-1].action_type if actions else None
        last_action_hours_ago = (
            max(0.0, (eval_time - actions[-1].timestamp).total_seconds() / 3600.0)
            if actions
            else None
        )

        active_promise = self._get_active_promise(case_id)
        promise_status = active_promise.status if active_promise else None
        promise_due_hours = (
            (active_promise.due_at - eval_time).total_seconds() / 3600.0
            if active_promise
            else None
        )

        is_terminal = CaseStateMachine.is_terminal(case.current_state)

        return ObservableCaseState(
            case_id=case.case_id,
            payment_id=payment.payment_id,
            customer_id=customer.customer_id,
            customer_segment=customer.segment,
            customer_channel_preference=customer.channel_preference,
            customer_opt_out=customer.opt_out,
            amount_due=case.amount_due,
            residual_amount=case.residual_amount,
            current_state=case.current_state,
            failure_code=latest_attempt.failure_code,
            failure_reason=latest_attempt.failure_reason,
            attempt_count=len(attempts),
            automated_action_count=case.automated_action_count,
            hours_since_failure=hours_since_failure,
            last_action_type=last_action_type,
            last_action_hours_ago=last_action_hours_ago,
            active_promise_status=promise_status,
            active_promise_due_hours=promise_due_hours,
            payment_status=payment.status,
            is_terminal=is_terminal,
        )

    def _get_active_promise(self, case_id: str) -> Optional[Promise]:
        promises = self._promises.get(case_id, [])
        for p in reversed(promises):
            if p.status in [PromiseState.PROMISE_PROPOSED, PromiseState.PROMISE_ACCEPTED, PromiseState.PROMISE_DUE]:
                return p
        return None

    def execute_action(
        self,
        case_id: str,
        action_type: ActionType,
        timestamp: datetime,
        idempotency_key: str,
        policy_version: str = "1.0.0",
    ) -> Tuple[Execution, RecoveryCase]:
        """
        Executes an intervention within the simulated environment.
        Updates case state, creates execution record, and checks counterfactual recovery.
        """
        case = self._cases[case_id]
        payment = self._payments[case.payment_id]
        customer = self._customers[case.customer_id]
        hidden = self._hidden_potential_outcomes[case_id]

        # 1. State machine validation
        if CaseStateMachine.is_terminal(case.current_state):
            raise ValueError(f"Cannot execute action on case in terminal state {case.current_state}")

        # 2. Check for adversarial execution failures (Scenario S6)
        exec_id = f"exec_{len(self._executions[case_id]) + 1}_{case_id}"
        if self.scenario.execution_timeout_rate > 0 and self.rng.random() < self.scenario.execution_timeout_rate:
            exec_rec = Execution(
                execution_id=exec_id,
                action_id="",
                case_id=case_id,
                status=ExecutionStatus.TIMEOUT,
                idempotency_key=idempotency_key,
                created_at=timestamp,
                updated_at=timestamp,
                error_message="Gateway connection timed out during execution",
            )
            case.current_state = CaseState.EXECUTION_UNKNOWN
            case.last_updated_at = timestamp
            self._executions[case_id].append(exec_rec)
            return exec_rec, case

        if self.scenario.execution_failure_rate > 0 and self.rng.random() < self.scenario.execution_failure_rate:
            exec_rec = Execution(
                execution_id=exec_id,
                action_id="",
                case_id=case_id,
                status=ExecutionStatus.FAILED,
                idempotency_key=idempotency_key,
                created_at=timestamp,
                updated_at=timestamp,
                error_message="Downstream provider rejected message delivery",
            )
            case.last_updated_at = timestamp
            self._executions[case_id].append(exec_rec)
            return exec_rec, case

        # 3. Calculate financial action cost and customer friction cost
        action_cost = self.action_costs.get(action_type, 0.0)
        friction_cost = min(
            case.automated_action_count * self.friction_per_action,
            self.friction_cap,
        )

        action_id = f"act_{len(self._actions[case_id]) + 1}_{case_id}"
        rec_action = RecoveryAction(
            action_id=action_id,
            case_id=case_id,
            action_type=action_type,
            timestamp=timestamp,
            status=ExecutionStatus.SUCCESS,
            cost=action_cost,
            friction_cost=friction_cost,
            policy_version=policy_version,
            channel_used=customer.channel_preference,
        )
        self._actions[case_id].append(rec_action)

        exec_rec = Execution(
            execution_id=exec_id,
            action_id=action_id,
            case_id=case_id,
            status=ExecutionStatus.SUCCESS,
            idempotency_key=idempotency_key,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._executions[case_id].append(exec_rec)

        # 4. Update case counters and state
        if action_type != ActionType.STOP:
            case.automated_action_count += 1

        # 5. Handle action-specific domain behavior
        if action_type == ActionType.STOP:
            case.current_state = CaseState.STOPPED
            case.terminal_reason = "POLICY_STOPPED"
        elif action_type == ActionType.ESCALATE:
            case.current_state = CaseState.MANUAL_REVIEW_REQUIRED
            case.terminal_reason = "ESCALATED_TO_HUMAN"
        elif action_type == ActionType.PROMISE_TO_PAY:
            # Set up promise state
            due_at = timestamp + timedelta(days=3)
            prom_id = f"prom_{len(self._promises[case_id]) + 1}_{case_id}"
            promise = Promise(
                promise_id=prom_id,
                case_id=case_id,
                promised_amount=case.residual_amount,
                promised_at=timestamp,
                due_at=due_at,
                status=PromiseState.PROMISE_ACCEPTED,
                verification_timestamp=timestamp,
            )
            self._promises[case_id].append(promise)
            case.active_promise_id = prom_id
            case.current_state = CaseState.WAITING_FOR_OUTCOME
        else:
            # REMINDER or PAYMENT_LINK
            case.current_state = CaseState.WAITING_FOR_OUTCOME

        case.last_updated_at = timestamp

        # 6. Check if recovery occurs under chosen action
        recovered = False
        recovery_time_hours = None

        if action_type == ActionType.REMINDER and hidden.y_reminder:
            recovered = True
            recovery_time_hours = hidden.recovery_time_hours_reminder
        elif action_type == ActionType.PAYMENT_LINK and hidden.y_payment_link:
            recovered = True
            recovery_time_hours = hidden.recovery_time_hours_payment_link
        elif action_type == ActionType.PROMISE_TO_PAY and hidden.y_promise_to_pay:
            recovered = True
            recovery_time_hours = hidden.recovery_time_hours_promise_to_pay
        elif action_type == ActionType.ESCALATE and hidden.y_escalate:
            recovered = True
            recovery_time_hours = hidden.recovery_time_hours_escalate

        if recovered:
            rec_timestamp = timestamp + timedelta(hours=recovery_time_hours or 1.0)
            payment.status = PaymentStatus.CAPTURED
            case.current_state = CaseState.RECOVERED
            case.residual_amount = 0.0
            case.last_updated_at = rec_timestamp

            # Fulfill any promise if present
            active_p = self._get_active_promise(case_id)
            if active_p:
                active_p.status = PromiseState.PROMISE_FULFILLED

            self._outcomes[case_id] = RecoveryOutcome(
                case_id=case_id,
                recovered_amount=case.amount_due,
                recovery_timestamp=rec_timestamp,
                attribution_window_hours=72,
                recovery_status=RecoveryStatus.FULLY_RECOVERED,
                is_attributed=True,
                action_attributed_id=action_id,
            )

        return exec_rec, case

    def check_natural_recovery_for_control(self, case_id: str, as_of_time: datetime):
        """Simulates natural recovery for ARM A (Control) where no action is taken."""
        case = self._cases[case_id]
        payment = self._payments[case.payment_id]
        hidden = self._hidden_potential_outcomes[case_id]

        if hidden.y_control:
            recovery_time = hidden.recovery_time_hours_control or 12.0
            rec_timestamp = case.created_at + timedelta(hours=recovery_time)
            if rec_timestamp <= as_of_time:
                payment.status = PaymentStatus.CAPTURED
                case.current_state = CaseState.RECOVERED
                case.residual_amount = 0.0
                case.last_updated_at = rec_timestamp
                self._outcomes[case_id] = RecoveryOutcome(
                    case_id=case_id,
                    recovered_amount=case.amount_due,
                    recovery_timestamp=rec_timestamp,
                    attribution_window_hours=72,
                    recovery_status=RecoveryStatus.FULLY_RECOVERED,
                    is_attributed=False, # Natural, not attributed to an action
                )

    def get_outcome(self, case_id: str) -> RecoveryOutcome:
        return self._outcomes[case_id]

    def get_audit_trail(self, case_id: str) -> List[AuditRecord]:
        return self._audits.get(case_id, [])

    # FOR EVALUATION AND BENCHMARK HARNESS ONLY
    def get_hidden_truth_FOR_EVALUATION_ONLY(self, case_id: str) -> PotentialOutcome:
        """
        EXPLICIT EVALUATION HOOK.
        MUST NEVER BE CALLED DURING AGENT OR POLICY INFERENCE.
        """
        return self._hidden_potential_outcomes[case_id]

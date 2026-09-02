from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from domain.enums import (
    ActionType,
    CaseState,
    PromiseState,
    ExecutionStatus,
    RecoveryStatus,
    PaymentStatus,
    FailureCode,
    CustomerSegment,
    ChannelPreference,
    EvaluationArm,
)

class DomainBaseModel(BaseModel):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

class Customer(DomainBaseModel):
    customer_id: str
    segment: CustomerSegment = CustomerSegment.STANDARD
    channel_preference: ChannelPreference = ChannelPreference.WHATSAPP
    opt_out: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Payment(DomainBaseModel):
    payment_id: str
    customer_id: str
    amount: float
    currency: str = "INR"
    created_at: datetime
    status: PaymentStatus = PaymentStatus.FAILED

class PaymentAttempt(DomainBaseModel):
    attempt_id: str
    payment_id: str
    failure_code: FailureCode
    failure_reason: str
    attempted_at: datetime
    gateway_reference: Optional[str] = None

class RecoveryCase(DomainBaseModel):
    case_id: str
    payment_id: str
    customer_id: str
    current_state: CaseState = CaseState.PAYMENT_FAILED
    amount_due: float
    residual_amount: float
    created_at: datetime
    last_updated_at: datetime
    automated_action_count: int = 0
    next_eligible_at: Optional[datetime] = None
    terminal_reason: Optional[str] = None
    active_promise_id: Optional[str] = None

class RecoveryAction(DomainBaseModel):
    action_id: str
    case_id: str
    action_type: ActionType
    timestamp: datetime
    status: ExecutionStatus = ExecutionStatus.PENDING
    cost: float = 0.0
    friction_cost: float = 0.0
    policy_version: str = "1.0.0"
    channel_used: Optional[ChannelPreference] = None

class Promise(DomainBaseModel):
    promise_id: str
    case_id: str
    promised_amount: float
    promised_at: datetime
    due_at: datetime
    status: PromiseState = PromiseState.PROMISE_PROPOSED
    verification_timestamp: Optional[datetime] = None

class RecoveryEvent(DomainBaseModel):
    event_id: str
    case_id: str
    event_type: str
    timestamp: datetime
    source: str
    payload_hash: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class PolicyDecision(DomainBaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    case_id: str
    candidate_actions: List[ActionType]
    selected_action: ActionType
    model_version: str
    policy_version: str
    confidence: float
    expected_incremental_recovery: float
    expected_cost: float
    expected_friction_cost: float = 0.0
    net_expected_value: float = 0.0
    decision_reason: str

class Execution(DomainBaseModel):
    execution_id: str
    action_id: str
    case_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    external_reference: Optional[str] = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None

class RecoveryOutcome(DomainBaseModel):
    case_id: str
    recovered_amount: float = 0.0
    recovery_timestamp: Optional[datetime] = None
    attribution_window_hours: int = 72
    recovery_status: RecoveryStatus = RecoveryStatus.UNRECOVERED
    is_attributed: bool = False
    action_attributed_id: Optional[str] = None

class AuditRecord(DomainBaseModel):
    audit_id: str
    timestamp: datetime
    case_id: str
    actor: str
    action: str
    observed_state: Dict[str, Any]
    model_output: Optional[Dict[str, Any]] = None
    policy_output: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None

class ExperimentRun(DomainBaseModel):
    run_id: str
    seed: int
    scenario: str
    arm: EvaluationArm
    case_count: int
    metrics: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

# SIMULATOR / EVALUATION ONLY: NEVER EXPOSED TO AGENTS OR POLICIES
class PotentialOutcome(DomainBaseModel):
    """Hidden ground truth: Potential outcomes under different interventions."""
    case_id: str
    latent_payment_propensity: float # P(pay natural) in [0, 1]
    latent_response_propensity: float # P(respond to messages) in [0, 1]
    latent_p2p_reliability: float # P(fulfill promise given accepted) in [0, 1]
    latent_friction_sensitivity: float # penalty per touchpoint in [0, 1]
    
    # Counterfactual outcomes Y(action): True if would recover under action
    y_control: bool
    y_reminder: bool
    y_payment_link: bool
    y_promise_to_pay: bool
    y_escalate: bool
    
    # Counterfactual time to recovery (hours from failure)
    recovery_time_hours_control: Optional[float] = None
    recovery_time_hours_reminder: Optional[float] = None
    recovery_time_hours_payment_link: Optional[float] = None
    recovery_time_hours_promise_to_pay: Optional[float] = None
    recovery_time_hours_escalate: Optional[float] = None

class ObservableCaseState(DomainBaseModel):
    """
    STRICT BARRIER: This is the ONLY context an agent/policy is permitted to observe.
    Contains NO potential outcomes, NO counterfactuals, and NO latent simulation variables.
    """
    case_id: str
    payment_id: str
    customer_id: str
    customer_segment: CustomerSegment
    customer_channel_preference: ChannelPreference
    customer_opt_out: bool
    amount_due: float
    residual_amount: float
    current_state: CaseState
    failure_code: FailureCode
    failure_reason: str
    attempt_count: int
    automated_action_count: int
    hours_since_failure: float
    last_action_type: Optional[ActionType] = None
    last_action_hours_ago: Optional[float] = None
    active_promise_status: Optional[PromiseState] = None
    active_promise_due_hours: Optional[float] = None
    payment_status: PaymentStatus = PaymentStatus.FAILED
    is_terminal: bool = False

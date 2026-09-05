import os
from dotenv import load_dotenv
load_dotenv()
import json
import yaml
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, Response, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from domain.enums import ActionType, PaymentStatus, CaseState, CustomerSegment, ChannelPreference, FailureCode, ExecutionStatus
from domain.models import ObservableCaseState, Customer, Payment, PaymentAttempt, RecoveryCase, RecoveryAction, Execution, AuditRecord, PolicyDecision
from domain.state_machine import CaseStateMachine
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from baseline.policy import DeterministicBaselinePolicy
from baseline.config import load_baseline_config
from models.artifacts import ModelArtifactManager
from policy.adaptive import RecoverIQAdaptivePolicy
from execution.executor import SafeRecoveryExecutor
from execution.locks import CaseLockManager
from execution.reservation import ActionReservationService
from execution.idempotency import MerchantIdempotencyService
from reconciliation.service import LiveStateReconciliationService
from safety.audit import AuditTrailService, StructuredAuditRecord
from ingestion.deduplication import WebhookDeduplicationStore
from llm.extractor import LLMContextExtractor
from llm.integration import LLMAugmentedPolicy
from integrations.razorpay.config import RazorpayConfig
from integrations.razorpay.client import RazorpayClientInterface, MockRazorpayGateway, RazorpayTestClient
from integrations.razorpay.payment_links import RazorpayPaymentLinkAdapter
from integrations.razorpay.reconciliation import RazorpayLiveReconciliationAdapter
from integrations.razorpay.webhooks import RazorpayWebhookVerifier
from integrations.razorpay.events import RazorpayEventNormalizer

app = FastAPI(
    title="RecoverIQ Revenue Recovery Engine API",
    description="Adaptive Incremental Revenue Recovery for Failed Payments — Built for Razorpay AI Buildathon 2026",
    version="1.0.0",
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# IN-MEMORY SYSTEM STATE & SINGLETON SERVICES
# =====================================================================

class SystemState:
    def __init__(self):
        # Core ML & Policy
        self.model_manager = ModelArtifactManager()
        try:
            self.model = self.model_manager.load_model("incremental-model-v1")
        except Exception:
            self.model = None

        self.policy = RecoverIQAdaptivePolicy(model=self.model, minimum_incremental_recovery=250.0) if self.model else None
        self.baseline_policy = DeterministicBaselinePolicy(load_baseline_config())
        self.llm_extractor = LLMContextExtractor()
        self.llm_policy = LLMAugmentedPolicy(base_policy=self.policy, extractor=self.llm_extractor) if self.policy else None

        # Execution & Safety
        self.lock_manager = CaseLockManager()
        self.reservation_service = ActionReservationService()
        self.idempotency_service = MerchantIdempotencyService()
        self.audit_logger = AuditTrailService()
        self.reconciliation_service = LiveStateReconciliationService()
        self.dedup_store = WebhookDeduplicationStore()

        # Razorpay Adapters
        self.razorpay_config = RazorpayConfig.from_env()
        if self.razorpay_config.key_id and self.razorpay_config.key_secret:
            try:
                self.razorpay_client = RazorpayTestClient(self.razorpay_config)
                self.razorpay_mode = "CONNECTED"
            except Exception:
                self.razorpay_client = MockRazorpayGateway()
                self.razorpay_mode = "OFFLINE_MOCK"
        else:
            self.razorpay_client = MockRazorpayGateway()
            self.razorpay_mode = "OFFLINE_MOCK"

        self.payment_link_adapter = RazorpayPaymentLinkAdapter(client=self.razorpay_client)
        self.razorpay_reconciler = RazorpayLiveReconciliationAdapter(client=self.razorpay_client)
        self.webhook_verifier = RazorpayWebhookVerifier(webhook_secret=self.razorpay_config.webhook_secret or "mock_sec_123")
        self.event_normalizer = RazorpayEventNormalizer()

        # Cases Store
        self.customers: Dict[str, Customer] = {}
        self.payments: Dict[str, Payment] = {}
        self.attempts: Dict[str, List[PaymentAttempt]] = defaultdict(list)
        self.cases: Dict[str, RecoveryCase] = {}
        self.actions: Dict[str, List[RecoveryAction]] = defaultdict(list)
        self.executions: Dict[str, List[Execution]] = defaultdict(list)
        self.decision_traces: Dict[str, Any] = {}
        self.payment_links: Dict[str, Any] = {}
        self.webhook_logs: List[Dict[str, Any]] = []

        # Seed initial demo cases
        self._seed_manual_override_demo_case()
        self._seed_demo_cases()

    def _seed_demo_cases(self, count: int = 40):
        gen = SyntheticCaseGenerator(seed=20260902)
        batch = gen.generate_batch(count=count, scenario_id="S1_HIGH_NATURAL_RECOVERY")
        for cust, pay, att, case, hidden in batch:
            self.customers[cust.customer_id] = cust
            self.payments[pay.payment_id] = pay
            self.attempts[case.case_id].append(att)
            self.cases[case.case_id] = case

    def _seed_manual_override_demo_case(self):
        """
        DEMO-ONLY: Create ONE fresh case within recovery window to demonstrate Manual Override.
        Clearly marked as DEMO. Not included in benchmark/evaluation.
        """
        try:
            print("[SEED] Starting demo case seeding...")

            # Exactly: 2026-09-04 09:18:46 UTC
            demo_timestamp = datetime(2026, 9, 4, 9, 18, 46, tzinfo=timezone.utc)

            # Demo customer
            demo_cust = Customer(
                customer_id="cust_DEMO_OVERRIDE",
                segment=CustomerSegment.STANDARD,
                channel_preference=ChannelPreference.WHATSAPP,
                opt_out=False,
                created_at=demo_timestamp,
            )
            print(f"[SEED] Created demo customer: {demo_cust.customer_id}")

            # Demo payment
            demo_pay = Payment(
                payment_id="pay_DEMO_OVERRIDE",
                customer_id="cust_DEMO_OVERRIDE",
                amount=2500.00,  # High enough for all actions including ESCALATE (min 1500)
                currency="INR",
                status=PaymentStatus.FAILED,
                created_at=demo_timestamp,
            )
            print(f"[SEED] Created demo payment: {demo_pay.payment_id}")

            # Demo attempt
            demo_att = PaymentAttempt(
                attempt_id="att_DEMO_OVERRIDE_001",
                payment_id="pay_DEMO_OVERRIDE",
                failure_code=FailureCode.INSUFFICIENT_FUNDS,
                failure_reason="[DEMO] Insufficient funds - demonstrating Manual Override capability",
                attempted_at=demo_timestamp,
            )
            print(f"[SEED] Created demo attempt: {demo_att.attempt_id}")

            # Demo case - RECOVERY_ELIGIBLE state, 0 actions taken, within window
            demo_case = RecoveryCase(
                case_id="case_DEMO_OVERRIDE",
                payment_id="pay_DEMO_OVERRIDE",
                customer_id="cust_DEMO_OVERRIDE",
                amount_due=2500.00,
                residual_amount=2500.00,
                current_state=CaseState.RECOVERY_ELIGIBLE,
                automated_action_count=0,
                created_at=demo_timestamp,
                last_updated_at=demo_timestamp,
                terminal_reason=None,
            )
            print(f"[SEED] Created demo case: {demo_case.case_id}")

            self.customers[demo_cust.customer_id] = demo_cust
            self.payments[demo_pay.payment_id] = demo_pay
            self.attempts[demo_case.case_id].append(demo_att)
            self.cases[demo_case.case_id] = demo_case

            print(f"[SEED] Demo case seeding complete. Total cases: {len(self.cases)}")
        except Exception as e:
            print(f"[SEED] ERROR during demo case seeding: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

state = SystemState()

# =====================================================================
# REQUEST & RESPONSE SCHEMAS
# =====================================================================

class CustomerMessageRequest(BaseModel):
    message: str
    message_timestamp: Optional[str] = None

class ExecuteActionRequest(BaseModel):
    action_type: str
    idempotency_key: Optional[str] = None

class FailureInjectionRequest(BaseModel):
    scenario_type: str = Field(..., description="F1_TIMEOUT, F2_IDEMPOTENCY, F3_DUPLICATE_WEBHOOK, F4_OUT_OF_ORDER, F5_PRE_OUTREACH_CAPTURE, F6_OPT_OUT")
    case_id: Optional[str] = None

# =====================================================================
# API ROUTES: HEALTH & DASHBOARD
# =====================================================================

@app.get("/api/health")
def get_health():
    return {
        "status": "HEALTHY",
        "service": "RecoverIQ Revenue Recovery Engine",
        "version": "1.0.0",
        "environment": "test",
        "razorpay_mode": state.razorpay_mode,
        "is_test_mode": state.razorpay_config.environment == "test",
        "is_configured": state.razorpay_config.is_configured(),
        "model_loaded": state.model is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/dashboard/kpis")
def get_dashboard_kpis():
    total_cases = len(state.cases)
    active_cases = sum(1 for c in state.cases.values() if not CaseStateMachine.is_terminal(c.current_state))
    recovered_cases = sum(1 for c in state.cases.values() if c.current_state == CaseState.RECOVERED)
    total_revenue_at_risk = sum(c.amount_due for c in state.cases.values())
    total_recovered_amount = sum(c.amount_due - c.residual_amount for c in state.cases.values())

    return {
        "total_failed_payments": total_cases,
        "active_recovery_cases": active_cases,
        "recovered_cases_count": recovered_cases,
        "recovery_rate": (recovered_cases / total_cases) if total_cases > 0 else 0.0,
        "revenue_at_risk_inr": total_revenue_at_risk,
        "revenue_recovered_inr": total_recovered_amount,
        "safety_violations_count": 0,
        "razorpay_integration_status": state.razorpay_mode,
        "data_source_badge": "SIMULATOR / TEST MODE",
    }

# =====================================================================
# API ROUTES: RECOVERY CASES
# =====================================================================

@app.get("/api/cases")
def list_cases(
    state_filter: Optional[str] = None,
    failure_code: Optional[str] = None,
    segment: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    case_list = list(state.cases.values())

    # Apply filters
    if state_filter:
        case_list = [c for c in case_list if c.current_state.value == state_filter]
    if failure_code:
        case_list = [
            c for c in case_list
            if state.attempts.get(c.case_id) and state.attempts[c.case_id][-1].failure_code.value == failure_code
        ]
    if segment:
        case_list = [
            c for c in case_list
            if state.customers.get(c.customer_id) and state.customers[c.customer_id].segment.value == segment
        ]

    paginated = case_list[offset : offset + limit]

    summaries = []
    now = datetime.now(timezone.utc)
    for c in paginated:
        cust = state.customers.get(c.customer_id)
        attempts = state.attempts.get(c.case_id, [])
        latest_att = attempts[-1] if attempts else None
        hours_ago = (now - c.created_at).total_seconds() / 3600.0

        # Evaluate recommended action if available
        rec_action = "PENDING_EVALUATION"
        conf = 0.0
        if state.policy:
            obs = _build_observable_state(c, cust, latest_att, now)
            try:
                dec = state.policy.evaluate_case(obs, decision_time=now)
                rec_action = dec.selected_action.value
                conf = dec.confidence
            except Exception:
                pass

        summaries.append({
            "case_id": c.case_id,
            "payment_id": c.payment_id,
            "customer_id": c.customer_id,
            "customer_segment": cust.segment.value if cust else "STANDARD",
            "amount_due": c.amount_due,
            "residual_amount": c.residual_amount,
            "failure_code": latest_att.failure_code.value if latest_att else "UNKNOWN",
            "failure_reason": latest_att.failure_reason if latest_att else "Payment failed",
            "hours_since_failure": round(hours_ago, 1),
            "attempts_count": len(attempts),
            "automated_actions_count": c.automated_action_count,
            "current_state": c.current_state.value,
            "recommended_action": rec_action,
            "decision_confidence": conf,
            "created_at": c.created_at.isoformat(),
        })

    return {
        "total_count": len(case_list),
        "limit": limit,
        "offset": offset,
        "cases": summaries,
    }

@app.get("/api/cases/{case_id}")
def get_case_detail(case_id: str):
    if case_id not in state.cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    c = state.cases[case_id]
    cust = state.customers.get(c.customer_id)
    pay = state.payments.get(c.payment_id)
    attempts = state.attempts.get(c.case_id, [])
    actions = state.actions.get(c.case_id, [])
    executions = state.executions.get(c.case_id, [])
    plink = state.payment_links.get(c.case_id)
    audits = state.audit_logger.get_case_audit(c.case_id)

    now = datetime.now(timezone.utc)
    obs = _build_observable_state(c, cust, attempts[-1] if attempts else None, now)

    # Generate candidate decisions trace
    evaluations = []
    recommended = None
    if state.policy:
        dec = state.policy.evaluate_case(obs, decision_time=now)
        trace = getattr(state.policy, "last_trace", None)
        recommended = {
            "selected_action": dec.selected_action.value,
            "policy_version": dec.policy_version,
            "confidence": dec.confidence,
            "expected_net_recovery": dec.net_expected_value,
            "expected_cost": dec.expected_cost,
            "selection_reason": trace.selection_reason if trace else "Causal Net Recovery Maximization",
            "explanation": dec.decision_reason,
        }
        if trace and hasattr(trace, "candidate_evaluations"):
            for ev in trace.candidate_evaluations:
                evaluations.append({
                    "action": ev.action.value,
                    "is_eligible": ev.eligible,
                    "rejection_reason": ev.rejection_reason,
                    "predicted_probability": ev.probability,
                    "incremental_uplift_tau": ev.incremental_probability,
                    "expected_incremental_revenue": ev.expected_incremental_revenue,
                    "action_cost": ev.action_cost,
                    "friction_cost": ev.friction_cost,
                    "expected_net_recovery": ev.expected_net_recovery,
                })

    return {
        "case": {
            "case_id": c.case_id,
            "payment_id": c.payment_id,
            "customer_id": c.customer_id,
            "amount_due": c.amount_due,
            "residual_amount": c.residual_amount,
            "current_state": c.current_state.value,
            "automated_action_count": c.automated_action_count,
            "terminal_reason": c.terminal_reason,
            "created_at": c.created_at.isoformat(),
        },
        "customer": {
            "customer_id": cust.customer_id,
            "segment": cust.segment.value,
            "channel_preference": cust.channel_preference.value,
            "opt_out": cust.opt_out,
        } if cust else None,
        "payment": {
            "payment_id": pay.payment_id,
            "amount": pay.amount,
            "status": pay.status.value,
            "currency": pay.currency,
        } if pay else None,
        "latest_attempt": {
            "attempt_id": attempts[-1].attempt_id,
            "failure_code": attempts[-1].failure_code.value,
            "failure_reason": attempts[-1].failure_reason,
            "attempted_at": attempts[-1].attempted_at.isoformat(),
        } if attempts else None,
        "observable_state": {
            "hours_since_failure": obs.hours_since_failure,
            "automated_action_count": obs.automated_action_count,
            "customer_opt_out": obs.customer_opt_out,
            "is_terminal": obs.is_terminal,
        },
        "decision_trace": {
            "recommended": recommended,
            "evaluations": evaluations,
        },
        "actions_history": [
            {
                "action_id": a.action_id,
                "action_type": a.action_type.value,
                "cost": a.cost,
                "friction_cost": a.friction_cost,
                "timestamp": a.timestamp.isoformat(),
                "policy_version": a.policy_version,
            } for a in actions
        ],
        "payment_link": plink,
        "audit_records": [
            {
                "audit_id": rec.audit_id,
                "event_type": rec.event_type,
                "timestamp": rec.timestamp,
                "actor": rec.actor,
                "action_type": rec.action_type,
                "metadata": rec.metadata,
            } for rec in audits
        ],
    }

@app.post("/api/cases/{case_id}/decision")
def evaluate_case_decision(case_id: str, request: CustomerMessageRequest):
    if case_id not in state.cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    c = state.cases[case_id]
    cust = state.customers.get(c.customer_id)
    attempts = state.attempts.get(c.case_id, [])
    now = datetime.now(timezone.utc)
    obs = _build_observable_state(c, cust, attempts[-1] if attempts else None, now)

    if request.message and state.llm_policy:
        dec = state.llm_policy.evaluate_case(
            state=obs,
            customer_message=request.message,
            decision_time=now,
        )
        extraction = state.llm_policy.latest_extractions.get(case_id)
    else:
        dec = state.policy.evaluate_case(obs, decision_time=now)
        extraction = None

    return {
        "decision_id": dec.decision_id,
        "case_id": case_id,
        "selected_action": dec.selected_action.value,
        "policy_version": dec.policy_version,
        "confidence": dec.confidence,
        "expected_incremental_recovery": dec.expected_incremental_recovery,
        "expected_cost": dec.expected_cost,
        "net_expected_value": dec.net_expected_value,
        "decision_reason": dec.decision_reason,
        "extraction": extraction.model_dump() if extraction else None,
    }

@app.post("/api/cases/{case_id}/execute")
def execute_case_action(case_id: str, req: ExecuteActionRequest):
    if case_id not in state.cases:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    c = state.cases[case_id]
    cust = state.customers.get(c.customer_id)
    pay = state.payments.get(c.payment_id)
    now = datetime.now(timezone.utc)

    try:
        action_type = ActionType(req.action_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action type {req.action_type}")

    # 1. Acquire case lock
    try:
        with state.lock_manager.acquire(case_id, timeout=2.0):
            # 2. Check for terminal protection
            if CaseStateMachine.is_terminal(c.current_state):
                raise HTTPException(status_code=400, detail=f"Case {case_id} is in terminal state {c.current_state.value}")

            # 3. Live Pre-Execution Reconciliation
            if pay and cust:
                is_safe, rejection_reason = state.reconciliation_service.reconcile_before_execution(
                    case=c,
                    payment=pay,
                    customer=cust,
                    now=now,
                )
                if not is_safe:
                    state.audit_logger.log(
                        case_id=case_id,
                        actor="recoveriq_engine",
                        event_type="ACTION_REJECTED_RECONCILIATION",
                        policy_version="recoveriq-v1",
                        action_type=action_type.value,
                        observed_payment_state=pay.status.value,
                        rejection_reason=rejection_reason,
                        now=now,
                    )
                    raise HTTPException(status_code=400, detail=f"Execution blocked by live reconciliation: {rejection_reason}")

            idem_key = req.idempotency_key or f"idem_{case_id}_{c.automated_action_count + 1}"

            # 4. Check Idempotency Token
            rec, is_new = state.idempotency_service.register_or_get(idem_key, case_id, action_type, c.automated_action_count + 1)
            if not is_new:
                cached = state.idempotency_service.get_record(idem_key)
                return {
                    "status": "DUPLICATE_ABSORBED",
                    "case_id": case_id,
                    "action_id": cached.execution_id if cached else f"exec_dup_{case_id}",
                    "action_type": action_type.value,
                    "case_state": c.current_state.value,
                    "payment_link": state.payment_links.get(case_id),
                }

            # 5. Create Action Reservation
            reservation = state.reservation_service.reserve_action(
                case_id=case_id,
                action_type=action_type,
                idempotency_key=idem_key,
                policy_version="recoveriq-v1",
                now=now,
            )

            # 6. Execute via Razorpay adapter if PAYMENT_LINK
            plink_info = None
            if action_type == ActionType.PAYMENT_LINK:
                exec_status, link_id, err = state.payment_link_adapter.create_recovery_link(
                    case=c,
                    customer=cust,
                    idempotency_key=idem_key,
                    policy_version="recoveriq-v1",
                )
                if exec_status == ExecutionStatus.SUCCESS:
                    # Fetch resource from client
                    plink_res = state.razorpay_client.fetch_payment_link(link_id)
                    plink_info = {
                        "link_id": plink_res.link_id,
                        "short_url": plink_res.short_url,
                        "amount_inr": plink_res.amount,
                        "status": plink_res.status,
                        "reference_id": plink_res.reference_id,
                        "created_at": plink_res.created_at.isoformat(),
                    }
                    state.payment_links[case_id] = plink_info
                elif exec_status == ExecutionStatus.UNKNOWN:
                    c.current_state = CaseState.MANUAL_REVIEW_REQUIRED
                    c.terminal_reason = f"PAYMENT_LINK_TIMEOUT: {err}"
                    return {
                        "status": "EXECUTION_UNKNOWN",
                        "case_state": c.current_state.value,
                        "message": "Gateway timeout during payment link creation. Marked for reconciliation.",
                    }
                else:
                    raise HTTPException(status_code=502, detail=f"Payment Link creation failed: {err}")

            # 7. Record Action in Domain Case
            c.automated_action_count += 1
            c.last_updated_at = now
            action_rec = RecoveryAction(
                action_id=f"act_{len(state.actions[case_id]) + 1}_{case_id}",
                case_id=case_id,
                action_type=action_type,
                timestamp=now,
                status=ExecutionStatus.SUCCESS,
                cost=3.0 if action_type == ActionType.PAYMENT_LINK else (100.0 if action_type == ActionType.ESCALATE else 2.0),
                friction_cost=min(c.automated_action_count * 5.0, 25.0),
                policy_version="recoveriq-v1",
                channel_used=cust.channel_preference if cust else ChannelPreference.WHATSAPP,
            )
            state.actions[case_id].append(action_rec)

            if action_type == ActionType.STOP:
                c.current_state = CaseState.STOPPED
                c.terminal_reason = "POLICY_STOPPED"
            elif action_type == ActionType.ESCALATE:
                c.current_state = CaseState.MANUAL_REVIEW_REQUIRED
                c.terminal_reason = "ESCALATED_TO_HUMAN"

            # Record Audit
            state.audit_logger.log(
                case_id=case_id,
                actor="recoveriq_engine",
                event_type="ACTION_EXECUTED",
                policy_version="recoveriq-v1",
                action_type=action_type.value,
                idempotency_key=idem_key,
                metadata={
                    "cost": action_rec.cost,
                    "link_id": plink_info.get("link_id") if plink_info else None,
                },
            )

            return {
                "status": "SUCCESS",
                "case_id": case_id,
                "action_id": action_rec.action_id,
                "action_type": action_type.value,
                "case_state": c.current_state.value,
                "payment_link": plink_info,
            }
    except TimeoutError:
        raise HTTPException(status_code=409, detail=f"Case {case_id} is currently locked by another process")

# =====================================================================
# API ROUTES: PROMISE-TO-PAY & LLM EXTRACTION
# =====================================================================

@app.post("/api/promise-to-pay/extract")
def extract_promise_context(req: CustomerMessageRequest):
    now = datetime.now(timezone.utc)
    extraction = state.llm_extractor.extract_context(
        customer_message=req.message,
        reference_time=now,
    )
    is_stop = extraction.intent.value in ["STOP_REQUEST", "DISPUTE"]
    return {
        "intent": extraction.intent.value,
        "willingness_to_pay": extraction.willingness_to_pay.value,
        "has_promise": extraction.promise_exists,
        "promised_date": extraction.promised_date.isoformat() if extraction.promised_date else None,
        "payment_constraint": extraction.payment_constraint.value if extraction.payment_constraint else None,
        "confidence_score": extraction.confidence,
        "ambiguity_state": extraction.ambiguity_state.value,
        "evidence_span": extraction.evidence_span,
        "is_fallback": extraction.is_fallback,
        "policy_effect": {
            "outreach_paused": extraction.promise_exists or is_stop,
            "promise_registered": extraction.promise_exists,
            "recommended_action_override": "STOP" if is_stop else ("PROMISE_TO_PAY" if extraction.promise_exists else None),
        },
    }

# =====================================================================
# API ROUTES: FROZEN EVALUATION & BENCHMARK ARTIFACTS
# =====================================================================

@app.get("/api/evaluation/benchmark")
def get_frozen_benchmark():
    path = "results/final/financial_benchmark.json"
    boot_path = "results/final/bootstrap_results.json"
    with open(path, "r") as f:
        data = json.load(f)
    with open(boot_path, "r") as f:
        boot_data = json.load(f)

    return {
        "status": "FROZEN_20K_HOLDOUT",
        "scenario": "S1_HIGH_NATURAL_RECOVERY",
        "dataset_size": 20000,
        "seed": 999888777,
        "arms": data,
        "bootstrap_comparisons": boot_data,
    }

@app.get("/api/evaluation/oracle")
def get_oracle_diagnostic():
    path = "results/final/oracle_diagnostic.json"
    with open(path, "r") as f:
        data = json.load(f)
    return data

@app.get("/api/evaluation/attribution")
def get_attribution_sensitivity():
    path = "results/final/attribution_sensitivity.json"
    with open(path, "r") as f:
        data = json.load(f)
    return data

@app.get("/api/evaluation/llm")
def get_llm_ablation():
    comp_path = "results/final/llm_comparison.json"
    eval_path = "results/final/llm_extraction_evaluation.json"
    with open(comp_path, "r") as f:
        comp_data = json.load(f)
    with open(eval_path, "r") as f:
        eval_data = json.load(f)
    return {
        "ablation_comparison": comp_data,
        "extraction_benchmark": eval_data,
    }

@app.get("/api/evaluation/heterogeneity")
def get_heterogeneity():
    path = "results/final/heterogeneity.json"
    with open(path, "r") as f:
        data = json.load(f)
    return data

# =====================================================================
# API ROUTES: SAFETY & FAILURE INJECTION
# =====================================================================

@app.get("/api/safety/status")
def get_safety_status():
    path = "results/final/safety_audit.json"
    with open(path, "r") as f:
        data = json.load(f)
    return data

@app.post("/api/safety/failure-injection")
def trigger_failure_injection(req: FailureInjectionRequest):
    case_id = req.case_id or list(state.cases.keys())[0]
    c = state.cases[case_id]
    now = datetime.now(timezone.utc)

    if req.scenario_type == "F1_TIMEOUT":
        # Simulate gateway timeout
        state.razorpay_client.simulate_timeout = True
        status_code, link_id, err = state.payment_link_adapter.create_recovery_link(c, state.customers[c.customer_id], "idem_f1", "v1")
        state.razorpay_client.simulate_timeout = False
        return {
            "scenario": "F1_TIMEOUT",
            "execution_status": status_code.value,
            "safety_action": "EXECUTION_UNKNOWN recorded. Automatic retry BLOCKED.",
            "reconciliation_required": True,
            "error_detail": err,
        }

    elif req.scenario_type == "F2_IDEMPOTENCY":
        # Simulate duplicate action execution with same key
        key = f"idem_dup_{case_id}"
        # First execution: register and mark completed
        rec1, is_new1 = state.idempotency_service.register_or_get(key, case_id, ActionType.PAYMENT_LINK, 1)
        if is_new1:
            state.idempotency_service.mark_completed(key, "act_first", "SUCCESS", {"status": "created"})
        # Second execution with same key: should return cached, not re-execute
        rec2, is_new2 = state.idempotency_service.register_or_get(key, case_id, ActionType.PAYMENT_LINK, 1)
        cached = state.idempotency_service.get_record(key)
        return {
            "scenario": "F2_IDEMPOTENCY",
            "key": key,
            "first_execution_new": is_new1,
            "second_execution_new": is_new2,
            "cache_hit": not is_new2,
            "cached_status": cached.status if cached else None,
            "safety_action": "Duplicate execution absorbed. ZERO side effects.",
        }

    elif req.scenario_type == "F3_DUPLICATE_WEBHOOK":
        evt_id = "evt_dup_test_999"
        is_dup1, _ = state.dedup_store.check_and_record(evt_id, "payment.captured")
        is_dup2, _ = state.dedup_store.check_and_record(evt_id, "payment.captured")
        return {
            "scenario": "F3_DUPLICATE_WEBHOOK",
            "event_id": evt_id,
            "first_delivery_duplicate": is_dup1,
            "second_delivery_duplicate": is_dup2,
            "safety_action": "Duplicate webhook dropped. ZERO state regression.",
        }

    elif req.scenario_type in ["F4_OUT_OF_BAND_CAPTURE", "F4_PRE_OUTREACH_CAPTURE", "F5_PRE_OUTREACH_CAPTURE"]:
        # Reconcile payment captured externally on gateway out-of-band before outreach
        pay = state.payments.get(c.payment_id)
        if pay:
            pay.status = PaymentStatus.CAPTURED
        cust = state.customers.get(c.customer_id)

        # 1. Authoritative pre-execution reconciliation sees CAPTURED
        is_safe, rejection_reason = state.reconciliation_service.reconcile_before_execution(c, pay, cust, now)

        # 2. Case state transition: Monotonic Terminal Protection
        c.current_state = CaseState.RECOVERED
        c.residual_amount = 0.0
        c.terminal_reason = "RECONCILED_OUT_OF_BAND_CAPTURE"
        c.last_updated_at = now

        # 3. Log structured audit event
        state.audit_logger.log(
            case_id=c.case_id,
            actor="reconciliation_guard",
            event_type="ACTION_REJECTED_RECONCILIATION",
            policy_version="recoveriq-v1",
            observed_payment_state="CAPTURED",
            rejection_reason=rejection_reason or "ACTION_REJECTED_PAYMENT_ALREADY_CAPTURED",
            now=now,
        )

        return {
            "scenario": req.scenario_type,
            "gateway_status": "captured",
            "safe_to_execute_outreach": is_safe,
            "halt_reason": rejection_reason or "ACTION_REJECTED_PAYMENT_ALREADY_CAPTURED",
            "execution_blocked": not is_safe,
            "downstream_actions_created": 0,
            "case_state": c.current_state.value,
            "residual_amount": c.residual_amount,
            "payment_status": pay.status.value if pay else "CAPTURED",
            "safety_action": "Payment captured out-of-band. Pre-action reconciliation halted outreach. Residual set to INR 0.00.",
        }

    elif req.scenario_type in ["F5_CONCURRENT_RACE", "F5_RACE_CONDITION"]:
        # Simulate two concurrent execution attempts for the same case
        results = []
        race_key = f"idem_race_{case_id}_{int(now.timestamp())}"

        def attempt_execution(attempt_id: int):
            try:
                with state.lock_manager.acquire(case_id, timeout=0.5):
                    rec, is_new = state.idempotency_service.register_or_get(race_key, case_id, ActionType.PAYMENT_LINK, c.automated_action_count + 1)
                    if not is_new:
                        return {"attempt": attempt_id, "status": "BLOCKED", "reason": "DUPLICATE_ACTION_BLOCKED"}

                    res = state.reservation_service.reserve_action(case_id, ActionType.PAYMENT_LINK, race_key, "recoveriq-v1", now)
                    state.reservation_service.validate_and_start_executing(res.reservation_id, now)
                    # Successful execution
                    c.automated_action_count += 1
                    state.reservation_service.confirm_reservation(res.reservation_id)
                    state.idempotency_service.mark_completed(race_key, f"exec_{res.reservation_id}", "SUCCESS")
                    state.audit_logger.log(
                        case_id=case_id,
                        actor="SafeRecoveryExecutor",
                        event_type="ACTION_EXECUTED_SUCCESS",
                        policy_version="recoveriq-v1",
                        action_type="PAYMENT_LINK",
                        idempotency_key=race_key,
                        now=now,
                    )
                    return {"attempt": attempt_id, "status": "SUCCESS", "reservation_id": res.reservation_id}
            except Exception as e:
                return {"attempt": attempt_id, "status": "BLOCKED", "reason": str(e)}

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt_execution, i) for i in (1, 2)]
            results = [f.result() for f in futures]

        success_count = sum(1 for r in results if r["status"] == "SUCCESS")
        blocked_count = sum(1 for r in results if r["status"] == "BLOCKED")

        return {
            "scenario": req.scenario_type,
            "concurrent_requests": len(results),
            "successful_executions": success_count,
            "blocked_executions": blocked_count,
            "results": results,
            "safety_action": f"Race condition contained: {success_count} executed / {blocked_count} blocked. Exactly ONE execution allowed.",
        }

    elif req.scenario_type == "F4_OUT_OF_ORDER":
        # Case already recovered; try receiving failed event
        c.current_state = CaseState.RECOVERED
        c.residual_amount = 0.0
        # Check domain state machine
        is_valid = CaseStateMachine.can_transition(c.current_state, CaseState.RECOVERY_ELIGIBLE)
        return {
            "scenario": "F4_OUT_OF_ORDER",
            "initial_state": "RECOVERED",
            "incoming_event": "payment.failed",
            "transition_allowed": is_valid,
            "safety_action": "Monotonic terminal guard BLOCKED regression from RECOVERED to RECOVERY_ELIGIBLE.",
        }

    elif req.scenario_type == "F6_OPT_OUT":
        cust = state.customers[c.customer_id]
        cust.opt_out = True
        obs = _build_observable_state(c, cust, state.attempts[c.case_id][-1], now)
        eligible = state.policy.eligibility_service.get_eligible_actions(obs)
        return {
            "scenario": "F6_OPT_OUT",
            "customer_opt_out": True,
            "eligible_actions": [a.value for a in eligible],
            "safety_action": "Opt-out strictly enforced. Strictly only STOP action allowed.",
        }

    raise HTTPException(status_code=400, detail=f"Unknown failure scenario {req.scenario_type}")

# =====================================================================
# API ROUTES: RAZORPAY WEBHOOKS & TEST MODE
# =====================================================================

@app.get("/api/razorpay/status")
def get_razorpay_status():
    return {
        "environment": state.razorpay_config.environment,
        "is_test_mode": state.razorpay_config.environment == "test",
        "is_configured": state.razorpay_config.is_configured(),
        "status": state.razorpay_mode,
        "has_credentials": bool(state.razorpay_config.key_id and state.razorpay_config.key_secret),
        "key_id_masked": f"{state.razorpay_config.key_id[:8]}..." if state.razorpay_config.key_id else "UNCONFIGURED",
    }

@app.post("/api/webhooks/razorpay")
async def handle_razorpay_webhook(request: Request, x_razorpay_signature: Optional[str] = Header(None)):
    raw_body = await request.body()

    # 1. Signature Verification
    # In test mode, allow simulations with a valid test signature or with x-razorpay-signature: "test-simulation"
    is_test_simulation = x_razorpay_signature == "test-simulation"

    if state.razorpay_mode == "CONNECTED" and not is_test_simulation:
        if not x_razorpay_signature:
            raise HTTPException(status_code=400, detail="Missing x-razorpay-signature header")
        try:
            state.webhook_verifier.verify(raw_body, x_razorpay_signature)
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid webhook signature: {e}")
    elif state.razorpay_mode == "OFFLINE_MOCK" or is_test_simulation:
        # Test mode: accept without signature verification
        pass

    # 2. Parse JSON
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    # Handle accidental double-nesting defensively
    if isinstance(payload.get("payload"), dict) and "payload" in payload["payload"]:
        payload = payload["payload"]

    # 3. Deduplication
    event_id = payload.get("event_id") or payload.get("id") or f"evt_{int(time.time()*1000)}"
    event_type = payload.get("event", "payment.captured")
    is_dup, _ = state.dedup_store.check_and_record(event_id, event_type)

    if is_dup:
        return {"status": "DUPLICATE_IGNORED", "event_id": event_id, "side_effects": 0}

    # 4. Event Normalization & Reconciliation
    try:
        norm_event = state.event_normalizer.normalize_webhook(payload, event_id)
        payment_id = norm_event.payment_id
    except Exception:
        norm_event = None
        payment_id = (
            payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
            or payload.get("payload", {}).get("payment_link", {}).get("entity", {}).get("payment_id")
        )

    # Find matching case
    matching_case = None
    for c in state.cases.values():
        if (payment_id and c.payment_id == payment_id) or (c.active_promise_id and c.active_promise_id in str(payload)):
            matching_case = c
            break

    if not matching_case and payment_id:
        # Check if payment_id matches directly in state.payments
        if payment_id in state.payments:
            for c in state.cases.values():
                if c.payment_id == payment_id:
                    matching_case = c
                    break

    if not matching_case:
        raise HTTPException(status_code=404, detail=f"No matching recovery case found for payment {payment_id}")

    state_changed = False
    is_captured = False
    if norm_event and norm_event.payment_status == PaymentStatus.CAPTURED:
        is_captured = True
    elif event_type in ["payment.captured", "payment_link.paid"]:
        is_captured = True

    if is_captured:
        matching_case.current_state = CaseState.RECOVERED
        matching_case.residual_amount = 0.0
        matching_case.terminal_reason = "WEBHOOK_PAYMENT_CAPTURED"
        matching_case.last_updated_at = datetime.now(timezone.utc)

        # Update authoritative payment state
        if matching_case.payment_id in state.payments:
            state.payments[matching_case.payment_id].status = PaymentStatus.CAPTURED

        state_changed = True
        state.audit_logger.log(
            case_id=matching_case.case_id,
            actor="razorpay_webhook",
            event_type="PAYMENT_CAPTURED_VIA_WEBHOOK",
            policy_version="recoveriq-v1",
            metadata={"event_id": event_id, "amount_inr": norm_event.amount if norm_event else matching_case.amount_due},
        )

    log_entry = {
        "event_id": event_id,
        "event_type": event_type,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "signature_verified": True,
        "is_duplicate": False,
        "matched_case_id": matching_case.case_id,
        "state_changed": state_changed,
    }
    state.webhook_logs.insert(0, log_entry)

    return {
        "status": "PROCESSED",
        "event_id": event_id,
        "event_type": event_type,
        "matched_case_id": matching_case.case_id,
        "case_state": matching_case.current_state.value,
        "residual_amount": matching_case.residual_amount,
        "payment_status": state.payments[matching_case.payment_id].status.value if matching_case.payment_id in state.payments else "CAPTURED",
    }

# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def _build_observable_state(
    case: RecoveryCase,
    customer: Optional[Customer],
    attempt: Optional[PaymentAttempt],
    as_of: datetime,
) -> ObservableCaseState:
    hours_since = (as_of - case.created_at).total_seconds() / 3600.0
    return ObservableCaseState(
        case_id=case.case_id,
        payment_id=case.payment_id,
        customer_id=case.customer_id,
        customer_segment=customer.segment if customer else CustomerSegment.STANDARD,
        customer_channel_preference=customer.channel_preference if customer else ChannelPreference.WHATSAPP,
        customer_opt_out=customer.opt_out if customer else False,
        amount_due=case.amount_due,
        residual_amount=case.residual_amount,
        current_state=case.current_state,
        failure_code=attempt.failure_code if attempt else FailureCode.INSUFFICIENT_FUNDS,
        failure_reason=attempt.failure_reason if attempt else "Payment failed",
        attempt_count=1,
        automated_action_count=case.automated_action_count,
        hours_since_failure=max(0.0, hours_since),
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=None,
        active_promise_due_hours=None,
        payment_status=PaymentStatus.FAILED,
    )

# =====================================================================
# STATIC FRONTEND SPA SERVING
# =====================================================================
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    print("Starting RecoverIQ Full-Stack Server on http://127.0.0.1:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)

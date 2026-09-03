import os
import sys
import json
import numpy as np
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.enums import ActionType, PaymentStatus, CaseState, PromiseState, CustomerSegment, ChannelPreference, FailureCode
from domain.models import ObservableCaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from models.artifacts import ModelArtifactManager
from policy.adaptive import RecoverIQAdaptivePolicy
from evaluation.bootstrap import compute_bootstrap_difference_ci
from llm.extractor import LLMContextExtractor
from llm.evaluator import ExtractionEvaluator
from llm.integration import LLMAugmentedPolicy
from llm.eval_dataset import get_fixed_extraction_evaluation_dataset
from execution.executor import SafeRecoveryExecutor
from execution.locks import CaseLockManager

def run_extraction_evaluation():
    print("\n=======================================================")
    print("1. LLM CONTEXT EXTRACTION BENCHMARK (SYNTHETIC CORPUS)")
    print("=======================================================")
    extractor = LLMContextExtractor()
    evaluator = ExtractionEvaluator(extractor)
    metrics = evaluator.run_evaluation()

    print(f"Total Samples Evaluated: {metrics['samples_evaluated']}")
    print(f"Intent Accuracy: {metrics['intent_accuracy']:.1%}")
    print(f"P2P Promise Detection Accuracy: {metrics['p2p_detection_accuracy']:.1%}")
    print(f"Promised Date Resolution Accuracy: {metrics['promised_date_accuracy']:.1%}")
    print(f"Constraint Extraction Accuracy: {metrics['constraint_accuracy']:.1%}")
    print(f"Adversarial Resilience Rate: {metrics['adversarial_resilience_rate']:.1%}")
    print(f"Fallback Rate: {metrics['fallback_rate']:.1%}")
    print(f"Avg Inference Latency: {metrics['avg_latency_ms']:.2f} ms")
    print(f"Estimated Tokens Processed: {metrics['total_tokens_estimated']}")
    return metrics

def run_three_arm_financial_ablation():
    print("\n=======================================================")
    print("2. THREE-ARM FINANCIAL BENCHMARK (N=1500, SCENARIO S1)")
    print("=======================================================")
    seed = 20260902
    gen = SyntheticCaseGenerator(seed=seed)
    cohort = gen.generate_batch(count=1500, scenario_id="S1_HIGH_NATURAL_RECOVERY")

    # Load ML Model and Policies
    model = ModelArtifactManager().load_model("incremental-model-v1")
    base_policy = RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)
    llm_policy = LLMAugmentedPolicy(base_policy=base_policy)
    llm_p2p_only_policy = LLMAugmentedPolicy(base_policy=base_policy, enable_p2p_only=True)

    # Inbound communication simulation for cases:
    # 25% of customers provide an inbound message with varied intent/promise
    inbound_messages = {}
    rng = np.random.default_rng(seed)
    message_templates = [
        "I will clear this on Friday after my salary.",
        "Will pay tomorrow morning once bank server issue is resolved.",
        "I can definitely pay in 3 days, please hold off on reminders.",
        "Stop messaging me. Unsubscribe.",
        "The money was already debited yesterday!",
        "I am travelling right now, will pay next week.",
    ]
    for cust, pay, att, c, hidden in cohort:
        if rng.random() < 0.25:
            # Select message based on customer latent propensity to respond
            msg_idx = rng.integers(0, len(message_templates))
            inbound_messages[c.case_id] = message_templates[msg_idx]

    # Arm Assignments: 1/3 Control, 1/3 RecoverIQ Structured, 1/3 RecoverIQ + LLM
    arms = ["CONTROL", "RECOVERIQ_STRUCTURED", "RECOVERIQ_LLM"]
    arm_indices = np.array([i % 3 for i in range(len(cohort))])
    rng.shuffle(arm_indices)
    arm_assignments = [arms[idx] for idx in arm_indices]

    arm_nets = defaultdict(list)
    arm_gross = defaultdict(float)
    arm_costs = defaultdict(float)
    arm_frictions = defaultdict(float)
    arm_recovered_counts = defaultdict(int)
    arm_interventions_counts = defaultdict(int)
    arm_unnecessary_counts = defaultdict(int)
    arm_safety_violations = defaultdict(int)
    arm_action_counts = defaultdict(lambda: defaultdict(int))

    for i, (cust, pay, att, case, hidden) in enumerate(cohort):
        arm = arm_assignments[i]
        case_id = case.case_id
        msg = inbound_messages.get(case_id)
        current_time = att.attempted_at

        env = SimulationEnvironment(scenario_id="S1_HIGH_NATURAL_RECOVERY", seed=seed + i)
        env.register_case(cust, pay, att, case, hidden)

        if arm == "CONTROL":
            # Zero outreach
            window_end = case.created_at + timedelta(hours=72)
            env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
            outcome = env.get_outcome(case_id)
            gross = outcome.recovered_amount
            net = gross
            cost = 0.0
            fric = 0.0
            arm_action_counts["CONTROL"]["STOP"] += 1
            if outcome.recovered_amount > 0:
                arm_recovered_counts["CONTROL"] += 1

        elif arm == "RECOVERIQ_STRUCTURED":
            # Standard RecoverIQ without LLM message interpretation
            sim_step = 0
            while sim_step < 3:
                obs = env.get_observable_state(case_id, current_time)
                if obs.is_terminal:
                    break
                decision = base_policy.evaluate_case(obs, current_time)
                sel_act = decision.selected_action
                arm_action_counts["RECOVERIQ_STRUCTURED"][sel_act.value] += 1

                if sel_act == ActionType.STOP:
                    window_end = case.created_at + timedelta(hours=72)
                    env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                    break

                arm_interventions_counts["RECOVERIQ_STRUCTURED"] += 1
                if hidden.y_control:
                    arm_unnecessary_counts["RECOVERIQ_STRUCTURED"] += 1

                exec_rec, updated_case = env.execute_action(
                    case_id=case_id,
                    action_type=sel_act,
                    timestamp=current_time,
                    idempotency_key=f"idem_{case_id}_{sim_step}",
                    policy_version="recoveriq-v1",
                )
                if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                    break
                current_time += timedelta(hours=14)
                sim_step += 1

            outcome = env.get_outcome(case_id)
            case_actions = env._actions.get(case_id, [])
            gross = outcome.recovered_amount
            cost = sum(a.cost for a in case_actions)
            fric = sum(a.friction_cost for a in case_actions)
            net = gross - cost - fric
            if outcome.recovered_amount > 0:
                arm_recovered_counts["RECOVERIQ_STRUCTURED"] += 1

        else:
            # RECOVERIQ_LLM: Evaluates with LLM-augmented message context
            sim_step = 0
            while sim_step < 3:
                obs = env.get_observable_state(case_id, current_time)
                if obs.is_terminal:
                    break
                # Process message on first step
                active_msg = msg if sim_step == 0 else None
                decision = llm_policy.evaluate_case(obs, customer_message=active_msg, decision_time=current_time)
                sel_act = decision.selected_action
                arm_action_counts["RECOVERIQ_LLM"][sel_act.value] += 1

                if sel_act == ActionType.STOP:
                    window_end = case.created_at + timedelta(hours=72)
                    env.check_natural_recovery_for_control(case_id, as_of_time=window_end)
                    break

                arm_interventions_counts["RECOVERIQ_LLM"] += 1
                if hidden.y_control:
                    arm_unnecessary_counts["RECOVERIQ_LLM"] += 1

                exec_rec, updated_case = env.execute_action(
                    case_id=case_id,
                    action_type=sel_act,
                    timestamp=current_time,
                    idempotency_key=f"idem_{case_id}_{sim_step}",
                    policy_version="recoveriq-llm-v1",
                )
                if updated_case.current_state in [CaseState.RECOVERED, CaseState.STOPPED, CaseState.MANUAL_REVIEW_REQUIRED]:
                    break
                current_time += timedelta(hours=14)
                sim_step += 1

            outcome = env.get_outcome(case_id)
            case_actions = env._actions.get(case_id, [])
            gross = outcome.recovered_amount
            cost = sum(a.cost for a in case_actions)
            fric = sum(a.friction_cost for a in case_actions)
            net = gross - cost - fric
            if outcome.recovered_amount > 0:
                arm_recovered_counts["RECOVERIQ_LLM"] += 1

        arm_nets[arm].append(net)
        arm_gross[arm] += gross
        arm_costs[arm] += cost
        arm_frictions[arm] += fric

    # Aggregate metrics
    print("\n--- 3-ARM FINANCIAL RESULTS (500 cases/arm) ---")
    for a in arms:
        n_cases = len(arm_nets[a])
        tot_net = sum(arm_nets[a])
        mean_net = tot_net / n_cases
        rec_rate = arm_recovered_counts[a] / n_cases
        tot_cost = arm_costs[a] + arm_frictions[a]
        eff = (arm_gross[a] / tot_cost) if tot_cost > 0 else 0.0
        n_int = arm_interventions_counts[a]
        unnec_rate = (arm_unnecessary_counts[a] / n_int) if n_int > 0 else 0.0

        print(f"\n[{a}]")
        print(f"  Gross Recovered: INR {arm_gross[a]:,.2f}")
        print(f"  Action Cost: INR {arm_costs[a]:,.2f} | Friction: INR {arm_frictions[a]:,.2f}")
        print(f"  Total Net Recovered: INR {tot_net:,.2f}")
        print(f"  Mean Net / Case: INR {mean_net:.2f}")
        print(f"  Recovery Rate: {rec_rate:.1%}")
        print(f"  Intervention Efficiency: {eff:.2f}")
        print(f"  Unnecessary Intervention Rate: {unnec_rate:.1%}")
        print(f"  Critical Safety Violations: {arm_safety_violations[a]}")
        print(f"  Action Dist (%): {dict(arm_action_counts[a])}")

    # Primary Comparison: RecoverIQ+LLM vs RecoverIQ-v1
    boot_res = compute_bootstrap_difference_ci(
        sample_a=arm_nets["RECOVERIQ_LLM"],
        sample_b=arm_nets["RECOVERIQ_STRUCTURED"],
        comparison_name="RecoverIQ+LLM vs RecoverIQ-v1",
        confidence_level=0.95,
        iterations=1000,
        seed=42,
    )
    print("\n--- PRIMARY COMPARISON (RecoverIQ+LLM vs RecoverIQ-v1) ---")
    print(f"Point Estimate (Mean Diff): INR {boot_res.point_estimate:.2f}")
    print(f"95% Bootstrap CI: [{boot_res.lower_bound:.2f}, {boot_res.upper_bound:.2f}]")
    print(f"Statistical Classification: {boot_res.claim_classification}")
    print(f"Decisions Changed by LLM Context: {llm_policy.stats['decisions_changed']}")
    print(f"Promises Registered by LLM Context: {llm_policy.stats['promises_registered']}")
    print(f"Opt-Outs Honored from Messages: {llm_policy.stats['opt_outs_honored']}")
    print(f"LLM Fallbacks: {llm_policy.stats['fallbacks']}")

def run_p2p_demo():
    print("\n=======================================================")
    print("3. COMPREHENSIVE P2P PIPELINE DEMO (SECTION 16)")
    print("=======================================================")
    raw_message = "I'll clear this on Friday after salary."
    ref_time = datetime(2026, 3, 2, 10, 0, 0, tzinfo=timezone.utc) # Monday

    print(f"1. RAW CUSTOMER MESSAGE: \"{raw_message}\"")

    # Step 2 & 3: Extraction
    extractor = LLMContextExtractor()
    extraction = extractor.extract_context(raw_message, reference_time=ref_time)
    print(f"2. LLM STRUCTURED EXTRACTION:")
    print(f"   Intent: {extraction.intent.value}")
    print(f"   Promise Exists: {extraction.promise_exists}")
    print(f"3. EXTRACTED PROMISED DATE: {extraction.promised_date.isoformat()}")
    print(f"   Payment Constraint: {extraction.payment_constraint.value}")
    print(f"4. CONFIDENCE / AMBIGUITY:")
    print(f"   Extraction Confidence: {extraction.confidence:.2f}")
    print(f"   Ambiguity State: {extraction.ambiguity_state.value}")
    print(f"   Evidence Span: \"{extraction.evidence_span}\"")

    # Step 5: Updated Observable Case Context
    initial_state = ObservableCaseState(
        case_id="case_demo_p2p_01",
        payment_id="pay_demo_01",
        customer_id="cust_demo_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=False,
        amount_due=4500.0,
        residual_amount=4500.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Insufficient balance in account",
        attempt_count=1,
        automated_action_count=0,
        hours_since_failure=4.0,
        payment_status=PaymentStatus.FAILED,
    )

    model = ModelArtifactManager().load_model("incremental-model-v1")
    base_policy = RecoverIQAdaptivePolicy(model=model, minimum_incremental_recovery=250.0)
    llm_policy = LLMAugmentedPolicy(base_policy=base_policy, extractor=extractor)

    updated_state = llm_policy.process_customer_message(initial_state, raw_message, ref_time)
    print(f"5. UPDATED OBSERVABLE CASE CONTEXT:")
    print(f"   Active Promise Status: {updated_state.active_promise_status.value}")
    print(f"   Active Promise Due Hours: {updated_state.active_promise_due_hours:.1f} hours")
    print(f"   Customer Opt Out: {updated_state.customer_opt_out}")

    # Step 6 & 7: Model & Economic Decision
    decision = llm_policy.evaluate_case(initial_state, customer_message=raw_message, decision_time=ref_time)
    print(f"6. INCREMENTAL RECOVERY ESTIMATES & ECONOMIC OPTIMIZATION:")
    trace = base_policy.last_trace.to_dict()
    for cand in trace["candidate_evaluations"]:
        print(f"   - {cand['action']:15}: Exp Net INR {cand['expected_net_recovery']:8.2f} | Eligible: {cand['eligible']} | Reason: {cand['rejection_reason']}")
    print(f"8. RECOVERIQ POLICY DECISION: {decision.selected_action.value}")
    print(f"   Decision Reason: {decision.decision_reason}")

    # Step 9 & 10: Safety Authorization & Execution
    from domain.models import RecoveryCase, Payment, Customer
    lock_mgr = CaseLockManager()
    executor = SafeRecoveryExecutor(lock_manager=lock_mgr)

    demo_cust = Customer(
        customer_id=initial_state.customer_id,
        segment=CustomerSegment.STANDARD,
    )
    demo_pay = Payment(
        payment_id=initial_state.payment_id,
        customer_id=initial_state.customer_id,
        amount=initial_state.amount_due,
        created_at=ref_time,
        status=PaymentStatus.FAILED,
    )
    demo_case = RecoveryCase(
        case_id=initial_state.case_id,
        payment_id=initial_state.payment_id,
        customer_id=initial_state.customer_id,
        amount_due=initial_state.amount_due,
        residual_amount=initial_state.residual_amount,
        created_at=ref_time,
        last_updated_at=ref_time,
        current_state=CaseState.RECOVERY_ELIGIBLE,
    )

    exec_rec, success, stop_reason = executor.execute_policy_decision(
        case=demo_case,
        payment=demo_pay,
        customer=demo_cust,
        action_type=decision.selected_action,
        policy_version=decision.policy_version,
        idempotency_key="idem_demo_p2p_01",
        now=ref_time,
    )
    print(f"9. SAFETY AUTHORIZATION: Authorized = {success} (Reason: {stop_reason})")
    print(f"10. EXECUTION RESULT: Status = {exec_rec.status.value} | Exec ID = {exec_rec.execution_id}")

    # Step 11: Subsequent Re-evaluation
    reval_state = updated_state.model_copy(update={"automated_action_count": 0, "hours_since_failure": 24.0})
    reval_dec = base_policy.evaluate_case(reval_state, ref_time + timedelta(hours=20))
    print(f"11. SUBSEQUENT RE-EVALUATION (While Promise Active):")
    print(f"    Action Chosen: {reval_dec.selected_action.value} (Waiting for promise fulfillment)")

if __name__ == "__main__":
    run_extraction_evaluation()
    run_three_arm_financial_ablation()
    run_p2p_demo()

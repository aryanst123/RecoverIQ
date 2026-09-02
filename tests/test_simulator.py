import pytest
from datetime import datetime, timezone, timedelta
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from simulator.scenarios import SCENARIOS, get_scenario
from domain.enums import ActionType, CaseState, ExecutionStatus, RecoveryStatus

def test_simulator_deterministic_reproducibility():
    gen1 = SyntheticCaseGenerator(seed=12345)
    gen2 = SyntheticCaseGenerator(seed=12345)
    
    cases1 = gen1.generate_batch(50, scenario_id="S1_HIGH_NATURAL_RECOVERY")
    cases2 = gen2.generate_batch(50, scenario_id="S1_HIGH_NATURAL_RECOVERY")
    
    assert len(cases1) == len(cases2) == 50
    for (c1, p1, a1, rc1, po1), (c2, p2, a2, rc2, po2) in zip(cases1, cases2):
        assert c1.customer_id == c2.customer_id
        assert p1.amount == p2.amount
        assert a1.failure_code == a2.failure_code
        assert po1.latent_payment_propensity == po2.latent_payment_propensity
        assert po1.y_control == po2.y_control
        assert po1.y_reminder == po2.y_reminder
        assert po1.y_payment_link == po2.y_payment_link
        assert po1.y_promise_to_pay == po2.y_promise_to_pay
        assert po1.y_escalate == po2.y_escalate

def test_all_scenarios_generation():
    for scenario_id in SCENARIOS:
        gen = SyntheticCaseGenerator(seed=999)
        cases = gen.generate_batch(20, scenario_id=scenario_id)
        assert len(cases) == 20
        scenario_cfg = get_scenario(scenario_id)
        assert scenario_cfg.scenario_id == scenario_id

def test_simulation_environment_action_execution():
    gen = SyntheticCaseGenerator(seed=42)
    env = SimulationEnvironment(scenario_id="S4_STRONG_INTERVENTION_EFFECT", seed=42)
    
    cases = gen.generate_batch(10, scenario_id="S4_STRONG_INTERVENTION_EFFECT")
    for customer, payment, attempt, case, hidden in cases:
        env.register_case(customer, payment, attempt, case, hidden)
    
    target_case_id = "case_000001"
    obs_state_before = env.get_observable_state(target_case_id)
    assert obs_state_before.automated_action_count == 0
    assert obs_state_before.current_state == CaseState.PAYMENT_FAILED

    # Execute a REMINDER action
    action_time = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    exec_rec, updated_case = env.execute_action(
        case_id=target_case_id,
        action_type=ActionType.REMINDER,
        timestamp=action_time,
        idempotency_key=f"idem_rem_{target_case_id}",
    )
    
    assert exec_rec.status == ExecutionStatus.SUCCESS
    obs_state_after = env.get_observable_state(target_case_id, current_time=action_time)
    assert obs_state_after.automated_action_count == 1
    assert obs_state_after.last_action_type == ActionType.REMINDER

def test_friction_cost_accumulation():
    gen = SyntheticCaseGenerator(seed=100)
    env = SimulationEnvironment(scenario_id="S1_HIGH_NATURAL_RECOVERY", seed=100)
    
    customer, payment, attempt, case, hidden = gen.generate_case(
        1, get_scenario("S1_HIGH_NATURAL_RECOVERY"), datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    )
    # Ensure hidden won't recover immediately so we can test 2 actions
    hidden.y_reminder = False
    env.register_case(customer, payment, attempt, case, hidden)

    t1 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    env.execute_action(case.case_id, ActionType.REMINDER, t1, "idem_1")
    action1 = env._actions[case.case_id][0]
    assert action1.friction_cost == 0.0 # 0 previous actions

    t2 = datetime(2026, 3, 1, 16, 0, tzinfo=timezone.utc)
    env.execute_action(case.case_id, ActionType.PAYMENT_LINK, t2, "idem_2")
    action2 = env._actions[case.case_id][1]
    assert action2.friction_cost == 5.0 # 1 previous action * ₹5

def test_scenario_s6_adversarial_failures():
    gen = SyntheticCaseGenerator(seed=777)
    env = SimulationEnvironment(scenario_id="S6_HIGH_EVENT_FAILURE_RATE", seed=777)
    
    cases = gen.generate_batch(50, scenario_id="S6_HIGH_EVENT_FAILURE_RATE")
    for customer, payment, attempt, case, hidden in cases:
        env.register_case(customer, payment, attempt, case, hidden)

    statuses = []
    for i, (_, _, _, c, _) in enumerate(cases):
        exec_rec, _ = env.execute_action(
            case_id=c.case_id,
            action_type=ActionType.REMINDER,
            timestamp=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            idempotency_key=f"idem_s6_{i}",
        )
        statuses.append(exec_rec.status)

    # In S6 with 20% failure and 15% timeout, we expect non-successes
    assert any(s in [ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED] for s in statuses)

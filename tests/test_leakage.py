import pytest
from datetime import datetime, timezone
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from simulator.scenarios import get_scenario

FORBIDDEN_LEAKAGE_SUBSTRINGS = [
    "latent",
    "potential",
    "counterfactual",
    "y_control",
    "y_reminder",
    "y_payment_link",
    "y_promise_to_pay",
    "y_escalate",
    "recovery_time",
    "ground_truth",
    "hidden",
]

def test_observable_case_state_schema_leakage_audit():
    """Verify that ObservableCaseState fields contain zero forbidden latent/counterfactual terms."""
    field_names = list(ObservableCaseState.model_fields.keys())
    for name in field_names:
        lower_name = name.lower()
        for forbidden in FORBIDDEN_LEAKAGE_SUBSTRINGS:
            assert forbidden not in lower_name, (
                f"LEAKAGE VIOLATION: Field '{name}' on ObservableCaseState matches forbidden term '{forbidden}'!"
            )

def test_observable_case_state_instance_dump_leakage_audit():
    """Verify that serializing ObservableCaseState dictionary contains zero forbidden keys."""
    gen = SyntheticCaseGenerator(seed=42)
    env = SimulationEnvironment(seed=42)
    customer, payment, attempt, case, hidden = gen.generate_case(
        1, get_scenario("S1_HIGH_NATURAL_RECOVERY"), datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    )
    env.register_case(customer, payment, attempt, case, hidden)

    obs = env.get_observable_state(case.case_id)
    dump = obs.model_dump()

    for key, value in dump.items():
        for forbidden in FORBIDDEN_LEAKAGE_SUBSTRINGS:
            assert forbidden not in key.lower(), (
                f"LEAKAGE VIOLATION: Dumped key '{key}' contains forbidden substring '{forbidden}'"
            )

def test_observable_state_attribute_access_guard():
    """Verify that attempting to read hidden latent/counterfactual fields on ObservableCaseState raises AttributeError."""
    gen = SyntheticCaseGenerator(seed=42)
    env = SimulationEnvironment(seed=42)
    customer, payment, attempt, case, hidden = gen.generate_case(
        1, get_scenario("S1_HIGH_NATURAL_RECOVERY"), datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    )
    env.register_case(customer, payment, attempt, case, hidden)
    obs = env.get_observable_state(case.case_id)

    with pytest.raises(AttributeError):
        _ = obs.latent_payment_propensity

    with pytest.raises(AttributeError):
        _ = obs.y_control

    with pytest.raises(AttributeError):
        _ = obs.y_reminder

    with pytest.raises(AttributeError):
        _ = obs.y_payment_link

    with pytest.raises(AttributeError):
        _ = obs.y_promise_to_pay

    with pytest.raises(AttributeError):
        _ = obs.recovery_time_hours_control

def test_environment_isolation_barrier():
    """
    Verify that the environment stores PotentialOutcome strictly in _hidden_potential_outcomes
    and never exposes it via get_observable_state.
    """
    gen = SyntheticCaseGenerator(seed=42)
    env = SimulationEnvironment(seed=42)
    customer, payment, attempt, case, hidden = gen.generate_case(
        1, get_scenario("S1_HIGH_NATURAL_RECOVERY"), datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    )
    env.register_case(customer, payment, attempt, case, hidden)

    obs = env.get_observable_state(case.case_id)
    
    # Assert obs has no reference to hidden
    assert not hasattr(obs, "_hidden")
    assert not hasattr(obs, "potential_outcome")
    assert not hasattr(obs, "ground_truth")
    
    # Assert modifying obs has no impact on internal hidden state
    obs.amount_due = 999999.0
    assert env._hidden_potential_outcomes[case.case_id].case_id == case.case_id
    assert env._cases[case.case_id].amount_due == payment.amount # Case retains true initial amount

import pytest
import numpy as np

from domain.enums import ActionType, FailureCode, CustomerSegment, ChannelPreference, CaseState
from domain.models import ObservableCaseState
from models.dataset import DatasetBuilder
from models.training import TLearnerTrainer
from models.incremental_recovery import IncrementalRecoveryModel
from models.explanations import ModelExplanationService
from models.diagnostics import SimulatorGroundTruthDiagnostic

@pytest.fixture(scope="module")
def trained_model_and_features():
    builder = DatasetBuilder()
    dataset = builder.build_dataset(count=120, seed=42)
    train, val = builder.train_validation_split(dataset, train_ratio=0.70, seed=42)
    trainer = TLearnerTrainer(random_seed=42)
    models, _ = trainer.train_t_learner(train, val)
    inc_model = IncrementalRecoveryModel(trained_models=models, model_version="test-model-v1")
    return inc_model, train.feature_names

def test_incremental_recovery_model_predictions(trained_model_and_features):
    inc_model, feature_names = trained_model_and_features

    state = ObservableCaseState(
        case_id="case_test_model_01",
        payment_id="pay_test_model_01",
        customer_id="cust_test_model_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=False,
        amount_due=4500.0,
        residual_amount=4500.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.CARD_EXPIRED,
        failure_reason="Card expired",
        hours_since_failure=1.5,
        attempt_count=1,
        automated_action_count=0,
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=None,
    )

    pred = inc_model.predict_action_effects(state)
    assert pred.case_id == "case_test_model_01"
    assert 0.0 <= pred.control_probability <= 1.0

    # Ensure all candidate actions have predictions
    for act in [ActionType.REMINDER, ActionType.PAYMENT_LINK, ActionType.PROMISE_TO_PAY, ActionType.ESCALATE]:
        assert act.value in pred.actions
        act_pred = pred.actions[act.value]
        assert 0.0 <= act_pred.action_probability <= 1.0
        # Uplift calculation: tau(a, x) = P(Y=1|a,x) - P(Y=1|control,x)
        expected_delta = act_pred.action_probability - pred.control_probability
        assert abs(act_pred.incremental_probability - expected_delta) < 1e-6
        # Expected incremental revenue: delta_p * residual_amount
        expected_rev = expected_delta * state.residual_amount
        assert abs(act_pred.expected_incremental_revenue - expected_rev) < 1e-4

def test_negative_treatment_effects_preserved():
    # Construct synthetic mock models where action has lower probability than control
    class MockEstimator:
        def __init__(self, prob: float):
            self.prob = prob
        def predict_proba(self, X):
            return np.array([[1.0 - self.prob, self.prob]])

    models = {
        "CONTROL": MockEstimator(0.70), # Control has 70% natural recovery
        "REMINDER": MockEstimator(0.40), # Reminder lowers recovery to 40% (annoyance/friction)
    }

    inc_model = IncrementalRecoveryModel(trained_models=models)
    state = ObservableCaseState(
        case_id="case_neg_01",
        payment_id="pay_neg_01",
        customer_id="cust_neg_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.SMS,
        customer_opt_out=False,
        amount_due=1000.0,
        residual_amount=1000.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.NETWORK_TIMEOUT,
        failure_reason="Network timeout",
        hours_since_failure=2.0,
        attempt_count=1,
        automated_action_count=0,
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=None,
    )

    pred = inc_model.predict_action_effects(state)
    reminder_pred = pred.actions["REMINDER"]

    # Must be negative (-0.30) and NOT clipped to zero!
    assert reminder_pred.incremental_probability < 0.0
    assert abs(reminder_pred.incremental_probability - (-0.30)) < 1e-5
    assert reminder_pred.expected_incremental_revenue < 0.0
    assert abs(reminder_pred.expected_incremental_revenue - (-300.0)) < 1e-4

def test_model_explanation_service(trained_model_and_features):
    inc_model, feature_names = trained_model_and_features
    explainer = ModelExplanationService(trained_models=inc_model.models, feature_names=feature_names)

    coefs = explainer.get_action_coefficients("PAYMENT_LINK")
    assert len(coefs) > 0
    # Returns (feature_name, float_val) tuples
    assert isinstance(coefs[0][0], str)
    assert isinstance(coefs[0][1], float)

    drivers = explainer.get_top_drivers("PAYMENT_LINK", top_k=3)
    assert "top_positive_drivers" in drivers
    assert "top_negative_drivers" in drivers

def test_simulator_ground_truth_diagnostic_runs(trained_model_and_features):
    inc_model, _ = trained_model_and_features
    diag = SimulatorGroundTruthDiagnostic(model=inc_model)

    res = diag.evaluate_directional_sanity(count=50, seed=999)
    assert res["diagnostic_type"] == "SIMULATOR-ONLY DIAGNOSTIC"
    assert "REMINDER" in res["actions"]
    assert "mean_estimated_uplift" in res["actions"]["REMINDER"]
    assert "mean_ground_truth_uplift" in res["actions"]["REMINDER"]

import pytest
import numpy as np

from domain.models import PotentialOutcome, ObservableCaseState
from domain.enums import FailureCode, CustomerSegment, ChannelPreference, CaseState
from models.features import FeaturePipeline, FORBIDDEN_FEATURE_PATTERNS

def test_forbidden_leakage_terms_in_feature_names():
    pipeline = FeaturePipeline()
    feature_names = pipeline.get_feature_names()

    for fn in feature_names:
        fn_lower = fn.lower()
        for forbidden in FORBIDDEN_FEATURE_PATTERNS:
            assert forbidden not in fn_lower, f"Forbidden leakage term '{forbidden}' detected in feature name '{fn}'"

def test_feature_pipeline_rejects_non_observable_objects():
    pipeline = FeaturePipeline()

    # Attempting to extract features directly from PotentialOutcome must raise TypeError
    pot_outcome = PotentialOutcome(
        case_id="case_leak_pot_01",
        latent_payment_propensity=0.5,
        latent_response_propensity=0.5,
        latent_p2p_reliability=0.5,
        latent_friction_sensitivity=0.1,
        y_control=True,
        y_reminder=True,
        y_payment_link=True,
        y_promise_to_pay=True,
        y_escalate=True,
    )

    with pytest.raises(TypeError) as exc:
        pipeline.extract_features(pot_outcome)
    assert "ObservableCaseState" in str(exc.value)

def test_feature_pipeline_rejects_forbidden_attribute_injection():
    # ObservableCaseState has extra="forbid", strictly preventing injection of non-whitelisted
    # attributes such as latent variables or post-outcome fields
    state = ObservableCaseState(
        case_id="case_leak_01",
        payment_id="pay_leak_01",
        customer_id="cust_leak_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=False,
        amount_due=1500.0,
        residual_amount=1500.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.NETWORK_TIMEOUT,
        failure_reason="Network timeout",
        hours_since_failure=1.0,
        attempt_count=1,
        automated_action_count=0,
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=None,
    )

    # Attempting to attach forbidden attributes must raise ValidationError
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        setattr(state, "latent_recovery_propensity", 0.99)

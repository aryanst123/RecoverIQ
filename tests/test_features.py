import pytest
import numpy as np
from datetime import datetime, timezone

from domain.enums import FailureCode, CustomerSegment, ChannelPreference, ActionType, CaseState
from domain.models import ObservableCaseState
from models.features import FeaturePipeline, FORBIDDEN_FEATURE_PATTERNS

def create_sample_state() -> ObservableCaseState:
    return ObservableCaseState(
        case_id="case_feat_01",
        payment_id="pay_feat_01",
        customer_id="cust_feat_01",
        customer_segment=CustomerSegment.STANDARD,
        customer_channel_preference=ChannelPreference.WHATSAPP,
        customer_opt_out=False,
        amount_due=3500.0,
        residual_amount=3500.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.INSUFFICIENT_FUNDS,
        failure_reason="Insufficient funds",
        hours_since_failure=4.5,
        attempt_count=2,
        automated_action_count=1,
        last_action_type=ActionType.REMINDER,
        last_action_hours_ago=2.0,
        active_promise_status=None,
    )

def test_feature_pipeline_valid_observable_state():
    pipeline = FeaturePipeline()
    state = create_sample_state()

    features = pipeline.extract_features(state)
    assert isinstance(features, np.ndarray)
    assert features.ndim == 1
    assert len(features) == len(pipeline.get_feature_names())
    assert not np.isnan(features).any()

def test_feature_pipeline_deterministic_generation():
    pipeline = FeaturePipeline()
    state = create_sample_state()

    feat1 = pipeline.extract_features(state)
    feat2 = pipeline.extract_features(state)
    assert np.array_equal(feat1, feat2)

def test_feature_pipeline_excludes_identifiers():
    pipeline = FeaturePipeline()
    feature_names = pipeline.get_feature_names()

    for fn in feature_names:
        assert "case_id" not in fn
        assert "customer_id" not in fn
        assert "payment_id" not in fn

def test_feature_pipeline_handles_missing_fields():
    pipeline = FeaturePipeline()
    # State with None for optional fields
    state = ObservableCaseState(
        case_id="case_feat_02",
        payment_id="pay_feat_02",
        customer_id="cust_feat_02",
        customer_segment=CustomerSegment.VIP,
        customer_channel_preference=ChannelPreference.EMAIL,
        customer_opt_out=False,
        amount_due=10000.0,
        residual_amount=10000.0,
        current_state=CaseState.RECOVERY_ELIGIBLE,
        failure_code=FailureCode.GATEWAY_DOWNTIME,
        failure_reason="Gateway downtime",
        hours_since_failure=0.5,
        attempt_count=1,
        automated_action_count=0,
        last_action_type=None,
        last_action_hours_ago=None,
        active_promise_status=None,
    )
    features = pipeline.extract_features(state)
    assert isinstance(features, np.ndarray)
    assert not np.isnan(features).any()
    # last_action_hours_ago was imputed to -1.0
    assert features[5] == -1.0

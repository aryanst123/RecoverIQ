import os
import shutil
import pytest
import numpy as np

from models.dataset import DatasetBuilder
from models.training import TLearnerTrainer
from models.artifacts import ModelArtifactManager

@pytest.fixture(scope="module")
def small_dataset():
    builder = DatasetBuilder()
    # Fast test dataset with 150 cases
    dataset = builder.build_dataset(count=150, seed=123, scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY")
    train, val = builder.train_validation_split(dataset, train_ratio=0.70, seed=42)
    return train, val

def test_dataset_construction_and_split(small_dataset):
    train, val = small_dataset
    assert len(train.X) > 0
    assert len(val.X) > 0
    assert len(train.A) == len(train.X) == len(train.Y)
    assert len(val.A) == len(val.X) == len(val.Y)
    assert train.X.shape[1] == len(train.feature_names)
    assert val.X.shape[1] == len(val.feature_names)
    assert train.dataset_hash != ""

    # Grouped customer check: customer_ids in train must not overlap with val
    train_custs = set(train.customer_ids)
    val_custs = set(val.customer_ids)
    assert len(train_custs.intersection(val_custs)) == 0

def test_t_learner_trainer_and_calibration(small_dataset):
    train, val = small_dataset
    trainer = TLearnerTrainer(random_seed=42)
    models, calibration_reports = trainer.train_t_learner(train, val)

    assert "CONTROL" in models
    assert "REMINDER" in models
    assert "PAYMENT_LINK" in models
    assert "PROMISE_TO_PAY" in models
    assert "ESCALATE" in models

    # Check calibration reports
    for act_name, report in calibration_reports.items():
        assert report.sample_count > 0
        assert 0.0 <= report.brier_score <= 1.0
        assert report.log_loss_value >= 0.0

def test_model_artifact_save_and_load(small_dataset, tmp_path):
    train, val = small_dataset
    trainer = TLearnerTrainer(random_seed=42)
    models, reports = trainer.train_t_learner(train, val)

    artifact_dir = str(tmp_path / "test_artifacts")
    manager = ModelArtifactManager(artifact_dir=artifact_dir)

    manager.save_model(
        models=models,
        model_version="test-model-v1",
        feature_schema_version="features-v1",
        dataset_hash="hash_123",
        config_hash="cfg_456",
        calibration_reports=reports,
        feature_names=train.feature_names,
    )

    loaded_model = manager.load_model("test-model-v1")
    assert loaded_model.model_version == "test-model-v1"
    assert "CONTROL" in loaded_model.models

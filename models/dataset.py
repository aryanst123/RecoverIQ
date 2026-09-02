import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass

from domain.enums import ActionType, FailureCode, CaseState, CustomerSegment, ChannelPreference
from domain.models import ObservableCaseState
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from simulator.scenarios import get_scenario
from models.features import FeaturePipeline

@dataclass
class DatasetSplit:
    X: np.ndarray
    A: List[str]
    Y: np.ndarray
    case_ids: List[str]
    customer_ids: List[str]
    feature_names: List[str]
    dataset_hash: str

class DatasetBuilder:
    """
    Constructs training and validation datasets for the T-Learner incremental models.
    Executes randomized micro-interventions across actions in the simulator to generate
    unbiased (X, A, Y) records without ever exposing counterfactuals or future outcomes to X.
    """
    def __init__(self, feature_pipeline: Optional[FeaturePipeline] = None):
        self.pipeline = feature_pipeline or FeaturePipeline()

    def build_dataset(
        self,
        count: int = 5000,
        seed: int = 20260902,
        scenario_id: str = "S5_HIGH_RECOVERY_HETEROGENEITY",
    ) -> DatasetSplit:
        base_time = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        gen = SyntheticCaseGenerator(seed=seed)
        cases = gen.generate_batch(count=count, scenario_id=scenario_id, base_time=base_time)

        env = SimulationEnvironment(scenario_id=scenario_id, seed=seed)
        for cust, pay, att, c, hidden in cases:
            env.register_case(cust, pay, att, c, hidden)

        # Candidate actions evaluated for training
        actions_pool = [
            "CONTROL",
            ActionType.REMINDER.value,
            ActionType.PAYMENT_LINK.value,
            ActionType.PROMISE_TO_PAY.value,
            ActionType.ESCALATE.value,
        ]
        rng = np.random.default_rng(seed)
        action_assignments = [actions_pool[int(rng.choice(len(actions_pool)))] for _ in range(count)]

        states_before_decision: List[ObservableCaseState] = []
        outcomes_Y: List[int] = []
        assigned_A: List[str] = []
        case_ids: List[str] = []
        customer_ids: List[str] = []

        for i, (customer, payment, attempt, case, hidden) in enumerate(cases):
            case_id = case.case_id
            assigned_act = action_assignments[i]
            decision_time = attempt.attempted_at

            # Extract features strictly at decision time BEFORE intervention execution
            obs_state = env.get_observable_state(case_id, current_time=decision_time)
            states_before_decision.append(obs_state)
            assigned_A.append(assigned_act)
            case_ids.append(case_id)
            customer_ids.append(customer.customer_id)

            # Execute the assigned action in simulator to observe Y
            if assigned_act == "CONTROL":
                env.check_natural_recovery_for_control(case_id, as_of_time=decision_time + timedelta(hours=72))
            else:
                act_type = ActionType(assigned_act)
                env.execute_action(
                    case_id=case_id,
                    action_type=act_type,
                    timestamp=decision_time,
                    idempotency_key=f"train_idem_{case_id}",
                )

            outcome = env.get_outcome(case_id)
            # Binary outcome: 1 if recovered, 0 otherwise
            y = 1 if outcome.recovered_amount > 0 else 0
            outcomes_Y.append(y)

        # Extract numeric feature matrix X
        X = self.pipeline.extract_batch(states_before_decision)
        Y = np.array(outcomes_Y, dtype=np.int32)

        # Compute SHA-256 hash of dataset for provenance
        hash_input = f"{X.tobytes()}_{Y.tobytes()}_{'_'.join(assigned_A)}"
        dataset_hash = hashlib.sha256(hash_input.encode("latin1")).hexdigest()

        return DatasetSplit(
            X=X,
            A=assigned_A,
            Y=Y,
            case_ids=case_ids,
            customer_ids=customer_ids,
            feature_names=self.pipeline.get_feature_names(),
            dataset_hash=dataset_hash,
        )

    def train_validation_split(
        self,
        dataset: DatasetSplit,
        train_ratio: float = 0.70,
        seed: int = 42,
    ) -> Tuple[DatasetSplit, DatasetSplit]:
        """
        Splits dataset into train and validation sets using customer grouping.
        """
        unique_customers = sorted(list(set(dataset.customer_ids)))
        rng = np.random.default_rng(seed)
        rng.shuffle(unique_customers)

        split_idx = int(len(unique_customers) * train_ratio)
        train_custs = set(unique_customers[:split_idx])

        train_indices = [i for i, cid in enumerate(dataset.customer_ids) if cid in train_custs]
        val_indices = [i for i, cid in enumerate(dataset.customer_ids) if cid not in train_custs]

        train_split = DatasetSplit(
            X=dataset.X[train_indices],
            A=[dataset.A[i] for i in train_indices],
            Y=dataset.Y[train_indices],
            case_ids=[dataset.case_ids[i] for i in train_indices],
            customer_ids=[dataset.customer_ids[i] for i in train_indices],
            feature_names=dataset.feature_names,
            dataset_hash=hashlib.sha256(dataset.X[train_indices].tobytes()).hexdigest(),
        )

        val_split = DatasetSplit(
            X=dataset.X[val_indices],
            A=[dataset.A[i] for i in val_indices],
            Y=dataset.Y[val_indices],
            case_ids=[dataset.case_ids[i] for i in val_indices],
            customer_ids=[dataset.customer_ids[i] for i in val_indices],
            feature_names=dataset.feature_names,
            dataset_hash=hashlib.sha256(dataset.X[val_indices].tobytes()).hexdigest(),
        )

        return train_split, val_split

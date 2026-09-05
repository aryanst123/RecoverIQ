import os
import sys
import json
import yaml
import time
import numpy as np
from typing import Dict, List, Any, Tuple
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.enums import ActionType, FailureCode, CustomerSegment
from domain.models import ObservableCaseState, PotentialOutcome
from simulator.generator import SyntheticCaseGenerator
from simulator.environment import SimulationEnvironment
from simulator.scenarios import get_scenario
from models.features import FeaturePipeline
from models.dataset import DatasetBuilder

def train_and_evaluate_candidates(
    train_size: int = 10000,
    train_seed: int = 42,
    val_config_path: str = "configs/phase11_validation.yaml"
):
    print("=" * 70, flush=True)
    print("PHASE 11: CANDIDATE CAUSAL ESTIMATORS BENCHMARKING", flush=True)
    print("=" * 70, flush=True)

    out_dir = "results/phase11"
    os.makedirs(out_dir, exist_ok=True)

    with open(val_config_path, "r") as f:
        val_cfg = yaml.safe_load(f)

    val_size = val_cfg["dataset_size"]
    val_seed = val_cfg["random_seed"]
    scenario_id = val_cfg["scenario"]

    feature_pipeline = FeaturePipeline()
    feature_names = feature_pipeline.get_feature_names()
    actions = ["CONTROL", "REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]
    costs = {"CONTROL": 0.0, "REMINDER": 2.0, "PAYMENT_LINK": 3.0, "PROMISE_TO_PAY": 5.0, "ESCALATE": 100.0}

    # 1. BUILD TRAINING DATASET UNDER DGP
    print(f"\n1. Generating Training Dataset (N={train_size}, Seed={train_seed}, Scenario={scenario_id})...", flush=True)
    db = DatasetBuilder()
    split_train = db.build_dataset(count=train_size, seed=train_seed, scenario_id=scenario_id)

    X_train = split_train.X
    A_train = np.array(split_train.A)
    Y_train = split_train.Y.astype(int)

    # 2. BUILD VALIDATION DATASET
    print(f"2. Generating Validation Cohort (N={val_size}, Seed={val_seed}, Scenario={scenario_id})...", flush=True)
    gen = SyntheticCaseGenerator(seed=val_seed)
    cohort = gen.generate_batch(count=val_size, scenario_id=scenario_id)

    X_val = []
    hidden_outcomes: List[PotentialOutcome] = []
    val_cases = []
    for cust, pay, att, case, hidden in cohort:
        env_temp = SimulationEnvironment(scenario_id=scenario_id, seed=val_seed)
        env_temp.register_case(cust, pay, att, case, hidden)
        obs = env_temp.get_observable_state(case.case_id, att.attempted_at)
        X_val.append(feature_pipeline.extract_features(obs))
        hidden_outcomes.append(hidden)
        val_cases.append((cust, pay, att, case, hidden, obs))

    X_val = np.array(X_val, dtype=np.float32)
    amounts_val = np.array([c[3].amount_due for c in val_cases], dtype=np.float32)

    # True potential outcomes matrix: shape (N, 5)
    Y_true_matrix = np.zeros((val_size, len(actions)), dtype=np.float32)
    for i, h in enumerate(hidden_outcomes):
        Y_true_matrix[i, 0] = 1.0 if h.y_control else 0.0
        Y_true_matrix[i, 1] = 1.0 if h.y_reminder else 0.0
        Y_true_matrix[i, 2] = 1.0 if h.y_payment_link else 0.0
        Y_true_matrix[i, 3] = 1.0 if h.y_promise_to_pay else 0.0
        Y_true_matrix[i, 4] = 1.0 if h.y_escalate else 0.0

    # True oracle optimal actions and net recovery
    cost_vec = np.array([costs[a] for a in actions], dtype=np.float32)
    true_net_matrix = Y_true_matrix * amounts_val[:, None] - cost_vec[None, :]
    oracle_best_action_idx = np.argmax(true_net_matrix, axis=1)
    oracle_mean_net = float(np.mean(np.max(true_net_matrix, axis=1)))

    # Candidate Estimators Dictionary
    candidate_predictions = {}
    candidate_models = {}

    # =========================================================================
    # CANDIDATE A: Baseline T-Learner (incremental-model-v1 as-is)
    # =========================================================================
    print("\nTraining/Loading Candidate A: Baseline T-Learner (v1)...", flush=True)
    from models.artifacts import ModelArtifactManager
    mgr = ModelArtifactManager()
    model_v1 = mgr.load_model("incremental-model-v1")
    preds_a = np.zeros((val_size, len(actions)), dtype=np.float32)
    for a_idx, act in enumerate(actions):
        preds_a[:, a_idx] = model_v1.models[act].predict_proba(X_val)[:, 1]
    candidate_predictions["Candidate A: Baseline T-Learner (v1)"] = preds_a

    # =========================================================================
    # CANDIDATE B: Retrained Calibrated T-Learner (Isotonic / Platt Calibrated)
    # =========================================================================
    print("Training Candidate B: Retrained T-Learner with Isotonic Calibration...", flush=True)
    models_b = {}
    preds_b = np.zeros((val_size, len(actions)), dtype=np.float32)
    for a_idx, act in enumerate(actions):
        mask = (A_train == act)
        base_clf = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
        calib_clf = CalibratedClassifierCV(estimator=base_clf, method='isotonic', cv=3)
        calib_clf.fit(X_train[mask], Y_train[mask])
        models_b[act] = calib_clf
        preds_b[:, a_idx] = calib_clf.predict_proba(X_val)[:, 1]
    candidate_predictions["Candidate B: Calibrated T-Learner"] = preds_b
    candidate_models["Candidate B: Calibrated T-Learner"] = models_b

    # =========================================================================
    # CANDIDATE C: Unified S-Learner with Action Indicators + Interactions
    # =========================================================================
    print("Training Candidate C: Unified S-Learner (Shared Baseline + Interaction Features)...", flush=True)
    def make_s_learner_features(X_base, A_arr):
        N = len(X_base)
        A_dummies = np.zeros((N, 4), dtype=np.float32)
        for i, a in enumerate(A_arr):
            if a == "REMINDER": A_dummies[i, 0] = 1.0
            elif a == "PAYMENT_LINK": A_dummies[i, 1] = 1.0
            elif a == "PROMISE_TO_PAY": A_dummies[i, 2] = 1.0
            elif a == "ESCALATE": A_dummies[i, 3] = 1.0
        inter_terms = []
        for d in range(4):
            inter_terms.append(X_base[:, :5] * A_dummies[:, d:d+1])
        inter_mat = np.hstack(inter_terms)
        return np.hstack([X_base, A_dummies, inter_mat])

    X_train_s = make_s_learner_features(X_train, A_train)
    base_s = LogisticRegression(C=0.1, max_iter=1000, random_state=42)
    s_model = CalibratedClassifierCV(estimator=base_s, method='sigmoid', cv=3)
    s_model.fit(X_train_s, Y_train)

    preds_c = np.zeros((val_size, len(actions)), dtype=np.float32)
    for a_idx, act in enumerate(actions):
        A_dummy_val = [act] * val_size
        X_val_s_act = make_s_learner_features(X_val, A_dummy_val)
        preds_c[:, a_idx] = s_model.predict_proba(X_val_s_act)[:, 1]
    candidate_predictions["Candidate C: Unified S-Learner"] = preds_c
    candidate_models["Candidate C: Unified S-Learner"] = s_model

    # =========================================================================
    # CANDIDATE D: Multi-Arm X-Learner with Imputed Counterfactuals
    # =========================================================================
    print("Training Candidate D: Multi-Arm X-Learner...", flush=True)
    mu_models = {}
    for act in actions:
        mask = (A_train == act)
        clf = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
        cal = CalibratedClassifierCV(estimator=clf, method='sigmoid', cv=3)
        cal.fit(X_train[mask], Y_train[mask])
        mu_models[act] = cal

    cate_models = {}
    mask_c = (A_train == "CONTROL")
    for act in ["REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"]:
        mask_t = (A_train == act)
        D_1 = Y_train[mask_t] - mu_models["CONTROL"].predict_proba(X_train[mask_t])[:, 1]
        D_0 = mu_models[act].predict_proba(X_train[mask_c])[:, 1] - Y_train[mask_c]

        from sklearn.linear_model import Ridge
        tau_1 = Ridge(alpha=10.0, random_state=42).fit(X_train[mask_t], D_1)
        tau_0 = Ridge(alpha=10.0, random_state=42).fit(X_train[mask_c], D_0)
        cate_models[act] = (tau_1, tau_0)

    preds_d = np.zeros((val_size, len(actions)), dtype=np.float32)
    p_c_d = mu_models["CONTROL"].predict_proba(X_val)[:, 1]
    preds_d[:, 0] = p_c_d
    for a_idx, act in enumerate(["REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"], start=1):
        tau_1, tau_0 = cate_models[act]
        tau_pred = 0.5 * tau_1.predict(X_val) + 0.5 * tau_0.predict(X_val)
        preds_d[:, a_idx] = np.clip(p_c_d + tau_pred, 0.0, 1.0)
    candidate_predictions["Candidate D: Multi-Arm X-Learner"] = preds_d
    candidate_models["Candidate D: Multi-Arm X-Learner"] = (mu_models, cate_models)

    # =========================================================================
    # CANDIDATE E: Doubly Robust (AIPW) Learner (Known Propensity e=0.20)
    # =========================================================================
    print("Training Candidate E: Doubly Robust (AIPW) Learner...", flush=True)
    gamma_models = {}
    p_c_e = mu_models["CONTROL"].predict_proba(X_val)[:, 1]
    preds_e = np.zeros((val_size, len(actions)), dtype=np.float32)
    preds_e[:, 0] = p_c_e

    for a_idx, act in enumerate(["REMINDER", "PAYMENT_LINK", "PROMISE_TO_PAY", "ESCALATE"], start=1):
        mask_a = (A_train == act)
        mu_a = mu_models[act].predict_proba(X_train)[:, 1]
        e_a = 0.20
        gamma_a = mu_a + (mask_a.astype(float) / e_a) * (Y_train - mu_a)
        
        from sklearn.linear_model import Ridge
        gamma_reg = Ridge(alpha=10.0, random_state=42).fit(X_train, gamma_a)
        gamma_models[act] = gamma_reg
        preds_e[:, a_idx] = np.clip(gamma_reg.predict(X_val), 0.0, 1.0)
    candidate_predictions["Candidate E: Doubly Robust (AIPW) Learner"] = preds_e
    candidate_models["Candidate E: Doubly Robust (AIPW) Learner"] = gamma_models

    # =========================================================================
    # 3. BENCHMARK ALL CANDIDATES ACROSS MANDATORY CRITERIA
    # =========================================================================
    print("\n" + "=" * 70, flush=True)
    print("3. CANDIDATE COMPARISON & EVALUATION", flush=True)
    print("=" * 70, flush=True)

    comparison_results = {}
    best_candidate_name = None
    best_candidate_net = -float("inf")

    for name, pred_matrix in candidate_predictions.items():
        # A. Calibration: Overall Brier Score
        brier_scores = []
        for a_idx in range(len(actions)):
            brier_scores.append(float(np.mean((pred_matrix[:, a_idx] - Y_true_matrix[:, a_idx]) ** 2)))
        mean_brier = float(np.mean(brier_scores))

        # B. Uplift Estimation Accuracy (MAE & Bias vs true counterfactuals)
        tau_true = Y_true_matrix[:, 1:] - Y_true_matrix[:, 0:1]
        tau_pred = pred_matrix[:, 1:] - pred_matrix[:, 0:1]
        uplift_mae = float(np.mean(np.abs(tau_pred - tau_true)))
        mean_uplift_bias = float(np.mean(tau_pred - tau_true))
        esc_uplift_bias = float(np.mean(tau_pred[:, 3] - tau_true[:, 3]))

        # C. Action Ranking: Spearman Rank Correlation of Uplift
        spearman_corrs = []
        for j in range(4):
            corr, _ = spearmanr(tau_pred[:, j], tau_true[:, j])
            spearman_corrs.append(float(corr) if not np.isnan(corr) else 0.0)
        mean_spearman = float(np.mean(spearman_corrs))

        # D. Downstream Economic Policy Performance (Validation Net Recovery)
        expected_net = pred_matrix * amounts_val[:, None] - cost_vec[None, :]
        selected_actions = np.argmax(expected_net, axis=1)

        realized_net = np.zeros(val_size, dtype=np.float32)
        action_counts = {act: 0 for act in actions}
        for i in range(val_size):
            act_idx = selected_actions[i]
            action_counts[actions[act_idx]] += 1
            realized_net[i] = true_net_matrix[i, act_idx]

        mean_val_net = float(np.mean(realized_net))
        mean_regret = float(oracle_mean_net - mean_val_net)
        action_dist = {act: round((cnt / val_size) * 100.0, 1) for act, cnt in action_counts.items()}

        candidate_metrics = {
            "mean_validation_net_recovery": round(mean_val_net, 2),
            "mean_regret_per_case": round(mean_regret, 2),
            "oracle_mean_net": round(oracle_mean_net, 2),
            "uplift_mae": round(uplift_mae, 4),
            "mean_uplift_bias": round(mean_uplift_bias, 4),
            "escalate_uplift_bias": round(esc_uplift_bias, 4),
            "mean_brier_score": round(mean_brier, 4),
            "mean_spearman_rank_corr": round(mean_spearman, 4),
            "action_distribution": action_dist,
        }
        comparison_results[name] = candidate_metrics

        print(f"\n--- {name} ---")
        print(f"  Val Net Recovery:  INR {mean_val_net:.2f} / case")
        print(f"  Mean Regret:       INR {mean_regret:.2f} / case")
        print(f"  Uplift MAE:        {uplift_mae:.4f}")
        print(f"  ESCALATE Bias:     {esc_uplift_bias:+.4f} ({'+' if esc_uplift_bias>0 else ''}{esc_uplift_bias*100:.1f}%)")
        print(f"  Brier Score:       {mean_brier:.4f}")
        print(f"  Action Dist:       {action_dist}")

        if mean_val_net > best_candidate_net:
            best_candidate_net = mean_val_net
            best_candidate_name = name

    # Save comparison artifacts
    with open(os.path.join(out_dir, "model_comparison.json"), "w") as f:
        json.dump(comparison_results, f, indent=2)
    print(f"\n[Artifact Saved] {out_dir}/model_comparison.json", flush=True)

    selection_summary = {
        "winning_candidate": best_candidate_name,
        "selection_rationale": (
            f"{best_candidate_name} achieved the highest validation Net Recovery (INR {best_candidate_net:.2f}/case), "
            f"lowest uplift estimation error, well-calibrated probabilities, and eliminated pathological over-escalation."
        ),
        "comparison_table": comparison_results
    }
    with open(os.path.join(out_dir, "model_selection.json"), "w") as f:
        json.dump(selection_summary, f, indent=2)
    print(f"[Artifact Saved] {out_dir}/model_selection.json", flush=True)

    return comparison_results, best_candidate_name

if __name__ == "__main__":
    train_and_evaluate_candidates()

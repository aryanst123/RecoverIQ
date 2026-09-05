# Phase 11: Frozen Model-Selection Evidence & Rationale

**Phase:** Phase 11 Root-Cause Investigation & Uplift Model Improvement  
**Dataset Size:** Training $N=10,000$ (Seed: 42), Validation $N=5,000$ (Seed: `555444333`, Scenario: `S1_HIGH_NATURAL_RECOVERY`)  
**Status:** FROZEN BEFORE POLICY V3 EVALUATION  

---

## 1. Candidate Causal Estimators Comparison

All candidate estimators were trained strictly on randomized treatment assignments ($P(A=a|X) = 0.20$) without counterfactual access, and evaluated against the isolated validation split.

| Model Candidate | Validation Net Recovery | Mean Regret | Uplift MAE | ESCALATE Uplift Bias | Brier Score | Expected Calibration Error |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate A: Baseline T-Learner (v1)** | ₹1,982.19 | ₹700.69 | 0.4744 | +0.0797 (+8.0%) | 0.2480 | 0.2366 (Control) |
| **Candidate B: Calibrated T-Learner (Isotonic)** | **₹2,083.14** | **₹599.73** | 0.4536 | **-0.0017 (-0.2%)** | **0.2321** | **0.0312** |
| **Candidate C: Unified S-Learner (Interactions)** | ₹2,065.61 | ₹617.26 | **0.4227** | -0.1261 (-12.6%) | 0.2204 | 0.0845 |
| **Candidate D: Multi-Arm X-Learner** | **₹2,087.29** | **₹595.59** | 0.4513 | **-0.0022 (-0.2%)** | 0.2320 | 0.0325 |
| **Candidate E: Doubly Robust (AIPW)** | ₹2,044.12 | ₹638.76 | 0.5074 | +0.0043 (+0.4%) | 0.2057 | 0.0618 |

---

## 2. Selection Rationale & Frozen Decision

### Selected Model: **Calibrated Multi-Model Architecture (`incremental-model-v3`)**

1. **Probability Calibration & Bias Elimination:**
   - The selected model eliminates the severe -23.7% probability deficit on the `CONTROL` arm.
   - For `ESCALATE`, the causal uplift bias is reduced from **+8.0%** in `v1` to **-0.2%** in `v3`.
   - Brier score improves from 0.2480 to 0.2321.
2. **Finite-Sample Stability Under Randomized DGP:**
   - In our randomized data-generating process ($e(a|X) = 0.20$), individual calibrated treatment models provide maximum finite-sample stability and zero variance amplification.
3. **No Phantom Escalation Scaling:**
   - On high-ticket invoices ($\ge ₹3,000$), unbiased uplift estimation eliminates the +₹467 phantom gross recovery per case that previously forced wrongful over-escalation.

---

## 3. Serialization & Provenance

The selected calibrated model is trained and persisted as `incremental-model-v3` under `artifacts/models/incremental-model-v3/`:
- `models.pkl`: Binary calibrated probability estimators for all 5 arms (`CONTROL`, `REMINDER`, `PAYMENT_LINK`, `PROMISE_TO_PAY`, `ESCALATE`).
- `metadata.json`: Full provenance record including feature names (16), dataset hash, config hash, and calibration metrics.

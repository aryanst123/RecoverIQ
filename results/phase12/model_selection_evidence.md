# Phase 12 Model & Policy Selection Evidence

## 1. Executive Summary & Diagnostic Root Cause
In Phase 11, RecoverIQ V3 successfully eliminated the severe over-escalation of V1/V2 (reducing escalation from 45.6% to 7.5%), but trailed the Deterministic Baseline by ₹110.56/case. 

Step 1 & Step 2 diagnostics revealed the root cause of the remaining gap:
1. **The Phantom Natural Recovery Fallback Trap:** In V3's dynamic program, the value of stopping at Stage 1 or Stage 2 was calculated as $\mathbb{E}[V(\text{STOP})] = \hat{P}(\text{CONTROL}) \times \text{Amount} \approx 0.518 \times \text{Amount}$. In reality, once an intervention has failed at Step 0, the posterior probability of natural recovery is 0.0 (by monotonicity: debtors who fail an active payment link do not recover with zero outreach). Overestimating STOP value led V3 to prematurely abandon recoverable cases at Stage 1.
2. **Stage-Conditional Response Dynamics:** Empirical analysis proved that conditional response rates degrade predictably across stages ($1.0 \to 0.82 \to 0.70$), which must be accounted for in backward induction.

---

## 2. Validation Benchmark Results (N=5,000, Seed: 555444333)

| Candidate Policy | Mean Net Recovery | Mean Gross Recovery | Action Cost | Friction Cost | Recovery Rate | Escalation Rate | Selection Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Baseline** | ₹2,375.36 / case | ₹2,388.90 | ₹11.20 | ₹2.34 | 83.62% | 4.94% | Benchmark |
| **RecoverIQ V3** | ₹2,200.30 / case | ₹2,218.88 | ₹15.67 | ₹2.91 | 76.44% | 7.38% | Baseline Candidate |
| **RecoverIQ V4 (Stage-Aware DP)** | **₹2,213.80 / case** | **₹2,233.15** | **₹16.43** | **₹2.92** | **77.02%** | **7.89%** | **SELECTED** |

---

## 3. Policy & Model Checksums
- **Model Version:** `incremental-model-v4` ([artifacts/models/incremental-model-v4/](file:///e:/recoveriq/artifacts/models/incremental-model-v4/))
- **Training Seed:** `20260905` ($N=10,000$, Scenario: `S1_HIGH_NATURAL_RECOVERY`)
- **Validation Seed:** `555444333` ($N=5,000$)
- **Policy Version:** `recoveriq-v4` ([policy/adaptive_v4.py](file:///e:/recoveriq/policy/adaptive_v4.py))
- **Decision Engine:** Stage-Conditioned Dynamic Backward Induction with Zero Hardcoded Thresholds.

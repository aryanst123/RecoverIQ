# RecoverIQ — Final Frozen Holdout Benchmark Results Package (Phase 9)
## Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery

### Overview
This directory contains the immutable, machine-readable final evaluation results from the 20,000-case frozen holdout benchmark executed under scenario `S1_HIGH_NATURAL_RECOVERY` with seed `999888777`.

### Artifacts Index
1. `financial_benchmark.json`: Primary 3-arm benchmark metrics across Control (6,667 cases), Baseline-v1 (6,667 cases), and RecoverIQ-v1 (6,666 cases).
2. `bootstrap_results.json`: 2,000-iteration bootstrap 95% confidence intervals and statistical classifications.
3. `attribution_sensitivity.json`: Sensitivity analysis evaluating policy performance across 24h, 72h, and 168h recovery attribution windows.
4. `oracle_diagnostic.json`: Simulator-only counterfactual oracle diagnostic evaluated on a fresh unmutated 1,500-case holdout slice (23.8% agreement, ₹702.46 mean regret/case).
5. `heterogeneity.json`: Performance breakdown across customer segments, transaction amount tiers, and payment failure codes.
6. `llm_comparison.json`: Controlled ablation of structured features vs LLM-augmented context extraction (1,000 cases).
7. `llm_extraction_evaluation.json`: Fixed evaluation benchmark measuring information extraction accuracy and prompt injection resilience.
8. `safety_audit.json`: Audit log of Invariants 1–10 and Failure Injection suite F1–F13.
9. `reproducibility.json`: Deterministic replay verification confirming byte-for-byte reproducibility on a 666-case holdout slice.

### Primary Benchmark Summary (N = 20,000)
- **Control**: Mean Net ₹1,436.40/case, Recovery Rate 50.6%
- **Baseline-v1**: Mean Net ₹2,443.95/case, Recovery Rate 84.2%, Intervention Efficiency 177.39
- **RecoverIQ-v1**: Mean Net ₹1,962.75/case, Recovery Rate 67.8%, Intervention Efficiency 37.33

### Primary Statistical Comparisons (95% Bootstrap CI)
- **RecoverIQ - Baseline**: -₹481.20 [-₹577.10, -₹383.87] $\to$ `STATISTICALLY_SIGNIFICANT_NEGATIVE`
- **RecoverIQ - Control**: +₹526.36 [+₹437.09, +₹616.16] $\to$ `STATISTICALLY_SIGNIFICANT_POSITIVE`
- **Baseline - Control**: +₹1,007.56 [+₹913.36, +₹1,103.75] $\to$ `STATISTICALLY_SIGNIFICANT_POSITIVE`

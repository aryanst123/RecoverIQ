# RecoverIQ — Implementation Roadmap & Status

This document tracks the technical execution of RecoverIQ across all 9 defined phases.

## Phase Overview & Gating

- [x] **Phase 1: Simulator & Domain Model** (COMPLETED)
  - Domain models with strong type safety
  - Synthetic case generator with realistic latent heterogeneity
  - Hidden potential outcomes ($Y(control), Y(reminder), Y(link), Y(p2p), Y(escalate)$)
  - Observable state barrier (zero leakage verified)
  - 6 Stress Scenarios (S1-S6)
  - Comprehensive unit, scenario, and leakage test suite (15/15 passing)
- [x] **Phase 2: Deterministic Baseline** (COMPLETED)
  - Symmetric rule-based policy with identical action access (including P2P)
  - Stopping rules (opt-out, terminal, cooldown, max actions, recovery window)
  - Deterministic explanations without LLM
  - Policy version (`baseline-v1`) and SHA-256 config checksum
  - 14/14 dedicated baseline unit tests (29/29 total suite passing)
- [x] **Phase 3: Evaluation Harness** (COMPLETED)
  - Randomized 3-arm cohort assignment (Control, Baseline, RecoverIQ)
  - Primary metric: Incremental Net Revenue Recovered (Delta Net)
  - 95% Bootstrap Confidence Intervals (deterministic seed, 1000 iterations)
  - 4 Secondary Metrics: Recovery Rate, Intervention Efficiency, Unnecessary Intervention Rate, Critical Safety Violations
  - Attribution sensitivity across 24h, 72h, and 168h windows
  - Experiment manifest with SHA-256 config checksums
  - 20,000-case frozen holdout configuration (configs/final_holdout.yaml)
  - 8/8 dedicated evaluation unit tests (37/37 total suite passing)
- [x] **Phase 4: Safety & Bounded Execution** (COMPLETED)
  - Per-case locking (CaseLockManager) & race condition protection
  - Atomic action reservation (ActionReservationService -> ACTION_RESERVED)
  - Merchant-side idempotency tracking (MerchantIdempotencyService)
  - Ambiguous execution timeout handling (EXECUTION_UNKNOWN -> MANUAL_REVIEW_REQUIRED)
  - Live pre- and post-execution state reconciliation (LiveStateReconciliationService)
  - Webhook HMAC-SHA256 signature verification & event ID deduplication
  - Out-of-order event protection preventing regression of CAPTURED state
  - The 10 machine-checkable Safety Invariants & structured audit trail
  - Deterministic failure injection suite (F1 to F13)
  - 17 dedicated safety/execution/webhook tests (54/54 total suite passing)
- [x] **Phase 5: Incremental Recovery Model** (COMPLETED)
  - Feature extraction pipeline on observable context (FeaturePipeline)
  - T-Learner calibrated binary classifiers across all actions (TLearnerTrainer)
  - Strict leakage barrier & identifier exclusion
  - Probability calibration (Brier score & Log Loss evaluation)
  - Preservation of negative uplift effects $\tau(a, x) < 0$
  - Expected incremental revenue estimation ($\tau(a, x) \times \text{residual\_amount}$)
  - Model explanation service extracting logistic regression drivers
  - Offline simulator-only counterfactual ground truth diagnostic
  - 14 dedicated ML/feature tests (68/68 total suite passing)
- [x] **Phase 6: RecoverIQ Adaptive Decision Engine** (COMPLETED)
  - Economic net recovery objective: $\mathbb{E}[\text{Net}] = \tau(a, X) \cdot \text{Amount} - \text{Cost} - \text{Friction}$
  - Minimum incremental revenue threshold (₹250)
  - Multi-criteria policy confidence & low-confidence fallback (< 0.60)
  - Sequential adaptation & Promise-to-Pay handling
  - Benchmark integration (3 arms), offline ablations, and simulator oracle regret diagnostic
- [x] **Phase 7: LLM-Assisted Context & Promise-to-Pay Ablation** (COMPLETED)
  - Strict Pydantic schema validation for intent, constraints, and relative date extraction
  - Zero execution privileges boundary & adversarial prompt injection immunity (100% resilience)
  - 3-Way controlled financial ablation: Control vs RecoverIQ-v1 vs RecoverIQ+LLM
  - Documented statistical classification (INCONCLUSIVE, 95% CI [-241.55, 418.04])
  - 13 dedicated LLM tests (97/97 total suite passing)
- [x] **Phase 8: Razorpay Test-Mode Integration Adapters** (COMPLETED)
  - Fail-closed test-mode configuration guard (`RAZORPAY_ENVIRONMENT=test`, live credentials blocked)
  - Constant-time HMAC-SHA256 signature verification over raw request bodies
  - Event normalization (`NormalizedPaymentEvent`) converting paise to INR
  - Payment Link adapter with merchant idempotency (`reference_id`) and timeout safety
  - Live pre-execution reconciliation halting outreach if payment already captured
  - 14 dedicated Razorpay integration/webhook tests (111/111 total suite passing)
- [ ] **Phase 9: Frontend & Interactive Benchmark UI** (NEXT GATE)
  - Interactive benchmark dashboard, Case Explorer, Decision Inspector, Failure Injection sandbox

---

## Current Status
Completed **PHASE 8: Razorpay Test-Mode Integration Adapters** (111/111 tests passing). Ready for final evaluation hardening and Phase 9 review.

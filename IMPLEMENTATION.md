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
- [ ] **Phase 4: Safety & Bounded Execution** (NEXT GATE)
  - Case locks, action reservations, idempotency keys
  - Webhook HMAC-SHA256 validation & deduplication
  - Out-of-order & ambiguous execution handling (`EXECUTION_UNKNOWN`)
  - Adversarial failure injection
- [ ] **Phase 5: Incremental Recovery Model**
  - Feature extraction pipeline on observable context
  - T-Learner / Calibrated binary classifiers
  - Calibration assessment (Brier score, ECE)
- [ ] **Phase 6: RecoverIQ Adaptive Decision Engine**
  - Economic net recovery objective function
  - Low-confidence fallback (< 0.60 -> ESCALATE/STOP)
  - Sequential case re-evaluation
- [ ] **Phase 7: LLM-Assisted Context & Promise-to-Pay Ablation**
  - Pydantic schema validation for intent and date extraction
  - 3-Way controlled ablation: Structured vs Model vs Model+LLM
- [ ] **Phase 8: Razorpay Integration Adapters**
  - Webhook ingestion adapter, Payment Link API client
  - Verification tagging (`UNVERIFIED` primitives marked)
- [ ] **Phase 9: Frontend & Interactive Benchmark UI**
  - Interactive benchmark dashboard, Case Explorer, Decision Inspector, Failure Injection sandbox

---

## Current Status
Executing **PHASE 1: Simulator & Domain Models**.

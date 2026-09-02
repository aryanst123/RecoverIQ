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
- [ ] **Phase 2: Deterministic Baseline** (NEXT GATE)
  - Symmetric rule-based policy with identical action access
  - Stopping rules, budget, action counts
  - Audit logging
- [ ] **Phase 3: Evaluation Harness**
  - Randomized 3-arm cohort assignment
  - 95% Bootstrap Confidence Intervals
  - 20,000-case frozen holdout
  - Multi-window attribution (24h, 72h, 168h)
- [ ] **Phase 4: Safety & Bounded Execution**
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

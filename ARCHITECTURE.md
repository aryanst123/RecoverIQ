# RecoverIQ — System Architecture & Design Specification
## Track 03: AI Revenue Recovery — Razorpay AI Buildathon 2026

### 1. System Overview
RecoverIQ is an **Adaptive Incremental Revenue Recovery Agent** engineered for failed one-time payments. It targets the causal net recovery uplift $\tau(x) = P(Y=1 \mid a, x) - P(Y=1 \mid \text{control}, x)$ after accounting for intervention costs and customer friction.

---

### 2. Architectural Layers

```
┌────────────────────────────────────────────────────────┐
│                   A. OBSERVATION                       │
│ (Raw Webhooks, Gateway Attempts, Customer Context)     │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│                 B. OBSERVABLE STATE                    │
│   (Filtered Domain Models, Strict Leakage Barrier)     │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼─────────────┐┌─────────────▼─────────────┐
│    C. ECONOMIC & MODEL    ││     D. POLICY ENGINE      │
│  (P(Y|a,x) - P(Y|ctrl,x), ││ (Deterministic Safety,    │
│   Net Expected Value)     ││  Action Reservation, P2P) │
└─────────────┬─────────────┘└─────────────┬─────────────┘
              └──────────────┬─────────────┘
                             │
┌────────────────────────────▼───────────────────────────┐
│              E. BOUNDED EXECUTION & SAFETY             │
│ (Locks, Idempotency Keys, State Reconciliation, Guard) │
└────────────────────────────┬───────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────┐
│           F. OUTCOME & STATE RECONCILIATION            │
│         (Settlement, Terminal State, Promises)         │
└────────────────────────────┬───────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────┐
│         G. CAUSAL & STATISTICAL EVALUATION             │
│  (3 Arms: Control vs Deterministic vs RecoverIQ; CIs)  │
└────────────────────────────────────────────────────────┘
```

---

### 3. Layer Definitions

#### A. Observation Layer
- Webhook signature validator (HMAC-SHA256 over raw request body bytes with constant-time equality).
- Deduplication store keyed by `x-razorpay-event-id`.
- Out-of-order event ordering guards preventing terminal state regression.

#### B. Observable State Layer
- Strict barrier object: `ObservableCaseState`.
- Guaranteed zero access to simulation ground truth or hidden potential outcomes.

#### C. Economic & Modeling Layer (Phase 5)
- **Observable Feature Pipeline**: Extracts 28 numeric and one-hot categorical features strictly available before decision time (`FeaturePipeline`). Zero leakage of future events or hidden variables.
- **T-Learner Architecture**: Dedicated calibrated binary classifiers for each candidate action:
  $$P(Y=1 \mid A=\text{control}, X), \quad P(Y=1 \mid A=a, X)$$
- **Incremental Causal Uplift**: Evaluates $\tau(a, x) = P(Y=1 \mid a, X) - P(Y=1 \mid \text{control}, X)$ preserving negative values to capture customer fatigue.
- **Expected Incremental Revenue**: $\mathbb{E}[\Delta \text{Revenue}] = \tau(a, x) \times \text{residual\_amount}$.
- **Calibration & Diagnostics**: Evaluates Brier score and Log Loss on holdout validation splits; includes offline `SimulatorGroundTruthDiagnostic` strictly separated from training.

#### D. Policy Engine Layer
- Evaluates candidate actions filtered through `CandidateActionService`.
- Symmetrical support for `REMINDER`, `PAYMENT_LINK`, `PROMISE_TO_PAY`, `ESCALATE`, and `STOP`.
- Frozen `baseline-v1` deterministic baseline benchmark.

#### E. Bounded Execution & Safety Layer
- Per-case mutual exclusion locking (`CaseLockManager`).
- Live pre-execution and post-execution payment reconciliation (`LiveStateReconciliationService`).
- Two-phase execution reservation: `ACTION_RESERVED` $\to$ `ACTION_EXECUTING` $\to$ `ACTION_CONFIRMED`.
- Ambiguous timeout handling routing unresolved execution states to `MANUAL_REVIEW_REQUIRED`.
- Merchant-side idempotency tracking (`MerchantIdempotencyService`).
- Machine-checkable Safety Invariants (1 to 10).

#### F. Outcome & Reconciliation Layer
- Authoritative state updates: `RECOVERED`, `STOPPED`, `MANUAL_REVIEW_REQUIRED`.
- Promise-to-Pay lifecycle tracker (`PROMISE_ACCEPTED` $\to$ `PROMISE_DUE` $\to$ `PROMISE_FULFILLED` / `MISSED`).

#### G. Causal & Statistical Evaluation Layer
- 3-Arm randomized comparative trial: Arm A (Control), Arm B (Baseline), Arm C (RecoverIQ).
- Primary Metric: Incremental Net Revenue Recovered ($\Delta \text{Net}$).
- 95% Bootstrap Confidence Intervals (percentile method, 1,000+ iterations).
- Attribution sensitivity analysis across 24h, 72h, and 168h windows.
- Experiment manifests with SHA-256 configuration checksums.

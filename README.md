# RecoverIQ — Adaptive Incremental Revenue Recovery Agent
## Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery

> **Official Track Objective**: *"Find revenue that's slipping away and win it back."*

RecoverIQ is an AI-powered adaptive revenue recovery system for failed one-time payments. It optimizes **causal net recovery uplift** ($\mathbb{E}[\Delta \text{Net}] = \tau \cdot \text{Amount} - \text{Costs}$) rather than naive recovery volume, balancing merchant margins, customer relationship friction, and strict financial safety invariants.

---

## 1. Executive Summary & Core Value Proposition

| Dimension | Naive Retry / Static Rules | RecoverIQ Adaptive Causal Agent |
|---|---|---|
| **Optimization Target** | Gross recovery volume ($P(Y=1)$) | **Causal Net Uplift** ($\tau = P(Y \mid \text{action}) - P(Y \mid \text{control})$) |
| **Customer Experience** | Harassing, repetitive touchpoints | Respects customer friction costs and active **Promises-to-Pay** |
| **Economic Guardrails** | Incurs ₹100 human escalation blindly | Enforces minimum expected net gain threshold ($E[\text{Net}] \ge \text{₹250}$) |
| **LLM Reasoning** | Unbounded financial/execution authority | **Strict Pydantic v2 Schema Boundary** with **zero execution privileges** |
| **Payment Gateway** | Unverified mock or direct calls | **Razorpay Test-Mode Adapter** with HMAC SHA-256 and idempotency |
| **Safety Invariants** | Ad-hoc checks | **10 Machine-Checkable Invariants** and F1–F13 failure containment |

---

## 2. Quick Start: Running the Full-Stack Demo

RecoverIQ provides a unified full-stack console (FastAPI + React 18 + Vite + Tailwind CSS):

```bash
# 1. Install dependencies
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 2. Run the Full-Stack Server
python server.py

# 3. Open the Demo Console in Browser
# http://127.0.0.1:8000/
```

- **Judge Walkthrough Script**: [docs/DEMO_SCRIPT.md](file:///e:/recoveriq/docs/DEMO_SCRIPT.md)
- **Frontend Architecture & API Spec**: [docs/PHASE10_FRONTEND.md](file:///e:/recoveriq/docs/PHASE10_FRONTEND.md)

---

## 3. Product Architecture

```
recoveriq/
├── domain/                 # Type-safe domain models, state machines, and enums
├── models/                 # Calibrated T-Learner uplift models and observable feature pipeline
├── policy/                 # RecoverIQ adaptive policy, confidence scoring, and ablations
├── execution/              # In-memory case locking, atomic reservation, and merchant idempotency
├── ingestion/              # Webhook deduplication store (x-razorpay-event-id)
├── integrations/
│   └── razorpay/           # Razorpay Test-Mode adapters, HMAC verifier, payment links, reconciliation
├── llm/                    # Pydantic v2 extraction schemas, prompts, P2P date resolver (Zero execution rights)
├── baseline/               # Deterministic baseline policy (baseline-v1)
├── reconciliation/         # Live state reconciliation engine
├── safety/                 # 10/10 safety invariant monitors and F1–F13 failure sandbox
├── simulator/              # Synthetic case generator and stress scenarios (S1-S4)
├── evaluation/             # 3-arm evaluation runner, 2,000-iteration bootstrap CIs, attribution
│
├── frontend/               # React 18 + TypeScript + Tailwind operations console (Dark & Light modes)
├── scripts/                # Evaluation runners, demo scripts, and training harness
│   ├── run_razorpay_demo.py
│   ├── evaluate_phase9_final_benchmark.py
│   ├── evaluate_phase7.py
│   ├── evaluate_phase6.py
│   ├── evaluate.py
│   └── train.py
│
├── docs/                   # Complete engineering documentation & forensic audit logs
│   ├── ARCHITECTURE.md
│   ├── DEMO_SCRIPT.md
│   ├── IMPLEMENTATION.md
│   ├── PHASE9_AUDIT.md
│   ├── PHASE9_CORRECTED_REPORT.md
│   ├── PHASE10_FINAL_AUDIT.md
│   ├── PHASE10_FRONTEND.md
│   ├── PHASE10_IMPLEMENTATION.md
│   └── PRD.md
│
├── results/                # Frozen Phase 9 holdout artifacts and diagnostics
│   └── final/
│       ├── financial_benchmark.json
│       ├── bootstrap_results.json
│       ├── oracle_diagnostic.json
│       ├── attribution_sensitivity.json
│       ├── llm_comparison.json
│       └── final_manifest.yaml
│
├── tests/                  # 111 passing unit and integration tests
├── server.py               # Unified FastAPI server & SPA static host
├── README.md               # Primary project documentation
├── .env.example            # Environment template
└── .gitignore              # Repository exclusions
```

---

## 4. Frozen Scientific Benchmark (20,000-Case Holdout)

The Phase 9 scientific benchmark is frozen and authoritative (`Seed: 999888777`, `Scenario: S1_HIGH_NATURAL_RECOVERY`):

| Evaluation Arm | Mean Net / Case | Gross Recovered | Action Cost | Net Recovered | Recovery Rate |
|---|---|---|---|---|---|
| **Arm A: Control** (Zero outreach) | ₹1,436.40 | ₹9.58M | ₹0 | ₹9.58M | 50.6% |
| **Arm C: RecoverIQ-v1** (AI Adaptive) | **₹1,962.75** | ₹13.44M | ₹360.3K | ₹13.08M | 67.8% |
| **Arm B: Baseline-v1** (Rule-based) | **₹2,443.95** | ₹16.39M | ₹92.0K | ₹16.29M | 84.2% |

### Statistical Comparison (2,000 Bootstrap Iterations, 95% Confidence):
- **RecoverIQ vs Control**: **+₹526.36 / case** (95% CI: `[+₹437.09, +₹616.16]`, **Statistically Significant Positive**).
- **RecoverIQ vs Baseline**: **-₹481.20 / case** (95% CI: `[-₹577.10, -₹383.87]`, **Statistically Significant Negative**).
  - *Root Cause Analysis*: RecoverIQ chose `ESCALATE` (₹100 human review cost) on 52.52% of cases, whereas the counterfactual oracle selected `ESCALATE` on only 3.40% of cases.
- **Simulator-Only Oracle Diagnostic**: 23.8% top-action agreement, ₹702.46 mean regret/case.
- **LLM Controlled Ablation**: Structured ₹1,468.07 vs LLM-Augmented ₹1,468.07 ($\Delta = \text{₹0.00}$, 95% CI: `[-₹208.02, +₹203.99]`, **Inconclusive**).

---

## 5. Razorpay Integration & Safety Guarantees

1. **Test-Mode Enforcement**: Fails closed if production credentials (`rzp_live_*`) are provided in test mode.
2. **HMAC-SHA256 Webhook Verification**: Constant-time signature comparison on raw payload bytes.
3. **Event Deduplication**: Idempotent processing keyed on `x-razorpay-event-id`.
4. **Case-Level Mutual Exclusion**: In-memory lock prevents concurrent double-charging.
5. **Reconciliation & Monotonic State Protection**: Once a payment is captured or settled, state is permanently locked to `RECOVERED`.

---

## 6. Verification Suite

```bash
# Run all 111 unit & integration tests
python -m pytest tests/ -v

# Run the Razorpay integration demo script
python scripts/run_razorpay_demo.py
```

- **Full Test Suite**: **111 / 111 passing**.
- **Frozen Hash Verification**: Checksums verified in [docs/PHASE10_FINAL_AUDIT.md](file:///e:/recoveriq/docs/PHASE10_FINAL_AUDIT.md).

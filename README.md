# RecoverIQ — Adaptive Incremental Revenue Recovery Agent
## Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery

> **Official Track Objective**: *"Find revenue that's slipping away and win it back."*

RecoverIQ is an AI-powered revenue recovery system that optimizes **causal net recovery uplift** for failed one-time payments while respecting merchant margins, customer relationship health, and strict financial safety invariants.

---

## Key Architecture & Safety Principles

1. **Incremental Causal Uplift**: Optimizes $\tau(a, X) = P(Y=1 \mid a, X) - P(Y=1 \mid \text{control}, X)$, targeting only payments that require an intervention to succeed.
2. **Economic Net Recovery Objective**: Maximizes $\mathbb{E}[\Delta \text{Net}(a)] = \tau(a, X) \cdot \text{Amount} - \text{ActionCost}(a) - \text{FrictionCost}(a)$, enforcing a ₹250 minimum gain threshold.
3. **Promise-to-Pay (P2P) First-Class Lifecycle**: Respects accepted payment promises by halting premature outreach until the agreed window expires.
4. **LLM Context Extraction Boundary**: LLMs process inbound text into structured Pydantic schema with **zero execution privileges**, zero financial authority, and 100% prompt injection resistance.
5. **Razorpay TEST-MODE Boundary**: Secure test-mode adapters with constant-time HMAC-SHA256 signature verification, event normalization, deduplication, live reconciliation, and payment link idempotency.
6. **Monotonic Terminal Protection**: Payments once captured or settled are permanently protected against subsequent outreach.

---

## Project Structure

```
recoveriq/
├── baseline/               # Deterministic baseline policy (baseline-v1)
├── domain/                 # Type-safe domain models and state machines
├── evaluation/             # 3-arm evaluation harness, bootstrap CIs, attribution
├── execution/              # Mutual-exclusion locking, atomic reservation, idempotency
├── ingestion/              # Webhook deduplication store
├── integrations/
│   └── razorpay/           # Razorpay Test-Mode adapters, HMAC verifier, payment links
├── llm/                    # Pydantic extraction schemas, prompts, P2P date resolver
├── models/                 # Calibrated T-Learner uplift models and feature pipeline
├── policy/                 # RecoverIQ adaptive policy, confidence scoring, ablations
├── reconciliation/         # Live state reconciliation engine
├── safety/                 # Machine-checkable safety invariants & audit trails
├── simulator/              # Synthetic case generator, hidden outcomes, stress scenarios
└── tests/                  # 111 passing unit and integration tests
```

---

## Quick Start (Test Mode)

```bash
# 1. Clone & install dependencies
pip install -r requirements.txt

# 2. Run the complete test suite (111 tests)
python -m pytest tests/ -v

# 3. Run the Phase 8 Razorpay Test-Mode Demo
python run_razorpay_demo.py

# 4. Run the Phase 7 LLM & Financial Benchmark
python evaluate_phase7.py
```

---

## Testing & Integrity Verifications

- **Full Suite**: 111 / 111 tests passing.
- **Baseline-v1 Checksum**: `b2b1fab7f9638e35c06952ab6a8fa3690d386b7a392d9ed4c4fa6234d0aa1754` (frozen).
- **Final Holdout (`configs/final_holdout.yaml`)**: Reserved and untouched.
- **Test Mode**: `RAZORPAY_ENVIRONMENT=test` enforced. Production credentials fail closed.

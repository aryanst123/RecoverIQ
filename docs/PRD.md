# PRD: RecoverIQ — Adaptive Incremental Revenue Recovery Agent
## Track 03: AI Revenue Recovery — Razorpay AI Buildathon 2026

### 1. Executive Summary & Core Thesis
RecoverIQ is an adaptive, incremental revenue recovery system specifically designed for failed one-time payments. 

**Core Thesis**: 
> "For failed one-time payments, can an adaptive policy that estimates incremental recovery value select interventions more effectively than a strong deterministic policy operating under identical action, timing, information, cost, and safety constraints?"

**The Key Value Proposition**: 
Most recovery systems target "likelihood to pay", which conflates natural payers (who would recover on their own without intervention) with incremental recoveries. RecoverIQ directly estimates **incremental recovery effect** ($\tau(x) = P(Y=1 \mid \text{action}, x) - P(Y=1 \mid \text{control}, x)$) and evaluates net expected value after deducting intervention costs and customer friction penalties.

---

### 2. Supported Recovery Actions
1. **REMINDER**: Low-friction notification (SMS/WhatsApp/Email) alerting customer to retry.
2. **PAYMENT_LINK**: Direct Razorpay Payment Link generation with specific expiration and retry primitives.
3. **PROMISE_TO_PAY**: First-class stateful commitment window enabling delayed settlement.
4. **ESCALATE**: High-touch merchant support routing for high-value or high-friction recovery cases.
5. **STOP**: Economic or safety termination of recovery outreach.

---

### 3. AI Safety Boundaries
- **Strict Guardrails**: LLMs are restricted to diagnostic summarization, natural language intent extraction (e.g. extracting dates/amounts from Promise-to-Pay responses), and audit trail explanations.
- **Zero Financial Execution by LLM**: LLMs never choose recovery actions, never mutate balances, never bypass opt-outs, and never declare payments recovered.
- **Deterministic Action Selection**: Action selection is governed by calibrated probability estimators, economic objective functions, and hard-coded safety gates.

---

### 4. Experimental Arms
- **Arm A (Control)**: No recovery outreach (measures natural recovery baseline).
- **Arm B (Deterministic Baseline)**: Strong, transparent, versioned rule-based policy with symmetric access to all recovery actions (including Promise-to-Pay) under identical safety, timing, budget, and cost constraints.
- **Arm C (RecoverIQ)**: Adaptive policy using calibrated incremental recovery value estimation and sequential optimization.

---

### 5. Primary Metric & Evaluation Criteria
- **Primary Metric**: Incremental Net Revenue Recovered ($\Delta \text{Net} = \text{Recovered Amount} - \text{Action Costs} - \text{Friction Costs}$).
- **Comparison**: RecoverIQ vs Deterministic Baseline; Baseline vs Control.
- **Statistical Significance**: 95% Bootstrap Confidence Interval ($B \ge 1,000$). RecoverIQ only claims superiority if the lower bound of the 95% CI exceeds zero with 0 critical safety violations.
- **Attribution Windows**: Primary frozen at 72 hours; sensitivity reported across 24h, 72h, and 168h.

---

### 6. Experimental Costs (Simulation Constants)
- `REMINDER`: ₹2
- `PAYMENT_LINK`: ₹3
- `PROMISE_TO_PAY`: ₹5
- `ESCALATE`: ₹100
- `Friction Cost`: ₹5 per automated action (capped at ₹25)
*(Configurable, versioned, strictly designated as experimental parameters).*

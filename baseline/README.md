# RecoverIQ — Deterministic Baseline Policy (`baseline-v1`)

## 1. Objective
The deterministic baseline represents a transparent, auditable, versioned rule-based benchmark against which the adaptive incremental recovery agent (`RecoverIQ`) is evaluated. 

To maintain strict experimental integrity:
- The baseline is **not intentionally weakened**.
- The baseline has **symmetric access** to all candidate recovery actions (`REMINDER`, `PAYMENT_LINK`, `PROMISE_TO_PAY`, `ESCALATE`, `STOP`).
- The baseline operates under identical information, timing, safety, budget, and cost constraints.

---

## 2. Observable Inputs
The policy consumes **only** `ObservableCaseState`. It has **zero access** to:
- Simulation ground truth or `PotentialOutcome`
- Latent payment, response, or friction propensities
- Future payment events or counterfactual outcomes

Key observable inputs:
- `failure_code` (`AUTHENTICATION_FAILED`, `INSUFFICIENT_FUNDS`, `CARD_EXPIRED`, `GATEWAY_DOWNTIME`, etc.)
- `residual_amount` / `amount_due`
- `automated_action_count` (0, 1, 2, ...)
- `hours_since_failure` and `last_action_hours_ago`
- `active_promise_status` (`PROMISE_ACCEPTED`, `PROMISE_DUE`, etc.)
- `customer_opt_out`
- `payment_status`

---

## 3. Decision Logic & Rules Hierarchy

### A. Hard Safety & Stopping Rules
1. **Opt-Out**: If `customer_opt_out == True` $\to$ `STOP`.
2. **Already Paid**: If `payment_status == CAPTURED` or `current_state == RECOVERED` $\to$ `STOP`.
3. **Action Limits**: If `automated_action_count >= 3` $\to$ `STOP`.
4. **Recovery Window**: If `hours_since_failure > 720h` (30 days) $\to$ `STOP`.
5. **Active Cooldown**: If `last_action_hours_ago < 12h` $\to$ `STOP` (wait for response).
6. **Active Promise**: If a Promise-to-Pay is active (`PROMISE_ACCEPTED` or `PROMISE_DUE`) $\to$ `STOP` (respect customer commitment window).

### B. Action Eligibility & Symmetry
- `PROMISE_TO_PAY`: Eligible when no active promise exists and `residual_amount >= ₹250`.
- `PAYMENT_LINK`: Eligible for fresh checkout sessions.
- `REMINDER`: Eligible for soft nudge retries.
- `ESCALATE`: Eligible only when `residual_amount >= ₹1500` (justifying ₹100 human support cost).

### C. Contextual Selection Rules
- **`CARD_EXPIRED`**: Selects `PAYMENT_LINK` (cannot retry expired instrument).
- **`INSUFFICIENT_FUNDS`**: Selects `PROMISE_TO_PAY` (enables deferred settlement without customer friction).
- **High-Value Stuck Cases**: If `residual_amount >= ₹1500` and `automated_action_count >= 2`, selects `ESCALATE`.
- **Transient Failures (`GATEWAY_DOWNTIME`, `NETWORK_TIMEOUT`)**:
  - 1st attempt: `REMINDER`.
  - 2nd attempt: `PAYMENT_LINK`.
- **Engagement Drop (`AUTHENTICATION_FAILED`, `USER_DROPPED`)**:
  - 1st attempt: `REMINDER`.
  - 2nd attempt: `PAYMENT_LINK`.
  - 3rd attempt: `PROMISE_TO_PAY` (if eligible) or `STOP`.

---

## 4. Economic Constraints (Simulation Constants)
- `REMINDER`: ₹2
- `PAYMENT_LINK`: ₹3
- `PROMISE_TO_PAY`: ₹5
- `ESCALATE`: ₹100
- Friction Cost: ₹5 per prior automated outreach (capped at ₹25)

---

## 5. Versioning and Checksum
- **Policy Version**: `baseline-v1`
- **Config Checksum**: Deterministic SHA-256 computed dynamically via `config.get_checksum()`.
- Every decision produces a structured `BaselineDecisionExplanation` containing rule trigger audit logs without LLM invocation.

---

## 6. Known Limitations
- Does not learn individual-level elasticity or causal uplift $\tau(x)$.
- Cannot differentiate between a high-intent customer who would pay naturally in 4 hours vs a customer requiring an intervention. (This is the specific opportunity RecoverIQ's incremental estimator addresses).

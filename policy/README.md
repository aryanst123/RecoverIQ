# RecoverIQ Adaptive Decision Engine (`recoveriq-v1`)

## 1. Decision Flow & Architecture
The adaptive decision engine selects revenue recovery interventions dynamically based on causal net expected value:

```
Observable State (ObservableCaseState)
      ↓
Feature Pipeline (28 Observable Features)
      ↓
T-Learner ML Model (P(Y=1|a, X) vs P(Y=1|control, X))
      ↓
Incremental Causal Uplift tau(a, X)
      ↓
Economic Objective Calculation (E[Net] = tau * Amount - Cost - Friction)
      ↓
Eligibility & Minimum Threshold Check (E[Revenue] >= INR 250)
      ↓
Policy Confidence Evaluation (Confidence >= 0.60)
      ↓
Argmax Net Expected Recovery Selection (or STOP)
      ↓
Execution Authorization via Safety Guard & Lock Manager
```

---

## 2. Economic Optimization Objective
For each candidate action $a \in \{\text{REMINDER}, \text{PAYMENT\_LINK}, \text{PROMISE\_TO\_PAY}, \text{ESCALATE}, \text{STOP}\}$:

$$\tau(a, X) = P(Y=1 \mid A=a, X) - P(Y=1 \mid A=\text{control}, X)$$

$$\mathbb{E}[\Delta \text{Revenue}(a)] = \tau(a, X) \times \text{residual\_amount}$$

$$\mathbb{E}[\Delta \text{Net}(a)] = \mathbb{E}[\Delta \text{Revenue}(a)] - \text{ActionCost}(a) - \text{FrictionCost}(a)$$

### Action Costs
- `STOP`: ₹0.0
- `REMINDER`: ₹2.0
- `PAYMENT_LINK`: ₹3.0
- `PROMISE_TO_PAY`: ₹5.0
- `ESCALATE`: ₹100.0

### Friction Cost
$$\text{FrictionCost} = \min(\text{automated\_action\_count} \times ₹5.0, ₹25.0)$$

### The Zero-Intervention Alternative (`STOP`)
For `STOP`:
$$\tau = 0.0, \quad \mathbb{E}[\Delta \text{Revenue}] = ₹0.0, \quad \text{Cost} = ₹0.0, \quad \mathbb{E}[\Delta \text{Net}] = ₹0.0$$
If all candidate interventions produce $\mathbb{E}[\Delta \text{Net}] \le 0.0$, `STOP` wins! RecoverIQ will never execute a value-destroying action.

---

## 3. Minimum Expected Incremental Recovery Threshold
- **Threshold**: ₹250.0
- **Rule**: If $\mathbb{E}[\Delta \text{Revenue}(a)] < ₹250.0$, action $a$ is marked ineligible for autonomous execution. This prevents spending outreach capital on micro-uplifts with high risk of touchpoint fatigue.

---

## 4. Policy Confidence & Low-Confidence Fallback
- **Threshold**: 0.60
- **Formula**: Weighted composite of action training support (40%), probability margin from 50/50 noise (30%), and domain validity (30%).
- **Fallback**: If the top candidate action has `confidence < 0.60`:
  - High-value stuck cases ($\ge ₹1,500$) route to `ESCALATE` for human handling.
  - All other cases route conservatively to `STOP`.

---

## 5. Sequential Adaptation & Promise-to-Pay (P2P)
- Decisions are evaluated sequentially at each eligible touchpoint rather than committing to a pre-planned ladder.
- If a case has an active promise (`PROMISE_ACCEPTED` or `PROMISE_DUE`), the system pauses interventions and waits for the customer to fulfill or miss their commitment.
- If a promise is missed, the case returns to `ACTION_EVALUATION` and is re-scored with updated observable state.

---

## 6. Versioning & Provenance
- **Policy Version**: `recoveriq-v1`
- **Policy Checksum**: Deterministically derived from version string, cost dictionary, threshold values, and confidence cutoffs.
- **Decision Trace**: Every decision produces a structured `DecisionTrace` with candidate evaluations, rejection reasons, and confidence metrics.

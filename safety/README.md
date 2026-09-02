# RecoverIQ — Execution Safety & Invariants Architecture

## 1. Core Architecture & Execution Lifecycle
RecoverIQ decouples algorithmic recommendation from financial execution. An autonomous policy decision is **never** authorization for external execution.

The strict execution pipeline is:
```
POLICY DECIDES
      ↓
LIVE PAYMENT RECONCILIATION
      ↓
SAFETY GUARDS & INVARIANT CHECKS
      ↓
IDEMPOTENCY VERIFICATION
      ↓
ATOMIC ACTION RESERVATION (ACTION_RESERVED)
      ↓
EXECUTION ATTEMPT (ACTION_EXECUTING)
      ↓
OUTCOME CONFIRMATION OR TIMEOUT RECONCILIATION
      ↓
STATE RECONCILIATION & AUDIT LOG
```

---

## 2. Concurrency Control & Case Locking
- **Lock Manager**: `CaseLockManager` provides re-entrant mutual exclusion per `case_id`.
- **Race Condition Prevention**: Prevents concurrent worker threads or parallel event handlers from executing simultaneous interventions for the same payment recovery case.

---

## 3. Merchant-Side Idempotency
- **Stable Token Generation**: Keys follow `{case_id}:{action_type}:{action_sequence}` with SHA-256 digest prefixes.
- **Deduplication Guarantee**: Re-submitting an identical logical intervention returns the cached execution result and prevents duplicate messages/links.

---

## 4. Atomic Action Reservation Model
- **State**: `ACTION_RESERVED`
- **TTL**: Configurable expiration (default 60 seconds).
- **Invariants**:
  - No action executes without an active reservation.
  - Expired or cancelled reservations cannot proceed to execution.

---

## 5. Ambiguous Execution & `EXECUTION_UNKNOWN`
If downstream API communication times out or produces an ambiguous response:
1. State transitions to `EXECUTION_UNKNOWN`.
2. The system **never** retries blindly.
3. State is reconciled downstream. If unresolvable, case transitions to `MANUAL_REVIEW_REQUIRED` with terminal reason `EXECUTION_TIMEOUT_UNRESOLVED` or `ESCALATION_FAILURE`.

---

## 6. Webhook Security & Ingestion
- **HMAC-SHA256**: Signatures computed over the raw incoming request body using constant-time comparison (`hmac.compare_digest`).
- **Deduplication**: Driven by `x-razorpay-event-id`. Duplicates are recorded in the audit trail (`duplicate_detected = True`) without re-executing business effects.
- **Out-of-Order Events**: Payments in `CAPTURED` state reject stale `payment.failed` webhooks to prevent state regression.

---

## 7. The 10 Machine-Checkable Safety Invariants
1. **Invariant 1**: No automated action after terminal recovery / captured payment.
2. **Invariant 2**: No execution without reservation.
3. **Invariant 3**: No duplicate logical execution.
4. **Invariant 4**: No action after customer opt-out.
5. **Invariant 5**: No action beyond maximum automated actions ($\le 3$).
6. **Invariant 6**: No action outside recovery window ($\le 720\text{h}$).
7. **Invariant 7**: Ambiguous execution cannot automatically become successful without reconciliation.
8. **Invariant 8**: Duplicate webhook cannot create duplicate business effects.
9. **Invariant 9**: Out-of-order events cannot regress terminal payment state.
10. **Invariant 10**: Every executed action has an immutable structured audit record.

---

## 8. Failure Injection Scenarios (F1 - F13)
- `F1`: Invalid Webhook Signature
- `F2`: Duplicate Webhook
- `F3`: Out-of-Order Webhook Event
- `F4`: Stale Payment State
- `F5`: Concurrent Action Requests (Lock Contention)
- `F6`: Execution Timeout
- `F7`: Ambiguous Execution State
- `F8`: Duplicate Execution Request
- `F9`: Payment Recovered Immediately Before Execution
- `F10`: Customer Opt-Out Immediately Before Execution
- `F11`: Action Limit Exceeded Ceiling
- `F12`: Recovery Window Expired
- `F13`: Human Escalation Routing Failure

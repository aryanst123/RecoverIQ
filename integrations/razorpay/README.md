# Razorpay Test-Mode Integration Adapters (Phase 8)

## Overview
RecoverIQ Phase 8 connects the already-validated RecoverIQ economic recovery engine to **Razorpay TEST MODE** through secure, bounded, and auditable integration adapters.

**STRICT BOUNDARY: TEST MODE ONLY.**
Production execution is strictly forbidden. The system will fail closed if production credentials (`rzp_live_*`) or ambiguous environment configurations are detected.

---

## Architecture Flow

```
Razorpay Test Mode
        ↓
Webhook Adapter (integrations/razorpay/webhooks.py)
        ↓
HMAC-SHA256 Signature Verification (Constant-Time)
        ↓
Event Normalization (integrations/razorpay/events.py)
        ↓
Deduplication & State Machines (ingestion/deduplication.py)
        ↓
Live Reconciliation (integrations/razorpay/reconciliation.py)
        ↓
RecoverIQ Adaptive Policy (policy/adaptive.py)
        ↓
Safety Invariant Guards & Locks (safety/guards.py)
        ↓
Bounded Executor (execution/executor.py)
        ↓
Razorpay Test-Mode Adapter (integrations/razorpay/payment_links.py)
        ↓
Reconciliation & Outcome Recording
```

---

## Key Guarantees

### 1. Webhook Authentication
- Validates HMAC-SHA256 signatures over raw request body bytes using `hmac.compare_digest`.
- Verification occurs before parsing JSON or invoking business logic.
- Rejects missing, invalid, or tampered signatures with `WebhookVerificationError`.

### 2. Event Normalization
- Converts raw webhook dictionaries into `NormalizedPaymentEvent`.
- Amounts in paise are converted to INR (`amount_paise / 100.0`).
- Failure reasons mapped to bounded `FailureCode` enums (`INSUFFICIENT_FUNDS`, `CARD_EXPIRED`, etc.).
- Raw payloads are audited via SHA-256 hash digests.

### 3. Deduplication & Out-of-Order Safety
- Deduplication key: `x-razorpay-event-id`.
- Duplicate webhooks return cached outcomes without creating duplicate cases or actions.
- Out-of-order events cannot regress a terminal state (`RECOVERED`, `STOPPED`).

### 4. Amount Integrity
- Payment link amounts are derived strictly from internal `RecoveryCase.residual_amount`.
- LLM outputs, customer messages, and webhook free-form text have zero influence over financial amounts.

### 5. Idempotency & Ambiguous Handling
- Payment Link requests pass a deterministic `reference_id` (`riq_{case_id}_{action_count}`).
- Network timeouts transition the action to `EXECUTION_UNKNOWN`, triggering live reconciliation rather than blind duplicate link creations.

---

## Configuration & Environment Variables

| Variable | Required | Description | Example |
| :--- | :--- | :--- | :--- |
| `RAZORPAY_ENVIRONMENT` | Yes | Must be strictly `test` | `test` |
| `RAZORPAY_KEY_ID` | Optional* | Test key (must start with `rzp_test_`) | `rzp_test_12345` |
| `RAZORPAY_KEY_SECRET` | Optional* | Test key secret | `<secret>` |
| `RAZORPAY_WEBHOOK_SECRET` | Optional* | Secret for webhook HMAC verification | `<secret>` |

*\* Optional for offline mock tests; required for live test-mode smoke testing.*

---

## Limitations

1. **Test-Mode Environment Only**: Bounded to Razorpay Sandbox/Test mode.
2. **Partial-Payment Semantics**: When partial payment is unsupported or residual amount is below threshold, the system enforces full payment links.
3. **External SMS/WhatsApp Channels**: Reminders require an external communication provider (e.g. Twilio/Gupshup) and are not natively emitted by Razorpay payment links without customer notification flags.

---

## WHAT THIS DOES NOT PROVE
- **Does NOT prove production readiness**: Real-world production requires hardened distributed locking, secrets management (e.g. AWS Secrets Manager/Vault), and rate-limit circuit breakers.
- **Does NOT prove production-scale throughput**: Tested under synchronous and sequential simulated workloads.
- **Does NOT prove actual merchant revenue recovery**: Simulator and test-mode synthetic events are proxies for evaluation.
- **Does NOT prove real customer conversion**: Customer willingness to pay on test links does not reflect production consumer psychology.
- **Does NOT prove Razorpay internal economics**: Gateway fee schedules and merchant MDR vary by contractual tier.
- **Does NOT prove production compliance certification**: PCI-DSS and RBI compliance require comprehensive external penetration and vulnerability audits.

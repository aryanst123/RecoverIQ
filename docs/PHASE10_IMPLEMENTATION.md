# PHASE 10 IMPLEMENTATION PLAN
## RecoverIQ — Demo Frontend & Razorpay Test-Mode Integration

**Project**: RecoverIQ (Track 03: AI Revenue Recovery — Razorpay AI Buildathon 2026)
**Status**: ACTIVE IMPLEMENTATION
**Author**: Principal Frontend & Full-Stack Systems Lead

---

### 1. CURRENT REPOSITORY ARCHITECTURE AUDIT

#### Backend & Core Domain:
- **Language/Framework**: Python 3.11, Pydantic v2, scikit-learn, NumPy, SciPy, FastAPI, Uvicorn.
- **Decision Engine**: `policy/adaptive.py` (`RecoverIQAdaptivePolicy`) evaluating causal uplift $\tau(a, X) \cdot \text{Amount} - \text{Costs}$ with low-confidence escalation and structured decision tracing.
- **Baseline**: `baseline/policy.py` (`DeterministicBaselinePolicy`, `baseline-v1`).
- **ML Pipeline**: `models/` calibrated T-Learner uplift models (`incremental-model-v1`).
- **Bounded Execution**: `execution/` with per-case mutual exclusion locking (`CaseLockManager`), atomic action reservation (`ActionReservationService`), and merchant idempotency (`MerchantIdempotencyService`).
- **Reconciliation**: `reconciliation/` with monotonic state machine guarantees and terminal state protection.
- **LLM Boundary**: `llm/` with Pydantic extraction schema (`RecoveryContextExtraction`), prompt templates (`p2p-prompt-v1`), relative date normalization, and prompt injection immunity.
- **Razorpay Integration**: `integrations/razorpay/` with constant-time HMAC-SHA256 signature verification, event normalization (`NormalizedPaymentEvent`), paise-to-INR conversion, `MockRazorpayGateway` & `RazorpayTestClient`, Payment Link creation with idempotency, and pre-execution live reconciliation.
- **Frozen Results**: `results/final/` containing `financial_benchmark.json`, `bootstrap_results.json`, `attribution_sensitivity.json`, `oracle_diagnostic.json`, `heterogeneity.json`, `llm_comparison.json`, `llm_extraction_evaluation.json`, `safety_audit.json`, and `reproducibility.json`.

---

### 2. FRONTEND ARCHITECTURE

- **Framework**: Vite + React 18/19 with TypeScript.
- **Styling**: Tailwind CSS + Custom Design System Tokens (enterprise financial dark/light mode).
- **Brand Identity**: Razorpay-inspired geometric design DNA, official Razorpay SVG logo asset, subtle Razorpay red accent (`#0C2340` / `#02040A` surfaces, `#3395FF` / `#0C2340` accents, `#072654` primary, `#EF4444` / `#53B483` semantic status chips).
- **Icons**: Lucide React (`lucide-react`).
- **Visualizations**: Recharts for responsive, accessible financial benchmark bar charts, action distributions, and sensitivity analysis.
- **State Management**: TanStack React Query / SWR for server state synchronization and real-time polling; localized state for UI filters and theme.
- **Theme**: Centralized `ThemeContext` with Light / Dark modes and `localStorage` persistence.

---

### 3. BACKEND API PLAN (`server.py`)

A FastAPI service running on port 8000 serving clean, typed REST endpoints:

| Endpoint | Method | Purpose | Source of Truth |
| :--- | :--- | :--- | :--- |
| `/api/health` | GET | Server health, environment (`test` / `offline`), version metadata | System |
| `/api/dashboard/kpis` | GET | Live/demo KPI summary cards | Backend state / Simulator |
| `/api/cases` | GET | List recovery cases with filters (state, segment, failure) | SQLite / In-Memory Store |
| `/api/cases/{case_id}` | GET | Full case workspace, timeline, attempts, customer context | Domain models |
| `/api/cases/{case_id}/decision` | POST | Evaluate RecoverIQ decision & return `DecisionTrace` | `policy/adaptive.py` |
| `/api/cases/{case_id}/execute` | POST | Execute policy decision with lock, reservation, and adapter | `execution/executor.py` |
| `/api/cases/{case_id}/audit` | GET | Retrieve immutable audit records for case | `safety/audit_logger.py` |
| `/api/promise-to-pay/extract` | POST | Extract structured context & dates from raw customer message | `llm/extractor.py` |
| `/api/evaluation/benchmark` | GET | Frozen 20,000-case holdout benchmark results & 95% CIs | `results/final/financial_benchmark.json` |
| `/api/evaluation/oracle` | GET | Corrected simulator-only oracle diagnostic | `results/final/oracle_diagnostic.json` |
| `/api/evaluation/attribution` | GET | Attribution sensitivity (24h, 72h, 168h) | `results/final/attribution_sensitivity.json` |
| `/api/evaluation/llm` | GET | LLM controlled ablation & synthetic NLP metrics | `results/final/llm_comparison.json` |
| `/api/evaluation/heterogeneity`| GET | Segment, amount, and failure code breakdowns | `results/final/heterogeneity.json` |
| `/api/safety/status` | GET | Invariants 1–10 status & audit summary | `results/final/safety_audit.json` |
| `/api/safety/failure-injection`| POST | Execute live failure injections (F1–F13) and return trace | `safety/` failure suite |
| `/api/razorpay/status` | GET | Check Test Mode connectivity & credential validity | `integrations/razorpay/config.py` |
| `/api/razorpay/payment-links` | POST | Create Test Mode Payment Link for a case | `integrations/razorpay/payment_links.py` |
| `/api/webhooks/razorpay` | POST | Ingest raw webhook with HMAC verification & deduplication | `integrations/razorpay/webhooks.py` |

---

### 4. RAZORPAY TEST MODE INTEGRATION PLAN

```
┌────────────────────────────────────────────────────────┐
│                   React Frontend UI                    │
└──────────────────────────┬─────────────────────────────┘
                           │ (HTTP REST / JSON)
┌──────────────────────────▼─────────────────────────────┐
│                 FastAPI Backend Service                │
│    (Server-Side Only: Never Exposes Secrets to Client) │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
┌─────────────▼─────────────┐┌─────────────▼─────────────┐
│    RecoverIQ Core Engine   ││ Razorpay Test Integration │
│ (Policy, Safety, Locking, ││ (HMAC Verifier, Events,   │
│  Reservation, Domain State││  Payment Link Adapter)    │
└───────────────────────────┘└─────────────┬─────────────┘
                                           │ (Paise conversion, reference_id)
                             ┌─────────────▼─────────────┐
                             │    Razorpay Test Mode     │
                             │  (api.razorpay.com/v1     │
                             │   or Mock Gateway)        │
                             └───────────────────────────┘
```

1. **Test-Mode Enforced**: `RAZORPAY_ENVIRONMENT=test` verified on startup. Production credentials (`rzp_live_*`) fail closed.
2. **Offline Resilience**: If live credentials are not present in `.env`, system gracefully runs with `MockRazorpayGateway` labeled `TEST MODE (OFFLINE / MOCK)`.
3. **Payment Link Generation**: Triggered exclusively from trusted internal residual amount.
4. **Webhook Processing**: Raw body HMAC-SHA256 signature verification via `hmac.compare_digest` before any JSON parsing. Event deduplication via `x-razorpay-event-id`. Monotonic terminal state updates.

---

### 5. FRONTEND ROUTES & PAGES

1. `/` (**Overview Dashboard**): Live KPI cards, Failed Payments Queue preview, Frozen 20k Benchmark comparison card, System Status badge (`TEST MODE`).
2. `/cases` (**Recovery Cases Queue**): Filterable table of payment failure cases (Status, Failure Code, Amount, Customer Segment, Action).
3. `/cases/:caseId` (**Case Workspace & Decision Inspector**): Full customer context, payment failure breakdown, structured economic decision trace, candidate actions comparison, live Razorpay Payment Link creation, timeline, and audit logs.
4. `/promise-to-pay` (**Promise-to-Pay Intelligence**): Interactive customer communication analyzer, LLM context extractor, date resolver, and policy pause effect visualizer.
5. `/evaluation` (**Evaluation & Benchmark Lab**): Interactive visualization of frozen 20k holdout, bootstrap 95% CIs, honest negative baseline delta, unmutated oracle diagnostic, attribution sensitivity, and LLM ablation.
6. `/safety` (**Safety & Failure Injection Sandbox**): Invariants 1–10 monitor, interactive failure injection buttons (duplicate webhook, timeout, out-of-order, pre-outreach capture, customer opt-out), and execution state machine visualizer.
7. `/architecture` (**System Architecture**): Interactive architectural flow diagram from webhook observation to bounded execution.

---

### 6. IMPLEMENTATION ORDER & GATES

- **PHASE 10A**: Repository audit & architecture verification (COMPLETE).
- **PHASE 10B**: FastAPI backend server (`server.py`) implementation and API data contracts.
- **PHASE 10C**: Razorpay Test-Mode backend verification and end-to-end integration tests.
- **PHASE 10D**: Vite + React + TypeScript + Tailwind application scaffold in `frontend/`.
- **PHASE 10E**: Theme system (Dark Mode with Razorpay visual DNA + Enterprise Light Mode) and brand assets.
- **PHASE 10F**: Overview Dashboard with live KPIs and frozen benchmark cards.
- **PHASE 10G**: Recovery Cases queue with sorting, filtering, and search.
- **PHASE 10H**: Case Detail workspace and Decision Inspector.
- **PHASE 10I**: Promise-to-Pay extraction workspace.
- **PHASE 10J**: Scientific Evaluation & Benchmark Lab.
- **PHASE 10K**: Safety & Failure Injection interactive sandbox.
- **PHASE 10L**: Live Razorpay Payment Link & Webhook demo flow.
- **PHASE 10M**: Responsive layout & visual QA.
- **PHASE 10N**: Full regression testing & verification.
- **PHASE 10O**: Demo script (`DEMO_SCRIPT.md`) and documentation (`PHASE10_FRONTEND.md`).

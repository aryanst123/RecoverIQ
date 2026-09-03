# Phase 10 — RecoverIQ Demo Frontend & Razorpay Test-Mode Integration
**Project:** RecoverIQ
**Track:** Track 03: AI Revenue Recovery — Razorpay AI Buildathon 2026
**Status:** COMPLETED & PRODUCTION-READY

---

## 1. Executive Summary

Phase 10 delivers a serious, enterprise-grade revenue recovery operations console and full-stack application for **RecoverIQ**. Built using modern React 18, Vite, TypeScript, Tailwind CSS, Lucide Icons, Recharts, and a FastAPI backend (`server.py`), the interface showcases the complete end-to-end lifecycle of failed payment recovery, causal decisioning, schema-bounded LLM extraction, Razorpay Test Mode integration, and unmanipulated scientific benchmark evidence.

---

## 2. Key Architecture & Design Highlights

1. **Brand Identity & Dual Themes**:
   - Built with official Razorpay visual DNA: deep slate/navy surfaces (`#0C2340`, `#02040A`), subtle Razorpay blue accents (`#3395FF`), and the official Razorpay geometric logo asset.
   - High-contrast **Enterprise Dark Mode** and crisp **Light Mode** with `localStorage` persistence.

2. **Epistemic Integrity & Badging**:
   - Strict visual and data separation between:
     - `FROZEN BENCHMARK`: Read-only, machine-readable results from the Phase 9 holdout (Seed: 999888777).
     - `RAZORPAY TEST MODE`: Live test sandbox adapter (`rzp_test_*` credentials fail closed on live keys).
     - `SIMULATOR / DEMO`: Synthetic test cases and failure injection matrix.

3. **Complete Navigation & Screen Matrix**:
   - **Dashboard Overview (`/`)**: Live revenue at risk, net recovery rate, safety invariant health, 3-arm benchmark snapshot, and recent failed payments queue.
   - **Recovery Cases Queue (`/cases`)**: Filterable, searchable queue across payment states, failure codes, customer segments, and confidence scores.
   - **Case Detail Workspace (`/cases/:caseId`)**: Deep-dive operational console featuring:
     - Full payment & customer history
     - Causal candidate action economics table ($E[\text{Net}] = \tau \cdot \text{Amount} - \text{Costs}$)
     - Live Razorpay Test Payment Link generator (`https://rzp.io/i/...`)
     - Simulated customer payment / inbound webhook trigger
     - Immutable cryptographically verified case audit ledger
   - **Promise-to-Pay Lab (`/promise-to-pay`)**: Natural language communication extraction playground with Pydantic v2 strict validation, relative date normalization, prompt injection defense, and downstream outreach pause enforcement.
   - **Scientific Evaluation Lab (`/evaluation`)**: Interactive Recharts visualization of the 20,000-case frozen holdout, honest negative baseline delta, unmutated counterfactual oracle diagnostic (23.8% agreement, ₹702.46 regret), 24h/72h/168h attribution window sensitivity, and LLM ablation.
   - **Safety & Failure Sandbox (`/safety`)**: Monitor for 10/10 active safety invariants and an interactive matrix to inject and observe failure scenarios F1–F13.
   - **System Architecture (`/architecture`)**: End-to-end interactive visual pipeline diagram.

---

## 3. Backend REST & Webhook Contract (`server.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Health check, test mode status, and model provenance |
| `/api/dashboard/kpis` | GET | Aggregated revenue at risk, recovered amount, and recovery rate |
| `/api/cases` | GET | Filterable, paginated recovery cases queue |
| `/api/cases/{case_id}` | GET | Full case workspace, observable state, candidate action economics, audit logs |
| `/api/cases/{case_id}/decision` | POST | Evaluates policy decision on case |
| `/api/cases/{case_id}/execute` | POST | Acquires case lock, atomic reservation, and creates Razorpay payment link |
| `/api/promise-to-pay/extract` | POST | Pydantic v2 schema-bounded LLM context extraction |
| `/api/evaluation/benchmark` | GET | Phase 9 frozen 20,000-case holdout 3-arm benchmark |
| `/api/evaluation/oracle` | GET | Pristine unmutated counterfactual oracle diagnostic |
| `/api/evaluation/attribution` | GET | Attribution sensitivity (24h, 72h, 168h windows) |
| `/api/evaluation/llm` | GET | LLM controlled ablation comparison |
| `/api/safety/status` | GET | 10/10 safety invariant verification |
| `/api/safety/failure-injection` | POST | Interactive failure injection test (F1–F13) |
| `/api/razorpay/status` | GET | Razorpay adapter configuration status |
| `/api/webhooks/razorpay` | POST | Authenticated webhook ingestion with HMAC SHA-256 and deduplication |

---

## 4. Verification & Testing

- **Backend Unit Tests**: 111 / 111 passing (`pytest tests/ -q`).
- **Frontend Compilation**: TypeScript compilation (`tsc`) and Vite production bundle generated without errors (`frontend/dist/`).
- **Full-Stack Execution**: FastAPI serves both static SPA bundle and REST endpoints at `http://127.0.0.1:8000/`.

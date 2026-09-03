import React from 'react';
import {
  Network,
  ShieldCheck,
  Cpu,
  Sparkles,
  Link,
  Layers,
  ArrowRight,
  CheckCircle2,
  Lock,
  Database,
  Radio,
  FileCheck,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';

export const Architecture: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
          System Architecture & Data Flow
          <Badge variant="primary">END-TO-END PIPELINE</Badge>
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Architectural blueprint of RecoverIQ: Bounded execution, causal uplift decisioning, LLM schema boundary, and Razorpay integration.
        </p>
      </div>

      {/* Main Flow Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {/* Step 1: Ingestion & Safety Invariant Layer */}
        <Card
          title="1. Ingestion & Invariant Layer"
          subtitle="Authentication, Deduplication, and Locking"
          badge={<Badge variant="default">EDGE</Badge>}
        >
          <div className="space-y-3 text-xs">
            <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 font-mono text-[11px] space-y-1">
              <div className="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-blue-500" />
                HMAC-SHA256 Webhook Auth
              </div>
              <div className="text-[10px] text-slate-500">
                Verifies Razorpay signature header against webhook secret before deserialization.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 font-mono text-[11px] space-y-1">
              <div className="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-emerald-500" />
                Event Deduplication Store
              </div>
              <div className="text-[10px] text-slate-500">
                Atomic in-memory dedup store keys on x-razorpay-event-id to prevent replay attacks.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 font-mono text-[11px] space-y-1">
              <div className="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-indigo-500" />
                Case Mutual Exclusion Lock
              </div>
              <div className="text-[10px] text-slate-500">
                Guarantees single-process execution per case ID to eliminate race conditions.
              </div>
            </div>
          </div>
        </Card>

        {/* Step 2: Causal ML Decision Engine */}
        <Card
          title="2. Causal Uplift ML Engine"
          subtitle="Incremental Revenue Optimization"
          badge={<Badge variant="primary">AI BRAIN</Badge>}
        >
          <div className="space-y-3 text-xs">
            <div className="p-2.5 rounded-lg border border-blue-200 dark:border-blue-900/60 bg-blue-50/40 dark:bg-blue-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-blue-500" />
                Treatment Potential Outcomes
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                Calculates P(Y | a, x) vs Control P(Y | a_0, x) across all candidate actions.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-blue-200 dark:border-blue-900/60 bg-blue-50/40 dark:bg-blue-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
                <Radio className="w-3.5 h-3.5 text-blue-500" />
                Causal Uplift $\tau(x)$
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                &tau;(a, x) = P(Y | a, x) - P(Y | control, x) preserves negative uplift.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-blue-200 dark:border-blue-900/60 bg-blue-50/40 dark:bg-blue-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-blue-500" />
                Expected Net Optimization
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                E[Net] = &tau; &middot; Amount - Action Cost - Friction Cost.
              </div>
            </div>
          </div>
        </Card>

        {/* Step 3: LLM Reasoning Boundary */}
        <Card
          title="3. LLM Schema Boundary"
          subtitle="Non-Execution Context Extraction"
          badge={<Badge variant="simulator">BOUNDED NLP</Badge>}
        >
          <div className="space-y-3 text-xs">
            <div className="p-2.5 rounded-lg border border-purple-200 dark:border-purple-900/60 bg-purple-50/40 dark:bg-purple-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                Pydantic v2 Schema
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                Strict frozen model with extra='forbid' guarantees zero unexpected parameters.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-purple-200 dark:border-purple-900/60 bg-purple-50/40 dark:bg-purple-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
                <FileCheck className="w-3.5 h-3.5 text-purple-500" />
                Deterministic Fallback
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                If NLP fails or times out, safely falls back to standard structured features.
              </div>
            </div>

            <div className="p-2.5 rounded-lg border border-purple-200 dark:border-purple-900/60 bg-purple-50/40 dark:bg-purple-950/20 font-mono text-[11px] space-y-1">
              <div className="font-bold text-purple-700 dark:text-purple-300 flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-purple-500" />
                Zero Execution Authority
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                LLM cannot trigger payments, alter amounts, or declare payments recovered.
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Integration & Reconciliation Banner */}
      <Card
        title="Razorpay Test-Mode Adapter & Reconciliation Flow"
        subtitle="Monotonic state machine transitions and audit guarantees"
      >
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 space-y-3 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-center">
            <div className="p-3 rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <div className="font-mono text-slate-400 text-[10px] uppercase">1. Failure Ingest</div>
              <div className="font-bold text-slate-900 dark:text-white mt-1">payment.failed</div>
              <div className="text-[10px] text-slate-500 mt-0.5">Normalized FailureCode</div>
            </div>

            <div className="p-3 rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <div className="font-mono text-slate-400 text-[10px] uppercase">2. Bounded Action</div>
              <div className="font-bold text-blue-500 mt-1">Atomic Reservation</div>
              <div className="text-[10px] text-slate-500 mt-0.5">Payment Link API (v1)</div>
            </div>

            <div className="p-3 rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <div className="font-mono text-slate-400 text-[10px] uppercase">3. Customer Touch</div>
              <div className="font-bold text-emerald-500 mt-1">Short URL Delivery</div>
              <div className="text-[10px] text-slate-500 mt-0.5">WhatsApp / SMS Channel</div>
            </div>

            <div className="p-3 rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
              <div className="font-mono text-slate-400 text-[10px] uppercase">4. Reconcile</div>
              <div className="font-bold text-slate-900 dark:text-white mt-1">payment.captured</div>
              <div className="text-[10px] text-slate-500 mt-0.5">Terminal State RECOVERED</div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};

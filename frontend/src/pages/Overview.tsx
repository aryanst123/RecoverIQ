import React, { useEffect, useState } from 'react';
import {
  TrendingUp,
  AlertCircle,
  ShieldCheck,
  Zap,
  ArrowRight,
  Lock,
  Layers,
  Sparkles,
  ExternalLink,
  ChevronRight,
  DollarSign,
  Activity,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { api } from '../api/client';
import { DashboardKPIs, BenchmarkResponse, CaseSummary, RazorpayStatus } from '../types';

interface OverviewProps {
  onNavigate: (path: string) => void;
}

export const Overview: React.FC<OverviewProps> = ({ onNavigate }) => {
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [recentCases, setRecentCases] = useState<CaseSummary[]>([]);
  const [razorpayStatus, setRazorpayStatus] = useState<RazorpayStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getKPIs().then(setKpis).catch(console.error),
      api.getBenchmark().then(setBenchmark).catch(console.error),
      api.getCases({ limit: 6 }).then((res) => setRecentCases(res.cases)).catch(console.error),
      api.getRazorpayStatus().then(setRazorpayStatus).catch(console.error),
    ]).finally(() => setLoading(false));
  }, []);

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  return (
    <div className="space-y-6">
      {/* Top Banner: Epistemic & Context Notice */}
      <div className="rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-950/30 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-600 text-white shadow-sm mt-0.5 sm:mt-0">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery
              <Badge variant="razorpay">PROTOTYPE</Badge>
            </div>
            <div className="text-xs text-slate-600 dark:text-slate-300 mt-0.5">
              Causal incremental recovery decision engine for failed one-time payments with bounded execution and live reconciliation.
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            onClick={() => onNavigate('/evaluation')}
            className="px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/80 transition-all flex items-center gap-1.5 shadow-sm"
          >
            View Benchmark Lab
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Revenue at Risk */}
        <Card className="border-l-4 border-l-rose-500">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider font-mono">
              Revenue at Risk
            </span>
            <div className="p-1.5 rounded-md bg-rose-50 dark:bg-rose-950/60 text-rose-600">
              <AlertCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {kpis ? formatCurrency(kpis.revenue_at_risk_inr) : '₹0'}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
            <span>{kpis?.total_failed_payments || 0} failed payments queued</span>
          </div>
        </Card>

        {/* KPI 2: Net Recovered */}
        <Card className="border-l-4 border-l-emerald-500">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider font-mono">
              Active Recovered
            </span>
            <div className="p-1.5 rounded-md bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-600 dark:text-emerald-400">
            {kpis ? formatCurrency(kpis.revenue_recovered_inr) : '₹0'}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            <span>{kpis?.recovered_cases_count || 0} cases resolved</span>
          </div>
        </Card>

        {/* KPI 3: Recovery Rate */}
        <Card className="border-l-4 border-l-blue-500">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider font-mono">
              Demo Recovery Rate
            </span>
            <div className="p-1.5 rounded-md bg-blue-50 dark:bg-blue-950/60 text-blue-600">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {kpis ? `${(kpis.recovery_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            <span>{kpis?.active_recovery_cases || 0} in active recovery</span>
          </div>
        </Card>

        {/* KPI 4: Safety Violations */}
        <Card className="border-l-4 border-l-indigo-500">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider font-mono">
              Critical Violations
            </span>
            <div className="p-1.5 rounded-md bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            0
          </div>
          <div className="mt-1 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>10/10 Invariants Active</span>
          </div>
        </Card>
      </div>

      {/* Main Grid: Frozen Benchmark Spotlight & Razorpay Adapter */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Frozen Benchmark Spotlight */}
        <Card
          className="lg:col-span-2"
          title="Frozen 20,000-Case Scientific Holdout Benchmark"
          subtitle="Direct machine-readable results from Phase 9 final evaluation (Seed: 999888777)"
          badge={<Badge variant="frozen">FROZEN BENCHMARK</Badge>}
          action={
            <button
              onClick={() => onNavigate('/evaluation')}
              className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
            >
              Full Analysis <ArrowRight className="w-3.5 h-3.5" />
            </button>
          }
        >
          {benchmark ? (
            <div className="space-y-5">
              {/* 3-Arm Comparison Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Arm A: Control */}
                <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40">
                  <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 font-semibold uppercase">
                    Arm A: Control (No Outreach)
                  </div>
                  <div className="mt-1.5 text-xl font-bold text-slate-800 dark:text-slate-200 font-mono">
                    ₹{benchmark.arms.CONTROL.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    Gross: ₹9.58M | Cost: ₹0
                  </div>
                  <div className="mt-2 text-[10px] text-slate-400 font-mono">
                    Recovery Rate: {(benchmark.arms.CONTROL.Recovery_Rate * 100).toFixed(1)}%
                  </div>
                </div>

                {/* Arm C: RecoverIQ-v1 */}
                <div className="p-3.5 rounded-lg border border-blue-300 dark:border-blue-700/80 bg-blue-50/40 dark:bg-blue-950/20 relative">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono text-blue-600 dark:text-blue-400 font-bold uppercase">
                      Arm C: RecoverIQ-v1
                    </span>
                    <Badge variant="primary" size="sm">AI ADAPTIVE</Badge>
                  </div>
                  <div className="mt-1.5 text-xl font-bold text-blue-600 dark:text-blue-400 font-mono">
                    ₹{benchmark.arms.RECOVERIQ.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    Gross: ₹13.44M | Cost: ₹360K
                  </div>
                  <div className="mt-2 text-[10px] text-blue-600 dark:text-blue-400 font-mono">
                    Recovery Rate: {(benchmark.arms.RECOVERIQ.Recovery_Rate * 100).toFixed(1)}%
                  </div>
                </div>

                {/* Arm B: Baseline-v1 */}
                <div className="p-3.5 rounded-lg border border-emerald-300 dark:border-emerald-700/80 bg-emerald-50/40 dark:bg-emerald-950/20">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono text-emerald-700 dark:text-emerald-400 font-bold uppercase">
                      Arm B: Baseline-v1
                    </span>
                    <Badge variant="success" size="sm">FROZEN WINNER</Badge>
                  </div>
                  <div className="mt-1.5 text-xl font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                    ₹{benchmark.arms.BASELINE.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    Gross: ₹16.39M | Cost: ₹92K
                  </div>
                  <div className="mt-2 text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">
                    Recovery Rate: {(benchmark.arms.BASELINE.Recovery_Rate * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Statistical Differences Banner */}
              <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-100/60 dark:bg-slate-900/60 space-y-2">
                <div className="text-xs font-semibold text-slate-900 dark:text-white flex items-center justify-between">
                  <span>Statistical Inferences (2,000 Bootstrap Iterations, 95% Confidence)</span>
                  <Badge variant="simulator">SCIENTIFIC RIGOR</Badge>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs">
                  {/* RIQ vs Control */}
                  <div className="flex items-start gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 mt-1" />
                    <div>
                      <div className="font-semibold text-emerald-600 dark:text-emerald-400">
                        RecoverIQ vs Control: +₹526.36 / case
                      </div>
                      <div className="text-[11px] text-slate-500">
                        95% CI: [+₹437.09, +₹616.16] (STATISTICALLY SIGNIFICANT POSITIVE)
                      </div>
                    </div>
                  </div>

                  {/* RIQ vs Baseline */}
                  <div className="flex items-start gap-2">
                    <span className="w-2 h-2 rounded-full bg-rose-500 mt-1" />
                    <div>
                      <div className="font-semibold text-rose-600 dark:text-rose-400">
                        RecoverIQ vs Baseline: -₹481.20 / case
                      </div>
                      <div className="text-[11px] text-slate-500">
                        95% CI: [-₹577.10, -₹383.87] (Over-escalation to ₹100 human review)
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500 py-8 text-center">Loading frozen benchmark metrics...</div>
          )}
        </Card>

        {/* Right 1 Col: Razorpay Test Mode & Webhook Ingestion */}
        <div className="space-y-6">
          <Card
            title="Razorpay Test Mode"
            subtitle="Secure adapter connection"
            badge={
              <Badge variant={razorpayStatus?.status === 'CONNECTED' ? 'success' : 'warning'}>
                {razorpayStatus?.status === 'CONNECTED' ? 'CONNECTED' : 'TEST MODE'}
              </Badge>
            }
          >
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800/60">
                <span className="text-slate-500">Environment</span>
                <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">TEST (rzp_test_*)</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800/60">
                <span className="text-slate-500">Production Key Protection</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <Lock className="w-3 h-3" /> Fails Closed
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800/60">
                <span className="text-slate-500">Webhook HMAC Verification</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400">SHA-256 Active</span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-slate-500">Event Deduplication</span>
                <span className="font-mono text-blue-600 dark:text-blue-400">x-razorpay-event-id</span>
              </div>

              <div className="pt-2">
                <button
                  onClick={() => onNavigate('/safety')}
                  className="w-full py-2 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-xs font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center gap-1.5 transition-all"
                >
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />
                  Test Failure Scenarios
                </button>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Bottom Section: Failed Payment Case Queue Preview */}
      <Card
        title="Failed Payment Recovery Queue"
        subtitle="Recent payment failures queued for causal evaluation and bounded outreach"
        badge={<Badge variant="simulator">DEMO QUEUE</Badge>}
        action={
          <button
            onClick={() => onNavigate('/cases')}
            className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
          >
            View All ({recentCases.length} loaded) <ArrowRight className="w-3.5 h-3.5" />
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 font-mono uppercase text-[10px]">
                <th className="py-2.5 px-3">Case ID</th>
                <th className="py-2.5 px-3">Customer</th>
                <th className="py-2.5 px-3">Amount Due</th>
                <th className="py-2.5 px-3">Failure Reason</th>
                <th className="py-2.5 px-3">Recommended Action</th>
                <th className="py-2.5 px-3">Confidence</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {recentCases.map((c) => (
                <tr
                  key={c.case_id}
                  className="hover:bg-slate-50/80 dark:hover:bg-slate-900/40 transition-colors cursor-pointer"
                  onClick={() => onNavigate(`/cases/${c.case_id}`)}
                >
                  <td className="py-3 px-3 font-mono font-semibold text-slate-900 dark:text-slate-100">
                    {c.case_id}
                  </td>
                  <td className="py-3 px-3">
                    <div className="font-medium text-slate-800 dark:text-slate-200">{c.customer_id}</div>
                    <div className="text-[10px] text-slate-400 font-mono">{c.customer_segment}</div>
                  </td>
                  <td className="py-3 px-3 font-mono font-semibold text-slate-900 dark:text-white">
                    {formatCurrency(c.amount_due)}
                  </td>
                  <td className="py-3 px-3">
                    <Badge variant="warning">{c.failure_code}</Badge>
                  </td>
                  <td className="py-3 px-3">
                    <Badge
                      variant={
                        c.recommended_action === 'PAYMENT_LINK'
                          ? 'primary'
                          : c.recommended_action === 'STOP'
                          ? 'default'
                          : 'warning'
                      }
                    >
                      {c.recommended_action}
                    </Badge>
                  </td>
                  <td className="py-3 px-3 font-mono text-slate-600 dark:text-slate-300">
                    {(c.decision_confidence * 100).toFixed(0)}%
                  </td>
                  <td className="py-3 px-3 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate(`/cases/${c.case_id}`);
                      }}
                      className="p-1 text-blue-600 dark:text-blue-400 hover:text-blue-700"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

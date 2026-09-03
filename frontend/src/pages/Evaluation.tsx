import React, { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from 'recharts';
import {
  BarChart3,
  TrendingDown,
  TrendingUp,
  AlertCircle,
  HelpCircle,
  Clock,
  Sparkles,
  Layers,
  ShieldAlert,
  Info,
  CheckCircle2,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { api } from '../api/client';
import {
  BenchmarkResponse,
  OracleDiagnostic,
  AttributionSensitivity,
  LLMAblationResponse,
} from '../types';

export const Evaluation: React.FC = () => {
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [oracle, setOracle] = useState<OracleDiagnostic | null>(null);
  const [attribution, setAttribution] = useState<AttributionSensitivity | null>(null);
  const [llmAblation, setLlmAblation] = useState<LLMAblationResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getBenchmark().then(setBenchmark).catch(console.error),
      api.getOracleDiagnostic().then(setOracle).catch(console.error),
      api.getAttributionSensitivity().then(setAttribution).catch(console.error),
      api.getLLMAblation().then(setLlmAblation).catch(console.error),
    ]).finally(() => setLoading(false));
  }, []);

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(val);

  if (loading || !benchmark) {
    return (
      <div className="py-20 text-center text-xs text-slate-500">
        Loading frozen scientific evaluation package...
      </div>
    );
  }

  // Bar chart dataset for primary 3-arm comparison
  const benchmarkChartData = [
    {
      name: 'Control (Arm A)',
      meanNet: benchmark.arms.CONTROL.Mean_Net_Per_Case,
      gross: benchmark.arms.CONTROL.Gross_Recovered / 1000000,
      cost: (benchmark.arms.CONTROL.Action_Cost + benchmark.arms.CONTROL.Friction_Cost) / 1000,
      color: '#64748b',
    },
    {
      name: 'RecoverIQ-v1 (Arm C)',
      meanNet: benchmark.arms.RECOVERIQ.Mean_Net_Per_Case,
      gross: benchmark.arms.RECOVERIQ.Gross_Recovered / 1000000,
      cost: (benchmark.arms.RECOVERIQ.Action_Cost + benchmark.arms.RECOVERIQ.Friction_Cost) / 1000,
      color: '#3395ff',
    },
    {
      name: 'Baseline-v1 (Arm B)',
      meanNet: benchmark.arms.BASELINE.Mean_Net_Per_Case,
      gross: benchmark.arms.BASELINE.Gross_Recovered / 1000000,
      cost: (benchmark.arms.BASELINE.Action_Cost + benchmark.arms.BASELINE.Friction_Cost) / 1000,
      color: '#10b981',
    },
  ];

  // Action distribution comparison data (RecoverIQ vs Oracle)
  const actionDistData = [
    { action: 'ESCALATE', recoveriq: 52.52, oracle: 3.40 },
    { action: 'STOP', recoveriq: 29.93, oracle: 60.07 },
    { action: 'PAYMENT_LINK', recoveriq: 8.60, oracle: 9.67 },
    { action: 'PROMISE_TO_PAY', recoveriq: 8.53, oracle: 5.27 },
    { action: 'REMINDER', recoveriq: 0.60, oracle: 21.60 },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-bold text-slate-900 dark:text-white">
            Scientific Evaluation & Benchmark Lab
          </h2>
          <Badge variant="frozen">FROZEN 20K HOLDOUT</Badge>
          <Badge variant="simulator">SCENARIO: S1_HIGH_NATURAL_RECOVERY</Badge>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Complete, unmanipulated benchmark evidence package from the Phase 9 frozen holdout execution (Seed: 999888777).
        </p>
      </div>

      {/* SECTION 1: PRIMARY FINANCIAL BENCHMARK & RECHARTS VISUALIZATION */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Bar Chart */}
        <Card
          className="lg:col-span-2"
          title="Primary Metric: Mean Net Recovered per Case"
          subtitle="Net = Gross Recovered - Action Costs (₹100 Escalate, ₹3 Link, ₹2 Reminder) - Friction Costs"
          badge={<Badge variant="primary">PRIMARY BENCHMARK</Badge>}
        >
          <div className="h-64 w-full mt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={benchmarkChartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.2} />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(val) => `₹${val}`} />
                <Tooltip
                  formatter={(val: any) => [`₹${Number(val).toFixed(2)}`, 'Mean Net / Case']}
                  contentStyle={{ backgroundColor: '#0B111E', borderColor: '#1E293B', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="meanNet" radius={[6, 6, 0, 0]}>
                  {benchmarkChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-xs font-mono border-t border-slate-100 dark:border-slate-800/60 pt-3">
            <div>
              <div className="text-slate-400 text-[10px]">CONTROL</div>
              <div className="text-base font-bold text-slate-700 dark:text-slate-300 mt-0.5">
                ₹{benchmark.arms.CONTROL.Mean_Net_Per_Case.toFixed(2)}
              </div>
              <div className="text-[10px] text-slate-500">Recovery: 50.6%</div>
            </div>

            <div className="border-x border-slate-100 dark:border-slate-800/60">
              <div className="text-blue-500 text-[10px] font-bold">RECOVERIQ-V1</div>
              <div className="text-base font-bold text-blue-500 mt-0.5">
                ₹{benchmark.arms.RECOVERIQ.Mean_Net_Per_Case.toFixed(2)}
              </div>
              <div className="text-[10px] text-slate-500">Recovery: 67.8%</div>
            </div>

            <div>
              <div className="text-emerald-500 text-[10px] font-bold">BASELINE-V1</div>
              <div className="text-base font-bold text-emerald-500 mt-0.5">
                ₹{benchmark.arms.BASELINE.Mean_Net_Per_Case.toFixed(2)}
              </div>
              <div className="text-[10px] text-slate-500">Recovery: 84.2%</div>
            </div>
          </div>
        </Card>

        {/* Right 1 Col: Honest Statistical Decisions */}
        <Card
          title="Statistical Significance"
          subtitle="95% Bootstrap Confidence Intervals (2,000 iterations)"
          badge={<Badge variant="simulator">RIGOROUS EVIDENCE</Badge>}
        >
          <div className="space-y-4 text-xs">
            {/* Comparison 1: RecoverIQ vs Baseline */}
            <div className="p-3 rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/20 space-y-1">
              <div className="flex items-center justify-between font-mono">
                <span className="font-bold text-rose-700 dark:text-rose-400">RecoverIQ vs Baseline</span>
                <Badge variant="danger">NEGATIVE</Badge>
              </div>
              <div className="text-lg font-bold font-mono text-rose-600 dark:text-rose-400">
                -₹481.20 / case
              </div>
              <div className="text-[11px] text-slate-500 font-mono">
                95% CI: [-₹577.10, -₹383.87]
              </div>
              <div className="text-[10px] text-slate-600 dark:text-slate-400 pt-1 font-sans">
                Statistically significant negative: RecoverIQ over-escalated to ₹100 human review.
              </div>
            </div>

            {/* Comparison 2: RecoverIQ vs Control */}
            <div className="p-3 rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/20 space-y-1">
              <div className="flex items-center justify-between font-mono">
                <span className="font-bold text-emerald-700 dark:text-emerald-400">RecoverIQ vs Control</span>
                <Badge variant="success">POSITIVE</Badge>
              </div>
              <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                +₹526.36 / case
              </div>
              <div className="text-[11px] text-slate-500 font-mono">
                95% CI: [+₹437.09, +₹616.16]
              </div>
              <div className="text-[10px] text-slate-600 dark:text-slate-400 pt-1 font-sans">
                Statistically significant positive: +₹3.51M net uplift across 6,666 cases over zero outreach.
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* SECTION 2: ROOT CAUSE ANALYSIS — ACTION DISTRIBUTION & OVER-ESCALATION */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Action Distribution Comparison */}
        <Card
          title="Root Cause Analysis: Policy vs Counterfactual Oracle"
          subtitle="Why did RecoverIQ lose to the deterministic baseline?"
          badge={<Badge variant="simulator">OVER-ESCALATION</Badge>}
        >
          <div className="space-y-3">
            <div className="text-xs text-slate-600 dark:text-slate-300">
              RecoverIQ selected <strong>ESCALATE (₹100 cost) on 52.52% of cases</strong> (3,501 / 6,666 cases), incurring ₹350,100 in escalation expenses. The counterfactual oracle chooses ESCALATE on only <strong>3.40% of cases</strong>, preferring automated reminders or stopping.
            </div>

            <div className="space-y-2 pt-2">
              {actionDistData.map((item) => (
                <div key={item.action} className="space-y-1 text-xs font-mono">
                  <div className="flex justify-between text-[11px]">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{item.action}</span>
                    <span className="text-slate-400">
                      RecoverIQ: <strong className="text-blue-500">{item.recoveriq}%</strong> | Oracle:{' '}
                      <strong className="text-emerald-500">{item.oracle}%</strong>
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 h-2 rounded bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className="h-full bg-blue-500" style={{ width: `${item.recoveriq}%` }} />
                    <div className="h-full bg-emerald-500" style={{ width: `${item.oracle}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Corrected Oracle Diagnostic Card */}
        <Card
          title="Simulator-Only Counterfactual Oracle Diagnostic"
          subtitle="Evaluated on pristine unmutated 1,500-case holdout slice"
          badge={<Badge variant="simulator">SIMULATOR ONLY</Badge>}
        >
          {oracle ? (
            <div className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">Oracle Top Agreement</div>
                  <div className="text-xl font-bold font-mono text-slate-900 dark:text-white mt-1">
                    {(oracle.oracle_agreement_rate * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-slate-500">357 / 1,500 matches</div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">Mean Policy Regret</div>
                  <div className="text-xl font-bold font-mono text-rose-500 mt-1">
                    ₹{oracle.mean_regret_per_case.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-slate-500">per case vs potential outcome</div>
                </div>
              </div>

              {oracle.audit_trail_invalidation_note && (
                <div className="p-3 rounded-lg border border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/20 text-[11px] text-amber-800 dark:text-amber-300 space-y-1">
                  <div className="font-bold flex items-center gap-1 font-mono uppercase text-[10px]">
                    <Info className="w-3.5 h-3.5" /> Audit Trace Invalidation Notice
                  </div>
                  <div>{oracle.audit_trail_invalidation_note}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">Loading oracle diagnostics...</div>
          )}
        </Card>
      </div>

      {/* SECTION 3: ATTRIBUTION SENSITIVITY & LLM ABLATION */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Attribution Sensitivity */}
        <Card
          title="Attribution Window Sensitivity"
          subtitle="Paired single-step analysis on N=1,500 cases (24h vs 72h vs 168h)"
          badge={<Badge variant="default">SENSITIVITY ANALYSIS</Badge>}
        >
          {attribution ? (
            <div className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400 uppercase text-[10px]">
                      <th className="py-2 px-3">Window</th>
                      <th className="py-2 px-3">Baseline Net</th>
                      <th className="py-2 px-3">RecoverIQ Net</th>
                      <th className="py-2 px-3">Delta</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {Object.entries(attribution).map(([win, data]) => (
                      <tr key={win}>
                        <td className="py-2.5 px-3 font-bold text-slate-900 dark:text-white">{win}</td>
                        <td className="py-2.5 px-3 text-emerald-500">₹{data.mean_net_base.toFixed(2)}</td>
                        <td className="py-2.5 px-3 text-blue-500">₹{data.mean_net_riq.toFixed(2)}</td>
                        <td className="py-2.5 px-3 font-bold text-rose-500">₹{data.delta_riq_minus_base.toFixed(2)}</td>
                        <td className="py-2.5 px-3">
                          <Badge variant={data.conclusion === 'FAVORS_BASELINE' ? 'danger' : 'default'} size="sm">
                            {data.conclusion}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-[11px] text-slate-500 font-sans">
                * Note: Evaluated on single-step outreach to isolate attribution window decay; primary 20k contract uses 72h sequential multi-step execution.
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">Loading sensitivity analysis...</div>
          )}
        </Card>

        {/* LLM Controlled Ablation */}
        <Card
          title="LLM Controlled Ablation (1,000 Cases)"
          subtitle="Structured-Only Features vs LLM-Augmented Context"
          badge={<Badge variant="simulator">INCONCLUSIVE RESULT</Badge>}
        >
          {llmAblation ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">Structured Only Net</div>
                  <div className="text-lg font-bold font-mono text-slate-900 dark:text-white mt-0.5">
                    ₹{llmAblation.ablation_comparison.structured_only_mean_net.toFixed(2)}
                  </div>
                </div>

                <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">LLM-Augmented Net</div>
                  <div className="text-lg font-bold font-mono text-slate-900 dark:text-white mt-0.5">
                    ₹{llmAblation.ablation_comparison.llm_augmented_mean_net.toFixed(2)}
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-100/60 dark:bg-slate-900/60 space-y-1 text-[11px]">
                <div className="flex justify-between font-mono">
                  <span>Delta (LLM - Structured):</span>
                  <strong className="text-slate-900 dark:text-white">₹0.00 / case</strong>
                </div>
                <div className="flex justify-between font-mono text-slate-500">
                  <span>95% Confidence Interval:</span>
                  <span>[-₹208.02, +₹203.99]</span>
                </div>
                <div className="text-[10px] text-slate-500 pt-1 font-sans">
                  "No detectable financial recovery improvement demonstrated. The LLM successfully registered 149 promises and 73 opt-outs without affecting net recovery."
                </div>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">Loading ablation study...</div>
          )}
        </Card>
      </div>
    </div>
  );
};

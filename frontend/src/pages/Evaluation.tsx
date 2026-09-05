import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Scale,
  BrainCircuit,
  BarChart2,
  Sliders,
} from 'lucide-react';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorMessage } from '../components/common/ErrorMessage';
import { useRecoverIQData } from '../context/useRecoverIQData';
import { api } from '../api/client';
import { BenchmarkResponse, OracleDiagnostic, AttributionSensitivity, LLMAblationResponse } from '../types';
import { animateBarGrowth, animateCounter, staggerReveal } from '../utils/motion';

export const Evaluation: React.FC = () => {
  const {
    benchmark: ctxBenchmark,
    oracleDiagnostic: ctxOracle,
    attributionSensitivity: ctxAttribution,
    llmAblation: ctxAblation,
    refreshEvaluationSuite,
    refreshBenchmark,
  } = useRecoverIQData();

  // Local state for resilient lifecycle & standalone retries
  const [benchmarkData, setBenchmarkData] = useState<BenchmarkResponse | null>(ctxBenchmark.data);
  const [oracleData, setOracleData] = useState<OracleDiagnostic | null>(ctxOracle.data);
  const [attributionData, setAttributionData] = useState<AttributionSensitivity | null>(ctxAttribution.data);
  const [ablationData, setAblationData] = useState<LLMAblationResponse | null>(ctxAblation.data);

  const [loading, setLoading] = useState<boolean>(!ctxBenchmark.data);
  const [error, setError] = useState<string | null>(ctxBenchmark.error);

  // Collapsible deep diagnostics sections (progressive disclosure)
  const [showDeepDiagnostics, setShowDeepDiagnostics] = useState<boolean>(false);
  const [showModelTrace, setShowModelTrace] = useState<boolean>(false);

  // Counter refs
  const baseNetRef = useRef<HTMLSpanElement>(null);
  const riqNetRef = useRef<HTMLSpanElement>(null);
  const ctrlNetRef = useRef<HTMLSpanElement>(null);

  const animationRan = useRef(false);

  // Fresh API fetch on mount or manual retry
  const loadEvaluationSuite = useCallback(async () => {
    setLoading(true);
    setError(null);

    refreshBenchmark().catch(() => {});
    refreshEvaluationSuite().catch(() => {});

    try {
      const [bm, orc, attr, abl] = await Promise.all([
        api.getBenchmark(),
        api.getOracleDiagnostic().catch(() => null),
        api.getAttributionSensitivity().catch(() => null),
        api.getLLMAblation().catch(() => null),
      ]);

      setBenchmarkData(bm);
      if (orc) setOracleData(orc);
      if (attr) setAttributionData(attr);
      if (abl) setAblationData(abl);
      setLoading(false);
    } catch (err: any) {
      setError(err?.message || 'Unable to load frozen holdout data.');
      setLoading(false);
    }
  }, [refreshBenchmark, refreshEvaluationSuite]);

  // Initial load if no data exists
  useEffect(() => {
    if (!benchmarkData && !ctxBenchmark.data) {
      loadEvaluationSuite();
    } else if (ctxBenchmark.data && !benchmarkData) {
      setBenchmarkData(ctxBenchmark.data);
      setLoading(false);
    }
  }, [benchmarkData, ctxBenchmark.data, loadEvaluationSuite]);

  // Synchronize with context updates safely
  useEffect(() => {
    if (ctxBenchmark.data) {
      setBenchmarkData(ctxBenchmark.data);
      setLoading(false);
    }
    if (ctxOracle.data) setOracleData(ctxOracle.data);
    if (ctxAttribution.data) setAttributionData(ctxAttribution.data);
    if (ctxAblation.data) setAblationData(ctxAblation.data);
  }, [ctxBenchmark.data, ctxOracle.data, ctxAttribution.data, ctxAblation.data]);

  // Coordinated evaluation entrance animation sequence (0.0s - 1.1s)
  useEffect(() => {
    if (benchmarkData && !animationRan.current) {
      animationRan.current = true;
      const arms = benchmarkData.arms;

      try {
        // 1. Reveal header & primary sections
        staggerReveal('.eval-section-block', { delay: 40, stagger: 60, translateY: 8 });

        // 2. Count numbers upward (0.25s - 1.0s)
        setTimeout(() => {
          animateCounter(baseNetRef.current, 0, arms.BASELINE.Mean_Net_Per_Case, {
            formatter: (val) => `${formatCurrency(val)} / case`,
            duration: 900,
          });
          animateCounter(riqNetRef.current, 0, arms.RECOVERIQ.Mean_Net_Per_Case, {
            formatter: (val) => `${formatCurrency(val)} / case`,
            duration: 900,
          });
          animateCounter(ctrlNetRef.current, 0, arms.CONTROL.Mean_Net_Per_Case, {
            formatter: (val) => `${formatCurrency(val)} / case`,
            duration: 900,
          });
        }, 200);

        // 3. Bars visibly grow from 0 -> target (0.35s - 1.2s, 1050ms duration)
        setTimeout(() => {
          animateBarGrowth('.comparison-bar-fill', { stagger: 90, duration: 1050 });
        }, 300);

        // 4. Stagger inference cards & diagnostics
        setTimeout(() => {
          staggerReveal('.eval-card-block', { delay: 30, stagger: 40 });
        }, 450);
      } catch (e) {
        console.warn('Evaluation animation notice:', e);
      }
    }
  }, [benchmarkData]);

  // Format INR currency
  const formatCurrency = (val: number | undefined) => {
    if (val === undefined || isNaN(val)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
  };

  // State 1: ERROR
  if (error && !benchmarkData) {
    return (
      <div className="space-y-6 max-w-2xl py-8">
        <ErrorMessage
          title="Benchmark unavailable"
          message={error || 'Unable to load frozen holdout data.'}
          onRetry={loadEvaluationSuite}
        />
        <div className="text-xs text-slate-500 dark:text-[#A3A3A3]">
          The frozen Phase 9 evaluation benchmark is authoritative and cannot be generated dynamically. Check backend connection to <code className="font-mono bg-slate-100 dark:bg-[#1A1A1A] px-1.5 py-0.5 rounded">/api/evaluation/benchmark</code>.
        </div>
      </div>
    );
  }

  // State 2: LOADING
  if (loading && !benchmarkData) {
    return (
      <div className="space-y-8 py-4">
        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Loading frozen benchmark…
          </div>
          <div className="text-xs text-slate-400">
            Fetching frozen 20,000-case holdout dataset evaluation artifacts.
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <LoadingSkeleton className="h-48 col-span-2" />
          <LoadingSkeleton className="h-48 col-span-1" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <LoadingSkeleton className="h-40" />
          <LoadingSkeleton className="h-40" />
        </div>
      </div>
    );
  }

  if (!benchmarkData) return null;

  // Active benchmark values
  const arms = benchmarkData.arms;
  const maxNet = Math.max(
    arms.BASELINE?.Mean_Net_Per_Case || 2443.95,
    arms.RECOVERIQ?.Mean_Net_Per_Case || 1962.75,
    arms.CONTROL?.Mean_Net_Per_Case || 1436.40
  );

  const comparisons = benchmarkData.bootstrap_comparisons;
  const riqVsBaseline = comparisons?.RecoverIQ_vs_Baseline;
  const riqVsControl = comparisons?.RecoverIQ_vs_Control;

  const actionDistData = [
    { action: 'Escalate', recoveriq: 52.52, oracle: 3.40, cost: '₹100' },
    { action: 'Stop', recoveriq: 29.93, oracle: 60.07, cost: '₹0' },
    { action: 'Payment link', recoveriq: 8.60, oracle: 9.67, cost: '₹20' },
    { action: 'Promise to pay', recoveriq: 8.53, oracle: 5.27, cost: '₹0' },
    { action: 'Reminder', recoveriq: 0.60, oracle: 21.60, cost: '₹10' },
  ];

  return (
    <div className="space-y-10">
      {/* 1. Header */}
      <div className="eval-section-block flex flex-col md:flex-row md:items-baseline justify-between gap-4 pb-6 border-b border-slate-200/80 dark:border-[#1F1F1F]">
        <div>
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Evaluation Lab
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400 font-semibold border border-blue-200/60 dark:border-blue-900/40">
              Frozen Holdout 20,000 Cases
            </span>
            <span className="text-xs font-mono text-slate-500 dark:text-[#737373]">
              Scenario S1 · Seed: {benchmarkData.seed || 999888777}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-1.5">
            Empirical randomized trial under High Natural Recovery. 3 randomized arms evaluated with paired bootstrapping.
          </p>
        </div>

        <button
          onClick={() => loadEvaluationSuite()}
          className="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer self-start md:self-auto hover:-translate-y-0.5 duration-150"
          title="Reload frozen benchmark data from backend"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Verify Evidence</span>
        </button>
      </div>

      {/* 2. Primary 3-Arm Comparison Bar Visualization & Bootstrap Inferences */}
      <div className="eval-section-block grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Animated Bar Comparison */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-200/80 dark:border-[#1F1F1F]">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                Mean Net Recovery Per Case
              </h2>
            </div>
            <span className="text-xs text-slate-400 font-mono">Net = Gross − Costs − Friction</span>
          </div>

          <div className="space-y-5 pt-1">
            {/* Arm B: Baseline-v1 */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">Baseline-v1 (Deterministic Rule)</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 font-medium">
                    Highest Net
                  </span>
                </div>
                <span ref={baseNetRef} className="font-bold text-emerald-600 dark:text-emerald-400 text-sm tabular-nums">
                  {formatCurrency(arms.BASELINE.Mean_Net_Per_Case)} / case
                </span>
              </div>
              <div className="h-5 rounded-md bg-slate-100 dark:bg-[#141414] overflow-hidden relative">
                <div
                  className="comparison-bar-fill h-full bg-emerald-500 rounded-md origin-left transition-all will-change-transform"
                  style={{
                    width: `${((arms.BASELINE.Mean_Net_Per_Case || 2443.95) / maxNet) * 100}%`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-500 dark:text-[#737373]">
                <span>Gross: {formatCurrency(arms.BASELINE.Gross_Recovered / arms.BASELINE.N)}</span>
                <span>Action Cost: {formatCurrency(arms.BASELINE.Action_Cost / arms.BASELINE.N)}</span>
                <span>Recovery Rate: {((arms.BASELINE.Recovery_Rate || 0.841) * 100).toFixed(1)}%</span>
              </div>
            </div>

            {/* Arm C: RecoverIQ-v1 */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-blue-600 dark:text-blue-400">RecoverIQ-v1 (AI Adaptive Policy)</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-medium">
                    Adaptive
                  </span>
                </div>
                <span ref={riqNetRef} className="font-bold text-blue-600 dark:text-blue-400 text-sm tabular-nums">
                  {formatCurrency(arms.RECOVERIQ.Mean_Net_Per_Case)} / case
                </span>
              </div>
              <div className="h-5 rounded-md bg-slate-100 dark:bg-[#141414] overflow-hidden relative">
                <div
                  className="comparison-bar-fill h-full bg-blue-500 rounded-md origin-left shadow-sm transition-all will-change-transform"
                  style={{
                    width: `${((arms.RECOVERIQ.Mean_Net_Per_Case || 1962.75) / maxNet) * 100}%`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-500 dark:text-[#737373]">
                <span>Gross: {formatCurrency(arms.RECOVERIQ.Gross_Recovered / arms.RECOVERIQ.N)}</span>
                <span>Action Cost: {formatCurrency(arms.RECOVERIQ.Action_Cost / arms.RECOVERIQ.N)}</span>
                <span>Recovery Rate: {((arms.RECOVERIQ.Recovery_Rate || 0.678) * 100).toFixed(1)}%</span>
              </div>
            </div>

            {/* Arm A: Control */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-600 dark:text-[#A3A3A3]">Control (Zero Outreach)</span>
                <span ref={ctrlNetRef} className="font-bold text-slate-800 dark:text-slate-200 text-sm tabular-nums">
                  {formatCurrency(arms.CONTROL.Mean_Net_Per_Case)} / case
                </span>
              </div>
              <div className="h-5 rounded-md bg-slate-100 dark:bg-[#141414] overflow-hidden relative">
                <div
                  className="comparison-bar-fill h-full bg-slate-500 rounded-md origin-left transition-all will-change-transform"
                  style={{
                    width: `${((arms.CONTROL.Mean_Net_Per_Case || 1436.40) / maxNet) * 100}%`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-500 dark:text-[#737373]">
                <span>Gross: {formatCurrency(arms.CONTROL.Gross_Recovered / arms.CONTROL.N)}</span>
                <span>Action Cost: ₹0.00</span>
                <span>Recovery Rate: {((arms.CONTROL.Recovery_Rate || 0.506) * 100).toFixed(1)}% (Natural)</span>
              </div>
            </div>
          </div>
        </div>

        {/* 95% Bootstrap Inferences */}
        <div className="space-y-4">
          <div className="pb-2 border-b border-slate-200/80 dark:border-[#1F1F1F]">
            <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Scale className="w-4 h-4 text-slate-600 dark:text-[#A3A3A3]" />
              95% Bootstrap Inferences
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-0.5 font-mono">
              2,000 paired holdout iterations
            </p>
          </div>

          <div className="space-y-4 text-xs">
            {/* Positive vs Control */}
            <div className="eval-card-block space-y-1 p-3 rounded-lg border border-emerald-200/60 dark:border-emerald-950/60 bg-emerald-50/30 dark:bg-emerald-950/10 hover:shadow-2xs transition-shadow">
              <div className="flex items-center justify-between">
                <span className="font-bold text-emerald-700 dark:text-emerald-400">RecoverIQ vs Control</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-bold tabular-nums text-sm">
                  +{formatCurrency(riqVsControl?.point_estimate || 526.36)}
                </span>
              </div>
              <div className="text-slate-500 dark:text-[#A3A3A3] text-[11px] font-mono">
                95% CI: [{formatCurrency(riqVsControl?.ci_95?.[0] || 437.09)}, {formatCurrency(riqVsControl?.ci_95?.[1] || 616.16)}]
              </div>
              <div className="text-slate-600 dark:text-[#D4D4D4] pt-0.5 text-[11px] leading-tight">
                Statistically significant net gain over zero outreach under scenario S1.
              </div>
            </div>

            {/* Negative vs Baseline */}
            <div className="eval-card-block space-y-1 p-3 rounded-lg border border-rose-200/60 dark:border-rose-950/60 bg-rose-50/30 dark:bg-rose-950/10 hover:shadow-2xs transition-shadow">
              <div className="flex items-center justify-between">
                <span className="font-bold text-rose-700 dark:text-rose-400">RecoverIQ vs Baseline</span>
                <span className="text-rose-600 dark:text-rose-400 font-bold tabular-nums text-sm">
                  {formatCurrency(riqVsBaseline?.point_estimate || -481.20)}
                </span>
              </div>
              <div className="text-slate-500 dark:text-[#A3A3A3] text-[11px] font-mono">
                95% CI: [{formatCurrency(riqVsBaseline?.ci_95?.[0] || -577.10)}, {formatCurrency(riqVsBaseline?.ci_95?.[1] || -383.87)}]
              </div>
              <div className="text-slate-600 dark:text-[#D4D4D4] pt-0.5 text-[11px] leading-tight">
                RecoverIQ recovered more than no outreach, but underperformed the deterministic baseline due to over-escalation.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Root Cause: Action Distribution & Over-Escalation */}
      <div className="eval-section-block space-y-3 pt-2 border-t border-slate-200/80 dark:border-[#1F1F1F]">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            Primary Diagnostic: Action Distribution & Over-Escalation
          </h3>
          <span className="text-xs text-slate-400">
            RecoverIQ escalated 52.5% of cases (₹100 cost) vs 3.4% in Oracle
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 pt-1">
          {actionDistData.map((item) => (
            <div key={item.action} className="p-3 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] space-y-1.5 text-xs hover:border-slate-300 dark:hover:border-[#2A2A2A] transition-colors">
              <div className="flex justify-between font-medium">
                <span className="text-slate-800 dark:text-slate-200">{item.action}</span>
                <span className="text-slate-400 text-[11px] font-mono">{item.cost}</span>
              </div>
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-blue-600 dark:text-blue-400 font-bold">RIQ: {item.recoveriq}%</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-bold">Oracle: {item.oracle}%</span>
              </div>
              <div className="grid grid-cols-2 gap-1 h-1.5 rounded bg-slate-100 dark:bg-[#1A1A1A] overflow-hidden">
                <div className="h-full bg-blue-500 rounded" style={{ width: `${item.recoveriq}%` }} />
                <div className="h-full bg-emerald-500 rounded" style={{ width: `${item.oracle}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Progressive Disclosure: Deeper Diagnostics Accordion */}
      <div className="eval-section-block space-y-4 pt-2 border-t border-slate-200/80 dark:border-[#1F1F1F]">
        <button
          onClick={() => setShowDeepDiagnostics(!showDeepDiagnostics)}
          className="w-full flex items-center justify-between p-3.5 rounded-lg border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] hover:bg-slate-50 dark:hover:bg-[#141414] transition-colors text-left cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <Sliders className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <div>
              <div className="font-bold text-xs text-slate-900 dark:text-white">
                Deep Diagnostics: Oracle, Attribution Sensitivity & LLM Ablation
              </div>
              <div className="text-[11px] text-slate-500 dark:text-[#A3A3A3] mt-0.5">
                Counterfactual regret (N=1,500), attribution window sensitivity (24h–168h), and LLM ablation tests.
              </div>
            </div>
          </div>
          {showDeepDiagnostics ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>

        {showDeepDiagnostics && (
          <div className="space-y-6 pt-2 animate-[fadeIn_0.2s_ease-out]">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Counterfactual Oracle Diagnostic */}
              <div className="p-4 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0A0A0A] space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs text-slate-900 dark:text-white">Oracle Diagnostic</h4>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-500 font-mono">N=1,500</span>
                </div>
                {oracleData ? (
                  <div className="space-y-2 text-xs divide-y divide-slate-100 dark:divide-[#1F1F1F]">
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Agreement Rate:</span>
                      <span className="font-bold text-slate-900 dark:text-white font-mono">
                        {((oracleData.oracle_agreement_rate || 0.238) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Mean Policy Regret:</span>
                      <span className="font-bold text-rose-500 font-mono">
                        {formatCurrency(oracleData.mean_regret_per_case || 702.46)}
                      </span>
                    </div>
                  </div>
                ) : (
                  <LoadingSkeleton className="h-16 w-full" />
                )}
              </div>

              {/* Attribution Window Sensitivity */}
              <div className="p-4 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0A0A0A] space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs text-slate-900 dark:text-white">Attribution Sensitivity</h4>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-500 font-mono">N=1,500</span>
                </div>
                {attributionData ? (
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-slate-400 text-[10px] border-b border-slate-100 dark:border-[#1F1F1F]">
                        <th className="pb-1">Window</th>
                        <th className="pb-1">Base</th>
                        <th className="pb-1">RIQ</th>
                        <th className="pb-1 text-right">Delta</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-[#1F1F1F] text-[11px] font-mono">
                      {Object.entries(attributionData).map(([win, d]) => (
                        <tr key={win}>
                          <td className="py-1 font-semibold text-slate-700 dark:text-slate-300">{win}</td>
                          <td className="py-1 text-emerald-600 dark:text-emerald-400">₹{d.mean_net_base.toFixed(0)}</td>
                          <td className="py-1 text-blue-600 dark:text-blue-400">₹{d.mean_net_riq.toFixed(0)}</td>
                          <td className="py-1 text-rose-500 text-right font-bold">₹{d.delta_riq_minus_base.toFixed(0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <LoadingSkeleton className="h-16 w-full" />
                )}
              </div>

              {/* LLM Controlled Ablation */}
              <div className="p-4 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0A0A0A] space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs text-slate-900 dark:text-white">LLM Ablation Test</h4>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-500 font-mono">Inconclusive</span>
                </div>
                {ablationData ? (
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-500">Structured Net:</span>
                      <span className="font-mono font-bold text-slate-900 dark:text-white">
                        {formatCurrency(ablationData.ablation_comparison.mean_net_structured)}
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-500">Augmented Net:</span>
                      <span className="font-mono font-bold text-slate-900 dark:text-white">
                        {formatCurrency(ablationData.ablation_comparison.mean_net_augmented)}
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-400 pt-1 font-mono">
                      Delta: ₹0.00 / case (95% CI: [-₹208, +₹204])
                    </div>
                  </div>
                ) : (
                  <LoadingSkeleton className="h-16 w-full" />
                )}
              </div>
            </div>
          </div>
        )}

        {/* What the Model Knew: Trace */}
        <button
          onClick={() => setShowModelTrace(!showModelTrace)}
          className="w-full flex items-center justify-between p-3.5 rounded-lg border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] hover:bg-slate-50 dark:hover:bg-[#141414] transition-colors text-left cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <BrainCircuit className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <div>
              <div className="font-bold text-xs text-slate-900 dark:text-white">
                What the Model Knew: Decision Trace Architecture
              </div>
              <div className="text-[11px] text-slate-500 dark:text-[#A3A3A3] mt-0.5">
                Observable features, candidate uplift calculations, and policy execution gates.
              </div>
            </div>
          </div>
          {showModelTrace ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>

        {showModelTrace && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-slate-50/50 dark:bg-[#0A0A0A] text-xs animate-[fadeIn_0.2s_ease-out]">
            <div className="space-y-1.5">
              <div className="font-semibold text-slate-900 dark:text-white text-[11px] text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                1. Observable State
              </div>
              <ul className="space-y-0.5 text-slate-600 dark:text-[#A3A3A3] text-[11px]">
                <li>• Hours since failure (0–72h)</li>
                <li>• Prior attempt count (1–3)</li>
                <li>• Amount due & customer segment</li>
                <li>• Failure reason code</li>
              </ul>
            </div>

            <div className="space-y-1.5">
              <div className="font-semibold text-slate-900 dark:text-white text-[11px] text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                2. Causal Uplift &tau;(x)
              </div>
              <ul className="space-y-0.5 text-slate-600 dark:text-[#A3A3A3] text-[11px]">
                <li>• P(Recovery | Action = a, X = x)</li>
                <li>• Incremental uplift &tau;(x) vs Control</li>
                <li>• Meta-learner potential outcomes</li>
              </ul>
            </div>

            <div className="space-y-1.5">
              <div className="font-semibold text-slate-900 dark:text-white text-[11px] text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                3. Economic Value
              </div>
              <ul className="space-y-0.5 text-slate-600 dark:text-[#A3A3A3] text-[11px]">
                <li>• E[Net] = &tau;(x) · Amount − Cost − Friction</li>
                <li>• Escalate cost: ₹100</li>
                <li>• Payment link: ₹20 · Reminder: ₹10</li>
              </ul>
            </div>

            <div className="space-y-1.5">
              <div className="font-semibold text-slate-900 dark:text-white text-[11px] text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                4. Safety Gate
              </div>
              <ul className="space-y-0.5 text-slate-600 dark:text-[#A3A3A3] text-[11px]">
                <li>• Max 3 automated touches hard cap</li>
                <li>• Max 30-day recovery window limit</li>
                <li>• Opt-out instant block</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

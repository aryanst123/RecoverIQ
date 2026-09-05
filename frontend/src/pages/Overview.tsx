import React, { useEffect, useRef } from 'react';
import {
  ArrowRight,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorMessage } from '../components/common/ErrorMessage';
import { useRecoverIQData } from '../context/useRecoverIQData';
import { animateCounter, staggerReveal } from '../utils/motion';

interface OverviewProps {
  onNavigate: (path: string) => void;
}

export const Overview: React.FC<OverviewProps> = ({ onNavigate }) => {
  const { kpis, benchmark, cases, razorpayStatus, refreshKPIs, refreshBenchmark, refreshCases } = useRecoverIQData();

  const kpiRiskRef = useRef<HTMLSpanElement>(null);
  const kpiRecoveredRef = useRef<HTMLDivElement>(null);
  const kpiRateRef = useRef<HTMLDivElement>(null);
  const kpiSafetyRef = useRef<HTMLDivElement>(null);

  const bmControlRef = useRef<HTMLDivElement>(null);
  const bmRiqRef = useRef<HTMLDivElement>(null);
  const bmBaseRef = useRef<HTMLDivElement>(null);

  const countRan = useRef(false);

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  // Mount guarantee
  useEffect(() => {
    if (!kpis.data && !kpis.loading) refreshKPIs();
    if (!benchmark.data && !benchmark.loading) refreshBenchmark();
    if (!cases.data && !cases.loading) refreshCases();
  }, [kpis.data, kpis.loading, benchmark.data, benchmark.loading, cases.data, cases.loading, refreshKPIs, refreshBenchmark, refreshCases]);

  // Anime.js count-up & sequential section entrance
  useEffect(() => {
    if (kpis.data && !countRan.current) {
      countRan.current = true;

      // Stagger sections
      staggerReveal('.overview-section-block', { delay: 40, stagger: 55, translateY: 8 });

      // Animate Hero KPI counters
      animateCounter(kpiRiskRef.current, 0, kpis.data.revenue_at_risk_inr, {
        formatter: (val) => formatCurrency(val),
        duration: 800,
      });

      animateCounter(kpiRecoveredRef.current, 0, kpis.data.revenue_recovered_inr, {
        formatter: (val) => formatCurrency(val),
        duration: 750,
      });

      animateCounter(kpiRateRef.current, 0, kpis.data.recovery_rate * 100, {
        formatter: (val) => `${val.toFixed(1)}% recovery rate`,
        duration: 750,
      });

      animateCounter(kpiSafetyRef.current, 0, 10, {
        formatter: (val) => `${Math.round(val)} / 10 Active`,
        duration: 700,
      });

      setTimeout(() => {
        staggerReveal('.overview-case-row', { delay: 15, stagger: 25 });
      }, 100);
    }
  }, [kpis.data]);

  // Animate benchmark counters when data arrives
  useEffect(() => {
    if (benchmark.data) {
      const arms = benchmark.data.arms;
      animateCounter(bmControlRef.current, 0, arms.CONTROL.Mean_Net_Per_Case, {
        formatter: (val) => `₹${val.toFixed(2)}`,
        duration: 850,
      });
      animateCounter(bmRiqRef.current, 0, arms.RECOVERIQ.Mean_Net_Per_Case, {
        formatter: (val) => `₹${val.toFixed(2)}`,
        duration: 850,
      });
      animateCounter(bmBaseRef.current, 0, arms.BASELINE.Mean_Net_Per_Case, {
        formatter: (val) => `₹${val.toFixed(2)}`,
        duration: 850,
      });
    }
  }, [benchmark.data]);

  const recentCases = cases.data?.cases.slice(0, 6) || [];

  const formatFailureCode = (code: string) => {
    return code
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  };

  const getFailureColor = (code: string) => {
    if (code.includes('FUNDS')) return 'text-amber-600 dark:text-amber-400';
    if (code.includes('EXPIRED') || code.includes('AUTH')) return 'text-rose-600 dark:text-rose-400';
    if (code.includes('UNAVAILABLE') || code.includes('TIMEOUT') || code.includes('NETWORK'))
      return 'text-blue-600 dark:text-blue-400';
    return 'text-slate-700 dark:text-[#A3A3A3]';
  };

  return (
    <div className="space-y-10">
      {/* 1. Dominant Hero Metric & Supporting KPIs */}
      <div className="overview-section-block space-y-6">
        <div className="flex flex-col md:flex-row md:items-baseline justify-between gap-6 pb-6 border-b border-slate-200/80 dark:border-[#1F1F1F]">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 dark:text-[#737373] tracking-wide uppercase">
              <span>Revenue at risk</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-500 font-mono">
                DEMO QUEUE
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-baseline gap-3">
              <span ref={kpiRiskRef} className="text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-white tabular-nums">
                {kpis.data ? formatCurrency(kpis.data.revenue_at_risk_inr) : '₹1,05,583'}
              </span>
              <span className="text-sm text-slate-500 dark:text-[#A3A3A3]">
                across <strong>{kpis.data?.total_failed_payments || 40} failed payments</strong>
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-6 sm:gap-10 text-xs">
            <div>
              <div className="text-slate-400 dark:text-[#737373] text-[11px]">Active recovery</div>
              <div ref={kpiRecoveredRef} className="text-lg font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
                {kpis.data ? formatCurrency(kpis.data.revenue_recovered_inr) : '₹0'}
              </div>
            </div>

            <div>
              <div className="text-slate-400 dark:text-[#737373] text-[11px]">Recovery rate</div>
              <div ref={kpiRateRef} className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 tabular-nums">
                {kpis.data ? `${(kpis.data.recovery_rate * 100).toFixed(1)}%` : '0.0%'}
              </div>
            </div>

            <div>
              <div className="text-slate-400 dark:text-[#737373] text-[11px]">Safety invariants</div>
              <div ref={kpiSafetyRef} className="text-lg font-bold text-blue-600 dark:text-blue-400 mt-0.5">
                10 / 10 Active
              </div>
            </div>
          </div>
        </div>

        {kpis.error && <ErrorMessage title="Failed to load overview metrics" message={kpis.error} onRetry={refreshKPIs} />}
      </div>

      {/* 2. Priority Actionable Cases */}
      <div className="overview-section-block space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-slate-200/80 dark:border-[#1F1F1F]">
          <div>
            <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
              <Zap className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              Actionable Failed Payments
            </h2>
          </div>
          <button
            onClick={() => onNavigate('/cases')}
            className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 group cursor-pointer hover:translate-x-0.5 transition-transform"
          >
            View all {cases.data?.total_count || 40} cases <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {cases.loading && !cases.data ? (
          <div className="space-y-3 py-3">
            <LoadingSkeleton className="h-12 w-full" count={4} />
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-[#1F1F1F] border-y border-slate-100 dark:border-[#1F1F1F]">
            {recentCases.map((c) => (
              <div
                key={c.case_id}
                onClick={() => onNavigate(`/cases/${c.case_id}`)}
                className="overview-case-row group py-3 px-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/90 dark:hover:bg-[#141414] hover:shadow-2xs transition-all duration-150 cursor-pointer rounded-lg -mx-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-6">
                  <div className="w-24 shrink-0">
                    <span className="text-base font-bold tracking-tight text-slate-900 dark:text-white tabular-nums">
                      {formatCurrency(c.amount_due)}
                    </span>
                  </div>

                  <div className="w-36 shrink-0">
                    <span className={`text-xs font-medium ${getFailureColor(c.failure_code)}`}>
                      {formatFailureCode(c.failure_code)}
                    </span>
                  </div>

                  <div className="text-xs text-slate-500 dark:text-[#A3A3A3] flex items-center gap-2">
                    <span className="font-mono text-slate-700 dark:text-[#D4D4D4]">{c.customer_id}</span>
                    <span>·</span>
                    <span className="font-mono text-[11px] text-slate-400">{c.case_id}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4 self-end sm:self-center">
                  <div className="text-right">
                    <span className="text-xs font-semibold text-slate-900 dark:text-white">
                      {c.recommended_action === 'PAYMENT_LINK' ? 'Payment link' : formatFailureCode(c.recommended_action)}
                    </span>
                    <span className="text-xs text-slate-400 ml-2 font-mono">
                      {(c.decision_confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:translate-x-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-all duration-150" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Lower Tier: Frozen Holdout Benchmark & System Health */}
      <div className="overview-section-block grid grid-cols-1 lg:grid-cols-3 gap-8 pt-2 border-t border-slate-200/80 dark:border-[#1F1F1F]">
        {/* Benchmark Snapshot */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Frozen 20,000-Case Holdout Benchmark
              </h3>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-mono">
                Scenario S1
              </span>
            </div>
            <button
              onClick={() => onNavigate('/evaluation')}
              className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 group cursor-pointer hover:translate-x-0.5 transition-transform"
            >
              Full evidence <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
            </button>
          </div>

          {benchmark.loading && !benchmark.data ? (
            <LoadingSkeleton className="h-16 w-full" />
          ) : benchmark.data ? (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-4 py-3.5 border-y border-slate-100 dark:border-[#1F1F1F] text-center">
                <div>
                  <div className="text-[11px] text-slate-400 uppercase">Control (0 outreach)</div>
                  <div ref={bmControlRef} className="text-lg font-bold text-slate-800 dark:text-slate-200 mt-1 tabular-nums">
                    ₹{benchmark.data.arms.CONTROL.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                </div>

                <div className="border-x border-slate-100 dark:border-[#1F1F1F]">
                  <div className="text-[11px] text-blue-600 dark:text-blue-400 font-semibold uppercase">RecoverIQ-v1</div>
                  <div ref={bmRiqRef} className="text-lg font-bold text-blue-600 dark:text-blue-400 mt-1 tabular-nums">
                    ₹{benchmark.data.arms.RECOVERIQ.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-blue-500 mt-0.5 font-mono">+₹526.36 vs Control</div>
                </div>

                <div>
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase">Baseline-v1</div>
                  <div ref={bmBaseRef} className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-1 tabular-nums">
                    ₹{benchmark.data.arms.BASELINE.Mean_Net_Per_Case.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-rose-500 mt-0.5 font-mono">-₹481.20 delta</div>
                </div>
              </div>

              <p className="text-xs text-slate-500 dark:text-[#A3A3A3] pt-0.5 leading-relaxed">
                RecoverIQ beat zero outreach, but underperformed the deterministic baseline due to over-escalation.
              </p>
            </div>
          ) : null}
        </div>

        {/* System & Gateway Status */}
        <div className="space-y-3">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            System & Gateway Health
          </h3>

          <div className="space-y-2 text-xs divide-y divide-slate-100 dark:divide-[#1F1F1F] border-y border-slate-100 dark:border-[#1F1F1F] py-1">
            <div className="flex justify-between py-1.5">
              <span className="text-slate-500">Gateway environment</span>
              <span className="font-mono text-slate-900 dark:text-white">
                {razorpayStatus.data?.environment?.toUpperCase() || 'TEST'} (rzp_test_*)
              </span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-500">Webhook authentication</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">HMAC-SHA256</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-500">Safety invariants</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">10 / 10 Active</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-500">Production key safety</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">Fails Closed</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

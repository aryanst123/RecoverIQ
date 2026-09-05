import React, { useState, useEffect } from 'react';
import {
  Search,
  RefreshCw,
  ArrowRight,
  Inbox,
} from 'lucide-react';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorMessage } from '../components/common/ErrorMessage';
import { useRecoverIQData } from '../context/useRecoverIQData';
import { staggerReveal } from '../utils/motion';

interface CasesProps {
  onNavigate: (path: string) => void;
}

export const Cases: React.FC<CasesProps> = ({ onNavigate }) => {
  const { cases, kpis, refreshCases } = useRecoverIQData();

  // Filter states
  const [stateFilter, setStateFilter] = useState<string>('');
  const [failureCodeFilter, setFailureCodeFilter] = useState<string>('');
  const [segmentFilter, setSegmentFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Track initial mount and previous filter states
  const isInitialMount = React.useRef(true);
  const lastAnimatedFingerprint = React.useRef<string>('');

  // Only fetch if cached data is missing or if filters are actively applied
  useEffect(() => {
    const hasActiveFilters = Boolean(stateFilter || failureCodeFilter || segmentFilter);

    if (isInitialMount.current) {
      isInitialMount.current = false;
      // Skip redundant initial fetch if cached data is already present and no filters are active
      if (cases.data && !hasActiveFilters) {
        return;
      }
    }

    refreshCases({
      state_filter: stateFilter || undefined,
      failure_code: failureCodeFilter || undefined,
      segment: segmentFilter || undefined,
      limit: 100,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateFilter, failureCodeFilter, segmentFilter]);

  // Animate queue items on initial entry or when case set genuinely changes
  useEffect(() => {
    if (cases.data?.cases && cases.data.cases.length > 0) {
      const fingerprint = cases.data.cases.map((c) => c.case_id).join(',');
      if (fingerprint !== lastAnimatedFingerprint.current) {
        lastAnimatedFingerprint.current = fingerprint;
        setTimeout(() => {
          staggerReveal('.queue-item-row', { delay: 15, stagger: 20 });
        }, 20);
      }
    }
  }, [cases.data]);

  const allCases = cases.data?.cases || [];
  const filteredCases = allCases.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.case_id.toLowerCase().includes(q) ||
      c.customer_id.toLowerCase().includes(q) ||
      c.payment_id.toLowerCase().includes(q) ||
      c.failure_code.toLowerCase().includes(q)
    );
  });

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  const formatFailureCode = (code: string) => {
    return code
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  };

  const formatSegment = (seg: string) => {
    return seg
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
    <div className="space-y-6">
      {/* 1. Header & Operational Summary */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-5 border-b border-slate-200/80 dark:border-[#1F1F1F]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Recovery Queue
            </h1>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-500 font-mono">
              DEMO QUEUE
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-1">
            <strong>{cases.data?.total_count || 0} failed payments</strong> requiring adaptive decisioning · {kpis.data ? formatCurrency(kpis.data.revenue_at_risk_inr) : '₹1,05,583'} total at risk
          </p>
        </div>

        {/* Lightweight Filter Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2 text-slate-400" />
            <input
              type="text"
              placeholder="Search cases or customers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500 w-48 sm:w-56 transition-all"
            />
          </div>

          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs text-slate-700 dark:text-[#D4D4D4] focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
          >
            <option value="">All States</option>
            <option value="RECOVERY_ELIGIBLE">Eligible</option>
            <option value="RECOVERED">Recovered</option>
            <option value="STOPPED">Stopped</option>
            <option value="MANUAL_REVIEW_REQUIRED">Manual Review</option>
          </select>

          <select
            value={failureCodeFilter}
            onChange={(e) => setFailureCodeFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs text-slate-700 dark:text-[#D4D4D4] focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
          >
            <option value="">All Failures</option>
            <option value="INSUFFICIENT_FUNDS">Insufficient funds</option>
            <option value="CARD_EXPIRED">Card expired</option>
            <option value="BANK_UNAVAILABLE">Bank unavailable</option>
            <option value="NETWORK_TIMEOUT">Network timeout</option>
          </select>

          <select
            value={segmentFilter}
            onChange={(e) => setSegmentFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs text-slate-700 dark:text-[#D4D4D4] focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
          >
            <option value="">All Segments</option>
            <option value="HIGH_VALUE">High value</option>
            <option value="STANDARD">Standard</option>
            <option value="NEW">New</option>
          </select>

          <button
            onClick={() =>
              refreshCases({
                state_filter: stateFilter || undefined,
                failure_code: failureCodeFilter || undefined,
                segment: segmentFilter || undefined,
                limit: 100,
              })
            }
            className="p-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-slate-600 dark:text-[#A3A3A3] hover:bg-slate-50 dark:hover:bg-[#1A1A1A] transition-colors cursor-pointer"
            title="Refresh cases queue"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${cases.loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 2. Operational Feed */}
      {cases.loading && !cases.data ? (
        <div className="space-y-3 py-3">
          <LoadingSkeleton className="h-14 w-full" count={6} />
        </div>
      ) : cases.error && !cases.data ? (
        <ErrorMessage
          title="Recovery queue unavailable"
          message={cases.error}
          onRetry={refreshCases}
        />
      ) : filteredCases.length === 0 ? (
        <div className="py-20 text-center text-xs text-slate-400 space-y-1">
          <Inbox className="w-8 h-8 text-slate-300 dark:text-[#333] mx-auto" />
          <div>No payment failure cases match the selected filters.</div>
        </div>
      ) : (
        <div className="divide-y divide-slate-100 dark:divide-[#1F1F1F] border-y border-slate-100 dark:border-[#1F1F1F]">
          {filteredCases.map((c) => {
            const isDemoCase = c.case_id.includes('DEMO');
            return (
              <div
                key={c.case_id}
                onClick={() => onNavigate(`/cases/${c.case_id}`)}
                className={`queue-item-row group py-3.5 px-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/90 dark:hover:bg-[#141414] hover:shadow-2xs transition-all duration-150 cursor-pointer rounded-lg -mx-3.5 ${
                  isDemoCase ? 'bg-blue-50/30 dark:bg-blue-950/10 border-l-2 border-blue-500' : ''
                }`}
              >
                {/* Left & Middle Column */}
                <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-6">
                  <div className="w-28 shrink-0">
                    <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white tabular-nums">
                      {formatCurrency(c.amount_due)}
                    </span>
                  </div>

                  <div className="w-40 shrink-0">
                    <span className={`text-xs font-semibold ${getFailureColor(c.failure_code)}`}>
                      {formatFailureCode(c.failure_code)}
                    </span>
                  </div>

                  <div className="text-xs text-slate-500 dark:text-[#A3A3A3] flex flex-wrap items-center gap-2">
                    {isDemoCase && (
                      <>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 font-bold">
                          DEMO
                        </span>
                        <span>·</span>
                      </>
                    )}
                    <span className="font-mono text-slate-700 dark:text-[#D4D4D4]">{c.customer_id}</span>
                    <span>·</span>
                    <span className="font-mono text-[11px] text-slate-400">{c.case_id}</span>
                    <span>·</span>
                    <span>{formatSegment(c.customer_segment)}</span>
                    <span>·</span>
                    <span>{c.hours_since_failure.toFixed(0)}h elapsed</span>
                    <span>·</span>
                    <span>{c.automated_actions_count}/3 touches</span>
                    {c.current_state !== 'RECOVERY_ELIGIBLE' && (
                      <>
                        <span>·</span>
                        <span className="text-blue-600 dark:text-blue-400 font-medium">{c.current_state}</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Right Column */}
                <div className="flex items-center gap-4 self-end sm:self-center">
                  <div className="text-right">
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      {c.recommended_action === 'PAYMENT_LINK' ? 'Payment link' : formatFailureCode(c.recommended_action)}
                    </span>
                    <span className="text-xs text-slate-400 ml-2 font-mono">
                      {(c.decision_confidence * 100).toFixed(0)}%
                    </span>
                  </div>

                  <ArrowRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-all duration-150" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

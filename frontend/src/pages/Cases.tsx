import React, { useEffect, useState } from 'react';
import {
  Search,
  Filter,
  RefreshCw,
  ChevronRight,
  AlertCircle,
  Clock,
  ArrowUpDown,
  ExternalLink,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { api } from '../api/client';
import { CaseSummary } from '../types';

interface CasesProps {
  onNavigate: (path: string) => void;
}

export const Cases: React.FC<CasesProps> = ({ onNavigate }) => {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters
  const [stateFilter, setStateFilter] = useState<string>('');
  const [failureCodeFilter, setFailureCodeFilter] = useState<string>('');
  const [segmentFilter, setSegmentFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const loadCases = () => {
    setLoading(true);
    api.getCases({
      state_filter: stateFilter || undefined,
      failure_code: failureCodeFilter || undefined,
      segment: segmentFilter || undefined,
      limit: 100,
    })
      .then((res) => {
        setCases(res.cases);
        setTotalCount(res.total_count);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCases();
  }, [stateFilter, failureCodeFilter, segmentFilter]);

  const filteredCases = cases.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return c.case_id.toLowerCase().includes(q) || c.customer_id.toLowerCase().includes(q) || c.payment_id.toLowerCase().includes(q);
  });

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            Recovery Cases Queue
            <Badge variant="simulator">DEMO CASES ({totalCount})</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Operational failed-payment queue. Inspect individual cases, causal decision economics, and trigger test recoveries.
          </p>
        </div>
        <button
          onClick={loadCases}
          className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors flex items-center gap-1.5 self-start sm:self-auto shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filters Bar */}
      <Card bodyClassName="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search Case ID or Customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* State Filter */}
          <div>
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Case States</option>
              <option value="RECOVERY_ELIGIBLE">RECOVERY_ELIGIBLE</option>
              <option value="RECOVERED">RECOVERED</option>
              <option value="STOPPED">STOPPED</option>
              <option value="MANUAL_REVIEW_REQUIRED">MANUAL_REVIEW_REQUIRED</option>
            </select>
          </div>

          {/* Failure Code Filter */}
          <div>
            <select
              value={failureCodeFilter}
              onChange={(e) => setFailureCodeFilter(e.target.value)}
              className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Failure Codes</option>
              <option value="INSUFFICIENT_FUNDS">INSUFFICIENT_FUNDS</option>
              <option value="CARD_EXPIRED">CARD_EXPIRED</option>
              <option value="BANK_UNAVAILABLE">BANK_UNAVAILABLE</option>
              <option value="NETWORK_TIMEOUT">NETWORK_TIMEOUT</option>
            </select>
          </div>

          {/* Customer Segment Filter */}
          <div>
            <select
              value={segmentFilter}
              onChange={(e) => setSegmentFilter(e.target.value)}
              className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Customer Segments</option>
              <option value="HIGH_VALUE">HIGH_VALUE</option>
              <option value="STANDARD">STANDARD</option>
              <option value="NEW">NEW</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Main Cases Table */}
      <Card bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 text-slate-500 font-mono uppercase text-[10px]">
                <th className="py-3 px-4">Case ID</th>
                <th className="py-3 px-4">Customer</th>
                <th className="py-3 px-4">Amount</th>
                <th className="py-3 px-4">Failure Code</th>
                <th className="py-3 px-4">Time Since Failure</th>
                <th className="py-3 px-4">Attempts</th>
                <th className="py-3 px-4">Current State</th>
                <th className="py-3 px-4">Recommended Action</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {filteredCases.map((c) => (
                <tr
                  key={c.case_id}
                  onClick={() => onNavigate(`/cases/${c.case_id}`)}
                  className="hover:bg-slate-50/80 dark:hover:bg-slate-900/40 transition-colors cursor-pointer"
                >
                  <td className="py-3.5 px-4 font-mono font-semibold text-slate-900 dark:text-white">
                    {c.case_id}
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="font-medium text-slate-800 dark:text-slate-200">{c.customer_id}</div>
                    <div className="text-[10px] text-slate-400 font-mono">{c.customer_segment}</div>
                  </td>
                  <td className="py-3.5 px-4 font-mono font-bold text-slate-900 dark:text-white">
                    {formatCurrency(c.amount_due)}
                  </td>
                  <td className="py-3.5 px-4">
                    <Badge variant="warning">{c.failure_code}</Badge>
                  </td>
                  <td className="py-3.5 px-4 text-slate-600 dark:text-slate-400 font-mono">
                    {c.hours_since_failure.toFixed(1)}h ago
                  </td>
                  <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                    {c.attempts_count} att / {c.automated_actions_count} act
                  </td>
                  <td className="py-3.5 px-4">
                    <Badge
                      variant={
                        c.current_state === 'RECOVERED'
                          ? 'success'
                          : c.current_state === 'STOPPED'
                          ? 'default'
                          : c.current_state === 'MANUAL_REVIEW_REQUIRED'
                          ? 'danger'
                          : 'info'
                      }
                    >
                      {c.current_state}
                    </Badge>
                  </td>
                  <td className="py-3.5 px-4">
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
                  <td className="py-3.5 px-4 font-mono font-medium text-slate-700 dark:text-slate-300">
                    {(c.decision_confidence * 100).toFixed(0)}%
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate(`/cases/${c.case_id}`);
                      }}
                      className="px-2.5 py-1 rounded bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors text-xs font-semibold"
                    >
                      Inspect →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredCases.length === 0 && !loading && (
            <div className="py-12 text-center text-xs text-slate-400">
              No failed payment cases matched the selected filter criteria.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};

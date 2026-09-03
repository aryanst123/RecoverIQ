import React, { useEffect, useState } from 'react';
import {
  ArrowLeft,
  DollarSign,
  User,
  CreditCard,
  Clock,
  Sparkles,
  Link,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Send,
  ExternalLink,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { api } from '../api/client';
import { CaseDetail as CaseDetailType, PromiseExtractionResult } from '../types';

interface CaseDetailProps {
  caseId: string;
  onNavigate: (path: string) => void;
}

export const CaseDetail: React.FC<CaseDetailProps> = ({ caseId, onNavigate }) => {
  const [detail, setDetail] = useState<CaseDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [inboundMessage, setInboundMessage] = useState('');
  const [extractionResult, setExtractionResult] = useState<PromiseExtractionResult | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [webhookProcessing, setWebhookProcessing] = useState(false);

  const loadCase = () => {
    setLoading(true);
    api.getCaseDetail(caseId)
      .then(setDetail)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCase();
  }, [caseId]);

  const handleExecuteAction = (actionType: string) => {
    setExecuting(true);
    api.executeAction(caseId, actionType)
      .then((res) => {
        loadCase();
      })
      .catch((err) => {
        alert(`Execution failed: ${err.message}`);
      })
      .finally(() => setExecuting(false));
  };

  const handleExtractCustomerContext = () => {
    if (!inboundMessage.trim()) return;
    api.extractPromise(inboundMessage)
      .then(setExtractionResult)
      .catch(console.error);
  };

  const handleSimulatePaymentCapture = () => {
    if (!detail) return;
    setWebhookProcessing(true);
    const mockPayload = {
      event: 'payment.captured',
      payload: {
        payment: {
          entity: {
            id: detail.payment?.payment_id || `pay_test_${caseId}`,
            amount: Math.round(detail.case.amount_due * 100),
            currency: 'INR',
            status: 'captured',
          },
        },
      },
    };
    api.simulateWebhook('payment.captured', mockPayload)
      .then((res) => {
        loadCase();
      })
      .catch((err) => alert(`Webhook processing error: ${err.message}`))
      .finally(() => setWebhookProcessing(false));
  };

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  if (loading || !detail) {
    return (
      <div className="py-20 text-center text-xs text-slate-500">
        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-500" />
        Loading case workspace for {caseId}...
      </div>
    );
  }

  const { case: c, customer, payment, latest_attempt, decision_trace, audit_records, payment_link } = detail;

  return (
    <div className="space-y-6">
      {/* Back Button & Top Case Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => onNavigate('/cases')}
            className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold font-mono text-slate-900 dark:text-white">
                Case #{c.case_id}
              </h2>
              <Badge
                variant={
                  c.current_state === 'RECOVERED'
                    ? 'success'
                    : c.current_state === 'STOPPED'
                    ? 'default'
                    : c.current_state === 'MANUAL_REVIEW_REQUIRED'
                    ? 'danger'
                    : 'primary'
                }
              >
                {c.current_state}
              </Badge>
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Payment ID: <span className="font-mono">{c.payment_id}</span> | Customer:{' '}
              <span className="font-mono">{c.customer_id}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {c.current_state !== 'RECOVERED' && (
            <button
              onClick={handleSimulatePaymentCapture}
              disabled={webhookProcessing}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              {webhookProcessing ? 'Reconciling...' : 'Simulate Customer Payment'}
            </button>
          )}
          <button
            onClick={loadCase}
            className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Case Overview Metrics Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card bodyClassName="p-4">
          <div className="text-[10px] font-mono font-semibold uppercase text-slate-400">Total Amount Due</div>
          <div className="text-xl font-bold font-mono text-slate-900 dark:text-white mt-1">
            {formatCurrency(c.amount_due)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Original transaction amount</div>
        </Card>

        <Card bodyClassName="p-4">
          <div className="text-[10px] font-mono font-semibold uppercase text-slate-400">Residual Amount</div>
          <div className="text-xl font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
            {formatCurrency(c.residual_amount)}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            {c.residual_amount === 0 ? '✓ Fully recovered' : 'Unrecovered balance'}
          </div>
        </Card>

        <Card bodyClassName="p-4">
          <div className="text-[10px] font-mono font-semibold uppercase text-slate-400">Failure Reason</div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white mt-1 flex items-center gap-1.5">
            <Badge variant="warning">{latest_attempt?.failure_code || 'FAILURE'}</Badge>
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">{latest_attempt?.failure_reason}</div>
        </Card>

        <Card bodyClassName="p-4">
          <div className="text-[10px] font-mono font-semibold uppercase text-slate-400">Customer Segment</div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white mt-1">
            {customer?.segment || 'STANDARD'}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Channel: {customer?.channel_preference || 'WHATSAPP'}</div>
        </Card>
      </div>

      {/* Main Grid: Decision Engine & Execution Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Decision Engine & Economics Table */}
        <div className="lg:col-span-2 space-y-6">
          {/* Decision Engine Recommended Action Banner */}
          <Card
            title="RecoverIQ Adaptive Decision Engine"
            subtitle={`Policy version: ${decision_trace.recommended?.policy_version || 'recoveriq-v1'}`}
            badge={<Badge variant="primary">CAUSAL DECISION TRACE</Badge>}
          >
            {decision_trace.recommended ? (
              <div className="space-y-4">
                <div className="p-4 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/60 dark:bg-blue-950/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <div className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider font-mono">
                      Optimal Selected Action
                    </div>
                    <div className="text-2xl font-bold font-mono text-slate-900 dark:text-white mt-1">
                      {decision_trace.recommended.selected_action}
                    </div>
                    <div className="text-xs text-slate-600 dark:text-slate-300 mt-1">
                      {decision_trace.recommended.explanation}
                    </div>
                  </div>

                  <div className="text-right sm:border-l sm:border-blue-200 dark:sm:border-blue-900/60 sm:pl-4">
                    <div className="text-[10px] font-mono uppercase text-slate-400">Decision Confidence</div>
                    <div className="text-lg font-bold font-mono text-slate-900 dark:text-white mt-0.5">
                      {(decision_trace.recommended.confidence * 100).toFixed(0)}%
                    </div>
                    <div className="text-[10px] text-slate-500">
                      Expected Net: {formatCurrency(decision_trace.recommended.expected_net_recovery)}
                    </div>
                  </div>
                </div>

                {/* Candidate Action Economics Comparison Table */}
                <div>
                  <div className="text-xs font-semibold text-slate-900 dark:text-white mb-2">
                    Candidate Action Economics (E[Net] = &tau; &middot; Amount - Costs)
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 font-mono text-[10px] uppercase">
                          <th className="py-2 px-2">Action</th>
                          <th className="py-2 px-2">Eligible</th>
                          <th className="py-2 px-2">Prob P(Y)</th>
                          <th className="py-2 px-2">Causal Uplift $\tau$</th>
                          <th className="py-2 px-2">Exp Gross</th>
                          <th className="py-2 px-2">Cost + Fric</th>
                          <th className="py-2 px-2 font-bold">Exp Net</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                        {decision_trace.evaluations.map((ev) => {
                          const isSelected = ev.action === decision_trace.recommended?.selected_action;
                          return (
                            <tr
                              key={ev.action}
                              className={`transition-colors ${
                                isSelected ? 'bg-blue-50/50 dark:bg-blue-950/20 font-semibold' : ''
                              }`}
                            >
                              <td className="py-2.5 px-2 font-mono flex items-center gap-1.5">
                                {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
                                {ev.action}
                              </td>
                              <td className="py-2.5 px-2">
                                {ev.is_eligible ? (
                                  <span className="text-emerald-600 dark:text-emerald-400 font-mono text-[11px]">✓ Yes</span>
                                ) : (
                                  <span className="text-rose-500 font-mono text-[10px]">{ev.rejection_reason || 'Ineligible'}</span>
                                )}
                              </td>
                              <td className="py-2.5 px-2 font-mono text-slate-600 dark:text-slate-300">
                                {(ev.predicted_probability * 100).toFixed(1)}%
                              </td>
                              <td className="py-2.5 px-2 font-mono text-blue-600 dark:text-blue-400">
                                {ev.incremental_uplift_tau >= 0 ? '+' : ''}
                                {(ev.incremental_uplift_tau * 100).toFixed(1)}%
                              </td>
                              <td className="py-2.5 px-2 font-mono text-slate-600 dark:text-slate-300">
                                {formatCurrency(ev.expected_incremental_revenue)}
                              </td>
                              <td className="py-2.5 px-2 font-mono text-slate-500">
                                ₹{ev.action_cost + ev.friction_cost}
                              </td>
                              <td className="py-2.5 px-2 font-mono font-bold text-slate-900 dark:text-white">
                                {formatCurrency(ev.expected_net_recovery)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Bounded Execution Trigger */}
                {c.current_state !== 'RECOVERED' && c.current_state !== 'STOPPED' && (
                  <div className="pt-2 flex items-center gap-3">
                    <button
                      onClick={() => handleExecuteAction(decision_trace.recommended!.selected_action)}
                      disabled={executing}
                      className="px-4 py-2 rounded-lg bg-[#0C2340] dark:bg-blue-600 text-white text-xs font-semibold hover:bg-slate-800 dark:hover:bg-blue-700 transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                    >
                      <Send className="w-3.5 h-3.5" />
                      {executing ? 'Executing with Bounded Lock...' : `Execute ${decision_trace.recommended.selected_action}`}
                    </button>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Case Lock + Atomic Reservation Enforced
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-500 py-6 text-center">No decision trace available</div>
            )}
          </Card>

          {/* Immutable Audit Trail */}
          <Card
            title="Immutable Case Audit Ledger"
            subtitle="Cryptographically verified event history and state machine transitions"
            badge={<Badge variant="default">AUDIT LOG</Badge>}
          >
            <div className="space-y-3">
              {audit_records.map((rec, idx) => (
                <div
                  key={rec.audit_id || idx}
                  className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 text-xs font-mono space-y-1"
                >
                  <div className="flex items-center justify-between text-slate-500 text-[10px]">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{rec.event_type}</span>
                    <span>{new Date(rec.timestamp).toLocaleString()}</span>
                  </div>
                  <div className="text-[11px] text-slate-600 dark:text-slate-400">
                    Actor: <span className="text-slate-800 dark:text-slate-200">{rec.actor}</span>
                    {rec.action_type && (
                      <span> | Action: <span className="text-blue-500 font-bold">{rec.action_type}</span></span>
                    )}
                  </div>
                  {rec.metadata && Object.keys(rec.metadata).length > 0 && (
                    <div className="text-[10px] text-slate-400 bg-white dark:bg-slate-950 p-1.5 rounded border border-slate-100 dark:border-slate-800/60 overflow-x-auto">
                      {JSON.stringify(rec.metadata)}
                    </div>
                  )}
                </div>
              ))}
              {audit_records.length === 0 && (
                <div className="text-xs text-slate-400 py-4 text-center">No audit records logged yet.</div>
              )}
            </div>
          </Card>
        </div>

        {/* Right 1 Col: Razorpay Payment Link & Customer Context Extraction */}
        <div className="space-y-6">
          {/* Active Payment Link Card */}
          <Card
            title="Razorpay Payment Link"
            subtitle="Generated via Test Mode Client"
            badge={
              <Badge variant={payment_link ? 'success' : 'default'}>
                {payment_link ? 'ACTIVE LINK' : 'NOT CREATED'}
              </Badge>
            }
          >
            {payment_link ? (
              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/20 space-y-1.5">
                  <div className="text-[10px] font-mono text-emerald-600 uppercase font-semibold">Short URL</div>
                  <div className="font-mono font-bold text-slate-900 dark:text-white break-all">
                    {payment_link.short_url}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Amount: {formatCurrency(payment_link.amount_inr || c.amount_due)}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(payment_link.short_url);
                      setCopiedLink(true);
                      setTimeout(() => setCopiedLink(false), 2000);
                    }}
                    className="flex-1 py-1.5 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    {copiedLink ? 'Copied' : 'Copy Link'}
                  </button>
                  <a
                    href={payment_link.short_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 py-1.5 px-3 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Open Page
                  </a>
                </div>
              </div>
            ) : (
              <div className="text-center py-6 space-y-3 text-xs text-slate-500">
                <p>No active Razorpay recovery link created for this case.</p>
                {c.current_state !== 'RECOVERED' && (
                  <button
                    onClick={() => handleExecuteAction('PAYMENT_LINK')}
                    disabled={executing}
                    className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors text-xs"
                  >
                    Generate Payment Link
                  </button>
                )}
              </div>
            )}
          </Card>

          {/* Interactive Customer Context Extraction (LLM Sandbox) */}
          <Card
            title="Inbound Customer Message"
            subtitle="Simulate LLM context extraction & Promise-to-Pay detection"
            badge={<Badge variant="simulator">LLM SANDBOX</Badge>}
          >
            <div className="space-y-3 text-xs">
              <textarea
                rows={3}
                placeholder="e.g., 'I will pay tomorrow at 6 PM, please pause reminders.'"
                value={inboundMessage}
                onChange={(e) => setInboundMessage(e.target.value)}
                className="w-full p-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <button
                onClick={handleExtractCustomerContext}
                disabled={!inboundMessage.trim()}
                className="w-full py-2 rounded-lg bg-[#0C2340] dark:bg-blue-600 text-white font-semibold hover:bg-slate-800 dark:hover:bg-blue-700 transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Extract Structured Context
              </button>

              {extractionResult && (
                <div className="mt-3 p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-slate-900/60 font-mono text-[11px] space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Intent:</span>
                    <span className="font-bold text-slate-900 dark:text-white">{extractionResult.intent}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Promise Exists:</span>
                    <span className={extractionResult.has_promise ? 'text-emerald-500 font-bold' : 'text-slate-400'}>
                      {extractionResult.has_promise ? 'YES' : 'NO'}
                    </span>
                  </div>
                  {extractionResult.promised_date && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Normalized Date:</span>
                      <span className="text-blue-400">{extractionResult.promised_date}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-slate-500">Confidence:</span>
                    <span>{(extractionResult.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                  <div className="pt-2 border-t border-slate-200 dark:border-slate-800 text-[10px] text-emerald-600 dark:text-emerald-400 font-sans">
                    ✓ Policy Effect: {extractionResult.policy_effect.outreach_paused ? 'Outreach paused until promised date' : 'Standard outreach maintained'}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

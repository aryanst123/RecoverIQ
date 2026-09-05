import React, { useEffect, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Send,
  ExternalLink,
  RefreshCw,
  Copy,
  Check,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  AlertCircle,
  Sliders,
  FileCheck,
  Cpu,
  Layers,
  Clock,
  Lock,
} from 'lucide-react';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorMessage } from '../components/common/ErrorMessage';
import { useToast } from '../context/useToast';
import { api } from '../api/client';
import { CaseDetail as CaseDetailType, PromiseExtractionResult } from '../types';
import { animatePipelineStages, staggerReveal } from '../utils/motion';

interface CaseDetailProps {
  caseId: string;
  onNavigate: (path: string) => void;
}

export const CaseDetail: React.FC<CaseDetailProps> = ({ caseId, onNavigate }) => {
  const { showToast } = useToast();
  const [detail, setDetail] = useState<CaseDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [inboundMessage, setInboundMessage] = useState('');
  const [extractionResult, setExtractionResult] = useState<PromiseExtractionResult | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [webhookProcessing, setWebhookProcessing] = useState(false);

  // Progressive Disclosure State (Collapsible technical depths)
  const [showEconomics, setShowEconomics] = useState(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const [showAuditTrail, setShowAuditTrail] = useState(false);

  // Review / Override Modal State
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [selectedOverrideAction, setSelectedOverrideAction] = useState<string>('');
  const [overrideReason, setOverrideReason] = useState<string>('');

  const loadCase = () => {
    setLoading(true);
    setError(null);
    api.getCaseDetail(caseId)
      .then((data) => {
        setDetail(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load case detail');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadCase();
  }, [caseId]);

  useEffect(() => {
    if (detail) {
      try {
        staggerReveal('.case-detail-card', { delay: 20, stagger: 40, translateY: 6 });
      } catch (e) {
        console.warn('Animation notice:', e);
      }
    }
  }, [detail]);

  // Handle accordion expansions with smooth animation
  useEffect(() => {
    if (showTechnicalDetails) {
      animatePipelineStages('#pipeline-container', 7);
    }
  }, [showTechnicalDetails]);

  const handleExecuteAction = (actionType: string) => {
    setExecuting(true);
    api.executeAction(caseId, actionType)
      .then(() => {
        showToast(`Action '${actionType}' executed safely`, 'success');
        setShowOverrideModal(false);
        loadCase();
      })
      .catch((err) => {
        showToast(`Action blocked: ${err.message}`, 'error');
      })
      .finally(() => setExecuting(false));
  };

  const handleExtractContext = () => {
    if (!inboundMessage.trim()) return;
    api.extractPromise(inboundMessage)
      .then((res) => {
        setExtractionResult(res);
        showToast('Customer intent extracted via Pydantic schema', 'info');
      })
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
      .then(() => {
        showToast('Payment reconciled: Case state updated to RECOVERED', 'success');
        loadCase();
      })
      .catch((err) => showToast(`Reconciliation error: ${err.message}`, 'error'))
      .finally(() => setWebhookProcessing(false));
  };

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val);

  const formatFailureCode = (code: string) => {
    return code
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  };

  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case 'PAYMENT_LINK':
        return 'bg-blue-600 text-white dark:bg-blue-600';
      case 'STOP':
        return 'bg-slate-700 text-white dark:bg-slate-800';
      case 'REMINDER':
        return 'bg-amber-600 text-white dark:bg-amber-700';
      case 'PROMISE_TO_PAY':
        return 'bg-purple-600 text-white dark:bg-purple-700';
      case 'ESCALATE':
        return 'bg-rose-600 text-white dark:bg-rose-700';
      default:
        return 'bg-slate-800 text-white';
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <LoadingSkeleton className="h-8 w-64" />
        <LoadingSkeleton className="h-40 w-full" />
        <LoadingSkeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4 max-w-5xl mx-auto">
        <button
          onClick={() => onNavigate('/cases')}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white hover:-translate-x-0.5 transition-transform"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to recovery queue
        </button>
        <ErrorMessage title={`Case ${caseId} Unavailable`} message={error || 'Case not found'} onRetry={loadCase} />
      </div>
    );
  }

  const { case: c, customer, latest_attempt, decision_trace, audit_records, payment_link } = detail;
  const isTerminal = c.current_state === 'RECOVERED' || c.current_state === 'STOPPED';
  const recommendedAction = decision_trace.recommended?.selected_action || 'STOP';
  const confidence = decision_trace.recommended?.confidence || 0;

  const pipelineStages = [
    { label: 'Payment failed', desc: `${formatCurrency(c.amount_due)}`, status: 'DONE' },
    { label: 'Diagnosis', desc: formatFailureCode(latest_attempt?.failure_code || 'Analyzed'), status: 'DONE' },
    { label: 'Eligibility', desc: 'Bounds verified', status: 'DONE' },
    { label: 'Economics', desc: 'Causal uplift \u03c4(x)', status: 'DONE' },
    { label: 'Safety', desc: '10 invariants passed', status: 'DONE' },
    { label: 'Decision', desc: recommendedAction, status: 'DONE' },
    { label: 'Settlement', desc: c.current_state, status: isTerminal ? 'DONE' : (payment_link ? 'ACTIVE' : 'PENDING') },
  ];

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* 1. Incident Bar (What happened?) */}
      <div className="case-detail-card flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200/80 dark:border-[#1F1F1F]">
        <div className="flex items-start gap-4">
          <button
            onClick={() => onNavigate('/cases')}
            className="p-2 rounded-md border border-slate-200 dark:border-[#1F1F1F] hover:bg-slate-100 dark:hover:bg-[#1A1A1A] hover:-translate-x-0.5 text-slate-500 transition-all duration-150 mt-1 cursor-pointer"
            title="Back to recovery queue"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white tabular-nums">
                {formatCurrency(c.amount_due)}
              </span>
              <span className="text-xs px-2 py-0.5 rounded font-semibold bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border border-rose-200/60 dark:border-rose-900/40">
                PAYMENT FAILED
              </span>
              <span className="text-sm text-slate-400">·</span>
              <span className="text-sm font-medium text-slate-700 dark:text-[#A3A3A3]">
                {formatFailureCode(latest_attempt?.failure_code || 'GATEWAY_ERROR')}
              </span>
            </div>

            <div className="text-xs text-slate-500 dark:text-[#737373] mt-1.5 flex flex-wrap items-center gap-2">
              <span>Case: <strong className="font-mono text-slate-700 dark:text-[#D4D4D4]">{c.case_id}</strong></span>
              <span>·</span>
              <span>Customer: <strong className="font-mono text-slate-700 dark:text-[#D4D4D4]">{c.customer_id}</strong> ({customer?.segment || 'STANDARD'})</span>
              <span>·</span>
              <span>Touches: {c.automated_action_count}/3</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5 self-start md:self-auto">
          {!isTerminal && (
            <button
              onClick={handleSimulatePaymentCapture}
              disabled={webhookProcessing}
              className="px-3.5 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 hover:-translate-y-0.5 active:translate-y-0 text-white text-xs font-semibold shadow-2xs flex items-center gap-1.5 transition-all duration-150 disabled:opacity-50 cursor-pointer"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              {webhookProcessing ? 'Reconciling...' : 'Simulate Customer Payment'}
            </button>
          )}
          <button
            onClick={loadCase}
            className="p-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-slate-600 dark:text-[#A3A3A3] hover:bg-slate-50 hover:-translate-y-0.5 transition-all duration-150 cursor-pointer"
            title="Refresh case data"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Autonomous Decision Focal Card (What did RecoverIQ decide & Why?) */}
      <div className="case-detail-card p-6 rounded-xl border border-slate-200/90 dark:border-[#1F1F1F] bg-white dark:bg-[#0E0E0E] shadow-sm space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
            <Cpu className="w-4 h-4" />
            <span>RecoverIQ Autonomous Decision</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-900/40">
              <ShieldCheck className="w-3.5 h-3.5" />
              Safety Verified
            </span>
            <span className="text-xs font-mono text-slate-500 dark:text-[#737373]">
              {(confidence * 100).toFixed(0)}% Confidence
            </span>
          </div>
        </div>

        {/* Action Title & Explanation */}
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`px-3 py-1 rounded-md text-base font-bold tracking-tight shadow-xs ${getActionBadgeColor(recommendedAction)}`}>
              {recommendedAction}
            </span>
            <span className="text-xs text-slate-500 dark:text-[#A3A3A3]">
              {recommendedAction === 'STOP' && 'Preserves customer relationship & eliminates cost.'}
              {recommendedAction === 'PAYMENT_LINK' && 'Direct frictionless payment channel.'}
              {recommendedAction === 'REMINDER' && 'Gentle non-intrusive notification.'}
              {recommendedAction === 'PROMISE_TO_PAY' && 'Customer promised future date.'}
              {recommendedAction === 'ESCALATE' && 'Agent outreach for high-value risk.'}
            </span>
          </div>

          <p className="text-sm text-slate-700 dark:text-[#D4D4D4] leading-relaxed pt-1">
            "{decision_trace.recommended?.explanation || 'Optimal expected net recovery evaluated across candidate interventions.'}"
          </p>
        </div>

        {/* Execution Status & Exception Control */}
        <div className="pt-3 border-t border-slate-100 dark:border-[#1A1A1A] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Execution Status:</span>
            {isTerminal ? (
              <span className="font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> {c.current_state}
              </span>
            ) : payment_link ? (
              <span className="font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" /> Link Active · Waiting for payment
              </span>
            ) : (
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                Ready for automated execution
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            {!isTerminal && (
              <>
                <button
                  onClick={() => handleExecuteAction(recommendedAction)}
                  disabled={executing}
                  className="px-3.5 py-1.5 rounded-md bg-[#0C2340] dark:bg-blue-600 hover:bg-slate-800 dark:hover:bg-blue-700 text-white font-semibold text-xs transition-all duration-150 flex items-center gap-1.5 shadow-2xs disabled:opacity-50 cursor-pointer"
                >
                  <Send className="w-3 h-3" />
                  {executing ? 'Executing...' : `Execute ${recommendedAction}`}
                </button>
                <button
                  onClick={() => {
                    setSelectedOverrideAction(recommendedAction);
                    setShowOverrideModal(true);
                  }}
                  className="px-3 py-1.5 rounded-md border border-slate-200 dark:border-[#222] bg-slate-50 dark:bg-[#141414] hover:bg-slate-100 dark:hover:bg-[#1C1C1C] text-slate-700 dark:text-[#D4D4D4] font-medium text-xs transition-colors cursor-pointer"
                >
                  Review / Override
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 3. Recovery Status & Active Link Banner (if link exists) */}
      {payment_link && (
        <div className="case-detail-card p-4 rounded-xl border border-blue-200/70 dark:border-blue-900/40 bg-blue-50/30 dark:bg-blue-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-900 dark:text-white">Active Payment Link:</span>
              <span className="font-mono text-blue-600 dark:text-blue-400">{payment_link.short_url}</span>
            </div>
            <div className="text-slate-500 dark:text-[#A3A3A3] text-[11px]">
              Razorpay Test Mode · Amount: {formatCurrency(payment_link.amount_inr || c.amount_due)}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                navigator.clipboard.writeText(payment_link.short_url);
                setCopiedLink(true);
                showToast('Link copied to clipboard', 'info');
                setTimeout(() => setCopiedLink(false), 2000);
              }}
              className="px-3 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs font-medium text-slate-700 dark:text-[#D4D4D4] hover:bg-slate-50 flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              {copiedLink ? 'Copied' : 'Copy'}
            </button>
            <a
              href={payment_link.short_url}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open Link
            </a>
          </div>
        </div>
      )}

      {/* 4. Progressive Disclosure: Collapsible Technical Sections */}
      <div className="space-y-4 pt-2">
        {/* Accordion 1: Why This Decision? (Candidate Economics) */}
        <div className="rounded-xl border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0E0E0E] overflow-hidden">
          <button
            onClick={() => setShowEconomics(!showEconomics)}
            className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50/70 dark:hover:bg-[#141414] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 rounded-md bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400">
                <Sliders className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900 dark:text-white">
                  Why This Decision? (Candidate Action Economics)
                </div>
                <div className="text-[11px] text-slate-500 dark:text-[#737373] mt-0.5">
                  Inspect comparative expected value, causal uplift &tau;(x), costs, and eligibility across all 5 actions.
                </div>
              </div>
            </div>
            {showEconomics ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {showEconomics && (
            <div className="p-4 pt-0 border-t border-slate-100 dark:border-[#1F1F1F] animate-[fadeIn_0.15s_ease-out]">
              <div className="overflow-x-auto pt-3">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-[#1F1F1F] text-slate-400 text-[11px]">
                      <th className="py-2.5 pr-4 font-medium">Action</th>
                      <th className="py-2.5 px-4 font-medium">Status</th>
                      <th className="py-2.5 px-4 font-medium">P(Recovery)</th>
                      <th className="py-2.5 px-4 font-medium">Uplift &tau;</th>
                      <th className="py-2.5 px-4 font-medium">Cost + Friction</th>
                      <th className="py-2.5 pl-4 font-semibold text-slate-900 dark:text-white text-right">Expected Net</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-[#1F1F1F]">
                    {decision_trace.evaluations.map((ev) => {
                      const isSelected = ev.action === recommendedAction;
                      return (
                        <tr
                          key={ev.action}
                          className={`transition-colors duration-150 ${isSelected ? 'bg-blue-50/50 dark:bg-blue-950/30 font-semibold' : 'hover:bg-slate-50/60 dark:hover:bg-[#121212]'}`}
                        >
                          <td className="py-2.5 pr-4 text-slate-900 dark:text-white flex items-center gap-2">
                            {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
                            {ev.action}
                          </td>
                          <td className="py-2.5 px-4">
                            {ev.is_eligible ? (
                              <span className="text-emerald-600 dark:text-emerald-400 text-xs">Eligible</span>
                            ) : (
                              <span className="text-rose-500 text-xs">{ev.rejection_reason || 'Ineligible'}</span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-slate-600 dark:text-[#A3A3A3] tabular-nums">
                            {(ev.predicted_probability * 100).toFixed(1)}%
                          </td>
                          <td className="py-2.5 px-4 text-blue-600 dark:text-blue-400 tabular-nums">
                            {ev.incremental_uplift_tau >= 0 ? '+' : ''}
                            {(ev.incremental_uplift_tau * 100).toFixed(1)}%
                          </td>
                          <td className="py-2.5 px-4 text-slate-500 tabular-nums">
                            ₹{ev.action_cost + ev.friction_cost}
                          </td>
                          <td className="py-2.5 pl-4 font-bold text-slate-900 dark:text-white text-right tabular-nums">
                            {formatCurrency(ev.expected_net_recovery)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Accordion 2: Technical Details (Reasoning Pipeline & NLP Context) */}
        <div className="rounded-xl border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0E0E0E] overflow-hidden">
          <button
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50/70 dark:hover:bg-[#141414] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 rounded-md bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400">
                <Cpu className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900 dark:text-white">
                  Technical & Pipeline Reasoning
                </div>
                <div className="text-[11px] text-slate-500 dark:text-[#737373] mt-0.5">
                  7-step reasoning pipeline progression, model features, and customer NLP message extraction.
                </div>
              </div>
            </div>
            {showTechnicalDetails ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {showTechnicalDetails && (
            <div className="p-4 pt-0 border-t border-slate-100 dark:border-[#1F1F1F] space-y-6 animate-[fadeIn_0.15s_ease-out]">
              {/* Reasoning Stages */}
              <div id="pipeline-container" className="space-y-2 pt-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-[#737373]">
                  Reasoning Timeline Stages
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                  {pipelineStages.map((st, idx) => (
                    <div
                      key={st.label}
                      data-stage-index={idx}
                      className={`p-2.5 rounded-lg border text-xs transition-all ${
                        st.status === 'DONE'
                          ? 'border-emerald-200/80 dark:border-emerald-900/40 bg-emerald-50/20 dark:bg-emerald-950/10 text-slate-900 dark:text-white'
                          : st.status === 'ACTIVE'
                          ? 'border-blue-300 dark:border-blue-900/60 bg-blue-50/30 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400'
                          : 'border-slate-100 dark:border-[#1F1F1F] bg-slate-50/40 dark:bg-[#0A0A0A] text-slate-400'
                      }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-slate-400">
                        <span>0{idx + 1}</span>
                        {st.status === 'DONE' && <Check className="w-3 h-3 text-emerald-500" />}
                      </div>
                      <div className="font-semibold text-xs mt-1 leading-tight">{st.label}</div>
                      <div className="text-[10px] text-slate-500 dark:text-[#A3A3A3] mt-0.5 truncate">{st.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Customer NLP Message Workspace */}
              <div className="space-y-3 pt-3 border-t border-slate-100 dark:border-[#1F1F1F]">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-[#737373]">
                  Customer Message NLP Context
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <textarea
                      rows={2}
                      placeholder="e.g. 'I will pay tomorrow by 5 PM...'"
                      value={inboundMessage}
                      onChange={(e) => setInboundMessage(e.target.value)}
                      className="w-full p-2.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-slate-50/50 dark:bg-[#0A0A0A] text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleExtractContext}
                      disabled={!inboundMessage.trim()}
                      className="px-3 py-1.5 rounded-md bg-slate-900 dark:bg-blue-600 text-white font-medium text-xs hover:bg-slate-800 dark:hover:bg-blue-700 transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      Extract Intent
                    </button>
                  </div>

                  {extractionResult ? (
                    <div className="p-3 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-slate-50 dark:bg-[#0A0A0A] text-xs space-y-1">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Intent:</span>
                        <span className="font-semibold text-slate-900 dark:text-white">{extractionResult.intent}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Promise to Pay:</span>
                        <span className={extractionResult.has_promise ? 'text-emerald-600 dark:text-emerald-400 font-semibold' : 'text-slate-400'}>
                          {extractionResult.has_promise ? 'Yes' : 'No'}
                        </span>
                      </div>
                      {extractionResult.promised_date && (
                        <div className="flex justify-between">
                          <span className="text-slate-400">Promised Date:</span>
                          <span className="text-blue-600 dark:text-blue-400 font-medium">{extractionResult.promised_date}</span>
                        </div>
                      )}
                      <div className="pt-1 border-t border-slate-200 dark:border-[#1F1F1F] text-[11px] text-emerald-600 dark:text-emerald-400">
                        Policy Effect: {extractionResult.policy_effect.outreach_paused ? 'Outreach paused until promised date' : 'Standard flow'}
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 rounded-md border border-dashed border-slate-200 dark:border-[#1F1F1F] text-xs text-slate-400 text-center flex items-center justify-center">
                      Type a customer message to test bounded Pydantic NLP extraction.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Accordion 3: Immutable Audit Ledger */}
        <div className="rounded-xl border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0E0E0E] overflow-hidden">
          <button
            onClick={() => setShowAuditTrail(!showAuditTrail)}
            className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50/70 dark:hover:bg-[#141414] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 rounded-md bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400">
                <FileCheck className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900 dark:text-white">
                  Immutable Case Audit Ledger ({audit_records.length} events)
                </div>
                <div className="text-[11px] text-slate-500 dark:text-[#737373] mt-0.5">
                  Append-only cryptographic record of actors, safety gate checks, state transitions, and gateway payloads.
                </div>
              </div>
            </div>
            {showAuditTrail ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {showAuditTrail && (
            <div className="p-4 pt-0 border-t border-slate-100 dark:border-[#1F1F1F] animate-[fadeIn_0.15s_ease-out]">
              <div className="divide-y divide-slate-100 dark:divide-[#1F1F1F] pt-2">
                {audit_records.map((rec, idx) => (
                  <div key={rec.audit_id || idx} className="py-2.5 flex items-center justify-between text-xs hover:bg-slate-50/50 dark:hover:bg-[#121212] px-2 -mx-2 rounded transition-colors duration-150">
                    <div>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{rec.event_type}</span>
                      <span className="text-slate-400 ml-2">· {rec.actor} {rec.action_type && `(${rec.action_type})`}</span>
                    </div>
                    <span className="text-slate-400 font-mono text-[11px]">
                      {new Date(rec.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
                {audit_records.length === 0 && (
                  <div className="py-4 text-xs text-slate-400 text-center">No audit entries recorded yet.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Review / Override Modal (Operator Exception Flow) */}
      {showOverrideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-[fadeIn_0.15s_ease-out]">
          <div className="relative w-full max-w-lg bg-white dark:bg-[#0F0F0F] rounded-xl border border-slate-200 dark:border-[#1F1F1F] shadow-2xl p-6 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-[#1F1F1F]">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Lock className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  Operator Review & Safety Override
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Manual intervention for Case <strong className="font-mono text-slate-700 dark:text-[#D4D4D4]">{c.case_id}</strong>
                </p>
              </div>
              <button
                onClick={() => setShowOverrideModal(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-sm font-bold p-1"
              >
                &times;
              </button>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 dark:text-[#D4D4D4] block">
                Select Alternative Action:
              </label>

              <div className="space-y-2">
                {decision_trace.evaluations.map((ev) => (
                  <div
                    key={ev.action}
                    onClick={() => {
                      if (ev.is_eligible) setSelectedOverrideAction(ev.action);
                    }}
                    className={`p-3 rounded-lg border text-xs flex items-center justify-between transition-all ${
                      !ev.is_eligible
                        ? 'opacity-50 border-slate-100 dark:border-[#1A1A1A] bg-slate-50/50 dark:bg-[#0A0A0A] cursor-not-allowed'
                        : selectedOverrideAction === ev.action
                        ? 'border-blue-500 bg-blue-50/60 dark:bg-blue-950/40 ring-1 ring-blue-500 cursor-pointer'
                        : 'border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#121212] hover:border-slate-300 cursor-pointer'
                    }`}
                  >
                    <div>
                      <div className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                        <span>{ev.action}</span>
                        {ev.action === recommendedAction && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 font-mono">
                            Autonomous Default
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {ev.is_eligible ? `Expected Net: ${formatCurrency(ev.expected_net_recovery)}` : `Blocked: ${ev.rejection_reason}`}
                      </div>
                    </div>
                    <div className="text-right">
                      {ev.is_eligible ? (
                        <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Safe</span>
                      ) : (
                        <span className="text-xs text-rose-500 font-medium">Safety Gate Blocked</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-[#D4D4D4] block">
                Override Justification (Logged to Audit Ledger):
              </label>
              <input
                type="text"
                placeholder="e.g. Verified customer requested payment link over phone support..."
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                className="w-full p-2 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0A0A0A] text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-100 dark:border-[#1F1F1F]">
              <button
                onClick={() => setShowOverrideModal(false)}
                className="px-3 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] text-slate-600 dark:text-[#A3A3A3] text-xs font-medium hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => handleExecuteAction(selectedOverrideAction)}
                disabled={executing || !selectedOverrideAction}
                className="px-3.5 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm disabled:opacity-50 cursor-pointer"
              >
                {executing ? 'Executing...' : `Confirm Override to ${selectedOverrideAction}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

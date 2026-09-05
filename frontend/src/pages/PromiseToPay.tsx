import React, { useState } from 'react';
import {
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Layers,
} from 'lucide-react';
import { api } from '../api/client';
import { PromiseExtractionResult } from '../types';
import { staggerReveal } from '../utils/motion';

export const PromiseToPay: React.FC = () => {
  const [message, setMessage] = useState('Hey, sorry I missed the payment yesterday. My salary gets credited tomorrow evening, so I will pay by 7 PM on Friday.');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PromiseExtractionResult | null>(null);
  const [activeStep, setActiveStep] = useState<string>('PROMISED');

  const handleExtract = () => {
    if (!message.trim()) return;
    setLoading(true);
    api.extractPromise(message)
      .then((data) => {
        setResult(data);
        if (data.has_promise) {
          setActiveStep('PROMISED');
        } else if (data.intent.includes('OPT_OUT')) {
          setActiveStep('NONE');
        } else {
          setActiveStep('REQUESTED');
        }
        setLoading(false);
        setTimeout(() => {
          staggerReveal('.ptp-result-row', { delay: 20, stagger: 25, translateY: 4 });
        }, 30);
      })
      .catch((err) => {
        alert(`Extraction error: ${err.message}`);
        setLoading(false);
      });
  };

  const stateMachineSteps = [
    { key: 'NONE', label: 'NONE', desc: 'No promise' },
    { key: 'REQUESTED', label: 'REQUESTED', desc: 'Outreach link sent' },
    { key: 'PROMISED', label: 'PROMISED', desc: 'Date committed' },
    { key: 'ACTIVE', label: 'ACTIVE', desc: 'Outreach paused' },
    { key: 'DUE', label: 'DUE', desc: 'Timestamp reached' },
  ];

  return (
    <div className="space-y-8">
      {/* 1. Header */}
      <div className="pb-5 border-b border-slate-200/80 dark:border-[#1F1F1F]">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Promise to Pay Intelligence
          </h1>
          <span className="text-xs px-2.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400 font-semibold border border-blue-200/60 dark:border-blue-900/40">
            Payment State Machine
          </span>
        </div>
        <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-1">
          Structured NLP context extraction with deterministic state lifecycle management.
        </p>
      </div>

      {/* 2. Authority Boundary Bar */}
      <div className="p-3 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-slate-50/70 dark:bg-[#0E0E0E] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
          <span className="font-semibold text-slate-900 dark:text-white">Authority Boundary</span>
        </div>
        <div className="text-[11px] font-mono text-slate-500 dark:text-[#A3A3A3]">
          LLM = extraction only · Policy = deterministic · Execution = safety-gated
        </div>
      </div>

      {/* 3. Payment-Recovery State Machine Visualization */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            Payment Recovery State Lifecycle
          </h2>
          <span className="text-xs font-mono text-slate-400">P2P-FSM</span>
        </div>

        {/* State Machine Sequence */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
          {stateMachineSteps.map((st, idx) => {
            const isCurrent = activeStep === st.key;
            return (
              <div
                key={st.key}
                onClick={() => setActiveStep(st.key)}
                className={`p-3 rounded-lg border text-xs transition-all duration-150 cursor-pointer select-none ${
                  isCurrent
                    ? 'border-blue-500 dark:border-blue-500 bg-blue-50/60 dark:bg-blue-950/40 text-blue-900 dark:text-white ring-1 ring-blue-500/20 scale-[1.02]'
                    : 'border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-slate-600 dark:text-[#A3A3A3] hover:border-slate-300 dark:hover:border-[#2A2A2A]'
                }`}
              >
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>0{idx + 1}</span>
                  {isCurrent && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
                </div>
                <div className="font-bold text-xs mt-1">{st.label}</div>
                <div className="text-[11px] text-slate-500 dark:text-[#737373] mt-0.5">{st.desc}</div>
              </div>
            );
          })}
        </div>

        {/* Terminal Outcomes */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
          <div
            onClick={() => setActiveStep('PAID')}
            className={`p-2.5 rounded-lg border text-xs transition-all duration-150 cursor-pointer flex items-center justify-between ${
              activeStep === 'PAID'
                ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/30 text-emerald-900 dark:text-white scale-[1.01]'
                : 'border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-slate-600 dark:text-[#A3A3A3]'
            }`}
          >
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              <span className="font-semibold text-slate-900 dark:text-white">Terminal: PAID</span>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400">
              Settled
            </span>
          </div>

          <div
            onClick={() => setActiveStep('BROKEN')}
            className={`p-2.5 rounded-lg border text-xs transition-all duration-150 cursor-pointer flex items-center justify-between ${
              activeStep === 'BROKEN'
                ? 'border-rose-500 bg-rose-50/50 dark:bg-rose-950/30 text-rose-900 dark:text-white scale-[1.01]'
                : 'border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-slate-600 dark:text-[#A3A3A3]'
            }`}
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
              <span className="font-semibold text-slate-900 dark:text-white">Terminal: BROKEN</span>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400">
              Resumes Outreach
            </span>
          </div>
        </div>
      </div>

      {/* 4. Structured Extraction Workflow */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 pt-3 border-t border-slate-200/80 dark:border-[#1F1F1F]">
        {/* Left Column: Customer Inbound Message Input */}
        <div className="space-y-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">
              Customer Inbound Message
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-0.5">
              WhatsApp / SMS reply from customer
            </p>
          </div>

          <textarea
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type customer reply..."
            className="w-full p-3 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500 leading-relaxed font-sans"
          />

          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setMessage('Will pay tomorrow 6 PM when salary arrives.')}
                className="px-2 py-1 rounded text-xs text-slate-600 dark:text-[#A3A3A3] bg-slate-100 dark:bg-[#1A1A1A] hover:text-slate-900 dark:hover:text-white hover:-translate-y-0.5 transition-all duration-150 cursor-pointer"
              >
                Sample: Valid promise
              </button>
              <button
                type="button"
                onClick={() => setMessage('Please stop messaging me. I want to cancel my subscription.')}
                className="px-2 py-1 rounded text-xs text-slate-600 dark:text-[#A3A3A3] bg-slate-100 dark:bg-[#1A1A1A] hover:text-slate-900 dark:hover:text-white hover:-translate-y-0.5 transition-all duration-150 cursor-pointer"
              >
                Sample: Opt-out
              </button>
            </div>

            <button
              onClick={handleExtract}
              disabled={loading || !message.trim()}
              className="px-3.5 py-1.5 rounded-md bg-[#0C2340] dark:bg-blue-600 text-white text-xs font-semibold hover:bg-slate-800 dark:hover:bg-blue-700 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150 flex items-center gap-1.5 shadow-2xs disabled:opacity-50 cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {loading ? 'Extracting...' : 'Extract Context'}
            </button>
          </div>
        </div>

        {/* Right Column: Schema Extraction Context */}
        <div className="space-y-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">
              Extracted Context & Policy Effect
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-0.5">
              Pydantic schema validation output
            </p>
          </div>

          {result ? (
            <div className="space-y-2 text-xs divide-y divide-slate-100 dark:divide-[#1F1F1F] border-y border-slate-100 dark:border-[#1F1F1F] py-1.5 animate-[fadeIn_0.2s_ease-out]">
              <div className="ptp-result-row flex justify-between py-1.5">
                <span className="text-slate-500">Intent</span>
                <span className="font-semibold text-slate-900 dark:text-white font-mono">{result.intent}</span>
              </div>
              <div className="ptp-result-row flex justify-between py-1.5">
                <span className="text-slate-500">Promise to Pay</span>
                <span className={result.has_promise ? 'text-emerald-600 dark:text-emerald-400 font-semibold' : 'text-slate-400'}>
                  {result.has_promise ? 'Yes (Registered)' : 'No'}
                </span>
              </div>
              {result.promised_date && (
                <div className="ptp-result-row flex justify-between py-1.5">
                  <span className="text-slate-500">Promised Date</span>
                  <span className="text-blue-600 dark:text-blue-400 font-semibold font-mono">{result.promised_date}</span>
                </div>
              )}
              {result.payment_constraint && (
                <div className="ptp-result-row flex justify-between py-1.5">
                  <span className="text-slate-500">Constraint</span>
                  <span className="font-semibold text-slate-900 dark:text-white">{result.payment_constraint}</span>
                </div>
              )}
              <div className="ptp-result-row flex justify-between py-1.5">
                <span className="text-slate-500">Confidence</span>
                <span className="font-mono text-slate-900 dark:text-white">{(result.confidence_score * 100).toFixed(0)}%</span>
              </div>
              <div className="ptp-result-row py-2 space-y-0.5">
                <div className="text-slate-500 text-[11px]">Deterministic Policy Effect</div>
                <div className="font-semibold text-emerald-600 dark:text-emerald-400 text-xs">
                  {result.policy_effect.outreach_paused
                    ? '✓ Outreach paused until promised date'
                    : '✓ Standard outreach flow'}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-slate-400 border border-dashed border-slate-200 dark:border-[#1F1F1F] rounded-md p-4">
              Click 'Extract Context' to run NLP extraction on the message.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

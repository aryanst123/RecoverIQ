import React, { useState, useEffect } from 'react';
import {
  Network,
  ChevronDown,
  ChevronUp,
  Cpu,
  Lock,
  Database,
  Layers,
  FileCheck,
} from 'lucide-react';
import { staggerReveal } from '../utils/motion';

export const Architecture: React.FC = () => {
  const [expandedLayer, setExpandedLayer] = useState<string | null>(null);

  useEffect(() => {
    // 8-stage pipeline one-time sequential entry stagger
    staggerReveal('.pipeline-stage-step', {
      delay: 50,
      stagger: 40,
      translateY: 6,
      duration: 220,
    });
    staggerReveal('.arch-layer-row', {
      delay: 200,
      stagger: 45,
      translateY: 6,
      duration: 220,
    });
  }, []);

  const pipelineSteps = [
    { num: '01', name: 'INGEST', desc: 'HMAC Webhooks & Mutex' },
    { num: '02', name: 'DIAGNOSE', desc: 'Taxonomy & NLP Context' },
    { num: '03', name: 'ESTIMATE', desc: 'Uplift &tau;(x) Estimation' },
    { num: '04', name: 'OPTIMIZE', desc: 'E[Net] Maximization' },
    { num: '05', name: 'POLICY', desc: 'Candidate Selection' },
    { num: '06', name: 'SAFETY', desc: '10 Invariants & Caps' },
    { num: '07', name: 'EXECUTE', desc: 'Razorpay API Adapter' },
    { num: '08', name: 'RECONCILE', desc: 'Immutable Ledger' },
  ];

  const technicalLayers = [
    {
      id: 'security',
      name: 'Security',
      icon: Lock,
      tags: ['HMAC-SHA256 Auth', 'Case Lock Mutex', 'Fails-Closed Guard'],
      details: [
        'Raw webhook request HMAC-SHA256 verification before JSON parsing',
        'Thread-safe in-memory mutex preventing concurrent case mutations',
        'Fail-closed guard halting execution if live credentials detected',
      ],
    },
    {
      id: 'intelligence',
      name: 'Intelligence',
      icon: Cpu,
      tags: ['Failure Taxonomy', 'Pydantic NLP Schema', 'Date Horizon'],
      details: [
        'Granular categorization of technical and financial failure reasons',
        'Schema-bounded NLP extraction for customer promise-to-pay intent',
        'Authority isolation: language model extracts context, cannot authorize funds',
      ],
    },
    {
      id: 'decisioning',
      name: 'Decisioning',
      icon: Layers,
      tags: ['Causal Forest \u03c4(x)', 'Expected Net E[Net]', 'Policy Bounds'],
      details: [
        'Meta-learner potential outcomes model estimating counterfactual uplift \u03c4(x)',
        'Economic value optimization: E[Net] = \u03c4(x) \u00b7 Amount \u2212 Cost \u2212 Friction',
        'Pre-execution action candidate evaluation across 5 intervention channels',
      ],
    },
    {
      id: 'execution',
      name: 'Execution',
      icon: Database,
      tags: ['Razorpay Test Adapter', 'Action Reservation', 'Touch Caps (Max 3)'],
      details: [
        'Razorpay Python SDK integration creating Test Mode Payment Links',
        'Merchant idempotency token store preventing duplicate dispatch',
        'Hard safety caps: max 3 automated touches, 30-day recovery window',
      ],
    },
    {
      id: 'evidence',
      name: 'Evidence',
      icon: FileCheck,
      tags: ['Monotonic State Machine', 'Immutable Audit Ledger', 'Cryptographic Proof'],
      details: [
        'Deterministic state lifecycle (CaseStateMachine) blocking terminal regression',
        'Append-only structured audit ledger recording actor, event, and timestamp',
        'Phase 9 empirical holdout reproducibility under frozen random seeds',
      ],
    },
  ];

  return (
    <div className="space-y-8">
      {/* 1. Header */}
      <div className="pb-5 border-b border-slate-200/80 dark:border-[#1F1F1F]">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            System Architecture
          </h1>
          <span className="text-xs px-2.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400 font-semibold border border-blue-200/60 dark:border-blue-900/40">
            Pipeline & Control Layers
          </span>
        </div>
        <p className="text-xs text-slate-500 dark:text-[#A3A3A3] mt-1">
          Payment recovery pipeline with causal economics and machine-checked safety invariants.
        </p>
      </div>

      {/* 2. Primary Hero Visual: 8-Stage Execution Pipeline */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Network className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            Execution Pipeline
          </h2>
          <span className="text-xs font-mono text-slate-400">
            Sequential Decision & Settlement Flow
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {pipelineSteps.map((st) => (
            <div
              key={st.name}
              className="pipeline-stage-step p-3 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-white dark:bg-[#0F0F0F] text-xs space-y-1 hover:border-blue-400 dark:hover:border-blue-900/70 hover:-translate-y-0.5 transition-all duration-150 shadow-2xs"
            >
              <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono font-semibold">
                <span>{st.num}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              </div>
              <div className="font-bold text-slate-900 dark:text-white tracking-tight">{st.name}</div>
              <div className="text-[11px] text-slate-500 dark:text-[#A3A3A3] leading-tight pt-0.5">{st.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 3. 5 Compact Technical Layers */}
      <div className="space-y-3 pt-4 border-t border-slate-200/80 dark:border-[#1F1F1F]">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">
            Technical Control Layers
          </h2>
          <span className="text-xs text-slate-400">5 Modular Subsystems</span>
        </div>

        <div className="divide-y divide-slate-100 dark:divide-[#1F1F1F] border-y border-slate-100 dark:border-[#1F1F1F]">
          {technicalLayers.map((layer) => {
            const Icon = layer.icon;
            const isExpanded = expandedLayer === layer.id;

            return (
              <div key={layer.id} className="arch-layer-row py-3 transition-colors">
                <button
                  onClick={() => setExpandedLayer(isExpanded ? null : layer.id)}
                  className="w-full flex items-center justify-between text-left cursor-pointer group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-1.5 rounded-md bg-slate-100 dark:bg-[#141414] text-slate-600 dark:text-[#A3A3A3] group-hover:text-blue-600 dark:group-hover:text-blue-400 group-hover:scale-105 transition-all duration-150">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="font-bold text-xs text-slate-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                        {layer.name}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="hidden sm:flex items-center gap-2">
                      {layer.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-[#141414] text-slate-600 dark:text-[#A3A3A3] border border-slate-200/60 dark:border-[#222]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </button>

                {isExpanded && (
                  <div className="mt-2.5 ml-9 p-3 rounded-lg border border-slate-200/80 dark:border-[#1F1F1F] bg-slate-50/60 dark:bg-[#0A0A0A] text-xs space-y-1.5 animate-[fadeIn_0.15s_ease-out]">
                    <ul className="space-y-1 text-slate-600 dark:text-[#D4D4D4] text-xs">
                      {layer.details.map((detail, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-blue-500 mt-0.5">•</span>
                          <span>{detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

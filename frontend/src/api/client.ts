import {
  DashboardKPIs,
  CaseSummary,
  CaseDetail,
  BenchmarkResponse,
  OracleDiagnostic,
  AttributionSensitivity,
  LLMAblationResponse,
  SafetyStatus,
  RazorpayStatus,
  PromiseExtractionResult,
} from '../types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let errorDetail = 'API request failed';
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || errJson.message || errorDetail;
    } catch (_) {
      errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export const api = {
  // Health & KPIs
  getHealth: () => fetchJson<{ status: string; environment: string; razorpay_mode: string; is_test_mode: boolean; is_configured: boolean }>('/health'),
  getKPIs: () => fetchJson<DashboardKPIs>('/dashboard/kpis'),

  // Cases Queue & Detail
  getCases: (params?: { state_filter?: string; failure_code?: string; segment?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.state_filter) query.set('state_filter', params.state_filter);
    if (params?.failure_code) query.set('failure_code', params.failure_code);
    if (params?.segment) query.set('segment', params.segment);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return fetchJson<{ total_count: number; limit: number; offset: number; cases: CaseSummary[] }>(`/cases${qs ? `?${qs}` : ''}`);
  },
  getCaseDetail: (caseId: string) => fetchJson<CaseDetail>(`/cases/${caseId}`),

  // Policy & Execution
  evaluateCaseDecision: (caseId: string, message?: string) =>
    fetchJson<{
      decision_id: string;
      selected_action: string;
      confidence: number;
      expected_incremental_recovery: number;
      expected_cost: number;
      net_expected_value: number;
      decision_reason: string;
    }>(`/cases/${caseId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ message: message || '' }),
    }),

  executeAction: (caseId: string, actionType: string, idempotencyKey?: string) =>
    fetchJson<{
      status: string;
      case_id: string;
      action_id: string;
      action_type: string;
      case_state: string;
      payment_link?: any;
    }>(`/cases/${caseId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ action_type: actionType, idempotency_key: idempotencyKey }),
    }),

  // Promise-to-Pay & LLM
  extractPromise: (message: string) =>
    fetchJson<PromiseExtractionResult>('/promise-to-pay/extract', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  // Frozen Evaluation & Research
  getBenchmark: () => fetchJson<BenchmarkResponse>('/evaluation/benchmark'),
  getOracleDiagnostic: () => fetchJson<OracleDiagnostic>('/evaluation/oracle'),
  getAttributionSensitivity: () => fetchJson<AttributionSensitivity>('/evaluation/attribution'),
  getLLMAblation: () => fetchJson<LLMAblationResponse>('/evaluation/llm'),
  getHeterogeneity: () => fetchJson<any>('/evaluation/heterogeneity'),

  // Safety & Failure Injection
  getSafetyStatus: () => fetchJson<SafetyStatus>('/safety/status'),
  triggerFailureInjection: (scenarioType: string, caseId?: string) =>
    fetchJson<any>('/safety/failure-injection', {
      method: 'POST',
      body: JSON.stringify({ scenario_type: scenarioType, case_id: caseId }),
    }),

  // Razorpay Integration & Webhooks
  getRazorpayStatus: () => fetchJson<RazorpayStatus>('/razorpay/status'),
  simulateWebhook: (event: string, payload: any, signature?: string) =>
    fetchJson<any>('/webhooks/razorpay', {
      method: 'POST',
      headers: signature ? { 'x-razorpay-signature': signature } : {},
      body: JSON.stringify({ event, payload }),
    }),
};

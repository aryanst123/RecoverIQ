export type ThemeMode = 'light' | 'dark';

export interface DashboardKPIs {
  total_failed_payments: number;
  active_recovery_cases: number;
  recovered_cases_count: number;
  recovery_rate: number;
  revenue_at_risk_inr: number;
  revenue_recovered_inr: number;
  safety_violations_count: number;
  razorpay_integration_status: string;
  data_source_badge: string;
}

export interface CaseSummary {
  case_id: string;
  payment_id: string;
  customer_id: string;
  customer_segment: string;
  amount_due: number;
  residual_amount: number;
  failure_code: string;
  failure_reason: string;
  hours_since_failure: number;
  attempts_count: number;
  automated_actions_count: number;
  current_state: string;
  recommended_action: string;
  decision_confidence: number;
  created_at: string;
}

export interface ActionEvaluationItem {
  action: string;
  is_eligible: boolean;
  rejection_reason?: string | null;
  predicted_probability: number;
  incremental_uplift_tau: number;
  expected_incremental_revenue: number;
  action_cost: number;
  friction_cost: number;
  expected_net_recovery: number;
}

export interface CaseDetail {
  case: {
    case_id: string;
    payment_id: string;
    customer_id: string;
    amount_due: number;
    residual_amount: number;
    current_state: string;
    automated_action_count: number;
    terminal_reason?: string | null;
    created_at: string;
  };
  customer?: {
    customer_id: string;
    segment: string;
    channel_preference: string;
    opt_out: boolean;
  } | null;
  payment?: {
    payment_id: string;
    amount: number;
    status: string;
    currency: string;
  } | null;
  latest_attempt?: {
    attempt_id: string;
    failure_code: string;
    failure_reason: string;
    attempted_at: string;
  } | null;
  observable_state: {
    hours_since_failure: number;
    automated_action_count: number;
    customer_opt_out: boolean;
    is_terminal: boolean;
  };
  decision_trace: {
    recommended?: {
      selected_action: string;
      policy_version: string;
      confidence: number;
      expected_net_recovery: number;
      expected_cost: number;
      selection_reason: string;
      explanation: string;
    } | null;
    evaluations: ActionEvaluationItem[];
  };
  actions_history: Array<{
    action_id: string;
    action_type: string;
    cost: number;
    friction_cost: number;
    timestamp: string;
    policy_version: string;
  }>;
  payment_link?: {
    link_id: string;
    short_url: string;
    amount_inr: number;
    status: string;
    reference_id: string;
    created_at: string;
  } | null;
  audit_records: Array<{
    audit_id: string;
    event_type: string;
    timestamp: string;
    actor: string;
    action_type?: string | null;
    metadata: Record<string, any>;
  }>;
}

export interface BenchmarkArm {
  N: number;
  Gross_Recovered: number;
  Action_Cost: number;
  Friction_Cost: number;
  Net_Recovered?: number;
  Total_Net_Recovered?: number;
  Mean_Net_Per_Case: number;
  Recovery_Rate: number;
  Intervention_Efficiency: number;
  Unnecessary_Intervention_Rate: number;
  Safety_Violations?: number;
  Critical_Safety_Violations?: number;
  Action_Distribution: Record<string, number>;
}

export interface BootstrapComparisonItem {
  point_estimate: number;
  ci_95: [number, number];
  classification: string;
}

export interface BenchmarkResponse {
  status: string;
  scenario: string;
  dataset_size: number;
  seed: number;
  arms: {
    CONTROL: BenchmarkArm;
    BASELINE: BenchmarkArm;
    RECOVERIQ: BenchmarkArm;
  };
  bootstrap_comparisons: {
    RecoverIQ_vs_Baseline: BootstrapComparisonItem;
    RecoverIQ_vs_Control: BootstrapComparisonItem;
    Baseline_vs_Control: BootstrapComparisonItem;
  };
}

export interface OracleDiagnostic {
  diagnostic_type: string;
  cohort_size: number;
  oracle_agreement_rate: number;
  mean_regret_per_case: number;
  policy_action_distribution: Record<string, number>;
  oracle_action_distribution: Record<string, number>;
  audit_trail_invalidation_note?: string;
}

export interface AttributionSensitivity {
  [windowHours: string]: {
    mean_net_base: number;
    mean_net_riq: number;
    delta_riq_minus_base: number;
    conclusion: string;
  };
}

export interface LLMAblationResponse {
  ablation_comparison: {
    mean_net_structured: number;
    mean_net_augmented: number;
    point_estimate: number;
    ci_95: [number, number];
    classification: string;
    decisions_changed: number;
    promises_registered: number;
    opt_outs_honored: number;
    fallback_rate: number;
  };
  extraction_benchmark: {
    evaluation_type: string;
    samples_evaluated: number;
    intent_accuracy: number;
    p2p_detection_accuracy: number;
    promised_date_accuracy: number;
    constraint_accuracy: number;
    adversarial_resilience_rate: number;
    fallback_rate: number;
    avg_latency_ms: number;
    total_tokens_estimated: number;
  };
}

export interface SafetyStatus {
  safety_audit: {
    invariants_checked: number;
    invariants_passed: number;
    critical_violations: number;
    invariants_detail: Record<string, boolean>;
    failure_injections_tested: number;
    failure_injections_passed: number;
  };
}

export interface RazorpayStatus {
  environment: string;
  is_test_mode: boolean;
  is_configured: boolean;
  status: 'CONNECTED' | 'OFFLINE_MOCK';
  has_credentials: boolean;
  key_id_masked: string;
}

export interface PromiseExtractionResult {
  intent: string;
  willingness_to_pay: string;
  has_promise: boolean;
  promised_date?: string | null;
  payment_constraint?: string | null;
  confidence_score: number;
  ambiguity_state: string;
  evidence_span?: string | null;
  is_fallback: boolean;
  policy_effect: {
    outreach_paused: boolean;
    promise_registered: boolean;
    recommended_action_override?: string | null;
  };
}

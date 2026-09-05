import React, { createContext, useState, useEffect, useCallback, ReactNode, useRef } from 'react';
import {
  DashboardKPIs,
  BenchmarkResponse,
  CaseSummary,
  RazorpayStatus,
  SafetyStatus,
  OracleDiagnostic,
  AttributionSensitivity,
  LLMAblationResponse,
} from '../types';
import { api } from '../api/client';

export type RequestState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

export interface DataContextType {
  kpis: RequestState<DashboardKPIs>;
  benchmark: RequestState<BenchmarkResponse>;
  cases: RequestState<{ total_count: number; cases: CaseSummary[] }>;
  razorpayStatus: RequestState<RazorpayStatus>;
  safetyStatus: RequestState<SafetyStatus>;
  oracleDiagnostic: RequestState<OracleDiagnostic>;
  attributionSensitivity: RequestState<AttributionSensitivity>;
  llmAblation: RequestState<LLMAblationResponse>;
  refreshKPIs: () => Promise<void>;
  refreshBenchmark: () => Promise<void>;
  refreshCases: (params?: any) => Promise<void>;
  refreshRazorpayStatus: () => Promise<void>;
  refreshSafetyStatus: () => Promise<void>;
  refreshEvaluationSuite: () => Promise<void>;
}

export const DataContext = createContext<DataContextType | null>(null);

export const DataProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [kpis, setKpis] = useState<RequestState<DashboardKPIs>>({ data: null, loading: true, error: null });
  const [benchmark, setBenchmark] = useState<RequestState<BenchmarkResponse>>({ data: null, loading: true, error: null });
  const [cases, setCases] = useState<RequestState<{ total_count: number; cases: CaseSummary[] }>>({ data: null, loading: true, error: null });
  const [razorpayStatus, setRazorpayStatus] = useState<RequestState<RazorpayStatus>>({ data: null, loading: true, error: null });
  const [safetyStatus, setSafetyStatus] = useState<RequestState<SafetyStatus>>({ data: null, loading: true, error: null });
  const [oracleDiagnostic, setOracleDiagnostic] = useState<RequestState<OracleDiagnostic>>({ data: null, loading: true, error: null });
  const [attributionSensitivity, setAttributionSensitivity] = useState<RequestState<AttributionSensitivity>>({ data: null, loading: true, error: null });
  const [llmAblation, setLlmAblation] = useState<RequestState<LLMAblationResponse>>({ data: null, loading: true, error: null });

  // In-flight request deduplication refs
  const inFlightBenchmark = useRef<Promise<void> | null>(null);
  const inFlightEvaluation = useRef<Promise<void> | null>(null);
  const inFlightCases = useRef<Map<string, Promise<void>>>(new Map());

  const refreshKPIs = useCallback(async () => {
    setKpis((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    try {
      const data = await api.getKPIs();
      setKpis({ data, loading: false, error: null });
    } catch (err: any) {
      setKpis((prev) => ({ ...prev, loading: false, error: err.message || 'Failed to load KPIs' }));
    }
  }, []);

  const refreshBenchmark = useCallback(async () => {
    if (inFlightBenchmark.current) return inFlightBenchmark.current;

    setBenchmark((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    const p = (async () => {
      try {
        const data = await api.getBenchmark();
        setBenchmark({ data, loading: false, error: null });
      } catch (err: any) {
        setBenchmark((prev) => ({ ...prev, loading: false, error: err.message || 'Failed to load holdout benchmark' }));
      } finally {
        inFlightBenchmark.current = null;
      }
    })();
    inFlightBenchmark.current = p;
    return p;
  }, []);

  const refreshCases = useCallback(async (params?: any) => {
    const key = JSON.stringify(params || { limit: 100 });
    const existing = inFlightCases.current.get(key);
    if (existing) return existing;

    setCases((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    const p = (async () => {
      try {
        const data = await api.getCases(params || { limit: 100 });
        setCases({ data, loading: false, error: null });
      } catch (err: any) {
        setCases((prev) => ({ ...prev, loading: false, error: err.message || 'Failed to load cases queue' }));
      } finally {
        inFlightCases.current.delete(key);
      }
    })();
    inFlightCases.current.set(key, p);
    return p;
  }, []);

  const refreshRazorpayStatus = useCallback(async () => {
    setRazorpayStatus((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    try {
      const data = await api.getRazorpayStatus();
      setRazorpayStatus({ data, loading: false, error: null });
    } catch (err: any) {
      setRazorpayStatus({
        data: {
          environment: 'test',
          is_test_mode: true,
          is_configured: false,
          status: 'OFFLINE_MOCK',
          has_credentials: false,
          key_id_masked: 'UNCONFIGURED',
        },
        loading: false,
        error: null,
      });
    }
  }, []);

  const refreshSafetyStatus = useCallback(async () => {
    setSafetyStatus((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    try {
      const data = await api.getSafetyStatus();
      setSafetyStatus({ data, loading: false, error: null });
    } catch (err: any) {
      setSafetyStatus((prev) => ({ ...prev, loading: false, error: err.message || 'Failed to load safety status' }));
    }
  }, []);

  const refreshEvaluationSuite = useCallback(async () => {
    if (inFlightEvaluation.current) return inFlightEvaluation.current;

    // Trigger benchmark in parallel
    refreshBenchmark();

    setOracleDiagnostic((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    setAttributionSensitivity((prev) => ({ ...prev, loading: prev.data === null, error: null }));
    setLlmAblation((prev) => ({ ...prev, loading: prev.data === null, error: null }));

    const p = (async () => {
      // Execute auxiliary diagnostics concurrently
      await Promise.allSettled([
        api.getOracleDiagnostic()
          .then((data) => setOracleDiagnostic({ data, loading: false, error: null }))
          .catch((err) => setOracleDiagnostic((prev) => ({ ...prev, loading: false, error: err.message }))),

        api.getAttributionSensitivity()
          .then((data) => setAttributionSensitivity({ data, loading: false, error: null }))
          .catch((err) => setAttributionSensitivity((prev) => ({ ...prev, loading: false, error: err.message }))),

        api.getLLMAblation()
          .then((data) => setLlmAblation({ data, loading: false, error: null }))
          .catch((err) => setLlmAblation((prev) => ({ ...prev, loading: false, error: err.message }))),
      ]);
      inFlightEvaluation.current = null;
    })();

    inFlightEvaluation.current = p;
    return p;
  }, [refreshBenchmark]);

  // Fast parallel initial load on application mount
  useEffect(() => {
    Promise.allSettled([
      refreshKPIs(),
      refreshBenchmark(),
      refreshCases(),
      refreshRazorpayStatus(),
      refreshSafetyStatus(),
    ]);
  }, [refreshKPIs, refreshBenchmark, refreshCases, refreshRazorpayStatus, refreshSafetyStatus]);

  return (
    <DataContext.Provider
      value={{
        kpis,
        benchmark,
        cases,
        razorpayStatus,
        safetyStatus,
        oracleDiagnostic,
        attributionSensitivity,
        llmAblation,
        refreshKPIs,
        refreshBenchmark,
        refreshCases,
        refreshRazorpayStatus,
        refreshSafetyStatus,
        refreshEvaluationSuite,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};

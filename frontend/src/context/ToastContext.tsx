import React, { createContext, useState, useCallback, ReactNode } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface Toast {
  id: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

export interface ToastContextType {
  showToast: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
}

export const ToastContext = createContext<ToastContextType | null>(null);

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3200);
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast Notification Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg border border-slate-200/90 dark:border-[#1a2638] bg-white/95 dark:bg-[#0c121e]/95 backdrop-blur-md shadow-lg text-xs transition-all animate-[fadeIn_0.25s_ease-out]"
          >
            <div className="flex items-center gap-2">
              {t.type === 'success' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />}
              {t.type === 'error' && <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />}
              {t.type === 'warning' && <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0" />}
              {t.type === 'info' && <Info className="w-3.5 h-3.5 text-blue-500 shrink-0" />}
              <span className="text-slate-800 dark:text-slate-200 font-medium leading-tight">
                {t.message}
              </span>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

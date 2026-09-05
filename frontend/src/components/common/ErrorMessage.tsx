import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  title = 'Data Unavailable',
  message,
  onRetry,
  className = '',
}) => {
  return (
    <div className={`p-4 rounded-lg border border-rose-200/80 dark:border-rose-900/40 bg-rose-50/40 dark:bg-rose-950/10 text-xs ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold text-rose-900 dark:text-rose-200">{title}</div>
            <div className="text-rose-700 dark:text-rose-400 mt-0.5 leading-relaxed">{message}</div>
          </div>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-2.5 py-1 rounded-md border border-rose-300 dark:border-rose-800/60 bg-white dark:bg-[#141414] text-rose-800 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors font-medium flex items-center gap-1.5 shrink-0 shadow-sm text-[11px]"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
};

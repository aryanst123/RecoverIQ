import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  badge,
  action,
  className = '',
  headerClassName = '',
  bodyClassName = '',
  noPadding = false,
}) => {
  return (
    <div
      className={`rounded-xl border border-slate-200/90 dark:border-[#1a2638] bg-white dark:bg-[#0c121e] shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:shadow-none transition-colors ${className}`}
    >
      {(title || subtitle || badge || action) && (
        <div
          className={`flex items-center justify-between border-b border-slate-100 dark:border-[#162032] px-5 py-3.5 ${headerClassName}`}
        >
          <div className="flex items-center gap-3">
            <div>
              {title && (
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                  {title}
                  {badge}
                </div>
              )}
              {subtitle && (
                <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {subtitle}
                </div>
              )}
            </div>
          </div>
          {action && <div className="text-xs">{action}</div>}
        </div>
      )}
      <div className={noPadding ? bodyClassName : `p-5 ${bodyClassName}`}>{children}</div>
    </div>
  );
};

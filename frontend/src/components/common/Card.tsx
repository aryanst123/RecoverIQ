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
}) => {
  return (
    <div
      className={`rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-[#0B111E] shadow-sm transition-all ${className}`}
    >
      {(title || subtitle || badge || action) && (
        <div
          className={`flex items-center justify-between border-b border-slate-100 dark:border-slate-800/60 px-5 py-4 ${headerClassName}`}
        >
          <div className="flex items-center gap-3">
            <div>
              {title && (
                <div className="text-base font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
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
          {action && <div>{action}</div>}
        </div>
      )}
      <div className={`p-5 ${bodyClassName}`}>{children}</div>
    </div>
  );
};

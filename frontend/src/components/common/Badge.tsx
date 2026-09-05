import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'frozen' | 'simulator' | 'razorpay';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'sm',
  className = '',
}) => {
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs font-medium';

  const variantClasses = {
    default: 'bg-slate-100 text-slate-700 dark:bg-slate-800/80 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/60',
    primary: 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400 border border-blue-200/80 dark:border-blue-800/50',
    success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/80 dark:border-emerald-800/50',
    warning: 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-400 border border-amber-200/80 dark:border-amber-800/50',
    danger: 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400 border border-rose-200/80 dark:border-rose-800/50',
    info: 'bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-400 border border-sky-200/80 dark:border-sky-800/50',
    frozen: 'bg-slate-100 text-slate-800 dark:bg-slate-800/90 dark:text-slate-200 border border-slate-300 dark:border-slate-700 font-mono font-medium',
    simulator: 'bg-slate-100 text-slate-700 dark:bg-slate-800/60 dark:text-slate-300 border border-slate-200 dark:border-slate-700/50 font-mono',
    razorpay: 'bg-blue-50 text-[#0C2340] dark:bg-blue-950/50 dark:text-blue-300 border border-blue-200 dark:border-blue-800/60 font-semibold',
  }[variant];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md font-medium tracking-tight transition-colors select-none ${sizeClasses} ${variantClasses} ${className}`}
    >
      {children}
    </span>
  );
};

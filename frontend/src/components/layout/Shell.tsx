import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  Inbox,
  Sparkles,
  BarChart3,
  ShieldCheck,
  Network,
  Sun,
  Moon,
  Menu,
  X,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Radio,
} from 'lucide-react';
import { useTheme } from '../../theme/ThemeContext';
import { api } from '../../api/client';
import { RazorpayStatus } from '../../types';

interface ShellProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ currentPath, onNavigate, children }) => {
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [razorpayStatus, setRazorpayStatus] = useState<RazorpayStatus | null>(null);

  useEffect(() => {
    api.getRazorpayStatus()
      .then(setRazorpayStatus)
      .catch(() => {
        setRazorpayStatus({
          environment: 'test',
          is_test_mode: true,
          is_configured: false,
          status: 'OFFLINE_MOCK',
          has_credentials: false,
          key_id_masked: 'UNCONFIGURED',
        });
      });
  }, []);

  const navItems = [
    {
      section: 'OVERVIEW',
      items: [
        { path: '/', label: 'Dashboard', icon: LayoutDashboard },
        { path: '/cases', label: 'Recovery Cases', icon: Inbox },
      ],
    },
    {
      section: 'INTELLIGENCE',
      items: [
        { path: '/promise-to-pay', label: 'Promise-to-Pay', icon: Sparkles },
        { path: '/evaluation', label: 'Evaluation & Benchmark', icon: BarChart3 },
      ],
    },
    {
      section: 'OPERATIONS',
      items: [
        { path: '/safety', label: 'Safety & Failure Sandbox', icon: ShieldCheck },
        { path: '/architecture', label: 'System Architecture', icon: Network },
      ],
    },
  ];

  const handleNav = (path: string) => {
    onNavigate(path);
    setMobileMenuOpen(false);
  };

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-[#02040A] text-slate-900 dark:text-slate-100 transition-colors">
      {/* Desktop Left Sidebar */}
      <aside className="hidden md:flex flex-col w-64 border-r border-slate-200 dark:border-slate-800/80 bg-white dark:bg-[#0B111E] fixed inset-y-0 left-0 z-30">
        {/* Brand Header */}
        <div className="p-5 border-b border-slate-100 dark:border-slate-800/60">
          <div className="flex items-center gap-3">
            <img src="/razorpay-logo.svg" alt="Razorpay" className="h-6 object-contain" />
          </div>
          <div className="mt-2.5 flex items-center justify-between">
            <div>
              <div className="text-base font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-1.5">
                RecoverIQ
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 font-mono font-semibold">
                  v1.0
                </span>
              </div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
                Adaptive Revenue Recovery
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Sections */}
        <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
          {navItems.map((sec) => (
            <div key={sec.section}>
              <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 font-mono">
                {sec.section}
              </div>
              <div className="space-y-1">
                {sec.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = currentPath === item.path || (item.path !== '/' && currentPath.startsWith(item.path));
                  return (
                    <button
                      key={item.path}
                      onClick={() => handleNav(item.path)}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                        isActive
                          ? 'bg-[#0C2340] text-white dark:bg-blue-600 dark:text-white shadow-sm'
                          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200'
                      }`}
                    >
                      <Icon className={`w-4 h-4 ${isActive ? 'text-blue-400 dark:text-white' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Bottom Status & Theme Panel */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800/60 space-y-2 bg-slate-50/50 dark:bg-[#070D17]">
          {/* Razorpay Test Mode Indicator */}
          <div className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-[#0B111E] text-xs">
            <div className="flex items-center justify-between font-mono">
              <span className="text-[10px] text-slate-400 font-bold uppercase">Razorpay Adapter</span>
              <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {razorpayStatus?.status === 'CONNECTED' ? 'CONNECTED' : 'TEST MODE'}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-slate-600 dark:text-slate-400 flex items-center justify-between">
              <span>{razorpayStatus?.status === 'CONNECTED' ? 'Live Sandbox API' : 'Offline / Mock Sandbox'}</span>
              <span className="font-mono text-[10px] text-slate-400">{razorpayStatus?.key_id_masked || 'TEST'}</span>
            </div>
          </div>

          {/* Theme Toggle & Buildathon Tag */}
          <div className="flex items-center justify-between px-1">
            <button
              onClick={toggleTheme}
              className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors py-1 px-2 rounded-md hover:bg-slate-200/60 dark:hover:bg-slate-800"
            >
              {theme === 'dark' ? (
                <>
                  <Sun className="w-3.5 h-3.5 text-amber-400" />
                  <span className="text-[11px]">Light Mode</span>
                </>
              ) : (
                <>
                  <Moon className="w-3.5 h-3.5 text-blue-600" />
                  <span className="text-[11px]">Dark Mode</span>
                </>
              )}
            </button>
            <span className="text-[9px] text-slate-400 font-mono tracking-tight">AI Buildathon 2026</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 md:ml-64 flex flex-col min-h-screen">
        {/* Global Top Header */}
        <header className="sticky top-0 z-20 h-14 border-b border-slate-200/80 dark:border-slate-800/80 bg-white/80 dark:bg-[#0B111E]/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-1.5 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            <div>
              <h1 className="text-sm font-semibold text-slate-900 dark:text-white capitalize">
                {currentPath === '/' ? 'Revenue Recovery Overview' : currentPath.slice(1).replace(/-/g, ' ')}
              </h1>
            </div>
          </div>

          {/* Right Header Badges */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-[11px] font-mono text-blue-700 dark:text-blue-300 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
              TEST MODE
            </div>
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[11px] font-mono text-slate-600 dark:text-slate-400">
              FROZEN HOLDOUT: 20K
            </div>
            <button
              onClick={toggleTheme}
              className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
            </button>
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 top-14 z-40 bg-white dark:bg-[#0B111E] p-4 border-b border-slate-200 dark:border-slate-800 space-y-4">
            {navItems.map((sec) => (
              <div key={sec.section}>
                <div className="text-[10px] font-bold text-slate-400 font-mono mb-1">{sec.section}</div>
                {sec.items.map((item) => (
                  <button
                    key={item.path}
                    onClick={() => handleNav(item.path)}
                    className="w-full text-left py-2 px-3 rounded text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-2"
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Page Body Viewport */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto space-y-6">
          {children}
        </main>

        {/* Subtle Footer Disclaimer */}
        <footer className="border-t border-slate-200 dark:border-slate-800/60 px-6 py-4 text-center text-xs text-slate-400 dark:text-slate-500">
          RecoverIQ is an AI revenue recovery prototype built for the Razorpay AI Buildathon 2026. All benchmark data is frozen from the Phase 9 scientific holdout.
        </footer>
      </div>
    </div>
  );
};

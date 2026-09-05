import React, { useState, useEffect, useRef } from 'react';
import {
  Menu,
  X,
  LayoutDashboard,
  Inbox,
  Sparkles,
  BarChart3,
  ShieldCheck,
  Network,
  Sun,
  Moon,
} from 'lucide-react';
import { useTheme } from '../../theme/useTheme';
import { useRecoverIQData } from '../../context/useRecoverIQData';
import { animateRouteArrival, animateDrawerOpen, animateDrawerClose } from '../../utils/motion';

interface ShellProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ currentPath, onNavigate, children }) => {
  const { theme, toggleTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [isRendered, setIsRendered] = useState(false);
  const { razorpayStatus } = useRecoverIQData();
  const mainContentRef = useRef<HTMLElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  // Close drawer smoothly with slide-out animation
  const closeMenu = () => {
    if (drawerRef.current && backdropRef.current) {
      animateDrawerClose(drawerRef.current, backdropRef.current, () => {
        setMenuOpen(false);
        setIsRendered(false);
      });
    } else {
      setMenuOpen(false);
      setIsRendered(false);
    }
  };

  const openMenu = () => {
    setIsRendered(true);
    setMenuOpen(true);
  };

  useEffect(() => {
    if (isRendered && menuOpen && drawerRef.current) {
      animateDrawerOpen(drawerRef.current, backdropRef.current);
    }
  }, [isRendered, menuOpen]);

  // Handle navigation
  const handleNav = (path: string) => {
    onNavigate(path);
    closeMenu();
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && menuOpen) {
        closeMenu();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [menuOpen]);

  // Animate page arrival on route change
  useEffect(() => {
    if (mainContentRef.current) {
      animateRouteArrival(mainContentRef.current);
    }
  }, [currentPath]);

  const navGroups = [
    {
      group: 'RECOVER',
      items: [
        { path: '/', label: 'Overview', icon: LayoutDashboard },
        { path: '/cases', label: 'Recovery Queue', icon: Inbox },
      ],
    },
    {
      group: 'INTELLIGENCE',
      items: [
        { path: '/promise-to-pay', label: 'Promise to Pay', icon: Sparkles },
        { path: '/evaluation', label: 'Evaluation Lab', icon: BarChart3 },
      ],
    },
    {
      group: 'CONTROL',
      items: [
        { path: '/safety', label: 'Safety & Sandbox', icon: ShieldCheck },
        { path: '/architecture', label: 'Architecture', icon: Network },
      ],
    },
  ];

  const getRazorpayStatusBadge = () => {
    if (razorpayStatus.data?.status === 'CONNECTED') {
      return {
        label: 'CONNECTED — TEST MODE',
        drawerLabel: 'Connected (Test Mode)',
        dotColor: 'bg-emerald-500',
        textColor: 'text-emerald-600 dark:text-emerald-400',
      };
    }
    if (razorpayStatus.data?.is_configured) {
      return {
        label: 'TEST MODE — OFFLINE',
        drawerLabel: 'Test Mode (Offline)',
        dotColor: 'bg-amber-500',
        textColor: 'text-amber-600 dark:text-amber-400',
      };
    }
    return {
      label: 'OFFLINE — MOCK',
      drawerLabel: 'Offline Mock Gateway',
      dotColor: 'bg-slate-400',
      textColor: 'text-slate-500 dark:text-slate-400',
    };
  };

  const rzpStatus = getRazorpayStatusBadge();

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#060606] text-slate-900 dark:text-[#F9FAFB] flex flex-col transition-colors">
      {/* 1. Global Persistent Top Navigation Bar (56–64px) */}
      <header className="sticky top-0 z-40 h-14 sm:h-16 border-b border-slate-200/80 dark:border-[#1F1F1F] bg-white/95 dark:bg-[#0F0F0F]/95 backdrop-blur-md px-4 sm:px-8 flex items-center justify-between">
        {/* Left: Menu Button & Brand Identity */}
        <div className="flex items-center gap-4 sm:gap-6">
          {/* Menu Trigger Button */}
          <button
            onClick={() => (menuOpen ? closeMenu() : openMenu())}
            className="flex items-center gap-2 px-2.5 sm:px-3 py-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#141414] hover:bg-slate-50 dark:hover:bg-[#1A1A1A] hover:-translate-y-0.5 active:translate-y-0 text-slate-700 dark:text-slate-200 text-xs font-semibold shadow-2xs transition-all duration-150 cursor-pointer select-none"
            aria-label="Toggle Navigation Menu"
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X className="w-4 h-4 text-blue-600 dark:text-blue-400" /> : <Menu className="w-4 h-4" />}
            <span className="hidden sm:inline">Menu</span>
          </button>

          {/* Brand Presence */}
          <div className="flex items-center gap-3 sm:gap-4">
            <img
              src="/razorpay-logo.png"
              alt="Razorpay"
              className="w-20 sm:w-24 h-auto object-contain dark:brightness-0 dark:invert transition-all"
            />
            <span className="text-slate-300 dark:text-[#2A2A2A] font-light select-none">|</span>
            <div className="flex items-baseline gap-2">
              <span className="text-base sm:text-lg font-bold tracking-tight text-slate-900 dark:text-white">
                RecoverIQ
              </span>
              <span className="hidden md:inline text-[11px] text-slate-500 dark:text-[#A3A3A3]">
                Adaptive Revenue Recovery
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-[#1A1A1A] text-slate-600 dark:text-[#A3A3A3]">
                v1.0
              </span>
            </div>
          </div>
        </div>

        {/* Right: Global Contextual Controls */}
        <div className="flex items-center gap-3 sm:gap-4 text-xs">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400 text-[11px] font-medium border border-blue-200/60 dark:border-blue-900/40">
            <span className={`w-1.5 h-1.5 rounded-full ${rzpStatus.dotColor}`} />
            {rzpStatus.label}
          </span>

          <span className="hidden sm:inline-flex px-2 py-0.5 rounded text-slate-500 dark:text-[#737373] text-[11px] font-mono border border-slate-200/50 dark:border-[#1A1A1A]">
            20K HOLDOUT
          </span>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-md border border-slate-200 dark:border-[#1F1F1F] bg-white dark:bg-[#141414] text-slate-600 dark:text-[#A3A3A3] hover:bg-slate-50 dark:hover:bg-[#1A1A1A] hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150 cursor-pointer"
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-slate-600" />
            )}
          </button>
        </div>
      </header>

      {/* 2. Slide-out Navigation Drawer / Popover */}
      {isRendered && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop with fade-in */}
          <div
            ref={backdropRef}
            onClick={closeMenu}
            className="fixed inset-0 bg-black/45 backdrop-blur-[2px] transition-opacity cursor-pointer opacity-0"
          />

          {/* Drawer Content - Translucent dark glass surface (rgba(10,10,10,0.85) + 20px blur) sliding from left */}
          <div
            ref={drawerRef}
            style={{ transform: 'translateX(-100%)' }}
            className="relative z-10 w-72 sm:w-80 bg-white/85 dark:bg-[#0A0A0A]/85 backdrop-blur-xl border-r border-slate-200/80 dark:border-[#1F1F1F] shadow-2xl h-full flex flex-col p-6 will-change-transform"
          >
            {/* Drawer Header */}
            <div className="drawer-nav-item flex items-center justify-between pb-5 border-b border-slate-100 dark:border-[#1F1F1F]">
              <div className="flex items-center gap-2.5">
                <img
                  src="/razorpay-logo.png"
                  alt="Razorpay"
                  className="w-20 h-auto object-contain dark:brightness-0 dark:invert"
                />
                <span className="font-bold text-sm text-slate-900 dark:text-white">RecoverIQ</span>
              </div>
              <button
                onClick={closeMenu}
                className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-[#1A1A1A] transition-colors cursor-pointer"
                aria-label="Close menu"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Navigation Groups */}
            <nav className="flex-1 py-6 space-y-6 overflow-y-auto">
              {navGroups.map((grp) => (
                <div key={grp.group} className="drawer-nav-item space-y-1.5">
                  <div className="px-3 text-[10px] font-semibold tracking-wider text-slate-400 dark:text-[#737373] uppercase">
                    {grp.group}
                  </div>
                  <div className="space-y-0.5">
                    {grp.items.map((item) => {
                      const Icon = item.icon;
                      const isActive =
                        currentPath === item.path ||
                        (item.path !== '/' && currentPath.startsWith(item.path));
                      return (
                        <button
                          key={item.path}
                          onClick={() => handleNav(item.path)}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-medium transition-all duration-150 cursor-pointer ${
                            isActive
                              ? 'bg-slate-100/90 text-blue-600 dark:bg-[#1A1A1A]/90 dark:text-blue-400 font-semibold shadow-2xs'
                              : 'text-slate-600 dark:text-[#A3A3A3] hover:bg-slate-50/80 dark:hover:bg-[#141414]/80 hover:text-slate-900 dark:hover:text-white hover:translate-x-1'
                          }`}
                        >
                          <Icon
                            className={`w-4 h-4 ${
                              isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400'
                            }`}
                          />
                          <span>{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>

            {/* Drawer Footer */}
            <div className="drawer-nav-item pt-4 border-t border-slate-100 dark:border-[#1F1F1F] text-xs space-y-1.5 text-slate-500 dark:text-[#737373]">
              <div className="flex items-center justify-between text-[11px]">
                <span>Gateway Status</span>
                <span className={`font-medium ${rzpStatus.textColor}`}>{rzpStatus.drawerLabel}</span>
              </div>
              <div className="text-[10px] text-slate-400 dark:text-[#666]">
                Track 03: AI Revenue Recovery · Razorpay
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. Full-Width Workspace Canvas (No Left Sidebar Margin) */}
      <main ref={mainContentRef} className="flex-1 p-6 sm:p-10 max-w-[1450px] w-full mx-auto space-y-10 will-change-[opacity,transform]">
        {children}
      </main>

      {/* 4. Global Footer */}
      <footer className="border-t border-slate-200/80 dark:border-[#1F1F1F] px-6 sm:px-10 py-5 text-xs text-slate-400 dark:text-[#737373] flex flex-col sm:flex-row items-center justify-between gap-3 max-w-[1450px] w-full mx-auto">
        <span>RecoverIQ — AI Revenue Recovery Platform</span>
        <span>Razorpay Ecosystem Integration · Track 03</span>
      </footer>
    </div>
  );
};

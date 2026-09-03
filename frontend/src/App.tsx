import React, { useState, useEffect } from 'react';
import { Shell } from './components/layout/Shell';
import { Overview } from './pages/Overview';
import { Cases } from './pages/Cases';
import { CaseDetail } from './pages/CaseDetail';
import { PromiseToPay } from './pages/PromiseToPay';
import { Evaluation } from './pages/Evaluation';
import { Safety } from './pages/Safety';
import { Architecture } from './pages/Architecture';

export const App: React.FC = () => {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    const hash = window.location.hash.replace(/^#/, '');
    return hash || '/';
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace(/^#/, '');
      setCurrentPath(hash || '/');
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigate = (path: string) => {
    window.location.hash = path;
    setCurrentPath(path);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderContent = () => {
    if (currentPath === '/' || currentPath === '') {
      return <Overview onNavigate={navigate} />;
    }
    if (currentPath === '/cases') {
      return <Cases onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/cases/')) {
      const caseId = currentPath.replace('/cases/', '');
      return <CaseDetail caseId={caseId} onNavigate={navigate} />;
    }
    if (currentPath === '/promise-to-pay') {
      return <PromiseToPay />;
    }
    if (currentPath === '/evaluation') {
      return <Evaluation />;
    }
    if (currentPath === '/safety') {
      return <Safety />;
    }
    if (currentPath === '/architecture') {
      return <Architecture />;
    }
    return <Overview onNavigate={navigate} />;
  };

  return (
    <Shell currentPath={currentPath} onNavigate={navigate}>
      {renderContent()}
    </Shell>
  );
};

import { useContext } from 'react';
import { DataContext } from './DataContext';

export const useRecoverIQData = () => {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useRecoverIQData must be used within DataProvider');
  return ctx;
};

import { useContext } from 'react';
import { AIHelpContext } from '@/components/AIHelpProvider';
import type { AIHelpContextValue } from '@/types/help';

export function useAIHelp(): AIHelpContextValue {
  const ctx = useContext(AIHelpContext);
  if (!ctx) {
    throw new Error('useAIHelp must be used within AIHelpProvider');
  }
  return ctx;
}

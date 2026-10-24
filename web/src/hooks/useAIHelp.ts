import { useContext } from 'react';
import { AIHelpContext, AIHelpStreamContext } from '@/components/AIHelpProvider';
import type { AIHelpContextValue, AIHelpStreamValue } from '@/types/help';

export function useAIHelp(): AIHelpContextValue {
  const ctx = useContext(AIHelpContext);
  if (!ctx) {
    throw new Error('useAIHelp must be used within AIHelpProvider');
  }
  return ctx;
}

/**
 * 订阅高频流式状态（steps / streamedText）。每个 SSE chunk 都会触发
 * 重渲染，只应在真正渲染打字机/步骤动画的组件（AIHelpDrawer）里使用；
 * 只要 open 等动作的组件请继续用 useAIHelp（2026-10-25 P0 拆分）。
 */
export function useAIHelpStream(): AIHelpStreamValue {
  const ctx = useContext(AIHelpStreamContext);
  if (!ctx) {
    throw new Error('useAIHelpStream must be used within AIHelpProvider');
  }
  return ctx;
}

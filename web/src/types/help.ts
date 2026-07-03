import type { Step } from '@/hooks/useStepStream';

export type HelpPageType =
  | 'score_ranking'
  | 'instrument_detail'
  | 'strategy_list'
  | 'backtest_detail'
  | 'screen'
  | 'pool_detail'
  | 'listing_preview'
  | 'signal_dashboard';

export interface HelpMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface HelpContext {
  pageType: HelpPageType;
  pageTitle: string;
  contextData: string;
  quickQuestions?: string[];
  /** 打开抽屉后自动发送的初始问题，默认会介绍当前页面 */
  initialQuestion?: string;
}

export interface AIHelpState {
  isOpen: boolean;
  context: HelpContext | null;
  messages: HelpMessage[];
  isLoading: boolean;
  error: string | null;
  sessionId: number | null;
  /** 步骤状态机（S3） */
  steps: Step[];
  /** 打字机渲染中的临时文本（S3） */
  streamedText: string;
}

export interface AIHelpContextValue extends AIHelpState {
  open: (context: HelpContext) => Promise<void>;
  close: () => void;
  sendMessage: (content: string) => Promise<void>;
  retryLast: () => Promise<void>;
}

export interface HelpTriggerProps {
  onClick?: () => void;
  tooltip?: string;
  size?: 'small' | 'default';
  style?: React.CSSProperties;
  className?: string;
}

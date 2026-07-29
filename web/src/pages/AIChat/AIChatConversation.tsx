import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, Tag } from 'antd';
// The phase5c-* styles live here (not in the page module) because this
// component also renders inside the global mobile BottomSheet on pages
// where the /chat chunk — and its CSS — is never loaded.
import './styles.css';
import {
  RobotOutlined,
  SendOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from '@/api/chat';
import StepProgress from '@/components/StepProgress';
import LoadingBlock from '@/components/LoadingBlock';
import type { AIChatController } from './useAIChatController';

const QUICK_PROMPTS = [
  { label: '分析 AAPL 的散户情绪', prompt: '请分析 AAPL 最近 7 日的散户情绪与多空比' },
  { label: '今日热点解读', prompt: '请总结今日 importance ≥ 4 的热点资讯' },
  { label: '自选股舆情', prompt: '我自选股的最新舆情和情绪如何？' },
];

export interface AIChatConversationProps {
  controller: AIChatController;
  /**
   * 'page'  — inside /chat: renders the card wrapper (border/shadow) and
   *           manages its own internal scroll pane.
   * 'sheet' — inside the global BottomSheet (方向 D): renders bare so the
   *           sheet body is the scroll container and the input bar is a
   *           sticky footer within it. No card chrome (the sheet is the
   *           surface).
   */
  variant?: 'page' | 'sheet';
  /** Show the mobile "← 返回列表" row (page variant only). */
  showBack?: boolean;
  onBack?: () => void;
}

/**
 * The AI assistant conversation (messages + composer), shared verbatim
 * between the /chat page and the global mobile BottomSheet so both
 * surfaces render — and stream — identically.
 */
export default function AIChatConversation({
  controller,
  variant = 'page',
  showBack = false,
  onBack,
}: AIChatConversationProps) {
  const {
    activeSession,
    messages,
    messagesLoading,
    sending,
    steps,
    streamedText,
    input,
    setInput,
    handleSend,
    messagesEndRef,
  } = controller;
  const navigate = useNavigate();

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const reducedMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    messagesEndRef.current?.scrollIntoView({
      behavior: reducedMotion ? 'auto' : 'smooth',
    });
  }, [messages, messagesEndRef]);

  const isSheet = variant === 'sheet';

  const messagesEl = (
    <div
      className={`phase5c-chat-messages ${isSheet ? 'phase5c-chat-messages--sheet' : ''}`}
    >
      {!activeSession ? (
        <div className="phase5c-chat-empty">
          <RobotOutlined className="phase5c-empty-icon" />
          <div className="phase5c-chat-empty__title">开始你的 AI 投研对话</div>
          <div className="phase5c-chat-empty__desc">
            点下面的建议问题直接开始，或在底部输入框提问
          </div>
          <div className="phase5c-chat-empty__prompts">
            {QUICK_PROMPTS.map((s) => (
              <button
                key={s.label}
                type="button"
                className="phase5c-chat-empty__prompt-card"
                onClick={() => void handleSend(s.prompt)}
                disabled={sending}
              >
                <span className="phase5c-chat-empty__prompt-label">{s.label}</span>
                <span className="phase5c-chat-empty__prompt-text">{s.prompt}</span>
              </button>
            ))}
          </div>
        </div>
      ) : messagesLoading ? (
        <LoadingBlock size="md" />
      ) : (
        messages?.map((msg: ChatMessage) => (
          <div
            key={msg.id}
            className={`phase5c-message-row ${msg.role === 'user' ? 'phase5c-message-row--user' : 'phase5c-message-row--assistant'}`}
          >
            <div className={`phase5c-message-bubble ${msg.role === 'user' ? 'phase5c-message-bubble--user' : 'phase5c-message-bubble--assistant'}`}>
              {msg.role === 'assistant' ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))
      )}
      {sending && (
        <div className="phase5c-message-row phase5c-message-row--assistant">
          <div className="phase5c-message-bubble phase5c-message-bubble--streaming">
            <StepProgress steps={steps} compact />
            {streamedText && (
              <div className="phase5c-streaming-divider">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamedText}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );

  const inputEl = (
    <div className={`phase5c-input-bar ${isSheet ? 'phase5c-input-bar--sheet' : ''}`}>
      {/* Sentiment quick-prompt hint. Tells the user the assistant has
          access to news/sentiment data and surfaces a clickable tag to
          jump to the sentiment dashboard. */}
      <div className="phase5c-quick-prompts">
        <HeartOutlined className="phase5c-icon-rise" />
        <span>AI 可访问资讯与情绪数据：</span>
        {QUICK_PROMPTS.map((s) => (
          <Tag
            key={s.label}
            className="phase5c-quick-tag"
            onClick={() => setInput(s.prompt)}
          >
            {s.label}
          </Tag>
        ))}
        <span className="phase5c-quick-prompts__spacer" />
        <Tag
          icon={<HeartOutlined />}
          color="default"
          className="phase5c-quick-tag"
          onClick={() => navigate('/sentiment')}
        >
          打开情绪看板
        </Tag>
      </div>
      <div className="phase5c-input-row">
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="输入问题... (Shift+Enter换行，Enter发送)"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={sending}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={() => handleSend()}
          loading={sending}
          disabled={sending || !input.trim()}
        />
      </div>
    </div>
  );

  // Sheet variant: no card wrapper — the BottomSheet body is the scroll
  // container and the input bar sticks to its bottom edge (classic
  // sticky-footer: it's the last child, pulled up by `bottom: 0`).
  if (isSheet) {
    return (
      <>
        {messagesEl}
        {inputEl}
      </>
    );
  }

  return (
    <div className="phase5c-chat-area">
      {/* Mobile back button */}
      {showBack && activeSession && (
        <div className="phase5c-mobile-back">
          <Button type="text" onClick={onBack}>
            ← 返回列表
          </Button>
        </div>
      )}
      {messagesEl}
      {inputEl}
    </div>
  );
}

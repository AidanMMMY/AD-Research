import { useRef, useEffect, useState } from 'react';
import { Drawer, Input, Button, Tag, Space, Alert } from 'antd';
import {
  RobotOutlined,
  SendOutlined,
  CloseOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useAIStatus } from '@/components/AISetupBanner';
import { useSettingsStore } from '@/stores/settings';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useFocusRestore } from '@/hooks/useFocusRestore';
import StepProgress from '@/components/StepProgress';
import { BottomSheet } from '@/components/BottomSheet';
import type { HelpMessage } from '@/types/help';
import './AIHelpDrawer.css';

function MessageBubble({ msg }: { msg: HelpMessage }) {
  const isUser = msg.role === 'user';

  return (
    <div
      className={`ai-message-row ${isUser ? 'ai-message-row--user' : 'ai-message-row--assistant'}`}
    >
      <div
        className={`ai-message-bubble ${isUser ? 'ai-message-bubble--user' : 'ai-message-bubble--assistant'}`}
      >
        {isUser ? (
          msg.content
        ) : (
          <div className="ai-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * AI 教学助手 surface.
 *
 * Desktop: right-side AntD Drawer (480px) — unchanged.
 * Mobile (≤767px, 方向 D 2026-07-29): the same conversation moves into
 * the global BottomSheet (half/full detents) so contextual help no
 * longer takes over the whole screen; ``avoidKeyboard`` keeps the
 * composer above the on-screen keyboard. Conversation state lives in
 * AIHelpProvider, so closing the sheet (scrim tap / swipe down / ESC)
 * preserves the thread — it only resets when a page re-invokes
 * ``open()`` with a fresh help context.
 */
export default function AIHelpDrawer() {
  const {
    isOpen,
    context,
    messages,
    isLoading,
    error,
    steps,
    streamedText,
    close,
    sendMessage,
    retryLast,
  } = useAIHelp();
  const { data: aiStatus, isLoading: aiStatusLoading } = useAIStatus();
  const { mode } = useSettingsStore();
  const isMobile = useIsMobile();
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const aiAvailable = aiStatus?.available ?? false;

  // WCAG 2.4.3: when the AI surface closes, return focus to the trigger
  // button (the help icon in the header) so keyboard users don't get
  // dumped back at <body>.
  useFocusRestore(isOpen);

  useEffect(() => {
    // Reduced-motion 用户：禁用平滑滚动，直接跳转（cross-fade 原则）
    const reduceMotion = window.matchMedia?.(
      '(prefers-reduced-motion: reduce)'
    ).matches;
    messagesEndRef.current?.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }, [messages, isLoading]);

  useEffect(() => {
    if (isOpen) {
      setInput('');
    }
  }, [isOpen, context?.pageType]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const content = input.trim();
    setInput('');
    await sendMessage(content);
  };

  const handleQuickQuestion = (question: string) => {
    if (isLoading) return;
    sendMessage(question);
  };

  const handleRetry = () => {
    if (messages.length === 0) return;
    retryLast();
  };

  const modeTag = (
    <Tag className={`ai-drawer__mode-tag ai-drawer__mode-tag--${mode}`}>
      {mode === 'novice' ? '新手' : '专业'}
    </Tag>
  );
  const contextTag = context?.contextData ? (
    <Tag className="ai-drawer__context-tag">
      <ThunderboltOutlined className="ai-drawer__context-tag-icon" />
      上下文已加载
    </Tag>
  ) : null;

  const statusAlert = !aiStatusLoading && !aiAvailable ? (
    <Alert
      type="warning"
      showIcon
      message="AI 功能未配置"
      description={`当前无法使用 AI 帮助。请在服务端配置 ${aiStatus?.provider === 'minimax' ? 'MINIMAX_API_KEY' : 'DEEPSEEK_API_KEY'} 后重启服务。`}
      className="ai-drawer__alert"
    />
  ) : null;

  const messagesEl = (
    <div
      className={`ai-drawer__messages ${isMobile ? 'ai-drawer__messages--sheet' : ''}`}
    >
      {messages.length === 0 && !isLoading && (
        <div className="ai-drawer__empty">
          <RobotOutlined className="ai-drawer__empty-icon" />
          <div>点击右上角帮助图标开始提问</div>
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} msg={msg} />
      ))}

      {isLoading && (
        <div className="ai-message-row ai-message-row--assistant">
          <div className="ai-message-bubble ai-message-bubble--assistant">
            <StepProgress steps={steps} compact />
            {streamedText && (
              <div className="ai-message-bubble__streamed ai-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamedText}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={handleRetry}
              className="ai-retry-btn"
            >
              重试
            </Button>
          }
          className="ai-error-alert"
        />
      )}

      <div ref={messagesEndRef} />
    </div>
  );

  const quickEl = context?.quickQuestions && messages.length <= 2 ? (
    <div className={`ai-drawer__quick ${isMobile ? 'ai-drawer__quick--sheet' : ''}`}>
      <div className="ai-drawer__quick-title">快捷问题</div>
      <Space size={8} wrap className="ai-drawer__quick-tags">
        {context.quickQuestions.map((q) => (
          <Tag
            key={q}
            className={`ai-drawer__quick-tag ${isLoading || !aiAvailable ? 'ai-drawer__quick-tag--disabled' : ''}`}
            onClick={() => handleQuickQuestion(q)}
          >
            {q}
          </Tag>
        ))}
      </Space>
    </div>
  ) : null;

  const inputRow = (
    <div
      className={`ai-drawer__input-row ${isMobile ? 'ai-drawer__input-row--sheet' : ''}`}
    >
      <Input.TextArea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder={aiAvailable ? '输入问题...（Shift+Enter 换行，Enter 发送）' : 'AI 未配置，无法提问'}
        autoSize={{ minRows: 1, maxRows: 4 }}
        disabled={isLoading || !aiAvailable}
        className="ai-drawer__input"
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        loading={isLoading}
        disabled={!input.trim() || !aiAvailable}
        className="ai-drawer__send"
      />
    </div>
  );

  // ── Mobile: global BottomSheet (方向 D) ────────────────────────────
  // The sheet chrome (grabber/title/close) replaces the drawer header;
  // the composer pins to the sheet footer so it never scrolls away, and
  // avoidKeyboard shrinks the content column when the keyboard opens.
  if (isMobile) {
    return (
      <BottomSheet
        open={isOpen}
        onClose={close}
        snaps={['half', 'full']}
        avoidKeyboard
        title={
          <span className="ai-drawer__title-row ai-drawer__title-row--sheet">
            <span className="ai-drawer__avatar ai-drawer__avatar--sheet">
              <RobotOutlined className="ai-drawer__avatar-icon" />
            </span>
            <span className="ai-drawer__titles">
              <span className="ai-drawer__title ai-drawer__title--sheet">
                AI 教学助手
              </span>
              {context && (
                <span className="ai-drawer__subtitle">{context.pageTitle}</span>
              )}
            </span>
          </span>
        }
        footer={inputRow}
      >
        <div className="ai-drawer__sheet-tags">
          {modeTag}
          {contextTag}
        </div>
        {statusAlert}
        {messagesEl}
        {quickEl}
      </BottomSheet>
    );
  }

  // ── Desktop: right Drawer (unchanged) ──────────────────────────────
  return (
    <Drawer
      placement="right"
      open={isOpen}
      onClose={close}
      width={480}
      closable={false}
      className="ai-drawer"
    >
      <div className="ai-drawer">
        {/* Header */}
        <div className="ai-drawer__header">
          <div className="ai-drawer__title-row">
            <div className="ai-drawer__avatar">
              <RobotOutlined className="ai-drawer__avatar-icon" />
            </div>
            <div className="ai-drawer__titles">
              <div className="ai-drawer__title">AI 教学助手</div>
              {context && (
                <div className="ai-drawer__subtitle">{context.pageTitle}</div>
              )}
            </div>
          </div>

          <div className="ai-drawer__header-actions">
            {modeTag}
            {contextTag}
            <Button
              type="text"
              icon={<CloseOutlined className="ai-drawer__close-icon" />}
              onClick={close}
              className="ai-drawer__close"
            />
          </div>
        </div>

        {/* AI Status Alert */}
        {statusAlert}

        {/* Messages */}
        {messagesEl}

        {/* Quick Questions */}
        {quickEl}

        {/* Input */}
        {inputRow}
      </div>
    </Drawer>
  );
}

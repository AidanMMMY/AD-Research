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
import { useIsMobile } from '@/hooks/useBreakpoint';
import StepProgress from '@/components/StepProgress';
import type { HelpMessage } from '@/types/help';

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
  const isMobile = useIsMobile();
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const aiAvailable = aiStatus?.available ?? false;

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

  return (
    <Drawer
      placement="right"
      open={isOpen}
      onClose={close}
      width={isMobile ? '100%' : 480}
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
            {context?.contextData && (
              <Tag className="ai-drawer__context-tag">
                <ThunderboltOutlined className="ai-drawer__context-tag-icon" />
                上下文已加载
              </Tag>
            )}
            <Button
              type="text"
              icon={<CloseOutlined className="ai-drawer__close-icon" />}
              onClick={close}
              className="ai-drawer__close"
            />
          </div>
        </div>

        {/* AI Status Alert */}
        {!aiStatusLoading && !aiAvailable && (
          <Alert
            type="warning"
            showIcon
            message="AI 功能未配置"
            description="当前无法使用 AI 帮助。请在服务端配置 DEEPSEEK_API_KEY 后重启服务。"
            className="ai-drawer__alert"
          />
        )}

        {/* Messages */}
        <div className="ai-drawer__messages">
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

        {/* Quick Questions */}
        {context?.quickQuestions && messages.length <= 2 && (
          <div className="ai-drawer__quick">
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
        )}

        {/* Input */}
        <div className="ai-drawer__input-row">
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
      </div>
    </Drawer>
  );
}

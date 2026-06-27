import { useRef, useEffect, useState } from 'react';
import { Drawer, Input, Button, Tag, Space, Alert, Spin } from 'antd';
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
import type { HelpMessage } from '@/types/help';

function MessageBubble({ msg }: { msg: HelpMessage }) {
  const isUser = msg.role === 'user';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
      }}
    >
      <div
        style={{
          maxWidth: '85%',
          padding: '12px 16px',
          borderRadius: 14,
          borderTopRightRadius: isUser ? 4 : 14,
          borderTopLeftRadius: isUser ? 14 : 4,
          background: isUser
            ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
            : 'rgba(255,255,255,0.06)',
          color: isUser ? '#fff' : '#e2e8f0',
          fontSize: 14,
          lineHeight: 1.7,
          border: isUser ? 'none' : '1px solid rgba(255,255,255,0.08)',
        }}
      >
        {isUser ? (
          msg.content
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p style={{ margin: '0 0 8px' }}>{children}</p>,
              ul: ({ children }) => <ul style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ul>,
              ol: ({ children }) => <ol style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ol>,
              li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
              code: ({ children }) => (
                <code
                  style={{
                    background: 'rgba(255,255,255,0.08)',
                    padding: '2px 6px',
                    borderRadius: 4,
                    fontSize: 13,
                    color: '#e2e8f0',
                  }}
                >
                  {children}
                </code>
              ),
              pre: ({ children }) => (
                <pre
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    padding: 10,
                    borderRadius: 8,
                    overflow: 'auto',
                    fontSize: 13,
                  }}
                >
                  {children}
                </pre>
              ),
              table: ({ children }) => (
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    marginBottom: 8,
                    fontSize: 13,
                  }}
                >
                  {children}
                </table>
              ),
              th: ({ children }) => (
                <th
                  style={{
                    border: '1px solid rgba(255,255,255,0.1)',
                    padding: '6px 10px',
                    background: 'rgba(255,255,255,0.06)',
                    textAlign: 'left',
                  }}
                >
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td
                  style={{
                    border: '1px solid rgba(255,255,255,0.08)',
                    padding: '6px 10px',
                  }}
                >
                  {children}
                </td>
              ),
            }}
          >
            {msg.content}
          </ReactMarkdown>
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
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
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
      styles={{
        body: { padding: 0, background: 'linear-gradient(180deg, #0a0f1e 0%, #0d1326 100%)' },
        header: { display: 'none' },
        mask: { background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' },
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                boxShadow: '0 0 12px rgba(99, 102, 241, 0.4)',
              }}
            >
              <RobotOutlined style={{ color: '#fff', fontSize: 18 }} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  color: '#f1f5f9',
                  lineHeight: '22px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                AI 教学助手
              </div>
              {context && (
                <div
                  style={{
                    fontSize: 12,
                    color: '#64748b',
                    lineHeight: '18px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {context.pageTitle}
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {context?.contextData && (
              <Tag
                color="purple"
                style={{
                  background: 'rgba(99,102,241,0.12)',
                  border: '1px solid rgba(99,102,241,0.2)',
                  color: '#818cf8',
                }}
              >
                <ThunderboltOutlined style={{ marginRight: 4 }} />
                上下文已加载
              </Tag>
            )}
            <Button
              type="text"
              icon={<CloseOutlined style={{ color: '#94a3b8', fontSize: 16 }} />}
              onClick={close}
              style={{ width: 32, height: 32, padding: 0 }}
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
            style={{
              margin: 12,
              borderRadius: 10,
              background: 'rgba(234,179,8,0.08)',
              border: '1px solid rgba(234,179,8,0.2)',
            }}
          />
        )}

        {/* Messages */}
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '16px 20px',
          }}
        >
          {messages.length === 0 && !isLoading && (
            <div style={{ textAlign: 'center', marginTop: 80, color: '#64748b' }}>
              <RobotOutlined style={{ fontSize: 40, marginBottom: 12, color: '#475569' }} />
              <div style={{ fontSize: 14 }}>点击右上角帮助图标开始提问</div>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {isLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
              <div
                style={{
                  padding: '12px 16px',
                  borderRadius: 14,
                  borderTopLeftRadius: 4,
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Spin size="small" />
                <span style={{ color: '#94a3b8', fontSize: 14 }}>AI 思考中...</span>
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
                  style={{
                    background: 'rgba(239,68,68,0.15)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    color: '#fca5a5',
                  }}
                >
                  重试
                </Button>
              }
              style={{
                marginTop: 8,
                borderRadius: 10,
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.2)',
              }}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Questions */}
        {context?.quickQuestions && messages.length <= 2 && (
          <div
            style={{
              padding: '12px 20px 0',
              borderTop: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>快捷问题</div>
            <Space size={8} wrap style={{ width: '100%' }}>
              {context.quickQuestions.map((q) => (
                <Tag
                  key={q}
                  style={{
                    cursor: isLoading || !aiAvailable ? 'not-allowed' : 'pointer',
                    borderRadius: 8,
                    padding: '4px 10px',
                    background: 'rgba(99,102,241,0.12)',
                    border: '1px solid rgba(99,102,241,0.25)',
                    color: '#a5b4fc',
                    fontSize: 13,
                    opacity: isLoading || !aiAvailable ? 0.5 : 1,
                  }}
                  onClick={() => handleQuickQuestion(q)}
                >
                  {q}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        {/* Input */}
        <div
          style={{
            padding: '12px 20px 16px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            display: 'flex',
            gap: 10,
          }}
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
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isLoading}
            disabled={!input.trim() || !aiAvailable}
            style={{
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              border: 'none',
              alignSelf: 'flex-end',
            }}
          />
        </div>
      </div>
    </Drawer>
  );
}

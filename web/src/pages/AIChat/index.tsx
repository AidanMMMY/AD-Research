import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Input, Button, List, Popconfirm, Empty, Skeleton, Tag } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
  SendOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import { chatApi, ChatSession, ChatMessage } from '@/api/chat';
import AISetupBanner from '@/components/AISetupBanner';
import StepProgress from '@/components/StepProgress';
import { useStepStream } from '@/hooks/useStepStream';
import { useIsMobile } from '@/hooks/useBreakpoint';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function AIChat() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [activeSession, setActiveSession] = useState<number | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const STEP_DEFS = [
    { id: 'fetch', label: '准备上下文' },
    { id: 'llm', label: '调用大模型' },
    { id: 'stream', label: '生成回答' },
  ];
  const { steps, streamedText, start, finish, reset, appendStreamed } = useStepStream(STEP_DEFS);

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => chatApi.listSessions().then((r) => r.data),
  });

  const { data: messages, isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', activeSession],
    queryFn: () =>
      activeSession
        ? chatApi.getMessages(activeSession).then((r) => r.data)
        : Promise.resolve([]),
    enabled: !!activeSession,
  });

  const createMutation = useMutation({
    mutationFn: () => chatApi.createSession('新对话'),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      setActiveSession(resp.data.id);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => chatApi.deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      if (activeSession) {
        setActiveSession(null);
      }
    },
  });

  const handleSend = async () => {
    if (!input.trim() || !activeSession || sending) return;
    const content = input;
    setInput('');
    setSending(true);
    reset(STEP_DEFS);
    try {
      start('fetch');
      await new Promise((r) => setTimeout(r, 120));
      finish('fetch', 'done');
      start('llm');
      // Real SSE stream — parses meta/delta/done frames server-side.
      let receivedContent = false;
      await new Promise<void>((resolve, reject) => {
        chatApi.streamMessage(activeSession, content, {
          onDelta: (chunk) => {
            receivedContent = true;
            appendStreamed(chunk);
          },
          onDone: () => {
            finish('llm', 'done');
            finish('stream', 'done');
            resolve();
          },
          onError: (err) => {
            finish('llm', 'error');
            // If no chunks arrived, fall back to the legacy POST.
            if (!receivedContent) {
              chatApi.sendMessage(activeSession, content)
                .then((res) => {
                  appendStreamed(res.data.content);
                  finish('stream', 'done');
                  resolve();
                })
                .catch(() => reject(new Error(err.error)));
              return;
            }
            resolve();
          },
        }).catch(reject);
      });
      queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSession] });
    } catch {
      finish('llm', 'error');
    }
    setSending(false);
  };

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Show session sidebar on desktop; toggle on mobile
  const showSidebar = !isMobile || !activeSession;

  const sidebar = (
    <div style={{
      width: isMobile ? '100%' : 240,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        loading={createMutation.isPending}
        onClick={() => createMutation.mutate()}
        block
        style={{ background: 'var(--accent)', border: 'none' }}
      >
        新对话
      </Button>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {sessionsLoading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : !sessions?.length ? (
          <Empty description="暂无对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            dataSource={sessions}
            renderItem={(s: ChatSession) => (
              <div
                onClick={() => setActiveSession(s.id)}
                style={{
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-lg)',
                  cursor: 'pointer',
                  marginBottom: 4,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: activeSession === s.id ? 'var(--accent-dim)' : 'transparent',
                  border: activeSession === s.id ? '1px solid var(--card-border)' : '1px solid transparent',
                }}
              >
                <span style={{
                  fontSize: 13,
                  color: activeSession === s.id ? 'var(--accent)' : 'var(--text-secondary)',
                  fontWeight: activeSession === s.id ? 600 : 400,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flex: 1,
                }}>
                  {s.title || '新对话'}
                </span>
                <Popconfirm
                  title="删除此对话？"
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    deleteMutation.mutate(s.id);
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <DeleteOutlined
                    style={{ color: 'var(--text-tertiary)', fontSize: 12, flexShrink: 0 }}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </div>
            )}
          />
        )}
      </div>
    </div>
  );

  const chatArea = (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--card-bg)',
      borderRadius: 'var(--card-radius)',
      border: '1px solid var(--card-border)',
      boxShadow: 'var(--shadow-card)',
      overflow: 'hidden',
    }}>
      {/* Mobile back button */}
      {isMobile && activeSession && (
        <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-default)' }}>
          <Button type="text" onClick={() => setActiveSession(null)}>
            ← 返回列表
          </Button>
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
        {!activeSession ? (
          <Empty
            description="选择一个对话或创建新对话"
            style={{ marginTop: 80 }}
            image={<RobotOutlined style={{ fontSize: 48, color: 'var(--text-tertiary)' }} />}
          />
        ) : messagesLoading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : (
          messages?.map((msg: ChatMessage) => (
            <div
              key={msg.id}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 16,
              }}
            >
              <div style={{
                maxWidth: '80%',
                padding: '12px 16px',
                borderRadius: 'var(--radius-lg)',
                borderTopRightRadius: msg.role === 'user' ? 4 : 'var(--radius-lg)',
                borderTopLeftRadius: msg.role === 'assistant' ? 4 : 'var(--radius-lg)',
                background:
                  msg.role === 'user'
                    ? 'var(--accent-dim)'
                    : 'var(--bg-elevated)',
                color: msg.role === 'user' ? 'var(--accent)' : 'var(--text-primary)',
                fontSize: 14,
                lineHeight: 1.7,
              }}>
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
          <div
            style={{
              padding: '12px 16px',
              marginBottom: 16,
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              borderTopLeftRadius: 4,
              maxWidth: '80%',
            }}
          >
            <StepProgress steps={steps} compact />
            {streamedText && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-default)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-primary)' }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamedText}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      {activeSession && (
        <div style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--border-default)',
        }}>
          {/* Sentiment quick-prompt hint. Tells the user the assistant has
              access to news/sentiment data and surfaces a clickable tag to
              jump to the sentiment dashboard. */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              flexWrap: 'wrap',
              marginBottom: 8,
              fontSize: 12,
              color: 'var(--text-tertiary)',
            }}
          >
            <HeartOutlined style={{ color: '#f5222d' }} />
            <span>AI 可访问资讯与情绪数据：</span>
            {[
              { label: '分析 AAPL 的散户情绪', prompt: '请分析 AAPL 最近 7 日的散户情绪与多空比' },
              { label: '今日热点解读', prompt: '请总结今日 importance ≥ 4 的热点资讯' },
              { label: '自选股舆情', prompt: '我自选股的最新舆情和情绪如何？' },
            ].map((s) => (
              <Tag
                key={s.label}
                style={{ cursor: 'pointer', fontSize: 11, margin: 0 }}
                onClick={() => setInput(s.prompt)}
              >
                {s.label}
              </Tag>
            ))}
            <span style={{ flex: 1 }} />
            <Tag
              icon={<HeartOutlined />}
              color="default"
              style={{ cursor: 'pointer', margin: 0, fontSize: 11 }}
              onClick={() => navigate('/sentiment')}
            >
              打开情绪看板
            </Tag>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
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
            style={{ flex: 1 }}
            disabled={sending}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={sending}
            disabled={!input.trim()}
            style={{
              background: 'var(--accent)',
              border: 'none',
              alignSelf: 'flex-end',
            }}
          />
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div>
      <AISetupBanner />
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        AI 助手
      </h1>
      <p
        style={{
          margin: '0 0 32px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        多会话 AI 对话，支持 Markdown 与代码高亮
      </p>
      <div style={{ display: 'flex', gap: 16, height: isMobile ? 'calc(100vh - 240px)' : 'calc(100vh - 280px)' }}>
        {(showSidebar || !isMobile) && sidebar}
        {(!showSidebar || !isMobile) && chatArea}
      </div>
    </div>
  );
}

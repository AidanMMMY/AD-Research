import { useState, useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Input, Button, List, Popconfirm, Empty, Skeleton, Tag } from 'antd';
import './styles.css';
import {
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
  SendOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import { chatApi, ChatSession, ChatMessage } from '@/api/chat';
import AISetupBanner from '@/components/AISetupBanner';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import StepProgress from '@/components/StepProgress';
import { useStepStream } from '@/hooks/useStepStream';
import { useIsMobile } from '@/hooks/useBreakpoint';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const QUICK_PROMPTS = [
  { label: '分析 AAPL 的散户情绪', prompt: '请分析 AAPL 最近 7 日的散户情绪与多空比' },
  { label: '今日热点解读', prompt: '请总结今日 importance ≥ 4 的热点资讯' },
  { label: '自选股舆情', prompt: '我自选股的最新舆情和情绪如何？' },
];

export default function AIChat() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get('symbol');
  const [activeSession, setActiveSession] = useState<number | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [firstMessageSent, setFirstMessageSent] = useState(false);
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

  const handleSend = async (override?: string) => {
    const content = override ?? input;
    if (!content.trim() || !activeSession || sending) return;
    if (override === undefined) {
      setInput('');
    }
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

  // ── Auto-trigger first message when arriving via ?symbol=... ──────────
  // Flow:
  //   1. InstrumentDetail "打开AI助手" navigates to /chat?symbol=510300.SH
  //   2. If we don't yet have a session, create one (and wait for its id).
  //   3. Once a session is active, push `帮我看看 <symbol>` automatically.
  // `firstMessageSent` is a per-mount latch so we only fire once per arrival.
  useEffect(() => {
    if (!symbolFromUrl) return;
    if (firstMessageSent) return;
    if (!activeSession) {
      // Kick off session creation if we don't have one yet.
      if (createMutation.isIdle) {
        createMutation.mutate();
      }
      return;
    }
    setFirstMessageSent(true);
    void handleSend(`帮我看看 ${symbolFromUrl}`);
    // We intentionally exclude `handleSend` from deps to avoid re-firing;
    // `activeSession` is the stable signal we care about.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSession, symbolFromUrl]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const reducedMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    messagesEndRef.current?.scrollIntoView({
      behavior: reducedMotion ? 'auto' : 'smooth',
    });
  }, [messages]);

  // Show session sidebar on desktop; toggle on mobile
  const showSidebar = !isMobile || !activeSession;

  const sidebar = (
    <div className="phase5c-chat-sidebar">
      <Button
        type="primary"
        icon={<PlusOutlined />}
        loading={createMutation.isPending}
        onClick={() => createMutation.mutate()}
        block
      >
        新对话
      </Button>

      <div className="phase5c-chat-sidebar__list">
        {sessionsLoading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : !sessions?.length ? (
          <Empty description="暂无对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            className="ad-list-compact"
            dataSource={sessions}
            renderItem={(s: ChatSession) => (
              <div
                onClick={() => setActiveSession(s.id)}
                className={`phase5c-chat-sidebar__item ${activeSession === s.id ? 'phase5c-chat-sidebar__item--active' : ''}`}
              >
                <span className="phase5c-chat-sidebar__title">
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
                    className="phase5c-chat-sidebar__delete"
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
    <div className="phase5c-chat-area">
      {/* Mobile back button */}
      {isMobile && activeSession && (
        <div className="phase5c-mobile-back">
          <Button type="text" onClick={() => setActiveSession(null)}>
            ← 返回列表
          </Button>
        </div>
      )}

      {/* Messages */}
      <div className="phase5c-chat-messages">
        {!activeSession ? (
          <Empty
            description="选择一个对话或创建新对话"
            className="phase5c-empty-robot"
            image={<RobotOutlined className="phase5c-empty-icon" />}
          />
        ) : messagesLoading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
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

      {/* Input */}
      {activeSession && (
        <div className="phase5c-input-bar">
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
      )}
    </div>
  );

  return (
    <PageShell maxWidth="wide">
      <AISetupBanner />
      <PageHeader
        eyebrow="AI"
        title="AI 助手"
        description="多会话 AI 对话，支持 Markdown 与代码高亮"
      />
      <div className="phase5c-chat-layout">
        {(showSidebar || !isMobile) && sidebar}
        {(!showSidebar || !isMobile) && chatArea}
      </div>
    </PageShell>
  );
}

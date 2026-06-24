import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Input, Button, List, Tag, Popconfirm, Empty, Skeleton } from 'antd';
import { PlusOutlined, DeleteOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons';
import { chatApi, ChatSession, ChatMessage } from '@/api/chat';
import GlassCard from '@/components/GlassCard';
import { useIsMobile } from '@/hooks/useBreakpoint';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function AIChat() {
  const isMobile = useIsMobile();
  const [activeSession, setActiveSession] = useState<number | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

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
    try {
      await chatApi.sendMessage(activeSession, content);
      queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSession] });
    } catch {
      // ignore
    }
    setSending(false);
  };

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Show session sidebar on desktop; toggle on mobile
  const showSidebar = !isMobile || !activeSession;

  return (
    <div style={{ display: 'flex', gap: 16, height: isMobile ? 'calc(100vh - 140px)' : 'calc(100vh - 180px)' }}>
      {/* Session Sidebar */}
      {(showSidebar || !isMobile) && (
        <div
          style={{
            width: isMobile ? '100%' : 240,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={createMutation.isPending}
            onClick={() => createMutation.mutate()}
            block
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none' }}
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
                      borderRadius: 8,
                      cursor: 'pointer',
                      marginBottom: 4,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: activeSession === s.id ? 'rgba(99,102,241,0.12)' : 'transparent',
                      border: activeSession === s.id ? '1px solid rgba(99,102,241,0.2)' : '1px solid transparent',
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        color: activeSession === s.id ? '#818cf8' : '#94a3b8',
                        fontWeight: activeSession === s.id ? 600 : 400,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flex: 1,
                      }}
                    >
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
                        style={{ color: '#475569', fontSize: 12, flexShrink: 0 }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </div>
                )}
              />
            )}
          </div>
        </div>
      )}

      {/* Chat Area */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(255,255,255,0.02)',
          borderRadius: 16,
          border: '1px solid rgba(255,255,255,0.06)',
          overflow: 'hidden',
        }}
      >
        {/* Mobile back button */}
        {isMobile && activeSession && (
          <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
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
              image={<RobotOutlined style={{ fontSize: 48, color: '#475569' }} />}
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
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '12px 16px',
                    borderRadius: 14,
                    borderTopRightRadius: msg.role === 'user' ? 4 : 14,
                    borderTopLeftRadius: msg.role === 'assistant' ? 4 : 14,
                    background:
                      msg.role === 'user'
                        ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                        : 'rgba(255,255,255,0.06)',
                    color: msg.role === 'user' ? '#fff' : '#e2e8f0',
                    fontSize: 14,
                    lineHeight: 1.7,
                  }}
                >
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
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        {activeSession && (
          <div
            style={{
              padding: '12px 20px',
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
                background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                border: 'none',
                alignSelf: 'flex-end',
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, List, Popconfirm } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import type { ChatSession } from '@/api/chat';
import AISetupBanner from '@/components/AISetupBanner';
import PageShell from '@/components/PageShell';
import EmptyState from '@/components/EmptyState';
import PageHeader from '@/components/PageHeader';
import LoadingBlock from '@/components/LoadingBlock';
import { useIsMobile } from '@/hooks/useBreakpoint';
import AIChatConversation from './AIChatConversation';
import { useAIChatController } from './useAIChatController';
import { useAIChatSheetStore } from './aiChatSheetStore';

/**
 * /chat — the AI assistant full page.
 *
 * Desktop: sessions sidebar + conversation (unchanged). Mobile: the page
 * stays for deep links (/chat?symbol=…) and session management, while
 * day-to-day chatting moves to the global BottomSheet (方向 D) — the
 * banner below offers one tap into that sheet mode. Both surfaces share
 * one controller state (active session + draft via useAIChatSheetStore,
 * messages via react-query), so switching between them is seamless.
 */
export default function AIChat() {
  const isMobile = useIsMobile();
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get('symbol');
  const [firstMessageSent, setFirstMessageSent] = useState(false);
  const openSheet = useAIChatSheetStore((s) => s.openSheet);
  const controller = useAIChatController();
  const {
    sessions,
    sessionsLoading,
    activeSession,
    setActiveSession,
    createMutation,
    deleteMutation,
    handleSend,
  } = controller;

  // ── Auto-trigger first message when arriving via ?symbol=... ──────────
  // Flow:
  //   1. InstrumentDetail "打开AI助手" navigates to /chat?symbol=510300.SH
  //   2. If we don't yet have a session, create one (and wait for its id).
  //   3. Once a session is active, push `帮我看看 <symbol>` automatically.
  // `firstMessageSent` is a per-mount latch so we only fire once per arrival.
  const handleSendRef = useRef(handleSend);
  useEffect(() => {
    handleSendRef.current = handleSend;
  });
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
    void handleSendRef.current(`帮我看看 ${symbolFromUrl}`);
    // `activeSession` is the stable signal we care about; handleSend goes
    // through a ref so a re-created closure never re-fires the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSession, symbolFromUrl]);

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
          <LoadingBlock size="md" />
        ) : !sessions?.length ? (
          <EmptyState title="暂无对话" description="点击「新建对话」开始你的第一次 AI 投研对话" />
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

  return (
    <PageShell maxWidth="wide">
      <AISetupBanner />
      <PageHeader
        eyebrow="AI"
        title="AI 助手"
        description="多会话 AI 对话，支持 Markdown 与代码高亮"
      />
      {/* 方向 D: on mobile the assistant primarily lives in the global
          BottomSheet (reachable from any page via the floating button).
          This entry opens it from /chat too — the conversation is shared,
          so the user picks up right where the page left off. */}
      {isMobile && (
        <div className="phase5c-sheet-entry">
          <span className="phase5c-sheet-entry__hint">
            AI 助手已支持全局浮层 — 任意页面右下角一键唤起，不打断当前浏览
          </span>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<RobotOutlined />}
            onClick={openSheet}
          >
            浮层打开
          </Button>
        </div>
      )}
      <div className="phase5c-chat-layout">
        {(showSidebar || !isMobile) && sidebar}
        {(!showSidebar || !isMobile) && (
          <AIChatConversation
            controller={controller}
            variant="page"
            showBack={isMobile}
            onBack={() => setActiveSession(null)}
          />
        )}
      </div>
    </PageShell>
  );
}

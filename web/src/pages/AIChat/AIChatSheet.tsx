import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import {
  PlusOutlined,
  RobotOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { BottomSheet } from '@/components/BottomSheet';
import { useIsMobile } from '@/hooks/useBreakpoint';
import AIChatConversation from './AIChatConversation';
import { useAIChatController } from './useAIChatController';
import { useAIChatSheetStore } from './aiChatSheetStore';

/**
 * Global mobile AI assistant sheet (方向 D, 2026-07-29).
 *
 * Mounted once in AppLayout (mobile only) so any page can summon the AI
 * chat without a route change — the user's context stays put underneath
 * the scrim. Detents: half (glance, page still peeking through) and
 * full (immersive input); ``avoidKeyboard`` keeps the composer glued to
 * the top of the on-screen keyboard.
 *
 * State survives close: ``activeSession``/``draft`` live in
 * ``useAIChatSheetStore`` and messages in the react-query cache — the
 * sheet unmounts its children, not the conversation. An in-flight stream
 * is never aborted on close; the trailing cache invalidation still runs
 * and the finished reply is waiting on reopen.
 *
 * Session management (list/rename/delete) stays on /chat — the sheet
 * offers 「新对话」 + a shortcut back to the full page.
 */
export default function AIChatSheet() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const sheetOpen = useAIChatSheetStore((s) => s.sheetOpen);
  const closeSheet = useAIChatSheetStore((s) => s.closeSheet);
  const controller = useAIChatController();
  const { sessions, activeSession, createMutation } = controller;

  if (!isMobile) return null;

  // Defensive: a malformed sessions payload (non-array) must never take
  // down the whole app through the error boundary — the sheet is mounted
  // globally in AppLayout.
  const activeTitle = Array.isArray(sessions)
    ? sessions.find((s) => s.id === activeSession)?.title || null
    : null;

  return (
    <BottomSheet
      open={sheetOpen}
      onClose={closeSheet}
      snaps={['half', 'full']}
      avoidKeyboard
      title={
        <span className="phase5c-sheet-title">
          <RobotOutlined aria-hidden="true" className="phase5c-sheet-title__icon" />
          <span>AI 助手</span>
          {activeTitle ? (
            <span className="phase5c-sheet-title__session">{activeTitle}</span>
          ) : null}
        </span>
      }
    >
      <div className="phase5c-sheet-toolbar">
        <Button
          size="small"
          icon={<PlusOutlined />}
          loading={createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          新对话
        </Button>
        <Button
          size="small"
          type="text"
          icon={<UnorderedListOutlined />}
          onClick={() => {
            closeSheet();
            navigate('/chat');
          }}
        >
          全部会话
        </Button>
      </div>
      <AIChatConversation controller={controller} variant="sheet" />
    </BottomSheet>
  );
}

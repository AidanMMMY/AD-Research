import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/api/chat';
import { useStepStream } from '@/hooks/useStepStream';
import { useAIChatSheetStore } from './aiChatSheetStore';

const STEP_DEFS = [
  { id: 'fetch', label: '准备上下文' },
  { id: 'llm', label: '调用大模型' },
  { id: 'stream', label: '生成回答' },
];

/**
 * Shared controller for the AI assistant conversation — used by both the
 * /chat page and the global mobile BottomSheet (方向 D).
 *
 * What lives here vs. elsewhere:
 *  - ``activeSession`` / ``draft`` come from ``useAIChatSheetStore`` so
 *    they survive the sheet unmounting on close.
 *  - ``sessions`` / ``messages`` come from react-query — closing the
 *    sheet keeps the cache, so reopening is instant.
 *  - ``sending`` / ``steps`` / ``streamedText`` are per-instance: if the
 *    sheet closes mid-stream the visual typewriter state is dropped, but
 *    the underlying stream promise keeps running (nobody aborts it) and
 *    the trailing ``invalidateQueries`` still lands, so the finished
 *    reply is there when the sheet reopens.
 */
export function useAIChatController() {
  const queryClient = useQueryClient();
  const activeSession = useAIChatSheetStore((s) => s.activeSession);
  const setActiveSession = useAIChatSheetStore((s) => s.setActiveSession);
  const input = useAIChatSheetStore((s) => s.draft);
  const setInput = useAIChatSheetStore((s) => s.setDraft);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { steps, streamedText, start, finish, reset, appendStreamed } =
    useStepStream(STEP_DEFS);

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
    if (!content.trim() || sending) return;
    if (override === undefined) {
      setInput('');
    }
    setSending(true);
    reset(STEP_DEFS);
    try {
      // Empty-state first message: no session yet — create one on the fly
      // before streaming, so the input bar works without a sidebar click.
      let sessionId = activeSession;
      if (!sessionId) {
        const resp = await createMutation.mutateAsync();
        sessionId = resp.data.id;
      }
      start('fetch');
      await new Promise((r) => setTimeout(r, 120));
      finish('fetch', 'done');
      start('llm');
      // Real SSE stream — parses meta/delta/done frames server-side.
      let receivedContent = false;
      await new Promise<void>((resolve, reject) => {
        chatApi.streamMessage(sessionId!, content, {
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
              chatApi.sendMessage(sessionId!, content)
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
      queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] });
    } catch {
      finish('llm', 'error');
    }
    setSending(false);
  };

  return {
    sessions,
    sessionsLoading,
    activeSession,
    setActiveSession,
    messages,
    messagesLoading,
    input,
    setInput,
    sending,
    steps,
    streamedText,
    messagesEndRef,
    createMutation,
    deleteMutation,
    handleSend,
  };
}

export type AIChatController = ReturnType<typeof useAIChatController>;

import { createContext, useState, useCallback, useRef } from 'react';
import { chatApi } from '@/api/chat';
import type { AIHelpContextValue, HelpContext, HelpMessage } from '@/types/help';
import { getSystemPrompt } from '@/utils/helpPrompts';

export const AIHelpContext = createContext<AIHelpContextValue | null>(null);

interface AIHelpProviderProps {
  children: React.ReactNode;
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function buildHelpMessage(pageType: HelpContext['pageType'], contextData: string, question: string): string {
  const systemPrompt = getSystemPrompt(pageType);
  return `[系统提示]\n${systemPrompt}\n\n[当前页面上下文数据]\n${contextData}\n\n[用户问题]\n${question}`;
}

export function AIHelpProvider({ children }: AIHelpProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [context, setContext] = useState<HelpContext | null>(null);
  const [messages, setMessages] = useState<HelpMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);

  const lastPayloadRef = useRef<string | null>(null);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  const open = useCallback(async (ctx: HelpContext) => {
    setContext(ctx);
    setMessages([]);
    setError(null);
    setIsLoading(true);
    setIsOpen(true);
    lastPayloadRef.current = null;

    try {
      const sessionRes = await chatApi.createSession(`帮助：${ctx.pageTitle}`);
      const newSessionId = sessionRes.data.id;
      setSessionId(newSessionId);

      const initialQuestion = ctx.initialQuestion || '请简要介绍当前页面最重要的 1-2 个专业概念，帮助用户快速理解。';
      const payload = buildHelpMessage(ctx.pageType, ctx.contextData, initialQuestion);
      lastPayloadRef.current = payload;

      setMessages([
        { id: generateId(), role: 'user', content: initialQuestion },
      ]);

      const res = await chatApi.sendMessage(newSessionId, payload);
      setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: res.data.content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建帮助会话失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || !context || isLoading) return;

    const payload = buildHelpMessage(context.pageType, context.contextData, content);
    lastPayloadRef.current = payload;

    setMessages((prev) => [...prev, { id: generateId(), role: 'user', content }]);
    setIsLoading(true);
    setError(null);

    try {
      const res = await chatApi.sendMessage(sessionId, payload);
      setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: res.data.content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败，请重试');
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, context, isLoading]);

  const retryLast = useCallback(async () => {
    if (!lastPayloadRef.current || !sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await chatApi.sendMessage(sessionId, lastPayloadRef.current);
      setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: res.data.content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败，请重试');
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const value: AIHelpContextValue = {
    isOpen,
    context,
    messages,
    isLoading,
    error,
    sessionId,
    open,
    close,
    sendMessage,
    retryLast,
  };

  return (
    <AIHelpContext.Provider value={value}>
      {children}
    </AIHelpContext.Provider>
  );
}

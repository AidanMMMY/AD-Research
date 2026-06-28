import { createContext, useState, useCallback, useRef } from 'react';
import type { AxiosError } from 'axios';
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

function friendlyErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    const axiosErr = err as AxiosError;
    // Timeout
    if (axiosErr.code === 'ECONNABORTED' || err.message.includes('timeout')) {
      return 'AI 响应超时，模型推理中…请点击重试按钮，或稍后再试。';
    }
    // Server errors
    if (axiosErr.response) {
      const status = axiosErr.response.status;
      if (status === 503) {
        return 'AI 服务未配置。请在服务端设置 DEEPSEEK_API_KEY 后重启服务。';
      }
      if (status >= 500) {
        return `服务器错误（${status}），请稍后重试或联系管理员。`;
      }
      if (status === 401) {
        return '登录已过期，请刷新页面重新登录。';
      }
    }
    return err.message;
  }
  return '请求失败，请重试';
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
      setError(friendlyErrorMessage(err));
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
      setError(friendlyErrorMessage(err));
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
      setError(friendlyErrorMessage(err));
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

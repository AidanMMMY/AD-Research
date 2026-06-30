import { createContext, useState, useCallback, useRef } from 'react';
import type { AxiosError } from 'axios';
import { chatApi } from '@/api/chat';
import type { AIHelpContextValue, HelpContext, HelpMessage } from '@/types/help';
import { getSystemPrompt } from '@/utils/helpPrompts';
import type { Step } from '@/hooks/useStepStream';

export const AIHelpContext = createContext<AIHelpContextValue | null>(null);

interface AIHelpProviderProps {
  children: React.ReactNode;
}

const STEP_DEFS = [
  { id: 'session', label: '创建会话' },
  { id: 'fetch', label: '拉取日线' },
  { id: 'indicators', label: '计算指标' },
  { id: 'llm', label: '调用大模型' },
  { id: 'stream', label: '生成回答' },
];

const INITIAL_STEPS: Step[] = STEP_DEFS.map((d) => ({
  id: d.id,
  label: d.label,
  status: 'pending',
}));

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
    if (axiosErr.code === 'ECONNABORTED' || err.message.includes('timeout')) {
      return 'AI 响应超时，模型推理中…请点击重试按钮，或稍后再试。';
    }
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

/**
 * 模拟步骤推进（在网络/IO 较快时合并；保持视觉节奏）
 */
async function advanceSteps(
  start: (id: string) => void,
  finish: (id: string, status: 'done' | 'error') => void,
  untilId: string,
): Promise<void> {
  const idx = STEP_DEFS.findIndex((s) => s.id === untilId);
  if (idx < 0) return;
  for (let i = 0; i <= idx; i++) {
    const def = STEP_DEFS[i];
    start(def.id);
    await new Promise((r) => setTimeout(r, 80 + Math.random() * 60));
    finish(def.id, 'done');
  }
}

/**
 * Drive the SSE stream for ``payload`` and resolve once the assistant
 * reply fully arrives. Falls back to the non-streaming POST + client
 * typewriter if the stream connection itself fails.
 */
async function streamReply(
  sessionId: number,
  payload: string,
  onChunk: (chunk: string) => void,
  finishStep: (id: string, status?: 'done' | 'error') => void,
  fallbackTypewriter: (content: string) => Promise<void>,
): Promise<string> {
  let fullContent = '';
  let streamErrored = false;

  const { abort, settled } = await chatApi.streamMessage(sessionId, payload, {
    onDelta: (chunk) => {
      fullContent += chunk;
      onChunk(chunk);
    },
    onDone: () => finishStep('stream', 'done'),
    onError: () => { streamErrored = true; },
    onComplete: () => {/* handled below via settled */},
  });
  void abort; // caller holds the AbortController itself
  await settled;

  if (streamErrored || !fullContent) {
    try {
      const res = await chatApi.sendMessage(sessionId, payload);
      await fallbackTypewriter(res.data.content);
      return res.data.content;
    } catch (e) {
      finishStep('stream', 'error');
      return '';
    }
  }
  return fullContent;
}

export function AIHelpProvider({ children }: AIHelpProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [context, setContext] = useState<HelpContext | null>(null);
  const [messages, setMessages] = useState<HelpMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const [streamedText, setStreamedText] = useState<string>('');

  const lastPayloadRef = useRef<string | null>(null);
  const typewriterRef = useRef<{ cancelled: boolean; timer?: number }>({ cancelled: false });
  const streamAbortRef = useRef<AbortController | null>(null);

  const startStep = useCallback((id: string) => {
    setSteps((prev) => {
      const idx = prev.findIndex((s) => s.id === id);
      if (idx < 0) return prev;
      return prev.map((s, i) => {
        if (i < idx) return { ...s, status: 'done' };
        if (i === idx) return { ...s, status: 'running' };
        return s;
      });
    });
  }, []);

  const finishStep = useCallback((id: string, status: 'done' | 'error' = 'done') => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s)));
  }, []);

  const resetSteps = useCallback(() => {
    setSteps(INITIAL_STEPS.map((s) => ({ ...s })));
    setStreamedText('');
  }, []);

  /**
   * Client-side typewriter fallback. Inherited from the pre-SSE build —
   * used only when the stream connection fails outright.
   */
  const fallbackTypewriter = useCallback((content: string, intervalMs = 20) => {
    typewriterRef.current.cancelled = false;
    return new Promise<void>((resolve) => {
      const chars = Array.from(content);
      let i = 0;
      const tick = () => {
        if (typewriterRef.current.cancelled) {
          setStreamedText(content);
          resolve();
          return;
        }
        if (i >= chars.length) {
          finishStep('stream', 'done');
          resolve();
          return;
        }
        const batch = Math.min(2, chars.length - i);
        i += batch;
        setStreamedText(chars.slice(0, i).join(''));
        typewriterRef.current.timer = window.setTimeout(tick, intervalMs);
      };
      setStreamedText('');
      startStep('stream');
      tick();
    });
  }, [startStep, finishStep]);

  const close = useCallback(() => {
    typewriterRef.current.cancelled = true;
    if (typewriterRef.current.timer) clearTimeout(typewriterRef.current.timer);
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsOpen(false);
  }, []);

  const open = useCallback(async (ctx: HelpContext) => {
    typewriterRef.current.cancelled = true;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setContext(ctx);
    setMessages([]);
    setError(null);
    setIsLoading(true);
    setIsOpen(true);
    setStreamedText('');
    resetSteps();
    lastPayloadRef.current = null;

    try {
      startStep('session');
      const sessionPromise = chatApi.createSession(`帮助：${ctx.pageTitle}`);
      const visualPromise = advanceSteps(startStep, finishStep, 'stream');
      const [sessionRes] = await Promise.all([sessionPromise, visualPromise]);
      finishStep('session', 'done');
      const newSessionId = sessionRes.data.id;
      setSessionId(newSessionId);

      const initialQuestion = ctx.initialQuestion || '请简要介绍当前页面最重要的 1-2 个专业概念，帮助用户快速理解。';
      const payload = buildHelpMessage(ctx.pageType, ctx.contextData, initialQuestion);
      lastPayloadRef.current = payload;

      setMessages([
        { id: generateId(), role: 'user', content: initialQuestion },
      ]);

      const fullContent = await streamReply(
        newSessionId,
        payload,
        (chunk) => setStreamedText((prev) => prev + chunk),
        finishStep,
        fallbackTypewriter,
      );
      streamAbortRef.current = null;

      if (fullContent) {
        setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: fullContent }]);
        setStreamedText('');
      }
    } catch (err) {
      setSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)));
      setError(friendlyErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [startStep, finishStep, resetSteps, fallbackTypewriter]);

  const sendMessage = useCallback(async (content: string) => {
    if (!sessionId || !context || isLoading) return;
    typewriterRef.current.cancelled = true;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;

    const payload = buildHelpMessage(context.pageType, context.contextData, content);
    lastPayloadRef.current = payload;

    setMessages((prev) => [...prev, { id: generateId(), role: 'user', content }]);
    setIsLoading(true);
    setError(null);
    setStreamedText('');
    resetSteps();

    try {
      await advanceSteps(startStep, finishStep, 'stream');

      const fullContent = await streamReply(
        sessionId,
        payload,
        (chunk) => setStreamedText((prev) => prev + chunk),
        finishStep,
        fallbackTypewriter,
      );
      streamAbortRef.current = null;

      if (fullContent) {
        setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: fullContent }]);
        setStreamedText('');
      }
    } catch (err) {
      setSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)));
      setError(friendlyErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, context, isLoading, startStep, finishStep, resetSteps, fallbackTypewriter]);

  const retryLast = useCallback(async () => {
    if (!lastPayloadRef.current || !sessionId) return;
    typewriterRef.current.cancelled = true;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsLoading(true);
    setError(null);
    setStreamedText('');
    resetSteps();
    try {
      await advanceSteps(startStep, finishStep, 'stream');

      const fullContent = await streamReply(
        sessionId,
        lastPayloadRef.current,
        (chunk) => setStreamedText((prev) => prev + chunk),
        finishStep,
        fallbackTypewriter,
      );
      streamAbortRef.current = null;

      if (fullContent) {
        setMessages((prev) => [...prev, { id: generateId(), role: 'assistant', content: fullContent }]);
        setStreamedText('');
      }
    } catch (err) {
      setSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)));
      setError(friendlyErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, startStep, finishStep, resetSteps, fallbackTypewriter]);

  const value: AIHelpContextValue = {
    isOpen,
    context,
    messages,
    isLoading,
    error,
    sessionId,
    steps,
    streamedText,
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

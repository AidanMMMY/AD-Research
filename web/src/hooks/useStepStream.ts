import { useCallback, useRef, useState } from 'react';

export type StepStatus = 'pending' | 'running' | 'done' | 'error';

export interface Step {
  id: string;
  label: string;
  status: StepStatus;
}

export interface StepDef {
  id: string;
  label: string;
}

export interface UseStepStreamResult {
  steps: Step[];
  /** 打字机渲染中的当前文本（assistant 输出） */
  streamedText: string;
  /** 是否正在等待任一步骤 */
  isRunning: boolean;
  /** 推进：把某步骤标记为 running；自动把前面标记为 done */
  start: (id: string) => void;
  /** 推进：把某步骤标记为 done/error，并触发下一轮 running */
  finish: (id: string, status: 'done' | 'error') => void;
  /** 重置为初始状态 */
  reset: (defs: StepDef[]) => void;
  /** 启动打字机效果（把完整 content 拆成 token 后逐个写入） */
  startTypewriter: (content: string, intervalMs?: number) => Promise<void>;
  /** 追加到当前流式文本（用于未来 SSE 场景） */
  appendStreamed: (chunk: string) => void;
  /** 立即完成打字机剩余部分 */
  flushTypewriter: () => void;
}

const DEFAULT_INTERVAL = 20;

function makeSteps(defs: StepDef[]): Step[] {
  return defs.map((d) => ({ id: d.id, label: d.label, status: 'pending' as StepStatus }));
}

export function useStepStream(defs: StepDef[]): UseStepStreamResult {
  const [steps, setSteps] = useState<Step[]>(() => makeSteps(defs));
  const [streamedText, setStreamedText] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const typewriterRef = useRef<{ cancelled: boolean; timer?: number }>({ cancelled: false });

  const start = useCallback(
    (id: string) => {
      setSteps((prev) => {
        const idx = prev.findIndex((s) => s.id === id);
        if (idx < 0) return prev;
        return prev.map((s, i) => {
          if (i < idx) return { ...s, status: 'done' };
          if (i === idx) return { ...s, status: 'running' };
          return s;
        });
      });
      setIsRunning(true);
    },
    [],
  );

  const finish = useCallback((id: string, status: 'done' | 'error') => {
    setSteps((prev) => {
      const idx = prev.findIndex((s) => s.id === id);
      if (idx < 0) return prev;
      const next = prev.map((s, i) => (i === idx ? { ...s, status } : s));
      // 全部 done 才退出 running
      if (next.every((s) => s.status === 'done' || s.status === 'error')) {
        setIsRunning(false);
      }
      return next;
    });
  }, []);

  const reset = useCallback((newDefs: StepDef[]) => {
    typewriterRef.current.cancelled = true;
    setSteps(makeSteps(newDefs));
    setStreamedText('');
    setIsRunning(false);
  }, []);

  const appendStreamed = useCallback((chunk: string) => {
    setStreamedText((prev) => prev + chunk);
  }, []);

  const startTypewriter = useCallback((content: string, intervalMs = DEFAULT_INTERVAL) => {
    typewriterRef.current.cancelled = false;
    return new Promise<void>((resolve) => {
      // 中文字符按 codePoint 拆分，避免代理对被切碎
      const chars = Array.from(content);
      let i = 0;
      const step = () => {
        if (typewriterRef.current.cancelled) {
          // flush remaining
          setStreamedText(content);
          resolve();
          return;
        }
        if (i >= chars.length) {
          resolve();
          return;
        }
        // 一次写入 1~3 个字符，保持视觉节奏
        const batch = Math.min(3, chars.length - i);
        i += batch;
        setStreamedText(chars.slice(0, i).join(''));
        typewriterRef.current.timer = window.setTimeout(step, intervalMs);
      };
      setStreamedText('');
      step();
    });
  }, []);

  const flushTypewriter = useCallback(() => {
    typewriterRef.current.cancelled = true;
    if (typewriterRef.current.timer) {
      clearTimeout(typewriterRef.current.timer);
    }
  }, []);

  return {
    steps,
    streamedText,
    isRunning,
    start,
    finish,
    reset,
    startTypewriter,
    appendStreamed,
    flushTypewriter,
  };
}
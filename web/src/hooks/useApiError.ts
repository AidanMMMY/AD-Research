import { useEffect } from 'react';
import { message } from 'antd';

/**
 * 统一 API 错误处理：导出含 queryKey 的友好提示 + 短 hash。
 *
 * 使用方式（hook 内）：
 *   useApiErrorToast(['backtests', strategyId], error, '加载回测失败');
 *
 * 注意：仍由调用方在 hook 返回值里暴露 `error`，本 hook 只做 toast，
 * 不吞错。
 */
export function useApiErrorToast(
  queryKey: string,
  error: unknown,
  fallbackMsg?: string,
): void {
  useEffect(() => {
    if (!error) return;
    const hash = generateErrorHash();
    const detail = extractErrorMessage(error);
    const baseMsg = fallbackMsg ?? '请求失败';
    message.error(`${baseMsg}（${queryKey} · ${hash}${detail ? ` · ${detail}` : ''}）`);
    // eslint-disable-next-line no-console
    console.error('[useApiErrorToast]', queryKey, error);
  }, [queryKey, error, fallbackMsg]);
}

function generateErrorHash(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID().slice(0, 8);
    }
  } catch {
    // fall through
  }
  return Math.random().toString(36).slice(2, 10);
}

function extractErrorMessage(error: unknown): string | undefined {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error) {
    const m = (error as { message?: unknown }).message;
    if (typeof m === 'string') return m;
  }
  return undefined;
}

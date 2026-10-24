/**
 * AIHelpProvider 级联渲染回归测试（2026-10-25 P0 修复）。
 *
 * 修复前：context value 每次 render 重建，流式回答期间每个 SSE chunk
 * （setStreamedText）都会让所有 useAIHelp 消费者重渲染——包括只取
 * open 动作的各页面与全站 HelpPopover。
 *
 * 修复后：value 拆成低频 context（useMemo 收敛依赖）+ 高频流式 context
 * （steps/streamedText）。本测试锁定两条契约：
 *  1. 流式 chunk / 步骤推进只重渲染 useAIHelpStream 消费者；
 *  2. 只订阅 useAIHelp 的组件在流式期间零重渲染。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { useEffect } from 'react';
import { cleanup, render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { AIHelpProvider } from '@/components/AIHelpProvider';
import { useAIHelp, useAIHelpStream } from '@/hooks/useAIHelp';
import { chatApi } from '@/api/chat';
import type { StreamChatHandler } from '@/api/chat';

vi.mock('@/api/chat', () => ({
  chatApi: {
    createSession: vi.fn(),
    sendMessage: vi.fn(),
    streamMessage: vi.fn(),
  },
}));

// vitest globals=false，RTL 自动 cleanup 不生效，手动清
afterEach(cleanup);

const mockedCreateSession = vi.mocked(chatApi.createSession);
const mockedStreamMessage = vi.mocked(chatApi.streamMessage);

const HELP_CTX = {
  pageType: 'score_ranking' as const,
  pageTitle: '评分排名',
  contextData: '页面数据摘要',
};

/**
 * 只消费低频 context 的探针（模拟各页面 / HelpPopover 的用法）。
 * 渲染计数在 effect 里累加（render 必须保持纯函数，react-hooks/globals）；
 * 无依赖数组的 effect 在每次提交后都会跑一次，等价于渲染计数。
 */
let helpProbeRenders = 0;
function HelpProbe() {
  const help = useAIHelp();
  useEffect(() => {
    helpProbeRenders += 1;
  });
  return (
    <div>
      <span data-testid="msg-count">{help.messages.length}</span>
      <span data-testid="loading">{String(help.isLoading)}</span>
      <button data-testid="open-btn" onClick={() => void help.open(HELP_CTX)}>open</button>
      <button data-testid="send-btn" onClick={() => void help.sendMessage('第二问')}>send</button>
    </div>
  );
}

/** 消费高频流式 context 的探针（模拟 AIHelpDrawer），计数方式同上。 */
let streamProbeRenders = 0;
function StreamProbe() {
  const { streamedText } = useAIHelpStream();
  useEffect(() => {
    streamProbeRenders += 1;
  });
  return <span data-testid="stream-text">{streamedText}</span>;
}

/** 立即完成的流（open() 的初始回答用）。 */
function immediateStream(content: string) {
  return (_sessionId: number, _payload: string, handler: StreamChatHandler) => {
    let resolveSettled!: () => void;
    const settled = new Promise<void>((r) => {
      resolveSettled = r;
    });
    void Promise.resolve().then(() => {
      handler.onDelta?.(content);
      handler.onDone?.({ message_id: 1 });
      resolveSettled();
    });
    return { abort: new AbortController(), settled };
  };
}

const helpRenders = () => helpProbeRenders;

describe('AIHelpProvider 级联渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    helpProbeRenders = 0;
    streamProbeRenders = 0;
    mockedCreateSession.mockResolvedValue({ data: { id: 42 } } as never);
    render(
      <AIHelpProvider>
        <HelpProbe />
        <StreamProbe />
      </AIHelpProvider>,
    );
  });

  it('流式 chunk 只驱动 useAIHelpStream 消费者，useAIHelp 消费者零重渲染', async () => {
    // ── 第一步：open() 完成初始问答（真实计时器，步骤动画 ~700ms）──
    mockedStreamMessage.mockImplementationOnce(immediateStream('初始回答'));
    fireEvent.click(screen.getByTestId('open-btn'));
    // advanceSteps 的 setTimeout 序列走真实时钟，放宽 waitFor 超时
    await waitFor(
      () => {
        expect(screen.getByTestId('loading').textContent).toBe('false');
        expect(screen.getByTestId('msg-count').textContent).toBe('2');
      },
      { timeout: 5000 },
    );

    // ── 第二步：sendMessage 挂起一条手动控制的流 ──
    let emitDelta!: (chunk: string) => void;
    let resolveStream!: () => void;
    mockedStreamMessage.mockImplementationOnce(
      (_sessionId: number, _payload: string, handler: StreamChatHandler) => {
        emitDelta = (chunk: string) => handler.onDelta?.(chunk);
        const settled = new Promise<void>((r) => {
          resolveStream = r;
        });
        return { abort: new AbortController(), settled };
      },
    );
    fireEvent.click(screen.getByTestId('send-btn'));
    // 用户消息入列 + isLoading=true 之后，步骤动画（setSteps）期间流才开始：
    // 等 streamMessage 被第二次调用，再等一拍让状态落定。
    await waitFor(() => expect(mockedStreamMessage).toHaveBeenCalledTimes(2), { timeout: 5000 });
    await act(async () => {});
    expect(screen.getByTestId('loading').textContent).toBe('true');

    const rendersBeforeStream = helpRenders();
    const streamRendersBefore = streamProbeRenders;

    // ── 第三步：模拟两个 SSE chunk（修复前这里会级联重渲染 HelpProbe）──
    await act(async () => {
      emitDelta('你');
      emitDelta('好');
    });
    expect(screen.getByTestId('stream-text').textContent).toBe('你好');
    // 流式消费者确实跟随 chunk 重渲染（每个 chunk 至少一次）
    expect(streamProbeRenders).toBeGreaterThan(streamRendersBefore);
    // 低频消费者零重渲染——核心回归断言
    expect(helpRenders()).toBe(rendersBeforeStream);

    // ── 第四步：收尾，回答入列（此时低频 context 变化，允许重渲染）──
    await act(async () => {
      resolveStream();
    });
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
      // open() 问答 2 条 + sendMessage 用户 1 条 + 流式回答 1 条
      expect(screen.getByTestId('msg-count').textContent).toBe('4');
    });
    expect(helpRenders()).toBeGreaterThan(rendersBeforeStream);
  });
});

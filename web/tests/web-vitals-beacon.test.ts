/**
 * Web Vitals 上报链路测试（2026-08-17，审计遗留 #5）。
 *
 * 覆盖 sendBeacon → fetch(keepalive) → axios 三级降级：
 *   1. 优先走 navigator.sendBeacon，且 Blob 类型必须是 application/json
 *      （后端 ingest_web_vital 是 FastAPI Pydantic JSON 端点，text/plain 会 422）。
 *   2. sendBeacon 不可用 / 拒收（返回 false）时退到 fetch keepalive。
 *   3. fetch 也不可用时退到 axios（statsApi.webVitals）。
 *   4. 所有路径 fire-and-forget：任何异常都不允许向上抛。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { reportToBackend, type WebVitalsSample } from '@/utils/webVitals';
import { statsApi } from '@/api/stats';

vi.mock('@/api/stats', () => ({
  statsApi: {
    webVitals: vi.fn(() => Promise.resolve()),
  },
}));

const sample: WebVitalsSample = {
  name: 'LCP',
  value: 1234.5,
  rating: 'good',
  id: 'v5-123',
  navigationType: 'navigate',
  page: '/instruments/510300.SH',
  ts: 1724000000000,
};

/** 期望发送到后端的字段（ts 是上报器内部字段，不入 payload）。 */
const expectedPayload = {
  name: 'LCP',
  value: 1234.5,
  rating: 'good',
  id: 'v5-123',
  navigationType: 'navigate',
  page: '/instruments/510300.SH',
};

function stubSendBeacon(impl: (() => boolean) | undefined) {
  Object.defineProperty(window.navigator, 'sendBeacon', {
    configurable: true,
    writable: true,
    value: impl ? vi.fn(impl) : undefined,
  });
}

/** jsdom 的 Blob 没有 .text()，用 FileReader 读取内容。 */
function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

describe('reportToBackend', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    stubSendBeacon(undefined);
    globalThis.fetch = originalFetch;
    vi.unstubAllGlobals();
  });

  it('sendBeacon 可用时优先走 beacon，Content-Type 为 application/json', async () => {
    stubSendBeacon(() => true);
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    reportToBackend(sample);

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
    const [url, data] = vi.mocked(navigator.sendBeacon).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/stats\/web-vitals$/);
    expect(data).toBeInstanceOf(Blob);
    const blob = data as Blob;
    expect(blob.type).toBe('application/json');
    expect(JSON.parse(await readBlob(blob))).toEqual(expectedPayload);
    // beacon 成功排队后不再走 fetch / axios
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(statsApi.webVitals).not.toHaveBeenCalled();
  });

  it('sendBeacon 拒收（返回 false）时退到 fetch keepalive', () => {
    stubSendBeacon(() => false);
    const fetchSpy = vi.fn(() => Promise.resolve(new Response('{}')));
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    reportToBackend(sample);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toMatch(/\/api\/v1\/stats\/web-vitals$/);
    expect(init.method).toBe('POST');
    expect(init.keepalive).toBe(true);
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual(expectedPayload);
    expect(statsApi.webVitals).not.toHaveBeenCalled();
  });

  it('sendBeacon 不存在时走 fetch keepalive', () => {
    stubSendBeacon(undefined);
    const fetchSpy = vi.fn(() => Promise.resolve(new Response('{}')));
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    reportToBackend(sample);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(statsApi.webVitals).not.toHaveBeenCalled();
  });

  it('sendBeacon 与 fetch 均不可用时退到 axios', () => {
    stubSendBeacon(undefined);
    // @ts-expect-error 模拟无 fetch 的运行时
    globalThis.fetch = undefined;

    reportToBackend(sample);

    expect(statsApi.webVitals).toHaveBeenCalledTimes(1);
    expect(statsApi.webVitals).toHaveBeenCalledWith(expectedPayload);
  });

  it('beacon 抛异常时静默降级 fetch，不向上抛', () => {
    stubSendBeacon(() => {
      throw new Error('beacon boom');
    });
    const fetchSpy = vi.fn(() => Promise.resolve(new Response('{}')));
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    expect(() => reportToBackend(sample)).not.toThrow();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('全部传输层都抛异常时仍然不抛（fire-and-forget）', () => {
    stubSendBeacon(() => {
      throw new Error('beacon boom');
    });
    globalThis.fetch = (() => {
      throw new Error('fetch boom');
    }) as unknown as typeof fetch;
    vi.mocked(statsApi.webVitals).mockImplementationOnce(() => {
      throw new Error('axios boom');
    });

    expect(() => reportToBackend(sample)).not.toThrow();
  });
});

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { marketApi } from '@/api/market';

export interface MarketTick {
  price: number;
  change_pct: number;
  /** Trade timestamp in ms (server-provided). 0 when unknown. */
  ts: number;
  /** Optional display name (when backend provides it). */
  name?: string;
  /** Optional market tag (when backend provides it). */
  market?: string;
}

export type MarketLatest = Record<string, MarketTick>;

export interface UseMarketStreamResult {
  latest: MarketLatest;
  isConnected: boolean;
  error: string | null;
  /** Manually force-reconnect (e.g. user pulled-to-refresh). */
  reconnect: () => void;
}

const MAX_BACKOFF_MS = 30_000;
const DEFAULT_BACKOFF_MS = 1_000;
const STREAM_PATH = '/stream/prices';

/**
 * Subscribe to a Server-Sent Events stream of latest daily prices for a set
 * of instrument codes. Reuses the same single SSE connection for the whole
 * list of symbols — the backend batches the snapshot and pushes it every
 * ~3 seconds as a JSON array of `{ code, price, change_pct, ... }` rows.
 *
 * The backend endpoint at `/api/v1/stream/prices` is currently unauthenticated
 * (public data), so no token needs to be passed via query string. If auth is
 * later added, append `&token=<jwt>` to the URL — EventSource does not
 * support custom headers.
 */
export function useMarketStream(codes: string[]): UseMarketStreamResult {
  const [latest, setLatest] = useState<MarketLatest>({});
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bump this counter to force a reconnect.
  const [reconnectNonce, setReconnectNonce] = useState(0);

  const esRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const backoffRef = useRef(DEFAULT_BACKOFF_MS);
  // We keep the latest code list in a ref so the connect closure always sees
  // the freshest set without re-running the entire effect.
  const codesRef = useRef<string[]>(codes);
  codesRef.current = codes;
  // Mirror connection state into a ref so the fallback poll can read the
  // freshest value without being re-created on every connect/disconnect.
  const isConnectedRef = useRef(false);
  isConnectedRef.current = isConnected;
  // Track the latest ticks in a ref so the fallback poll can decide whether
  // the UI already has data without re-subscribing to state.
  const latestRef = useRef<MarketLatest>(latest);
  latestRef.current = latest;

  const close = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => {
    const validCodes = (codesRef.current || []).filter(Boolean);
    if (validCodes.length === 0) {
      close();
      setLatest({});
      setIsConnected(false);
      setError(null);
      return;
    }

    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      close();

      const params = new URLSearchParams();
      // Backend accepts either `?codes=510300,159915` (single param, CSV)
      // or repeated `?codes=...&codes=...`. We use CSV to match what
      // usePriceStream already does.
      params.set('codes', validCodes.join(','));
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
      const url = `${baseUrl}${STREAM_PATH}?${params.toString()}`;

      let es: EventSource;
      try {
        es = new EventSource(url);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(`无法建立 SSE 连接: ${msg}`);
        scheduleReconnect();
        return;
      }
      esRef.current = es;

      es.onopen = () => {
        if (cancelled) return;
        setIsConnected(true);
        setError(null);
        backoffRef.current = DEFAULT_BACKOFF_MS;
      };

      es.onmessage = (event) => {
        if (cancelled) return;
        try {
          const parsed: unknown = JSON.parse(event.data);
          const rows: Array<{
            code?: string;
            price?: number;
            change_pct?: number;
            timestamp?: number;
            name?: string;
            market?: string;
          }> = Array.isArray(parsed)
            ? (parsed as Array<{
                code?: string;
                price?: number;
                change_pct?: number;
                timestamp?: number;
                name?: string;
                market?: string;
              }>)
            : parsed && typeof parsed === 'object' && 'code' in parsed
              ? [parsed as {
                  code?: string;
                  price?: number;
                  change_pct?: number;
                  timestamp?: number;
                  name?: string;
                  market?: string;
                }]
              : [];

          if (rows.length === 0) return;
          setLatest((prev) => {
            const next: MarketLatest = { ...prev };
            for (const r of rows) {
              if (!r || typeof r.code !== 'string') continue;
              const code = r.code;
              const previous = prev[code];
              next[code] = {
                price: typeof r.price === 'number' ? r.price : previous?.price ?? 0,
                change_pct:
                  typeof r.change_pct === 'number' ? r.change_pct : previous?.change_pct ?? 0,
                ts: typeof r.timestamp === 'number' ? r.timestamp : previous?.ts ?? 0,
                name: r.name ?? previous?.name,
                market: r.market ?? previous?.market,
              };
            }
            return next;
          });
        } catch {
          // ignore malformed events
        }
      };

      es.addEventListener('error', (event) => {
        // EventSource fires onerror for any connection issue; we treat
        // anything in non-OPEN state as a hard disconnect and reconnect.
        if (cancelled) return;
        const evt = event as MessageEvent | Event;
        const data = (evt as MessageEvent).data;
        if (typeof data === 'string' && data) {
          try {
            const parsed = JSON.parse(data);
            if (parsed && typeof parsed.error === 'string') {
              setError(parsed.error);
            }
          } catch {
            // SSE keep-alive comments or empty error events
          }
        }
        if (es.readyState === EventSource.CLOSED) {
          setIsConnected(false);
          es.close();
          if (esRef.current === es) esRef.current = null;
          scheduleReconnect();
        }
      });
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        connect();
      }, delay);
    };

    connect();

    return () => {
      cancelled = true;
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.join(','), reconnectNonce]);

  const reconnect = useCallback(() => {
    backoffRef.current = DEFAULT_BACKOFF_MS;
    setReconnectNonce((n) => n + 1);
  }, []);

  // ── REST snapshot fallback ────────────────────────────────────────────
  // EventSource reports `isConnected` as soon as the HTTP stream opens, even
  // when the backend produces zero rows (e.g. an instrument-code format the
  // stream can't resolve). And a real network drop can wedge the stream for
  // up to MAX_BACKOFF_MS between retries. As a safety net we poll the REST
  // snapshot endpoint every 30s and merge any rows into `latest`, so the UI
  // still shows the last daily close even when the live stream is silent.
  useEffect(() => {
    const validCodes = (codes || []).filter(Boolean);
    if (validCodes.length === 0) return;

    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      try {
        const res = await marketApi.snapshot(validCodes);
        // Backend shape: { items: [{ etf_code, close, change_pct, ... }], count }.
        const payload = res.data as unknown as {
          items?: Array<{
            etf_code?: string;
            etf_name?: string;
            close?: number;
            change_pct?: number;
          }>;
        };
        const rows = payload?.items ?? [];
        if (cancelled || rows.length === 0) return;
        setLatest((prev) => {
          const next: MarketLatest = { ...prev };
          for (const r of rows) {
            if (!r || typeof r.etf_code !== 'string') continue;
            const code = r.etf_code;
            const previous = prev[code];
            next[code] = {
              price: typeof r.close === 'number' ? r.close : previous?.price ?? 0,
              change_pct:
                typeof r.change_pct === 'number' ? r.change_pct : previous?.change_pct ?? 0,
              ts: previous?.ts ?? 0,
              name: r.etf_name ?? previous?.name,
              market: previous?.market,
            };
          }
          return next;
        });
      } catch {
        // best-effort fallback — ignore failures
      }
    };

    // Prime the UI shortly after mount if the stream hasn't delivered data
    // yet, then keep a slow background poll running as a safety net.
    const initial = window.setTimeout(() => {
      if (!isConnectedRef.current || Object.keys(latestRef.current).length === 0) {
        void poll();
      }
    }, 2_000);
    const interval = window.setInterval(() => void poll(), 30_000);

    return () => {
      cancelled = true;
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.join(',')]);

  return useMemo(
    () => ({ latest, isConnected, error, reconnect }),
    [latest, isConnected, error, reconnect]
  );
}

import { useEffect, useRef, useState, useCallback } from 'react';

export interface PriceTick {
  price: number;
  change_pct: number;
}

const MAX_BACKOFF_MS = 30_000;

export function usePriceStream(codes: string[]) {
  const [prices, setPrices] = useState<Record<string, PriceTick>>({});
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const backoffRef = useRef(1_000);

  const close = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => {
    const validCodes = codes.filter(Boolean);
    if (validCodes.length === 0) {
      close();
      setPrices({});
      setConnected(false);
      return;
    }

    const connect = () => {
      close();
      const query = new URLSearchParams();
      validCodes.forEach((c) => query.append('codes', c));
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
      const es = new EventSource(`${baseUrl}/stream/prices?${query.toString()}`);
      esRef.current = es;

      es.onopen = () => {
        setConnected(true);
        backoffRef.current = 1_000;
      };

      es.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed && typeof parsed.code === 'string') {
            setPrices((prev) => ({
              ...prev,
              [parsed.code]: {
                price: typeof parsed.price === 'number' ? parsed.price : prev[parsed.code]?.price ?? 0,
                change_pct: typeof parsed.change_pct === 'number' ? parsed.change_pct : prev[parsed.code]?.change_pct ?? 0,
              },
            }));
          } else if (Array.isArray(parsed)) {
            const next: Record<string, PriceTick> = {};
            parsed.forEach((item: unknown) => {
              const it = item as { code?: string; price?: number; change_pct?: number };
              if (it && typeof it.code === 'string') {
                next[it.code] = {
                  price: typeof it.price === 'number' ? it.price : 0,
                  change_pct: typeof it.change_pct === 'number' ? it.change_pct : 0,
                };
              }
            });
            setPrices(next);
          }
        } catch {
          // ignore malformed events
        }
      };

      es.onerror = () => {
        if (esRef.current !== es) return;
        setConnected(false);
        es.close();
        const timeout = Math.min(backoffRef.current, MAX_BACKOFF_MS);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
          connect();
        }, timeout);
      };
    };

    connect();
    return () => close();
  }, [codes.join(','), close]);

  return { prices, connected };
}

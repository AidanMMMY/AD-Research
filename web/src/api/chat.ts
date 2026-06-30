import client from './client';

export interface ChatSession {
  id: number;
  title?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatMessage {
  id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
}

/** Chat requests may need longer timeout — DeepSeek reasoning can take 60s+. */
const CHAT_TIMEOUT = 120_000;

export interface StreamChatMeta {
  message_id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content_length: number;
}

export interface StreamChatDone {
  message_id: number | null;
}

export interface StreamChatError {
  error: string;
  code?: string;
}

export interface StreamChatHandler {
  onMeta?: (meta: StreamChatMeta) => void;
  onDelta?: (chunk: string) => void;
  onDone?: (info: StreamChatDone) => void;
  onError?: (err: StreamChatError) => void;
  /** Called exactly once when the stream settles (done or error). */
  onComplete?: () => void;
}

export const chatApi = {
  createSession: (title?: string) =>
    client.post<ChatSession>('/research/chat/sessions', title ? { title } : {}, { timeout: CHAT_TIMEOUT }),

  listSessions: () =>
    client.get<ChatSession[]>('/research/chat/sessions', { timeout: CHAT_TIMEOUT }),

  deleteSession: (id: number) =>
    client.delete(`/research/chat/sessions/${id}`, { timeout: CHAT_TIMEOUT }),

  sendMessage: (sessionId: number, content: string) =>
    client.post<ChatMessage>(`/research/chat/sessions/${sessionId}/messages`, { content }, { timeout: CHAT_TIMEOUT }),

  getMessages: (sessionId: number) =>
    client.get<ChatMessage[]>(`/research/chat/sessions/${sessionId}/messages`, { timeout: CHAT_TIMEOUT }),

  /**
   * Stream a chat reply via Server-Sent Events.
   *
   * Opens a POST to /research/chat/sessions/{id}/messages/stream and parses
   * ``meta`` -> ``delta``* -> ``done`` SSE frames. The returned
   * Promise resolves to ``{ abort, settled }``:
   * - ``abort`` is an AbortController that cancels the in-flight request.
   * - ``settled`` is a Promise<void> that resolves when the stream fully
   *   terminates (after ``done`` or ``error``).
   */
  streamMessage: (sessionId: number, content: string, handler: StreamChatHandler) => {
    const controller = new AbortController();
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    const token = localStorage.getItem('token');

    let settled = false;
    let resolveSettled!: () => void;
    const settled_promise = new Promise<void>((r) => { resolveSettled = r; });
    const complete = () => {
      if (settled) return;
      settled = true;
      handler.onComplete?.();
      resolveSettled();
    };

    (async () => {
      try {
        const resp = await fetch(`${baseUrl}/research/chat/sessions/${sessionId}/messages/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          handler.onError?.({
            error: `Stream request failed: ${resp.status} ${resp.statusText}`,
            code: 'HTTP_ERROR',
          });
          complete();
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const parseFrames = (raw: string): string => {
          // SSE frames are separated by a blank line ("\n\n").
          const parts = raw.split('\n\n');
          const remainder = parts.pop() ?? '';
          for (const frame of parts) {
            if (!frame.trim()) continue;
            let event = 'message';
            let dataStr = '';
            for (const line of frame.split('\n')) {
              if (line.startsWith('event:')) event = line.slice(6).trim();
              else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
            }
            if (!dataStr) continue;
            let payload: any;
            try {
              payload = JSON.parse(dataStr);
            } catch {
              payload = dataStr;
            }
            if (event === 'meta') handler.onMeta?.(payload as StreamChatMeta);
            else if (event === 'delta') handler.onDelta?.(String(payload.chunk ?? ''));
            else if (event === 'done') {
              handler.onDone?.(payload as StreamChatDone);
              complete();
              return remainder;
            } else if (event === 'error') handler.onError?.(payload as StreamChatError);
          }
          return remainder;
        };

        let encounteredError = false;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            buffer = parseFrames(buffer);
            if (settled) break;
          }
          buffer += decoder.decode();
          if (buffer.trim()) parseFrames(buffer + '\n\n');
        } catch (e: any) {
          if (e?.name !== 'AbortError') {
            handler.onError?.({ error: e?.message || 'stream interrupted' });
            encounteredError = true;
          }
        }
        if (!settled) {
          if (encounteredError) complete();
          else {
            // Stream closed without a done frame → treat as terminal.
            handler.onDone?.({ message_id: null });
            complete();
          }
        }
      } catch (e: any) {
        if (e?.name !== 'AbortError') {
          handler.onError?.({ error: e?.message || 'request failed' });
        }
        complete();
      }
    })();

    return Promise.resolve({ abort: controller, settled: settled_promise });
  },
};

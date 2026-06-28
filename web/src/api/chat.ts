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
};

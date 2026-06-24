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

export const chatApi = {
  createSession: (title?: string) =>
    client.post<ChatSession>('/research/chat/sessions', title ? { title } : {}),

  listSessions: () =>
    client.get<ChatSession[]>('/research/chat/sessions'),

  deleteSession: (id: number) =>
    client.delete(`/research/chat/sessions/${id}`),

  sendMessage: (sessionId: number, content: string) =>
    client.post<ChatMessage>(`/research/chat/sessions/${sessionId}/messages`, { content }),

  getMessages: (sessionId: number) =>
    client.get<ChatMessage[]>(`/research/chat/sessions/${sessionId}/messages`),
};

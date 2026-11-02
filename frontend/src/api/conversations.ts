import { request } from './client'
import type { Conversation, ConversationDetail } from './types'

export const conversationsApi = {
  list: () => request<Conversation[]>('/conversations'),
  create: (title?: string) => request<Conversation>('/conversations', { method: 'POST', body: JSON.stringify({ title }) }),
  detail: (id: number) => request<ConversationDetail>(`/conversations/${id}`),
  delete: (id: number) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
}

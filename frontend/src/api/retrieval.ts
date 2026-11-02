import { request } from './client'
import type {
  DocumentCategory,
  RetrievalSearchResponse,
  VectorIndexStatus,
} from './types'

export const retrievalApi = {
  status: () => request<VectorIndexStatus>('/admin/retrieval/status'),
  search: (question: string, category: DocumentCategory | null, limit = 5) =>
    request<RetrievalSearchResponse>('/admin/retrieval/search', {
      method: 'POST',
      body: JSON.stringify({ question, category, limit }),
    }),
  rebuild: (profile: 'bge-small' | 'qwen-0.6b' | null = null) =>
    request<VectorIndexStatus>('/admin/retrieval/rebuild', {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),
  switchProfile: (profile: 'bge-small' | 'qwen-0.6b') =>
    request<VectorIndexStatus>('/admin/retrieval/switch', {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),
}

import { request } from './client'
import type {
  BatchUploadResponse,
  DocumentCategory,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  UploadCategory,
} from './types'

export const documentsApi = {
  list: () => request<KnowledgeDocument[]>('/admin/documents'),
  detail: (id: number) => request<KnowledgeDocumentDetail>(`/admin/documents/${id}`),
  upload: (file: File, title: string, category: UploadCategory, overwrite = false) => {
    const body = new FormData()
    body.append('file', file)
    body.append('title', title)
    body.append('category', category)
    body.append('overwrite', String(overwrite))
    return request<KnowledgeDocument>('/admin/documents', { method: 'POST', body })
  },
  uploadMany: (files: File[], category: UploadCategory, overwrite = false) => {
    const body = new FormData()
    for (const file of files) body.append('files', file)
    body.append('category', category)
    body.append('overwrite', String(overwrite))
    return request<BatchUploadResponse>('/admin/documents/batch', { method: 'POST', body })
  },
  updateDocument: (id: number, changes: { title?: string; category?: DocumentCategory }) =>
    request<KnowledgeDocument>(`/admin/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  reindex: (id: number) => request<KnowledgeDocument>(`/admin/documents/${id}/reindex`, { method: 'POST' }),
  disable: (id: number) => request<KnowledgeDocument>(`/admin/documents/${id}/disable`, { method: 'POST' }),
  enable: (id: number) => request<KnowledgeDocument>(`/admin/documents/${id}/enable`, { method: 'POST' }),
  delete: (id: number) => request<void>(`/admin/documents/${id}`, { method: 'DELETE' }),
}

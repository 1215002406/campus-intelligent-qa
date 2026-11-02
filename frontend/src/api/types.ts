export type Role = 'student' | 'admin'

export interface User {
  id: number
  username: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface RegisterRequest {
  username: string
  password: string
  role: 'student' | 'admin'
  admin_code?: string
}

export interface SourceSnapshot {
  citation_id: number
  chunk_id: number
  document_code: string
  document_title: string
  section_id: string
  excerpt: string
  page_start: number | null
  page_end: number | null
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  status: 'completed' | 'failed'
  sources_json: SourceSnapshot[]
  created_at: string
}

export interface Conversation {
  id: number
  user_id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export type DocumentCategory = '教务' | '学工' | '后勤' | '跨部门'
export type UploadCategory = '自动' | DocumentCategory
export type DocumentStatus = 'pending' | 'parsing' | 'indexing' | 'ready' | 'failed' | 'disabled'

export interface KnowledgeDocument {
  id: number
  document_code: string
  title: string
  category: DocumentCategory
  original_name: string
  status: DocumentStatus
  index_version: string | null
  chunk_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeChunk {
  id: number
  document_id: number
  index_version: string
  section_id: string
  chunk_index: number
  content: string
  page_start: number | null
  page_end: number | null
  metadata_json: Record<string, unknown>
  created_at: string
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  chunks: KnowledgeChunk[]
}

export interface BatchUploadItem {
  filename: string
  success: boolean
  status_code: number
  document: KnowledgeDocument | null
  error: string | null
  overwritten: boolean
}

export interface BatchUploadResponse {
  total: number
  accepted: number
  rejected: number
  items: BatchUploadItem[]
}

export interface EmbeddingProfileStatus {
  id: 'bge-small' | 'qwen-0.6b'
  label: string
  model: string
  dimensions: number
  indexed_chunks: number
  expected_chunks: number
  ready: boolean
  active: boolean
}

export interface VectorIndexStatus {
  active_profile: 'bge-small' | 'qwen-0.6b'
  profiles: EmbeddingProfileStatus[]
  progress: {
    state: 'idle' | 'queued' | 'running' | 'completed' | 'failed'
    completed: number
    total: number
    message: string
    started_at: string | null
    finished_at: string | null
  }
}

export interface RetrievalHit {
  chunk_id: number
  document_id: number
  document_title: string
  category: DocumentCategory
  section_id: string
  page_start: number | null
  page_end: number | null
  content: string
  score: number
  vector_score: number
  keyword_score: number
}

export interface RetrievalSearchResponse {
  profile: 'bge-small' | 'qwen-0.6b'
  hits: RetrievalHit[]
}

export interface LLMModelProfile {
  id: 'local' | 'remote'
  label: string
  configured: boolean
  active: boolean
  base_url: string
  model: string
}

export interface LLMModelStatus {
  active_provider: 'local' | 'remote'
  profiles: LLMModelProfile[]
}

export type ChatEvent =
  | { event: 'status'; data: { stage: string; message: string } }
  | { event: 'message'; data: { content: string } }
  | { event: 'message_replace'; data: { content: string } }
  | { event: 'sources'; data: { sources: SourceSnapshot[] } }
  | { event: 'done'; data: { conversation_id: number; message_id: number } }
  | { event: 'error'; data: { code: string; message: string } }

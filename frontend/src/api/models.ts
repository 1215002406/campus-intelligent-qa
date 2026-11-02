import { request } from './client'
import type { LLMModelStatus } from './types'

export const modelsApi = {
  status: () => request<LLMModelStatus>('/admin/models/status'),
  switchModel: (provider: 'local' | 'remote') =>
    request<LLMModelStatus>('/admin/models/switch', {
      method: 'POST',
      body: JSON.stringify({ provider }),
    }),
  configureRemote: (config: { base_url: string; model: string; api_key?: string }) =>
    request<LLMModelStatus>('/admin/models/remote', {
      method: 'PATCH',
      body: JSON.stringify(config),
    }),
}

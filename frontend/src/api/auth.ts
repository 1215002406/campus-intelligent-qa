import { request } from './client'
import type { LoginResponse, RegisterRequest, User } from './types'

export const authApi = {
  login: (username: string, password: string) => request<LoginResponse>('/auth/login', {
    method: 'POST', body: JSON.stringify({ username, password }),
  }),
  register: (payload: RegisterRequest) => request<LoginResponse>('/auth/register', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  me: () => request<User>('/auth/me'),
}

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '../api/auth'
import { TOKEN_KEY } from '../api/client'
import type { RegisterRequest, User } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref(sessionStorage.getItem(TOKEN_KEY) ?? '')
  const isAdmin = computed(() => user.value?.role === 'admin')
  let hydration: Promise<void> | null = null

  async function login(username: string, password: string) {
    const response = await authApi.login(username.trim(), password)
    token.value = response.access_token
    sessionStorage.setItem(TOKEN_KEY, response.access_token)
    user.value = response.user
  }

  async function register(payload: RegisterRequest) {
    const response = await authApi.register({
      ...payload,
      username: payload.username.trim(),
    })
    token.value = response.access_token
    sessionStorage.setItem(TOKEN_KEY, response.access_token)
    user.value = response.user
  }

  async function hydrate() {
    if (user.value || !token.value) return
    if (!hydration) {
      hydration = authApi.me().then((value) => { user.value = value }).finally(() => { hydration = null })
    }
    await hydration
  }

  function clear() {
    sessionStorage.removeItem(TOKEN_KEY)
    token.value = ''
    user.value = null
  }

  return { user, token, isAdmin, login, register, hydrate, clear }
})

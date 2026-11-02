import { defineStore } from 'pinia'
import { ref } from 'vue'
import { conversationsApi } from '../api/conversations'
import type { Conversation, ConversationDetail } from '../api/types'

export const useConversationsStore = defineStore('conversations', () => {
  const items = ref<Conversation[]>([])
  const active = ref<ConversationDetail | null>(null)
  const loading = ref(false)
  let selection = 0

  async function load() { items.value = await conversationsApi.list() }
  async function select(id: number) {
    const request = ++selection
    loading.value = true
    try {
      const value = await conversationsApi.detail(id)
      if (request === selection) active.value = value
    } finally { if (request === selection) loading.value = false }
  }
  async function create(title?: string) {
    const item = await conversationsApi.create(title)
    items.value = [item, ...items.value.filter((existing) => existing.id !== item.id)]
    await select(item.id)
    return item
  }
  async function remove(id: number) {
    await conversationsApi.delete(id)
    items.value = items.value.filter((item) => item.id !== id)
    if (active.value?.id === id) clearActive()
  }
  function clearActive() { selection++; active.value = null; loading.value = false }
  function reset() { clearActive(); items.value = [] }
  return { items, active, loading, load, select, create, remove, clearActive, reset }
})

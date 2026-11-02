import { apiFetch, ApiError } from './client'
import type { ChatEvent } from './types'

/** Read POST SSE without assuming that UTF-8 characters or lines fit a network chunk. */
export async function streamChat(
  conversationId: number,
  question: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
  onOpen?: () => void,
): Promise<void> {
  const response = await apiFetch('/chat/stream', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, question }),
    signal,
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
    throw new ApiError(502, '服务没有返回有效的问答事件流。')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'
  let dataLines: string[] = []
  let finished = false

  function dispatch() {
    if (!dataLines.length) { eventName = 'message'; return }
    const raw = dataLines.join('\n')
    dataLines = []
    const name = eventName
    eventName = 'message'
    if (!['status', 'message', 'message_replace', 'sources', 'done', 'error'].includes(name)) return
    let data: unknown
    try { data = JSON.parse(raw) } catch { throw new ApiError(502, '问答事件格式无效，请重新尝试。') }
    if (!data || typeof data !== 'object') throw new ApiError(502, '问答事件缺少有效数据。')
    const value = data as Record<string, unknown>
    if (name === 'status' && (typeof value.stage !== 'string' || typeof value.message !== 'string')) {
      throw new ApiError(502, '状态事件缺少进度信息。')
    }
    if (name === 'message' && typeof value.content !== 'string') throw new ApiError(502, '回答事件缺少文本。')
    if (name === 'message_replace' && typeof value.content !== 'string') throw new ApiError(502, '回答替换事件缺少文本。')
    if (name === 'sources' && !Array.isArray(value.sources)) throw new ApiError(502, '来源事件缺少来源列表。')
    if (name === 'done' && (typeof value.message_id !== 'number' || typeof value.conversation_id !== 'number')) {
      throw new ApiError(502, '回答完成事件缺少消息编号。')
    }
    if (name === 'error' && typeof value.message !== 'string') throw new ApiError(502, '错误事件缺少错误说明。')
    const event = { event: name, data } as ChatEvent
    onEvent(event)
    if (event.event === 'error') throw new ApiError(500, event.data.message)
    if (event.event === 'done') finished = true
  }

  function line(value: string) {
    if (!value) { dispatch(); return }
    if (value.startsWith(':')) return
    const colon = value.indexOf(':')
    const field = colon === -1 ? value : value.slice(0, colon)
    const content = colon === -1 ? '' : value.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') eventName = content
    if (field === 'data') dataLines.push(content)
  }

  function consume(final = false) {
    while (buffer.length) {
      const index = buffer.search(/[\r\n]/)
      if (index === -1) break
      if (!final && buffer[index] === '\r' && index === buffer.length - 1) break
      const length = buffer[index] === '\r' && buffer[index + 1] === '\n' ? 2 : 1
      line(buffer.slice(0, index))
      buffer = buffer.slice(index + length)
      if (finished) return
    }
    if (final && !finished) {
      if (buffer) line(buffer)
      buffer = ''
      dispatch()
    }
  }

  try {
    onOpen?.()
    while (!finished) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      consume(done)
      if (done) break
    }
    if (!finished) throw new ApiError(502, '连接已中断，回答未完成，请重新尝试。')
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '../api/chat'
import { errorMessage } from '../api/client'
import type { SourceSnapshot } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import MarkdownContent from '../components/MarkdownContent.vue'
import SourceDrawer from '../components/SourceDrawer.vue'
import { useConversationsStore } from '../stores/conversations'

const conversations = useConversationsStore()
const draft = ref('')
const busy = ref(false)
const sendError = ref('')
const scrollArea = ref<HTMLElement>()
const drawer = ref(false)
const sources = ref<SourceSnapshot[]>([])
const streamingQuestion = ref('')
const streamingAnswer = ref('')
const streamingSources = ref<SourceSnapshot[]>([])
const streamingStatus = ref('正在准备回答…')
let controller: AbortController | undefined
let inFlightConversation: number | undefined
const hasMessages = computed(() => Boolean(conversations.active?.messages.length || streamingQuestion.value))
const suggestions = [
  { category: '教务服务', question: '补考与重修有什么区别？', icon: 'book' },
  { category: '学生事务', question: '国家助学金如何申请？', icon: 'shield' },
  { category: '校园生活', question: '宿舍报修应该联系哪里？', icon: 'campus' },
]
function openSources(value: SourceSnapshot[]) { sources.value = value; drawer.value = true }
function choose(value: string) { draft.value = value; sendError.value = '' }
async function scrollBottom() { await nextTick(); if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight }
watch(() => [conversations.active?.id, conversations.active?.messages.length, streamingAnswer.value], scrollBottom)
watch(() => conversations.active?.id, (id) => {
  sendError.value = ''
  draft.value = ''
  if (busy.value && inFlightConversation !== undefined && id !== inFlightConversation) {
    controller?.abort()
  }
})
async function send() {
  const question = draft.value.trim()
  if (!question || busy.value) return
  busy.value = true
  sendError.value = ''
  controller = new AbortController()
  streamingQuestion.value = question
  streamingStatus.value = '正在准备回答…'
  void scrollBottom()
  let conversationId: number | undefined
  try {
    conversationId = conversations.active?.id ?? (await conversations.create()).id
    inFlightConversation = conversationId
    await streamChat(conversationId, question, (event) => {
      if (event.event === 'status') streamingStatus.value = event.data.message
      if (event.event === 'message') streamingAnswer.value += event.data.content
      if (event.event === 'message_replace') streamingAnswer.value = event.data.content
      if (event.event === 'sources') streamingSources.value = event.data.sources
    }, controller.signal, () => { draft.value = ''; void scrollBottom() })
    await conversations.select(conversationId)
    await conversations.load()
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      sendError.value = errorMessage(error)
      draft.value = question
      if (streamingQuestion.value && conversationId) {
        try { await conversations.select(conversationId) } catch { ElMessage.warning('历史消息未刷新，请重新打开会话。') }
      }
    }
  } finally {
    busy.value = false
    streamingQuestion.value = ''
    streamingAnswer.value = ''
    streamingSources.value = []
    streamingStatus.value = '正在准备回答…'
    inFlightConversation = undefined
  }
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); void send() }
}
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <main class="chat-page">
    <div class="phase-banner"><AppIcon name="info" :size="17" /><p><strong>本地 RAG 问答</strong><span>回答基于校园知识库并实时流式生成，请以引用来源为准。</span></p><span class="phase-pill">已接入</span></div>
    <div ref="scrollArea" class="chat-scroll" :class="{ 'with-messages': hasMessages }" :aria-busy="conversations.loading">
      <div v-if="conversations.loading" class="loading-state"><el-skeleton :rows="4" animated /></div>
      <section v-else-if="!hasMessages" class="welcome">
        <div class="welcome-symbol"><AppIcon name="spark" :size="34" /><span class="symbol-dot"></span></div>
        <span class="eyebrow">让校园知识，更容易被找到</span>
        <h1>你好，今天想了解什么？</h1>
        <p>从教务规定到校园生活，<br class="mobile-only" />在这里探索有据可查的答案。</p>
        <div class="question-cards"><button v-for="item in suggestions" :key="item.category" class="question-card" @click="choose(item.question)"><span class="question-category"><AppIcon :name="item.icon" :size="18" />{{ item.category }}</span><span>{{ item.question }}</span><AppIcon name="arrow" :size="17" /></button></div>
        <div class="welcome-footnote"><AppIcon name="shield" :size="15" />回答仅依据知识库资料，知识不足时会明确拒答。</div>
        <div v-if="conversations.active" class="empty-conversation"><AppIcon name="chat" :size="14" />已打开会话：{{ conversations.active.title }}</div>
      </section>
      <section v-else class="message-list" aria-live="polite">
        <div class="conversation-caption">{{ conversations.active?.title }}</div>
        <article v-for="message in conversations.active?.messages ?? []" :key="message.id" class="message" :class="message.role">
          <span class="message-avatar"><AppIcon v-if="message.role === 'assistant'" name="spark" :size="19" /><span v-else>我</span></span>
          <div class="message-body"><div class="message-author">{{ message.role === 'assistant' ? '知校园' : '你' }}<span v-if="message.status === 'failed'" class="failed-label">回答未完成</span></div><MarkdownContent v-if="message.role === 'assistant'" :content="message.content" /><div v-else class="user-content">{{ message.content }}</div><button v-if="message.role === 'assistant' && message.sources_json.length" class="sources-button" @click="openSources(message.sources_json)"><AppIcon name="book" :size="15" />查看 {{ message.sources_json.length }} 条来源<AppIcon name="chevron" :size="13" /></button></div>
        </article>
        <template v-if="streamingQuestion"><article class="message user"><span class="message-avatar">我</span><div class="message-body"><div class="message-author">你</div><div class="user-content">{{ streamingQuestion }}</div></div></article><article class="message assistant"><span class="message-avatar"><AppIcon name="spark" :size="19" /></span><div class="message-body"><div class="message-author">知校园<span class="streaming-label">生成中</span></div><MarkdownContent v-if="streamingAnswer" :content="streamingAnswer" /><span v-else class="thinking-dots">{{ streamingStatus }}</span><button v-if="streamingSources.length" class="sources-button" @click="openSources(streamingSources)"><AppIcon name="book" :size="15" />查看来源</button></div></article></template>
      </section>
    </div>
    <div class="composer-area"><el-alert v-if="sendError" class="send-error" :title="sendError" type="warning" :closable="false" show-icon /><form class="composer" @submit.prevent="send"><textarea v-model="draft" aria-label="输入校园问题" placeholder="输入你的校园问题…" rows="2" maxlength="4000" :disabled="busy" @keydown="onKeydown"></textarea><div class="composer-bottom"><span><AppIcon name="book" :size="14" />基于校园知识库回答<span class="composer-length">{{ draft.length }} / 4000</span></span><el-button type="primary" :disabled="!draft.trim() || conversations.loading" :loading="busy" native-type="submit" aria-label="发送问题"><AppIcon v-if="!busy" name="send" :size="18" /><span>发送</span></el-button></div></form><p class="composer-disclaimer">Enter 发送 · Shift + Enter 换行<span>回答应以原文为准，请留意来源。</span></p></div>
    <SourceDrawer v-model="drawer" :sources="sources" />
  </main>
</template>

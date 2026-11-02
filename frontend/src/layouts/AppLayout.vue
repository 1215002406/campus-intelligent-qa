<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { useAuthStore } from '../stores/auth'
import { useConversationsStore } from '../stores/conversations'
import { errorMessage } from '../api/client'
import type { Conversation } from '../api/types'

const auth = useAuthStore()
const conversations = useConversationsStore()
const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
const adminNavOpen = ref(localStorage.getItem('campus-qa.admin-nav') !== 'closed')
const openingNew = ref(false)
const listError = ref('')
async function load() {
  listError.value = ''
  try { await conversations.load() } catch (error) { listError.value = errorMessage(error) }
}
onMounted(load)
async function startNew() {
  if (openingNew.value) return
  openingNew.value = true
  try {
    const empty = conversations.items.find((item) => item.title === '新会话')
    if (empty) await conversations.select(empty.id)
    else conversations.clearActive()
    await router.push('/')
    sidebarOpen.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    openingNew.value = false
  }
}
async function select(item: Conversation) {
  try {
    await conversations.select(item.id)
    await router.push('/')
    sidebarOpen.value = false
  } catch (error) { ElMessage.error(errorMessage(error)) }
}
async function remove(item: Conversation) {
  try {
    await ElMessageBox.confirm(`“${item.title}”及其消息将被永久删除。`, '删除会话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await conversations.remove(item.id)
    ElMessage.success('会话已删除')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)) }
}
function logout() {
  auth.clear()
  conversations.reset()
  void router.replace('/login')
}
function toggleAdminNav() {
  adminNavOpen.value = !adminNavOpen.value
  localStorage.setItem('campus-qa.admin-nav', adminNavOpen.value ? 'open' : 'closed')
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(value))
}
</script>

<template>
  <div class="app-shell">
    <button v-if="sidebarOpen" class="sidebar-backdrop" aria-label="收起侧边栏" @click="sidebarOpen = false"></button>
    <aside class="sidebar" :class="{ 'is-open': sidebarOpen }">
      <router-link to="/" class="brand sidebar-brand" @click="sidebarOpen = false"><span class="brand-mark"><AppIcon :size="25" /></span><span>知校园<small>CAMPUS KNOWLEDGE</small></span></router-link>
      <el-button class="new-conversation" type="primary" :loading="openingNew" @click="startNew"><AppIcon name="plus" :size="18" />新建会话<span class="shortcut">＋</span></el-button>
      <div class="sidebar-section-title"><span>最近会话</span><span>{{ conversations.items.length }}</span></div>
      <div class="history-list">
        <div v-if="listError" class="history-empty"><p>{{ listError }}</p><el-button text size="small" @click="load">重新加载</el-button></div>
        <div v-else-if="!conversations.items.length" class="history-empty"><AppIcon name="chat" :size="26" /><p>还没有会话</p><small>从一次新的探索开始吧</small></div>
        <div v-for="item in conversations.items" :key="item.id" class="history-item" :class="{ active: conversations.active?.id === item.id && route.name === 'chat' }">
          <button class="history-main" @click="select(item)"><AppIcon name="chat" :size="17" /><span><strong>{{ item.title }}</strong><small>{{ formatDate(item.updated_at) }}</small></span></button>
          <button class="history-delete" :aria-label="`删除会话 ${item.title}`" @click="remove(item)"><AppIcon name="trash" :size="15" /></button>
        </div>
      </div>
      <div class="sidebar-bottom">
        <nav v-if="auth.isAdmin" class="admin-nav" :class="{ collapsed: !adminNavOpen }" aria-label="管理员工具">
          <button type="button" class="admin-nav-title" :aria-expanded="adminNavOpen" @click="toggleAdminNav">
            <span>管理工具</span><small>ADMIN</small><span class="admin-nav-toggle"><AppIcon name="chevron" :size="13" /></span>
          </button>
          <div v-show="adminNavOpen" class="admin-nav-links">
            <router-link class="admin-nav-link" :class="{ active: route.name === 'knowledge' }" to="/admin/knowledge" @click="sidebarOpen = false">
              <span class="admin-nav-icon"><AppIcon name="book" :size="17" /></span><span>知识库管理</span><small>资料</small>
            </router-link>
            <router-link class="admin-nav-link" :class="{ active: route.name === 'retrieval' }" to="/admin/retrieval" @click="sidebarOpen = false">
              <span class="admin-nav-icon"><AppIcon name="spark" :size="17" /></span><span>检索调试</span><small>测试</small>
            </router-link>
            <router-link class="admin-nav-link" :class="{ active: route.name === 'models' }" to="/admin/models" @click="sidebarOpen = false">
              <span class="admin-nav-icon"><AppIcon name="shield" :size="17" /></span><span>回答模型</span><small>配置</small>
            </router-link>
          </div>
        </nav>
        <div class="stage-note"><span class="status-dot"></span><span>本地 RAG 问答 · 可用</span></div>
        <div class="user-box"><span class="user-avatar">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span><div><strong>{{ auth.user?.username }}</strong><small>{{ auth.isAdmin ? '管理员' : '学生账号' }}</small></div><button class="icon-button" title="退出登录" aria-label="退出登录" @click="logout"><AppIcon name="logout" :size="18" /></button></div>
      </div>
    </aside>
    <section class="main-shell">
      <header class="topbar"><div class="topbar-heading"><button class="icon-button mobile-menu" aria-label="展开侧边栏" @click="sidebarOpen = true"><AppIcon name="menu" /></button><span>{{ route.name === 'knowledge' ? '知识库管理' : route.name === 'retrieval' ? '检索调试' : route.name === 'models' ? '回答模型' : '校园问答' }}</span><span class="topbar-divider">/</span><span class="topbar-muted">{{ route.name === 'knowledge' ? '资料与索引' : route.name === 'retrieval' ? '召回与模型' : route.name === 'models' ? '本地与远程' : '你的校园知识助手' }}</span></div><span class="local-badge"><span class="status-dot"></span>本地演示</span></header>
      <router-view />
    </section>
  </div>
</template>

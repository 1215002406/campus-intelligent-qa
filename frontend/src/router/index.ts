import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue') },
    {
      path: '/', component: () => import('../layouts/AppLayout.vue'), meta: { requiresAuth: true },
      children: [
        { path: '', name: 'chat', component: () => import('../views/ChatView.vue') },
        { path: 'admin/knowledge', name: 'knowledge', component: () => import('../views/KnowledgeView.vue'), meta: { admin: true } },
        { path: 'admin/retrieval', name: 'retrieval', component: () => import('../views/RetrievalView.vue'), meta: { admin: true } },
        { path: 'admin/models', name: 'models', component: () => import('../views/ModelSettingsView.vue'), meta: { admin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (auth.token && !auth.user) {
    try { await auth.hydrate() } catch { auth.clear() }
  }
  if (to.meta.requiresAuth && !auth.user) return { name: 'login' }
  if (to.meta.admin && !auth.isAdmin) return { name: 'chat' }
  if ((to.name === 'login' || to.name === 'register') && auth.user) return { name: 'chat' }
  const titles: Record<string, string> = {
    login: '登录 · 知校园',
    register: '注册 · 知校园',
    knowledge: '知识库 · 知校园',
    retrieval: '检索调试 · 知校园',
    models: '回答模型 · 知校园',
  }
  document.title = titles[String(to.name)] ?? '知校园 · 校园智能问答'
})

export default router

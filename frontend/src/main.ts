import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElAlert, ElButton, ElDrawer, ElEmpty, ElInput, ElMessage, ElSkeleton } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/client'
import { useAuthStore } from './stores/auth'
import { useConversationsStore } from './stores/conversations'

const app = createApp(App)
app.use(createPinia())
setUnauthorizedHandler(() => {
  useAuthStore().clear()
  useConversationsStore().reset()
  if (router.currentRoute.value.name !== 'login') {
    ElMessage.warning('登录已过期，请重新登录。')
    void router.replace({ name: 'login' })
  }
})
app.use(router)
for (const component of [ElAlert, ElButton, ElDrawer, ElEmpty, ElInput, ElSkeleton]) {
  app.component(component.name!, component)
}
app.mount('#app')

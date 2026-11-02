<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConversationsStore } from '../stores/conversations'
import { errorMessage } from '../api/client'
import AppIcon from '../components/AppIcon.vue'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
async function submit() {
  if (busy.value) return
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码。'; return }
  busy.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    useConversationsStore().reset()
    await router.replace('/')
  } catch (reason) { error.value = errorMessage(reason) }
  finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-story">
      <a href="/" class="brand"><span class="brand-mark"><AppIcon :size="27" /></span><span>知校园<small>CAMPUS KNOWLEDGE</small></span></a>
      <div class="story-content">
        <span class="eyebrow">校园智能问答系统</span>
        <h1>校园里的问题，<br />在这里找到<span>依据。</span></h1>
        <p>连接分散的校园知识，让每一次查询<br class="desktop-only" />都有清晰的答案与可追溯的出处。</p>
        <div class="story-chips"><span><AppIcon name="book" :size="16" />校园资料</span><span><AppIcon name="chat" :size="16" />自然对话</span><span><AppIcon name="shield" :size="16" />来源可查</span></div>
        <div class="campus-art" aria-hidden="true"><div class="art-sun"></div><div class="art-orbit"></div><div class="art-roof"></div><div class="art-building"><i></i><i></i><i></i><i></i><i></i></div><div class="art-ground"></div><span class="art-note"><AppIcon name="spark" :size="18" />让知识，触手可及</span></div>
      </div>
      <div class="story-footer">基于校园资料 · 面向校园生活</div>
    </section>
    <section class="login-panel">
      <div class="login-card">
        <span class="small-label">WELCOME BACK</span>
        <h2>欢迎来到知校园</h2>
        <p class="login-subtitle">登录你的账号，开启校园知识之旅。</p>
        <form @submit.prevent="submit">
          <label for="username">用户名</label>
          <el-input id="username" v-model="username" name="username" autocomplete="username" placeholder="请输入预置账号" size="large" :disabled="busy" autofocus />
          <label for="password">密码</label>
          <el-input id="password" v-model="password" name="password" type="password" autocomplete="current-password" placeholder="请输入密码" show-password size="large" :disabled="busy" />
          <el-alert v-if="error" class="login-error" :title="error" type="error" :closable="false" show-icon />
          <el-button class="login-submit" type="primary" native-type="submit" size="large" :loading="busy">登录<AppIcon v-if="!busy" name="arrow" :size="18" /></el-button>
        </form>
        <p class="auth-switch">还没有账号？<router-link to="/register">注册学生或管理员账号</router-link></p>
        <div class="login-hint"><AppIcon name="info" :size="17" /><p>使用预置的管理员账号登录。<br />账号信息请查看本地环境配置。</p></div>
      </div>
      <p class="login-footer">知校园 · 毕业设计本地演示系统</p>
    </section>
  </main>
</template>

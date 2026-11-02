<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useConversationsStore } from '../stores/conversations'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const confirmation = ref('')
const role = ref<'student' | 'admin'>('student')
const adminCode = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim()) {
    error.value = '请输入用户名。'
    return
  }
  if (!password.value) {
    error.value = '请输入密码。'
    return
  }
  if (password.value !== confirmation.value) {
    error.value = '两次输入的密码不一致。'
    return
  }
  if (role.value === 'admin' && !adminCode.value) {
    error.value = '请输入管理员邀请码。'
    return
  }
  busy.value = true
  try {
    await auth.register({
      username: username.value,
      password: password.value,
      role: role.value,
      admin_code: role.value === 'admin' ? adminCode.value : undefined,
    })
    useConversationsStore().reset()
    await router.replace('/')
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="register-page">
    <section class="register-shell">
      <router-link to="/login" class="brand register-brand">
        <span class="brand-mark"><AppIcon :size="27" /></span>
        <span>知校园<small>CAMPUS KNOWLEDGE</small></span>
      </router-link>
      <div class="register-card">
        <span class="small-label">CREATE ACCOUNT</span>
        <h1>创建校园账号</h1>
        <p class="register-subtitle">注册后即可登录校园智能问答系统。</p>

        <div class="role-switch" role="radiogroup" aria-label="账号类型">
          <button type="button" :class="{ active: role === 'student' }" :aria-checked="role === 'student'" role="radio" @click="role = 'student'">
            <AppIcon name="campus" :size="18" /><span><strong>学生</strong><small>直接注册</small></span>
          </button>
          <button type="button" :class="{ active: role === 'admin' }" :aria-checked="role === 'admin'" role="radio" @click="role = 'admin'">
            <AppIcon name="shield" :size="18" /><span><strong>管理员</strong><small>需要邀请码</small></span>
          </button>
        </div>

        <form @submit.prevent="submit">
          <label for="register-username">用户名</label>
          <el-input id="register-username" v-model="username" autocomplete="username" placeholder="1–80 个字符" size="large" :disabled="busy" />
          <label for="register-password">密码</label>
          <el-input id="register-password" v-model="password" type="password" autocomplete="new-password" placeholder="请输入密码" show-password size="large" :disabled="busy" />
          <label for="confirm-password">确认密码</label>
          <el-input id="confirm-password" v-model="confirmation" type="password" autocomplete="new-password" placeholder="再次输入密码" show-password size="large" :disabled="busy" />
          <template v-if="role === 'admin'">
            <label for="admin-code">管理员邀请码</label>
            <el-input id="admin-code" v-model="adminCode" type="password" autocomplete="off" placeholder="请输入管理员邀请码" show-password size="large" :disabled="busy" />
          </template>
          <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
          <el-button class="register-submit" type="primary" native-type="submit" size="large" :loading="busy">
            注册并登录<AppIcon v-if="!busy" name="arrow" :size="18" />
          </el-button>
        </form>

        <p class="back-login">已有账号？<router-link to="/login">返回登录</router-link></p>
      </div>
      <p class="register-footer">知校园 · 毕业设计本地演示系统</p>
    </section>
  </main>
</template>

<style scoped>
.register-page {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 32px;
  background:
    radial-gradient(circle at 12% 10%, rgba(81, 156, 130, .15), transparent 31%),
    radial-gradient(circle at 86% 84%, rgba(157, 184, 122, .17), transparent 32%),
    #f7faf6;
}

.register-shell {
  width: min(560px, 100%);
}

.register-brand {
  margin: 0 0 22px 8px;
}

.register-card {
  padding: 38px;
  border: 1px solid #e2eae2;
  border-radius: 20px;
  background: rgba(255, 255, 255, .94);
  box-shadow: 0 24px 70px rgba(46, 85, 69, .12);
}

.register-card h1 {
  margin: 9px 0 7px;
  color: #2f5043;
  font-size: 25px;
  font-weight: 600;
  letter-spacing: .5px;
}

.register-subtitle {
  margin: 0 0 23px;
  color: #8ea198;
  font-size: 11px;
}

.role-switch {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 9px;
  margin-bottom: 22px;
}

.role-switch button {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid #e0e9e1;
  border-radius: 10px;
  background: #f9fbf8;
  padding: 11px 12px;
  color: #82988d;
  text-align: left;
}

.role-switch button.active {
  border-color: #83b7a5;
  background: #f0f8f3;
  color: #28836c;
  box-shadow: 0 3px 12px rgba(41, 113, 89, .08);
}

.role-switch span {
  display: grid;
  gap: 3px;
}

.role-switch strong {
  font-size: 11px;
  font-weight: 550;
}

.role-switch small {
  color: #a0afa7;
  font-size: 8px;
}

form {
  display: grid;
  gap: 8px;
}

form > label {
  margin-top: 4px;
  color: #617a6e;
  font-size: 10px;
}

form > :deep(.el-alert) {
  margin-top: 7px;
}

.register-submit {
  width: 100%;
  margin-top: 12px;
}

.register-submit :deep(span) {
  gap: 8px;
}

.back-login,
.register-footer {
  text-align: center;
  color: #91a399;
  font-size: 10px;
}

.back-login {
  margin: 20px 0 0;
}

.back-login a {
  color: #27816b;
  font-weight: 550;
}

.register-footer {
  margin: 17px 0 0;
}

@media (max-width: 560px) {
  .register-page {
    padding: 18px;
  }

  .register-card {
    padding: 28px 21px;
  }
}
</style>

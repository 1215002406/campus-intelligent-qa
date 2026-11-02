<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { modelsApi } from '../api/models'
import { errorMessage } from '../api/client'
import type { LLMModelStatus } from '../api/types'

const state = ref<LLMModelStatus>()
const loading = ref(false)
const switching = ref<'local' | 'remote'>()
const loadError = ref('')
const remoteFormOpen = ref(false)
const remoteBaseUrl = ref('')
const remoteModel = ref('')
const remoteApiKey = ref('')
const savingRemote = ref(false)
const remoteFormError = ref('')
const activeProfile = computed(() => state.value?.profiles.find((item) => item.active))

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    state.value = await modelsApi.status()
    syncRemoteForm()
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

function syncRemoteForm() {
  const remote = state.value?.profiles.find((item) => item.id === 'remote')
  remoteBaseUrl.value = remote?.base_url ?? ''
  remoteModel.value = remote?.model ?? ''
  remoteApiKey.value = ''
}

function openRemoteSettings() {
  syncRemoteForm()
  remoteFormError.value = ''
  remoteFormOpen.value = true
}

async function saveRemoteSettings() {
  remoteFormError.value = ''
  const baseUrl = remoteBaseUrl.value.trim()
  const model = remoteModel.value.trim()
  const remote = state.value?.profiles.find((item) => item.id === 'remote')
  if (!baseUrl || !model) {
    remoteFormError.value = '请填写接口地址和模型名称。'
    return
  }
  if (!remote?.configured && !remoteApiKey.value.trim()) {
    remoteFormError.value = '首次配置必须填写 API Key。'
    return
  }
  savingRemote.value = true
  try {
    state.value = await modelsApi.configureRemote({
      base_url: baseUrl,
      model,
      api_key: remoteApiKey.value.trim() || undefined,
    })
    remoteFormOpen.value = false
    remoteApiKey.value = ''
    ElMessage.success('远程模型配置已保存')
  } catch (error) {
    remoteFormError.value = errorMessage(error)
  } finally {
    savingRemote.value = false
  }
}

async function activate(provider: 'local' | 'remote') {
  switching.value = provider
  try {
    state.value = await modelsApi.switchModel(provider)
    ElMessage.success(provider === 'local' ? '已切换到本地回答模型' : '已切换到远程回答模型')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    switching.value = undefined
  }
}

onMounted(() => void load())
</script>

<template>
  <main class="model-page">
    <div class="page-heading">
      <div>
        <span class="small-label">MODEL SETTINGS</span>
        <h1>回答模型</h1>
        <p>切换负责生成回答的模型。检索索引不会因此重建。</p>
      </div>
      <span class="outlined-badge"><AppIcon name="shield" :size="15" />管理员空间</span>
    </div>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
    <el-skeleton v-if="loading && !state" :rows="5" animated />
    <template v-else-if="state">
      <section class="current-panel">
        <div class="current-icon"><AppIcon name="spark" :size="25" /></div>
        <div><span>当前回答模型</span><strong>{{ activeProfile?.label }}</strong><small>{{ activeProfile?.model }}</small></div>
        <span class="running-label"><i></i>已启用</span>
      </section>

      <section class="profile-grid">
        <article v-for="profile in state.profiles" :key="profile.id" class="profile-card" :class="{ active: profile.active, unavailable: !profile.configured }">
          <header>
            <span class="profile-kind">{{ profile.id === 'local' ? 'LOCAL' : 'REMOTE' }}</span>
            <span v-if="profile.active" class="active-badge">当前使用</span>
            <span v-else-if="!profile.configured" class="inactive-badge">未配置</span>
          </header>
          <h2>{{ profile.label }}</h2>
          <dl>
            <div><dt>接口地址</dt><dd>{{ profile.base_url || '尚未填写' }}</dd></div>
            <div><dt>模型名称</dt><dd>{{ profile.model || '尚未填写' }}</dd></div>
          </dl>
          <p v-if="profile.id === 'local'">通过本机 llama.cpp 服务生成回答，使用显卡推理。</p>
          <p v-else-if="profile.configured">通过 OpenAI 兼容远程接口生成回答，密钥仅保存在后端。</p>
          <p v-else>填写 OpenAI 兼容接口地址、模型名称和 API Key 后即可启用。</p>
          <div class="profile-actions">
            <el-button v-if="!profile.active" type="primary" :loading="switching === profile.id" :disabled="!profile.configured" @click="activate(profile.id)">
              {{ profile.configured ? '切换到该模型' : '请先配置' }}
            </el-button>
            <span v-else class="in-use">正在使用</span>
            <el-button v-if="profile.id === 'remote'" text @click="openRemoteSettings">{{ profile.configured ? '修改远程配置' : '配置远程模型' }}</el-button>
          </div>
        </article>
      </section>

      <section v-if="remoteFormOpen" class="remote-config">
        <div class="panel-title">
          <div><span class="small-label">REMOTE MODEL</span><h2>配置远程回答模型</h2></div>
          <button type="button" class="config-close" @click="remoteFormOpen = false"><AppIcon name="close" :size="16" /></button>
        </div>
        <form @submit.prevent="saveRemoteSettings">
          <label><span>OpenAI 兼容接口地址</span><input v-model="remoteBaseUrl" placeholder="https://服务商地址/v1" autocomplete="url" /></label>
          <label><span>模型名称</span><input v-model="remoteModel" placeholder="远程模型名称" autocomplete="off" /></label>
          <label><span>API Key{{ state.profiles.find((item) => item.id === 'remote')?.configured ? '（留空保持不变）' : '' }}</span><input v-model="remoteApiKey" type="password" placeholder="仅保存在后端，不会回显" autocomplete="new-password" /></label>
          <el-alert v-if="remoteFormError" :title="remoteFormError" type="error" :closable="false" show-icon />
          <div class="config-actions">
            <el-button @click="remoteFormOpen = false">取消</el-button>
            <el-button type="primary" native-type="submit" :loading="savingRemote">保存配置</el-button>
          </div>
        </form>
      </section>

      <section class="model-note">
        <AppIcon name="info" :size="18" />
        <div><strong>回答模型与索引模型相互独立</strong><p>切换这里只影响最终文字生成，不会修改向量索引，也不需要重新上传文档。索引模型请在“检索调试”页面管理。</p></div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.model-page {
  padding: 42px;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  overflow-y: auto;
  flex: 1;
}

.model-page > * + * {
  margin-top: 22px;
}

.page-heading p {
  line-height: 1.8;
}

.current-panel {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px 22px;
  border: 1px solid #dce9e0;
  border-radius: 14px;
  background: linear-gradient(135deg, #f2f8f3, #fff);
}

.current-icon {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: #deefe6;
  color: #2e856e;
}

.current-panel > div:nth-child(2) {
  min-width: 0;
  flex: 1;
}

.current-panel span,
.current-panel strong,
.current-panel small {
  display: block;
}

.current-panel > div > span {
  color: #91a59b;
  font-size: 9px;
}

.current-panel strong {
  margin-top: 4px;
  color: #355647;
  font-size: 15px;
}

.current-panel small {
  margin-top: 5px;
  overflow: hidden;
  color: #91a59b;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.running-label {
  color: #32836c !important;
  font-size: 9px;
}

.running-label i {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: 50%;
  background: #3fa17d;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px;
}

.profile-card {
  padding: 21px;
  border: 1px solid #e2eae4;
  border-radius: 14px;
  background: #fff;
}

.profile-card.active {
  border-color: #81b7a4;
  box-shadow: 0 7px 24px rgba(39, 117, 92, .09);
}

.profile-card.unavailable {
  background: #fafbfa;
}

.profile-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.profile-kind {
  color: #87a095;
  font-size: 8px;
  letter-spacing: 1.8px;
}

.active-badge,
.inactive-badge {
  padding: 3px 7px;
  border-radius: 5px;
  font-size: 8px;
}

.active-badge {
  color: #2d806b;
  background: #e3f1e9;
}

.inactive-badge {
  color: #a08279;
  background: #f3ebe8;
}

.profile-card h2 {
  margin: 15px 0 17px;
  color: #3a594c;
  font-size: 17px;
  font-weight: 550;
}

.profile-card dl {
  display: grid;
  gap: 9px;
  margin: 0;
}

.profile-card dl > div {
  display: grid;
  grid-template-columns: 65px minmax(0, 1fr);
  gap: 10px;
}

.profile-card dt,
.profile-card dd {
  margin: 0;
  font-size: 9px;
}

.profile-card dt {
  color: #9aaba2;
}

.profile-card dd {
  overflow: hidden;
  color: #5e776b;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-card > p {
  min-height: 38px;
  margin: 17px 0;
  color: #8da097;
  font-size: 9px;
  line-height: 1.7;
}

.profile-card code {
  color: #597567;
}

.profile-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-actions .el-button:first-child {
  flex: 1;
}

.in-use {
  color: #32836c;
  font-size: 10px;
}

.model-note {
  display: flex;
  gap: 12px;
  padding: 17px 19px;
  border-radius: 11px;
  background: #f7faf7;
  color: #6f897c;
}

.remote-config {
  padding: 23px;
  border: 1px solid #dce8e0;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 12px 34px rgba(46, 92, 75, .08);
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.panel-title h2 {
  margin: 6px 0 0;
  color: #3b594d;
  font-size: 17px;
  font-weight: 550;
}

.config-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: #f3f7f4;
  color: #7f978b;
}

.remote-config form {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.2fr;
  gap: 13px;
  align-items: end;
}

.remote-config label {
  display: grid;
  gap: 7px;
}

.remote-config label span {
  color: #758d81;
  font-size: 9px;
}

.remote-config input {
  width: 100%;
  height: 38px;
  border: 1px solid #dfe8e2;
  border-radius: 8px;
  color: #355348;
  padding: 0 11px;
  outline: none;
}

.remote-config input:focus {
  border-color: #6fac9a;
  box-shadow: 0 0 0 3px #e9f4ef;
}

.remote-config .el-alert,
.config-actions {
  grid-column: 1 / -1;
}

.config-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 3px;
}

.model-note strong {
  font-size: 10px;
  font-weight: 550;
}

.model-note p {
  margin: 6px 0 0;
  font-size: 9px;
  line-height: 1.7;
}

@media (max-width: 760px) {
  .model-page {
    padding: 30px 24px;
  }

  .profile-grid {
    grid-template-columns: 1fr;
  }

  .remote-config form {
    grid-template-columns: 1fr;
  }
}
</style>

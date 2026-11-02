<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { retrievalApi } from '../api/retrieval'
import { errorMessage } from '../api/client'
import type { DocumentCategory, RetrievalHit, VectorIndexStatus } from '../api/types'

const status = ref<VectorIndexStatus>()
const question = ref('')
const category = ref<DocumentCategory | ''>('')
const hits = ref<RetrievalHit[]>([])
const searchedProfile = ref('')
const loading = ref(false)
const searching = ref(false)
const statusError = ref('')
const searchError = ref('')
let pollTimer: ReturnType<typeof setTimeout> | undefined

const categories: DocumentCategory[] = ['教务', '学工', '后勤', '跨部门']
const activeProfile = computed(() => status.value?.profiles.find((item) => item.active))
const progressPercent = computed(() => {
  const progress = status.value?.progress
  if (!progress?.total) return progress?.state === 'completed' ? 100 : 0
  return Math.round(progress.completed / progress.total * 100)
})
const canSearch = computed(() => Boolean(activeProfile.value?.ready && status.value?.progress.state !== 'running'))

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer)
  const progress = status.value?.progress.state
  if (progress === 'queued' || progress === 'running') {
    pollTimer = setTimeout(() => void loadStatus(true), 1800)
  }
}

async function loadStatus(silent = false) {
  if (!silent) loading.value = true
  statusError.value = ''
  try {
    status.value = await retrievalApi.status()
    schedulePoll()
  } catch (error) {
    statusError.value = errorMessage(error)
  } finally {
    if (!silent) loading.value = false
  }
}

async function rebuild(profile: 'bge-small' | 'qwen-0.6b') {
  try {
    status.value = await retrievalApi.rebuild(profile)
    ElMessage.success('已开始重建该模型的向量索引')
    schedulePoll()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function activate(profile: 'bge-small' | 'qwen-0.6b') {
  try {
    status.value = await retrievalApi.switchProfile(profile)
    hits.value = []
    ElMessage.success('检索模型已切换')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function search() {
  const value = question.value.trim()
  if (!value || searching.value) return
  searching.value = true
  searchError.value = ''
  try {
    const response = await retrievalApi.search(value, category.value || null, 5)
    hits.value = response.hits
    searchedProfile.value = response.profile
    if (!response.hits.length) searchError.value = '没有检索到符合当前分类的校园资料。'
  } catch (error) {
    searchError.value = errorMessage(error)
  } finally {
    searching.value = false
  }
}

function pageLabel(hit: RetrievalHit) {
  if (!hit.page_start) return ''
  return hit.page_end && hit.page_end !== hit.page_start
    ? `第 ${hit.page_start}–${hit.page_end} 页`
    : `第 ${hit.page_start} 页`
}

onMounted(() => void loadStatus())
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <main class="retrieval-page">
    <div class="page-heading">
      <div>
        <span class="small-label">RETRIEVAL LAB</span>
        <h1>检索调试</h1>
        <p>检查问题会召回哪些校园切片，并在本地向量模型之间安全切换。</p>
      </div>
      <span class="outlined-badge"><AppIcon name="shield" :size="15" />管理员空间</span>
    </div>

    <el-alert v-if="statusError" :title="statusError" type="error" :closable="false" show-icon />
    <el-skeleton v-if="loading && !status" :rows="4" animated />
    <section v-else-if="status" class="model-panel">
      <div class="panel-title">
        <div><span class="small-label">EMBEDDING MODELS</span><h2>向量索引模型</h2></div>
        <el-button text :loading="loading" @click="loadStatus()"><AppIcon name="refresh" :size="16" />刷新</el-button>
      </div>
      <div class="profile-grid">
        <article v-for="profile in status.profiles" :key="profile.id" class="profile-card" :class="{ active: profile.active }">
          <header><strong>{{ profile.label }}</strong><span v-if="profile.active">当前使用</span></header>
          <p>{{ profile.model }}</p>
          <div><span>{{ profile.dimensions }} 维</span><span>{{ profile.indexed_chunks }} / {{ profile.expected_chunks }} 切片</span></div>
          <div class="profile-actions">
            <el-button v-if="!profile.active" :disabled="!profile.ready || status.progress.state === 'running'" @click="activate(profile.id)">切换到此模型</el-button>
            <el-button text :disabled="status.progress.state === 'running'" @click="rebuild(profile.id)">重建索引</el-button>
          </div>
        </article>
      </div>
      <div v-if="status.progress.state !== 'idle'" class="index-progress">
        <div><span>{{ status.progress.message }}</span><strong>{{ progressPercent }}%</strong></div>
        <el-progress :percentage="progressPercent" :status="status.progress.state === 'failed' ? 'exception' : undefined" :show-text="false" />
      </div>
    </section>

    <section class="search-panel">
      <div class="panel-title">
        <div><span class="small-label">SEARCH TEST</span><h2>测试检索效果</h2></div>
        <span class="active-model">当前：{{ activeProfile?.label ?? '加载中' }}</span>
      </div>
      <form class="search-form" @submit.prevent="search">
        <input v-model="question" maxlength="4000" placeholder="例如：校园卡遗失后怎么补办？" />
        <select v-model="category"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
        <el-button type="primary" native-type="submit" :loading="searching" :disabled="!question.trim() || !canSearch">检索</el-button>
      </form>
      <el-alert v-if="searchError" :title="searchError" type="warning" :closable="false" show-icon />
      <div v-if="hits.length" class="result-heading"><span>召回结果</span><small>{{ searchedProfile }} · Top {{ hits.length }}</small></div>
      <div v-if="hits.length" class="result-list">
        <article v-for="(hit, index) in hits" :key="hit.chunk_id" class="result-card">
          <header>
            <span class="rank">{{ index + 1 }}</span>
            <div><strong>{{ hit.document_title }}</strong><small>{{ hit.section_id }} · {{ hit.category }}<template v-if="pageLabel(hit)"> · {{ pageLabel(hit) }}</template></small></div>
            <span class="score">融合 {{ hit.score.toFixed(4) }}</span>
          </header>
          <div class="score-details">向量 {{ hit.vector_score.toFixed(3) }} · 关键词 {{ hit.keyword_score.toFixed(3) }}</div>
          <p>{{ hit.content }}</p>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.retrieval-page {
  padding: 42px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  overflow-y: auto;
  flex: 1;
}

.retrieval-page > * + * {
  margin-top: 22px;
}

.page-heading p {
  line-height: 1.8;
}

.model-panel,
.search-panel {
  border: 1px solid #e5ece4;
  border-radius: 15px;
  background: #fff;
  padding: 24px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.panel-title h2 {
  margin: 6px 0 0;
  color: #3d5b50;
  font-size: 18px;
  font-weight: 550;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;
}

.profile-card {
  border: 1px solid #e3ebe5;
  border-radius: 11px;
  background: #f9fbf8;
  padding: 17px;
}

.profile-card.active {
  border-color: #8bbba9;
  background: #f1f8f3;
  box-shadow: 0 5px 18px rgba(45, 115, 92, .08);
}

.profile-card header,
.profile-card > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.profile-card header strong {
  color: #3f6254;
  font-size: 13px;
}

.profile-card header span {
  color: #2f8b73;
  background: #e1f1e9;
  border-radius: 5px;
  padding: 3px 6px;
  font-size: 8px;
}

.profile-card p {
  margin: 10px 0 13px;
  overflow: hidden;
  color: #8ca097;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-card > div > span {
  color: #91a59a;
  font-size: 9px;
}

.profile-actions {
  margin-top: 14px;
  justify-content: flex-end !important;
}

.profile-actions :deep(.el-button) {
  font-size: 10px;
}

.index-progress {
  margin-top: 16px;
  padding: 13px 15px;
  border-radius: 9px;
  background: #f6f9f6;
}

.index-progress > div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 9px;
  color: #789185;
  font-size: 9px;
}

.active-model {
  color: #7b9387;
  font-size: 9px;
}

.search-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px auto;
  gap: 10px;
}

.search-form input,
.search-form select {
  height: 40px;
  border: 1px solid #dfe8e2;
  border-radius: 8px;
  background: #fff;
  color: #355348;
  padding: 0 12px;
  outline: none;
}

.search-form input:focus,
.search-form select:focus {
  border-color: #6fac9a;
  box-shadow: 0 0 0 3px #e9f4ef;
}

.result-heading {
  display: flex;
  justify-content: space-between;
  margin: 24px 0 10px;
  color: #6f8a7e;
  font-size: 10px;
}

.result-heading small {
  color: #99aaa1;
  font-size: 8px;
}

.result-list {
  display: grid;
  gap: 10px;
}

.result-card {
  border: 1px solid #e4ebe5;
  border-radius: 10px;
  overflow: hidden;
}

.result-card header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  background: #f7faf7;
  border-bottom: 1px solid #edf2ed;
}

.rank {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  flex: none;
  border-radius: 7px;
  background: #e7f2ec;
  color: #32886f;
  font-size: 10px;
}

.result-card header div {
  min-width: 0;
  flex: 1;
}

.result-card header strong,
.result-card header small {
  display: block;
}

.result-card header strong {
  color: #415f52;
  font-size: 11px;
  font-weight: 550;
}

.result-card header small {
  margin-top: 4px;
  color: #98a9a0;
  font-size: 8px;
}

.score {
  color: #438975;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.score-details {
  padding: 7px 14px 0;
  color: #98aaa0;
  font-size: 8px;
}

.result-card p {
  margin: 0;
  padding: 14px;
  color: #53675e;
  font-size: 10px;
  line-height: 1.8;
  white-space: pre-wrap;
}

@media (max-width: 800px) {
  .retrieval-page {
    padding: 30px 24px;
  }

  .profile-grid,
  .search-form {
    grid-template-columns: 1fr;
  }
}
</style>

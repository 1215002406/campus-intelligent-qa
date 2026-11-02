<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppIcon from '../components/AppIcon.vue'
import { documentsApi } from '../api/documents'
import { errorMessage } from '../api/client'
import type {
  DocumentCategory,
  DocumentStatus,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  UploadCategory,
} from '../api/types'

const fileInput = ref<HTMLInputElement>()
const selectedFiles = ref<File[]>([])
const title = ref('')
const category = ref<UploadCategory>('自动')
const activeCategory = ref<'全部' | DocumentCategory>('全部')
const documents = ref<KnowledgeDocument[]>([])
const loading = ref(false)
const uploading = ref(false)
const actingId = ref<number>()
const loadError = ref('')
const detailOpen = ref(false)
const detailLoading = ref(false)
const savingCategory = ref(false)
const detailDocument = ref<KnowledgeDocumentDetail>()
const detailTitle = ref('')
const detailCategory = ref<DocumentCategory>('跨部门')
let pollTimer: ReturnType<typeof setTimeout> | undefined

const categories: DocumentCategory[] = ['教务', '学工', '后勤', '跨部门']
const uploadCategories: UploadCategory[] = ['自动', ...categories]
const categoryFilters: Array<'全部' | DocumentCategory> = ['全部', ...categories]
const statusLabels: Record<DocumentStatus, string> = {
  pending: '等待处理',
  parsing: '解析中',
  indexing: '写入切片',
  ready: '可用',
  failed: '处理失败',
  disabled: '已停用',
}
const processingCount = computed(() => documents.value.filter((item) =>
  ['pending', 'parsing', 'indexing'].includes(item.status)
).length)
const readyCount = computed(() => documents.value.filter((item) => item.status === 'ready').length)
const failedCount = computed(() => documents.value.filter((item) => item.status === 'failed').length)
const filteredDocuments = computed(() => activeCategory.value === '全部'
  ? documents.value
  : documents.value.filter((item) => item.category === activeCategory.value))

function categoryCount(value: '全部' | DocumentCategory) {
  return value === '全部' ? documents.value.length : documents.value.filter((item) => item.category === value).length
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function pageLabel(chunk: KnowledgeDocumentDetail['chunks'][number]) {
  if (!chunk.page_start) return '无页码'
  if (!chunk.page_end || chunk.page_end === chunk.page_start) return `第 ${chunk.page_start} 页`
  return `第 ${chunk.page_start}–${chunk.page_end} 页`
}

async function openDetail(document: KnowledgeDocument) {
  detailOpen.value = true
  await loadDetail(document.id)
}

async function loadDetail(documentId: number) {
  detailLoading.value = true
  try {
    detailDocument.value = await documentsApi.detail(documentId)
    detailTitle.value = detailDocument.value.title
    detailCategory.value = detailDocument.value.category
  } catch (error) {
    ElMessage.error(errorMessage(error))
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

const detailChanged = computed(() => Boolean(detailDocument.value) && (
  detailTitle.value.trim() !== detailDocument.value?.title
  || detailCategory.value !== detailDocument.value?.category
))

async function saveDocumentInfo() {
  if (!detailDocument.value || !detailChanged.value) return
  savingCategory.value = true
  try {
    const updated = await documentsApi.updateDocument(detailDocument.value.id, {
      title: detailTitle.value.trim(),
      category: detailCategory.value,
    })
    detailDocument.value = { ...detailDocument.value, ...updated }
    detailTitle.value = updated.title
    detailCategory.value = updated.category
    const index = documents.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) documents.value[index] = updated
    ElMessage.success('文档信息已更新')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    savingCategory.value = false
  }
}

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer)
  if (processingCount.value > 0) {
    pollTimer = setTimeout(() => void load(true), 1500)
  }
}

async function load(silent = false) {
  if (!silent) loading.value = true
  loadError.value = ''
  try {
    documents.value = await documentsApi.list()
    if (detailOpen.value && detailDocument.value) {
      await loadDetail(detailDocument.value.id)
    }
    schedulePoll()
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    if (!silent) loading.value = false
  }
}

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  const incoming = Array.from(input.files ?? [])
  const known = new Set(selectedFiles.value.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
  for (const file of incoming) {
    const key = `${file.name}:${file.size}:${file.lastModified}`
    if (!known.has(key) && selectedFiles.value.length < 20) {
      selectedFiles.value.push(file)
      known.add(key)
    }
  }
  if (selectedFiles.value.length === 1 && !title.value.trim()) {
    title.value = selectedFiles.value[0].name.replace(/\.(pdf|docx|xlsx|csv|md|markdown|txt)$/i, '')
  }
  input.value = ''
}

function removeSelected(index: number) {
  selectedFiles.value.splice(index, 1)
  if (selectedFiles.value.length !== 1) title.value = ''
}

function clearFiles() {
  selectedFiles.value = []
  if (fileInput.value) fileInput.value.value = ''
}

function mergeDocuments(incoming: KnowledgeDocument[]) {
  const existing = new Map(documents.value.map((item) => [item.id, item]))
  const added: KnowledgeDocument[] = []
  for (const item of incoming) {
    if (!existing.has(item.id)) added.push(item)
    existing.set(item.id, item)
  }
  documents.value = [...added, ...existing.values()]
}

async function confirmSameNameOverwrite(files: File[]): Promise<boolean> {
  const existingNames = new Set(documents.value.map((item) => item.original_name.toLocaleLowerCase()))
  const conflicts = files.filter((file) => existingNames.has(file.name.toLocaleLowerCase()))
  if (!conflicts.length) return false
  const names = conflicts.slice(0, 3).map((file) => `“${file.name}”`).join('、')
  const extra = conflicts.length > 3 ? `等 ${conflicts.length} 个文件` : ''
  await ElMessageBox.confirm(
    `${names}${extra}与知识库现有文档同名。覆盖会替换原文件并重新解析、重建切片索引，是否继续？`,
    '覆盖同名文档',
    {
      confirmButtonText: '覆盖并更新',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
  return true
}

async function upload() {
  if (!selectedFiles.value.length) {
    ElMessage.warning('请先选择知识文件')
    return
  }
  if (selectedFiles.value.length === 1 && !title.value.trim()) {
    ElMessage.warning('请输入文档标题')
    return
  }
  if (selectedFiles.value.some((file) => file.size > 20 * 1024 * 1024)) {
    ElMessage.warning('单个文件不能超过 20 MB')
    return
  }
  let overwrite = false
  try {
    overwrite = await confirmSameNameOverwrite(selectedFiles.value)
  } catch {
    return
  }
  uploading.value = true
  try {
    if (selectedFiles.value.length === 1) {
      const document = await documentsApi.upload(
        selectedFiles.value[0],
        title.value.trim(),
        category.value,
        overwrite,
      )
      mergeDocuments([document])
      ElMessage.success(overwrite ? '同名文档已覆盖，正在重新解析' : '文件已上传，正在后台解析')
    } else {
      const result = await documentsApi.uploadMany(selectedFiles.value, category.value, overwrite)
      const uploaded = result.items.flatMap((item) => item.document ? [item.document] : [])
      mergeDocuments(uploaded)
      if (result.rejected) {
        const reasons = result.items.filter((item) => !item.success).slice(0, 3)
          .map((item) => `${item.filename}：${item.error}`).join('；')
        ElMessage.warning(`成功 ${result.accepted} 个，失败 ${result.rejected} 个。${reasons}`)
      } else {
        ElMessage.success(`已批量上传 ${result.accepted} 个文件`)
      }
    }
    clearFiles()
    title.value = ''
    schedulePoll()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    uploading.value = false
  }
}

async function runAction(document: KnowledgeDocument, action: 'reindex' | 'disable' | 'enable') {
  actingId.value = document.id
  try {
    const updated = action === 'reindex'
      ? await documentsApi.reindex(document.id)
      : action === 'disable'
        ? await documentsApi.disable(document.id)
        : await documentsApi.enable(document.id)
    const index = documents.value.findIndex((item) => item.id === document.id)
    if (index >= 0) documents.value[index] = updated
    ElMessage.success(action === 'reindex' ? '已提交重新索引' : action === 'disable' ? '文档已停用' : '文档已启用')
    schedulePoll()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    actingId.value = undefined
  }
}

async function remove(document: KnowledgeDocument) {
  try {
    await ElMessageBox.confirm(
      `“${document.title}”的原始文件、切片和索引信息都会被永久删除。`,
      '删除文档',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    actingId.value = document.id
    await documentsApi.delete(document.id)
    documents.value = documents.value.filter((item) => item.id !== document.id)
    ElMessage.success('文档已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  } finally {
    actingId.value = undefined
  }
}

onMounted(() => void load())
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <main class="knowledge-page">
    <div class="page-heading">
      <div>
        <span class="small-label">KNOWLEDGE BASE</span>
        <h1>让校园资料成为知识</h1>
        <p>支持 PDF、DOCX、XLSX、CSV、TXT 和 Markdown；可单份或批量上传，系统会自动解析、切片并保存到 MySQL。</p>
      </div>
      <span class="outlined-badge"><AppIcon name="shield" :size="15" />管理员空间</span>
    </div>

    <section class="upload-panel">
      <div class="panel-title">
        <div><span class="small-label">ADD DOCUMENT</span><h2>上传知识文档</h2></div>
        <span class="format-note">PDF · DOCX · XLSX · CSV · TXT · Markdown<br />单文件最大 20 MB · 每批最多 20 个</span>
      </div>
      <form class="upload-form" @submit.prevent="upload">
        <button type="button" class="file-picker" :class="{ selected: selectedFiles.length }" @click="fileInput?.click()">
          <AppIcon name="file" :size="24" />
          <span>
            <strong>{{ selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : '选择一个或多个知识文件' }}</strong>
            <small>{{ selectedFiles.length ? '点击继续添加，最多 20 个' : '支持混合格式批量上传' }}</small>
          </span>
        </button>
        <input ref="fileInput" class="sr-only" type="file" multiple accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain,text/markdown" @change="chooseFile" />
        <label class="field"><span>文档标题{{ selectedFiles.length > 1 ? '（批量时使用文件名）' : '' }}</span><input v-model="title" maxlength="200" :disabled="selectedFiles.length > 1" :placeholder="selectedFiles.length > 1 ? '批量上传自动使用文件名' : '例如：2026 年选课指南'" /></label>
        <label class="field category-field"><span>所属分类</span><select v-model="category"><option v-for="item in uploadCategories" :key="item">{{ item }}</option></select></label>
        <el-button class="upload-button" type="primary" native-type="submit" :loading="uploading" :disabled="!selectedFiles.length || (selectedFiles.length === 1 && !title.trim())"><AppIcon :name="uploading ? 'clock' : 'plus'" :size="17" />{{ selectedFiles.length > 1 ? '批量上传' : '上传并解析' }}</el-button>
      </form>
      <div v-if="selectedFiles.length" class="selected-files">
        <span v-for="(file, index) in selectedFiles" :key="`${file.name}-${file.size}-${file.lastModified}`">
          <AppIcon name="file" :size="13" />{{ file.name }}
          <button type="button" :aria-label="`移除 ${file.name}`" @click="removeSelected(index)"><AppIcon name="close" :size="12" /></button>
        </span>
      </div>
    </section>

    <nav class="category-nav" aria-label="知识库分类导航">
      <button v-for="item in categoryFilters" :key="item" type="button" :class="{ active: activeCategory === item }" @click="activeCategory = item">
        <span>{{ item }}</span><small>{{ categoryCount(item) }}</small>
      </button>
    </nav>

    <section class="knowledge-metrics">
      <div><span>{{ documents.length }}</span><p>全部文档</p></div>
      <div><span>{{ readyCount }}</span><p>可用文档</p></div>
      <div><span>{{ processingCount }}</span><p>正在处理</p></div>
      <div><span>{{ failedCount }}</span><p>处理失败</p></div>
    </section>

    <section class="library-panel">
      <div class="panel-title">
        <div><span class="small-label">LIBRARY</span><h2>知识库文档</h2></div>
        <el-button text :loading="loading" @click="load()"><AppIcon name="refresh" :size="16" />刷新</el-button>
      </div>

      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
      <el-skeleton v-if="loading && !documents.length" :rows="4" animated />
      <div v-else-if="!filteredDocuments.length" class="library-empty">
        <AppIcon name="book" :size="31" />
        <h3>{{ documents.length ? `“${activeCategory}”分类下暂无文档` : '还没有知识文档' }}</h3>
        <p>{{ documents.length ? '可以切换分类，或在文档详情中修改分类。' : '先上传校园知识文档，完成后再接入检索和问答。' }}</p>
      </div>
      <div v-else class="document-list">
        <article v-for="document in filteredDocuments" :key="document.id" class="document-item">
          <div class="document-mark"><AppIcon name="book" :size="20" /></div>
          <button type="button" class="document-main" @click="openDetail(document)">
            <div class="document-name">
              <strong>{{ document.title }}</strong>
              <span class="category-label">{{ document.category }}</span>
            </div>
            <p>{{ document.original_name }} · {{ document.chunk_count }} 个切片 · {{ formatDate(document.updated_at) }}</p>
            <small v-if="document.error_message" class="document-error">{{ document.error_message }}</small>
          </button>
          <span class="status-label" :class="`status-${document.status}`"><i></i>{{ statusLabels[document.status] }}</span>
          <div class="document-actions">
            <button v-if="document.status === 'ready'" type="button" :disabled="actingId === document.id" @click.stop="runAction(document, 'disable')">停用</button>
            <button v-if="document.status === 'disabled'" type="button" :disabled="actingId === document.id" @click.stop="runAction(document, 'enable')">启用</button>
            <button v-if="['ready', 'disabled', 'failed'].includes(document.status)" type="button" :disabled="actingId === document.id" @click.stop="runAction(document, 'reindex')">重建</button>
            <button type="button" class="danger" aria-label="删除文档" :disabled="actingId === document.id || ['parsing', 'indexing'].includes(document.status)" @click.stop="remove(document)"><AppIcon name="trash" :size="15" /></button>
          </div>
        </article>
      </div>
    </section>

    <section class="knowledge-next">
      <div><span>已完成</span><strong>文档上传与切片</strong></div>
      <AppIcon name="arrow" :size="18" />
      <div><span>下一步</span><strong>中文向量与混合检索</strong></div>
      <AppIcon name="arrow" :size="18" />
      <div><span>之后</span><strong>大模型问答与来源引用</strong></div>
    </section>

    <el-drawer v-model="detailOpen" size="min(760px, 94vw)" class="document-detail-drawer">
      <template #header>
        <div class="detail-heading">
          <span class="small-label">DOCUMENT CONTENT</span>
          <h2>{{ detailDocument?.title ?? '文档详情' }}</h2>
        </div>
      </template>
      <el-skeleton v-if="detailLoading" :rows="8" animated />
      <div v-else-if="detailDocument" class="detail-content">
        <div class="detail-meta">
          <span class="status-label" :class="`status-${detailDocument.status}`"><i></i>{{ statusLabels[detailDocument.status] }}</span>
          <span>{{ detailDocument.chunk_count }} 个切片</span>
          <span>{{ detailDocument.original_name }}</span>
        </div>
        <div class="detail-category-editor">
          <label class="detail-title-field"><span>文档名称</span><input v-model="detailTitle" maxlength="200" placeholder="请输入文档名称" /></label>
          <label><span>文档分类</span><select v-model="detailCategory"><option v-for="item in categories" :key="item">{{ item }}</option></select></label>
          <el-button type="primary" :loading="savingCategory" :disabled="!detailChanged || !detailTitle.trim()" @click="saveDocumentInfo">保存修改</el-button>
        </div>
        <el-alert v-if="detailDocument.error_message" :title="detailDocument.error_message" type="error" :closable="false" show-icon />
        <div v-if="!detailDocument.chunks.length" class="detail-empty">
          <AppIcon name="clock" :size="26" />
          <p>{{ ['pending', 'parsing', 'indexing'].includes(detailDocument.status) ? '文档正在处理中，完成后可查看切片。' : '当前没有可查看的切片。' }}</p>
        </div>
        <div v-else class="chunk-list">
          <article v-for="chunk in detailDocument.chunks" :key="chunk.id" class="chunk-card">
            <header><strong>{{ chunk.section_id }}</strong><span>{{ pageLabel(chunk) }}</span><small>切片 {{ chunk.chunk_index + 1 }}</small></header>
            <pre>{{ chunk.content }}</pre>
          </article>
        </div>
      </div>
    </el-drawer>
  </main>
</template>

<style scoped>
.knowledge-page {
  gap: 22px;
}

.knowledge-page > * + * {
  margin-top: 22px;
}

.page-heading p {
  max-width: 650px;
  line-height: 1.8;
}

.category-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border: 1px solid #e5ece4;
  border-radius: 12px;
  background: #f8fbf6;
  overflow-x: auto;
}

.category-nav button {
  min-width: 92px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #789085;
  padding: 9px 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 13px;
  white-space: nowrap;
  font-size: 10px;
}

.category-nav button small {
  min-width: 19px;
  height: 19px;
  border-radius: 10px;
  background: #e9f0e9;
  display: grid;
  place-items: center;
  color: #8ca095;
  font-size: 8px;
}

.category-nav button:hover {
  background: #eff6f0;
  color: #3f7d6b;
}

.category-nav button.active {
  background: #fff;
  color: #287b68;
  box-shadow: 0 2px 10px rgba(52, 102, 82, .09);
}

.category-nav button.active small {
  background: #e4f1eb;
  color: #2b806b;
}

.knowledge-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid #e5ece4;
  border-radius: 14px;
  background: linear-gradient(135deg, #f8fbf6, #fff);
  overflow: hidden;
}

.knowledge-metrics > div {
  padding: 18px 22px;
  border-right: 1px solid #edf2eb;
}

.knowledge-metrics > div:last-child {
  border-right: 0;
}

.knowledge-metrics span {
  color: #315e50;
  font-size: 25px;
  font-weight: 600;
}

.knowledge-metrics p {
  margin: 5px 0 0;
  color: #91a39a;
  font-size: 10px;
}

.upload-panel,
.library-panel {
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
  margin-bottom: 19px;
}

.panel-title h2 {
  margin: 6px 0 0;
  color: #3d5b50;
  font-size: 18px;
  font-weight: 550;
}

.format-note {
  color: #8ba197;
  font-size: 10px;
  line-height: 1.6;
  text-align: right;
}

.upload-form {
  display: grid;
  grid-template-columns: minmax(230px, 1.5fr) minmax(180px, 1fr) 110px auto;
  gap: 12px;
  align-items: end;
}

.file-picker {
  min-height: 58px;
  border: 1px dashed #bfd2c6;
  border-radius: 10px;
  background: #f8fbf7;
  color: #6c8579;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 11px;
  text-align: left;
}

.file-picker:hover,
.file-picker.selected {
  border-color: #6eac98;
  background: #f1f8f4;
}

.file-picker span {
  min-width: 0;
}

.file-picker strong,
.file-picker small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-picker strong {
  color: #47685b;
  font-size: 11px;
  font-weight: 550;
}

.file-picker small {
  margin-top: 5px;
  color: #97aaa0;
  font-size: 9px;
}

.field {
  display: grid;
  gap: 7px;
}

.field > span {
  color: #718a7e;
  font-size: 10px;
}

.field input,
.field select {
  width: 100%;
  height: 38px;
  border: 1px solid #dfe8e2;
  border-radius: 8px;
  background: #fff;
  color: #355348;
  padding: 0 11px;
  outline: none;
}

.field input:focus,
.field select:focus {
  border-color: #6fac9a;
  box-shadow: 0 0 0 3px #e9f4ef;
}

.field input:disabled {
  color: #8fa39a;
  background: #f5f8f5;
}

.upload-button {
  height: 38px;
  padding: 0 15px;
}

.selected-files {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 13px;
}

.selected-files > span {
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  background: #f1f7f3;
  color: #668176;
  padding: 5px 6px 5px 8px;
  font-size: 9px;
}

.selected-files > span > :first-child {
  flex: none;
}

.selected-files button {
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #91a69b;
  display: grid;
  place-items: center;
}

.selected-files button:hover {
  color: #ac6659;
  background: #f8eae7;
}

.upload-button :deep(span) {
  gap: 6px;
}

.library-panel .panel-title {
  margin-bottom: 14px;
}

.library-empty {
  padding: 38px 20px;
  text-align: center;
  color: #94a89c;
}

.library-empty h3 {
  margin: 11px 0 7px;
  color: #5f796d;
  font-size: 14px;
  font-weight: 500;
}

.library-empty p {
  margin: 0;
  font-size: 10px;
}

.document-list {
  border-top: 1px solid #edf2ed;
}

.document-item {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 88px 180px;
  gap: 12px;
  align-items: center;
  padding: 16px 4px;
  border-bottom: 1px solid #edf2ed;
}

.document-mark {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: #edf5ef;
  color: #4d8e7b;
}

.document-main {
  min-width: 0;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
}

.document-main:hover .document-name strong {
  color: #258b77;
}

.document-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.document-name strong {
  overflow: hidden;
  text-overflow: ellipsis;
  color: #345247;
  font-size: 12px;
  font-weight: 550;
  white-space: nowrap;
}

.category-label {
  flex: none;
  color: #719384;
  background: #eff5ef;
  border-radius: 5px;
  padding: 3px 6px;
  font-size: 8px;
}

.document-main p,
.document-error {
  margin: 6px 0 0;
  color: #98a99f;
  font-size: 9px;
}

.document-error {
  display: block;
  color: #ae7268;
  line-height: 1.5;
}

.status-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #798f84;
  font-size: 9px;
  white-space: nowrap;
}

.status-label i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #aabbb1;
}

.status-ready i { background: #3aa37e; }
.status-disabled i { background: #99a39e; }
.status-failed i { background: #c47767; }
.status-pending i,
.status-parsing i,
.status-indexing i { background: #d4a44e; }

.document-actions {
  display: flex;
  justify-content: flex-end;
  gap: 5px;
}

.document-actions button {
  border: 1px solid #e1e9e3;
  border-radius: 7px;
  background: #fff;
  color: #70897d;
  height: 30px;
  padding: 0 9px;
  font-size: 9px;
}

.document-actions button:hover:not(:disabled) {
  border-color: #9fc5b5;
  color: #2d806b;
  background: #f5faf7;
}

.document-actions button.danger {
  width: 30px;
  padding: 0;
  display: grid;
  place-items: center;
  color: #a28176;
}

.document-actions button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.knowledge-next {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 2px 16px;
  color: #b1c0b5;
}

.knowledge-next > div {
  min-width: 0;
}

.knowledge-next span,
.knowledge-next strong {
  display: block;
}

.knowledge-next span {
  margin-bottom: 5px;
  font-size: 8px;
}

.knowledge-next strong {
  color: #809b8d;
  font-size: 10px;
  font-weight: 500;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.detail-heading h2 {
  margin: 7px 0 0;
  color: #36574b;
  font-size: 18px;
  font-weight: 550;
}

.detail-content {
  display: grid;
  gap: 18px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  color: #91a49a;
  font-size: 9px;
}

.detail-category-editor {
  display: flex;
  align-items: end;
  gap: 10px;
  padding: 15px;
  border: 1px solid #e3ebe5;
  border-radius: 11px;
  background: #f8fbf7;
}

.detail-category-editor label {
  display: grid;
  gap: 6px;
  flex: 1;
}

.detail-category-editor .detail-title-field {
  flex: 2;
}

.detail-category-editor label span {
  color: #718a7e;
  font-size: 9px;
}

.detail-category-editor select,
.detail-category-editor input {
  height: 34px;
  border: 1px solid #dce7df;
  border-radius: 7px;
  background: #fff;
  color: #3c5d50;
  padding: 0 9px;
  outline: none;
}

.detail-category-editor input:focus,
.detail-category-editor select:focus {
  border-color: #6fac9a;
  box-shadow: 0 0 0 3px #e9f4ef;
}

.detail-category-editor .el-button {
  height: 34px;
}

.detail-empty {
  padding: 45px 20px;
  text-align: center;
  color: #9aaca1;
}

.detail-empty p {
  margin: 10px 0 0;
  font-size: 10px;
}

.chunk-list {
  display: grid;
  gap: 12px;
}

.chunk-card {
  border: 1px solid #e4ebe5;
  border-radius: 11px;
  background: #fff;
  overflow: hidden;
}

.chunk-card header {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 13px;
  border-bottom: 1px solid #edf2ed;
  background: #f8fbf7;
}

.chunk-card header strong {
  color: #347a68;
  font-size: 10px;
  font-weight: 600;
}

.chunk-card header span,
.chunk-card header small {
  color: #9aaca1;
  font-size: 8px;
}

.chunk-card header small {
  margin-left: auto;
}

.chunk-card pre {
  margin: 0;
  padding: 14px;
  color: #4a6257;
  font-family: inherit;
  font-size: 11px;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1000px) {
  .upload-form {
    grid-template-columns: 1fr 1fr;
  }

  .document-item {
    grid-template-columns: 42px minmax(0, 1fr) 92px;
  }

  .document-actions {
    grid-column: 2 / -1;
  }
}

@media (max-width: 700px) {
  .category-nav {
    margin-right: -4px;
    margin-left: -4px;
  }

  .category-nav button {
    min-width: 82px;
  }

  .knowledge-metrics {
    grid-template-columns: repeat(2, 1fr);
  }

  .knowledge-metrics > div:nth-child(2) {
    border-right: 0;
  }

  .knowledge-metrics > div:nth-child(-n+2) {
    border-bottom: 1px solid #edf2eb;
  }

  .upload-form {
    grid-template-columns: 1fr;
  }

  .panel-title {
    align-items: flex-start;
  }

  .format-note {
    text-align: right;
    max-width: 120px;
    line-height: 1.5;
  }

  .document-item {
    grid-template-columns: 36px minmax(0, 1fr);
  }

  .document-mark {
    width: 32px;
    height: 32px;
  }

  .status-label {
    grid-column: 2;
  }

  .document-actions {
    grid-column: 2;
    justify-content: flex-start;
  }

  .knowledge-next {
    display: none;
  }

  .detail-category-editor {
    flex-wrap: wrap;
  }

  .detail-category-editor .detail-title-field {
    flex-basis: 100%;
  }
}
</style>

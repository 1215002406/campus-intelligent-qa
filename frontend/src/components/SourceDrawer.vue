<script setup lang="ts">
import type { SourceSnapshot } from '../api/types'
import AppIcon from './AppIcon.vue'
defineProps<{ modelValue: boolean; sources: SourceSnapshot[] }>()
defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <el-drawer :model-value="modelValue" title="回答来源" size="min(460px, 100vw)" @update:model-value="$emit('update:modelValue', $event)">
    <p class="source-intro">以下为回答生成时保存的原文快照，用于核对事实和出处。</p>
    <el-empty v-if="!sources.length" description="这条回答暂时没有来源快照" :image-size="90" />
    <article v-for="source in sources" :key="`${source.citation_id}-${source.chunk_id}`" class="source-card">
      <div class="source-card-top"><span class="citation">{{ source.citation_id }}</span><span>{{ source.document_code }}</span></div>
      <h3><AppIcon name="file" :size="18" />{{ source.document_title }}</h3>
      <div class="source-meta">章节 {{ source.section_id || '未标注' }}<span v-if="source.page_start != null"> · 第 {{ source.page_start }}<template v-if="source.page_end != null && source.page_end !== source.page_start">—{{ source.page_end }}</template> 页</span></div>
      <blockquote>{{ source.excerpt }}</blockquote>
    </article>
  </el-drawer>
</template>

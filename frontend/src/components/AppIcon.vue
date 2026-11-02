<script setup lang="ts">
withDefaults(defineProps<{ name?: string; size?: number }>(), { name: 'campus', size: 20 })
const paths: Record<string, string> = {
  campus: 'M3 10 12 4l9 6M5 10v10h14V10M9 20v-6h6v6M9 10h.01M15 10h.01M2 20h20',
  plus: 'M12 5v14M5 12h14',
  chat: 'M21 11.5a8.4 8.4 0 0 1-.9 3.8A8.5 8.5 0 0 1 12.5 20a8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z',
  book: 'M4 3h6a3 3 0 0 1 3 3v15a4 4 0 0 0-4-3H3V3h1ZM13 6a3 3 0 0 1 3-3h5v15h-5a4 4 0 0 0-3 3',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  logout: 'M9 5H4v14h5M13 8l4 4-4 4M8 12h13',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  send: 'm22 2-7 20-4-9-9-4L22 2ZM11 13 22 2',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3ZM8 12l3 3 5-6',
  chevron: 'm9 5 7 7-7 7',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  file: 'M14 2H5v20h14V7l-5-5ZM14 2v6h5M8 12h8M8 16h5',
  info: 'M12 8h.01M12 11v6M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
  refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] ?? paths.campus" /></svg>
</template>

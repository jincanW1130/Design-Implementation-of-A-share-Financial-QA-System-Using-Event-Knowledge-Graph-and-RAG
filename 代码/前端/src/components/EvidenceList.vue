<script setup>
// 代码\前端\src\components\EvidenceList.vue —— 证据按四类分组展示（第 9 阶段 T9／F5）
//
// 四类固定顺序与后端 `qa_service.EVIDENCE_TYPES` 一致：
//   回答来源／新闻来源／公告来源／相关事件。
// 每条显示 rank／title／source／publish_time／doc_id／chunk_id，
// 并提供「查看原文上下文」→ 调 `GET /api/documents/{doc_id}/chunks/{chunk_id}`，
// 展示 chunk_content 正文与相邻块（`neighbor_chunks`）。

import { computed, reactive, ref } from 'vue'
import { getChunk } from '../api.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** 后端返回的四类计数（`groups`）；缺省时按 items 现算。 */
  groups: { type: Object, default: () => ({}) },
})

// 与后端 EVIDENCE_TYPES 逐字对齐、顺序一致
const TYPES = ['回答来源', '新闻来源', '公告来源', '相关事件']

const grouped = computed(() => {
  const out = {}
  for (const t of TYPES) out[t] = props.items.filter((it) => it.evidence_type === t)
  return out
})

function countOf(t) {
  // 优先用后端计数；后端没给（或为 0 而本地有）时按本地 items 累计
  const n = props.groups ? props.groups[t] : undefined
  return typeof n === 'number' ? n : grouped.value[t].length
}

const openKey = ref('')                 // 当前展开的条目（同一时刻只展开一条）
const chunks = reactive({})             // 缓存：key → {loading, error, data}

function keyOf(it) { return `${it.doc_id}-${it.chunk_id}` }

async function toggleChunk(it) {
  const key = keyOf(it)
  if (openKey.value === key) { openKey.value = ''; return }
  openKey.value = key
  if (chunks[key] && !chunks[key].error) return   // 已缓存成功结果，不重复请求
  chunks[key] = { loading: true, error: '', data: null }
  try {
    const data = await getChunk(it.doc_id, it.chunk_id)
    chunks[key] = { loading: false, error: '', data }
  } catch (e) {
    chunks[key] = { loading: false, error: `${e.code ? '[' + e.code + '] ' : ''}${e.message}`, data: null }
  }
}

function fmtTime(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 16) : '—' }
</script>

<template>
  <div class="evidence">
    <div v-if="!items.length" class="empty">本次回答未返回证据条目。</div>

    <div v-for="t in TYPES" :key="t" class="group">
      <h3 class="group-head">
        <span class="group-name">{{ t }}</span>
        <span class="tag">{{ countOf(t) }} 条</span>
      </h3>
      <p v-if="!grouped[t].length" class="muted group-none">（本类无证据）</p>

      <ul v-else class="ev-list">
        <li v-for="it in grouped[t]" :key="keyOf(it)" class="ev-item">
          <div class="ev-row">
            <span class="tag">rank {{ it.rank }}</span>
            <span class="ev-title">{{ it.title }}</span>
          </div>
          <div class="ev-meta muted">
            <span>来源：{{ it.source || '—' }}</span>
            <span>发布时间：{{ fmtTime(it.publish_time) }}</span>
            <span>doc_id：{{ it.doc_id }}</span>
            <span>chunk_id：{{ it.chunk_id }}</span>
          </div>
          <div class="ev-actions">
            <button class="btn" @click="toggleChunk(it)">
              {{ openKey === keyOf(it) ? '收起原文上下文' : '查看原文上下文' }}
            </button>
            <a v-if="it.url" class="src-link" :href="it.url" target="_blank" rel="noopener">原文链接</a>
          </div>

          <div v-if="openKey === keyOf(it)" class="chunk-panel">
            <p v-if="chunks[keyOf(it)] && chunks[keyOf(it)].loading" class="muted">加载中…</p>
            <p v-else-if="chunks[keyOf(it)] && chunks[keyOf(it)].error" class="err">
              {{ chunks[keyOf(it)].error }}
            </p>
            <template v-else-if="chunks[keyOf(it)] && chunks[keyOf(it)].data">
              <div class="chunk-doc muted">
                文档：{{ chunks[keyOf(it)].data.doc.title }}
                ｜ chunk_index={{ chunks[keyOf(it)].data.chunk_index }}
              </div>
              <div class="chunk-block">
                <div class="chunk-label">正文（chunk_{{ chunks[keyOf(it)].data.chunk_id }}）</div>
                <pre class="chunk-text">{{ chunks[keyOf(it)].data.chunk_content }}</pre>
              </div>
              <div v-for="nb in (chunks[keyOf(it)].data.neighbor_chunks || [])" :key="nb.chunk_id"
                   class="chunk-block neighbor">
                <div class="chunk-label">相邻块 chunk_{{ nb.chunk_id }}（index={{ nb.chunk_index }}）</div>
                <pre class="chunk-text">{{ nb.chunk_content }}</pre>
              </div>
            </template>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.group { margin-bottom: 16px; }
.group-head { display: flex; align-items: center; gap: 10px; margin: 0 0 8px; font-size: 14px; }
.group-name { font-weight: 600; }
.group-none { margin: 0 0 0 2px; font-size: 13px; }
.ev-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.ev-item { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; }
.ev-row { display: flex; gap: 8px; align-items: baseline; }
.ev-title { font-weight: 600; }
.ev-meta { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12px; margin: 4px 0 6px; }
.ev-actions { display: flex; align-items: center; gap: 12px; }
.src-link { font-size: 12px; }
.chunk-panel { margin-top: 10px; border-top: 1px dashed var(--line); padding-top: 10px; }
.chunk-doc { font-size: 12px; margin-bottom: 6px; }
.chunk-block { margin-bottom: 8px; }
.chunk-label { font-size: 12px; color: var(--ink-soft); margin-bottom: 2px; }
.chunk-text {
  margin: 0; white-space: pre-wrap; word-break: break-word; background: #f8f9fb;
  border: 1px solid var(--line); border-radius: 4px; padding: 8px; font-size: 13px;
  font-family: inherit; max-height: 260px; overflow: auto;
}
.neighbor .chunk-text { background: #fbfbfc; color: var(--ink-soft); }
</style>

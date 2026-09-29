<script setup>
// 代码\前端\src\views\HistoryView.vue —— 历史记录页（第 9 阶段 T10）
//
// 取数：
//   * `GET /api/history?session_id=…&page=&page_size=` → 列表（question_id／ask_time／answer_summary／evidence_count）
//   * `GET /api/history/{question_id}?session_id=…`    → 回看（问题／答案／证据）
//   `session_id` 由 api.js 自动带上（会话隔离 FR-06）。
//
// **回看只还原三表内容，不重新渲染当时的图谱路径视图**（硬约束 11）：
// 后端只回 `graph_path_available` 布尔，页面据此给出提示，**不呈现路径本体**。
//
// 空列表是正常业务状态（2002 语义），给「未检索到匹配结果」提示而不是错误样式。

import { computed, onMounted, ref } from 'vue'
import { listHistory, getHistoryDetail } from '../api.js'
import AnswerSections from '../components/AnswerSections.vue'
import EvidenceList from '../components/EvidenceList.vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const error = ref(null)
const empty = ref(false)

const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

async function load() {
  error.value = null
  empty.value = false
  loading.value = true
  detail.value = null
  try {
    const data = await listHistory(page.value, pageSize.value)
    items.value = (data && data.items) || []
    total.value = (data && data.total) || 0
    empty.value = items.value.length === 0
  } catch (e) {
    items.value = []
    total.value = 0
    error.value = { code: e.code, message: e.message }
  } finally {
    loading.value = false
  }
}

async function openDetail(questionId) {
  detailError.value = null
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await getHistoryDetail(questionId)
  } catch (e) {
    detailError.value = { code: e.code, message: e.message }
  } finally {
    detailLoading.value = false
  }
}

function go(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  load()
}

function fmtTime(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 19) : '—' }

onMounted(load)
</script>

<template>
  <div>
    <div class="card">
      <div class="head">
        <h2>历史记录</h2>
        <span class="muted">共 {{ total }} 条，第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" :disabled="loading" @click="load">刷新</button>
      </div>

      <p class="warnbox note">
        <strong>回看说明：</strong>回看只还原 question／answer／answer_evidence 三表内容
        （问题、答案、证据），<strong>不重新渲染当时的图谱路径视图</strong>；
        是否有图谱路径仅以布尔标记提示（`graph_path_available`）。
      </p>

      <p v-if="error" class="err">{{ error.code ? '[' + error.code + '] ' : '' }}{{ error.message }}</p>
      <p v-else-if="loading" class="muted">加载中…</p>
      <div v-else-if="empty" class="empty">未检索到匹配结果（本会话暂无历史记录，非错误）。</div>

      <table v-else class="grid">
        <thead>
          <tr><th>question_id</th><th>提问时间</th><th>答案摘要</th><th>证据数</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.question_id">
            <td class="mono">{{ it.question_id }}</td>
            <td class="mono">{{ fmtTime(it.ask_time) }}</td>
            <td class="summary">{{ it.answer_summary }}</td>
            <td>{{ it.evidence_count }}</td>
            <td><button class="btn" @click="openDetail(it.question_id)">回看</button></td>
          </tr>
        </tbody>
      </table>

      <div class="pager" v-if="!error && !empty">
        <button class="btn" :disabled="page <= 1 || loading" @click="go(page - 1)">上一页</button>
        <button class="btn" :disabled="page >= totalPages || loading" @click="go(page + 1)">下一页</button>
      </div>
    </div>

    <div class="card" v-if="detailLoading || detailError || detail">
      <h2>回看详情</h2>
      <p v-if="detailLoading" class="muted">加载中…</p>
      <p v-else-if="detailError" class="err">
        {{ detailError.code ? '[' + detailError.code + '] ' : '' }}{{ detailError.message }}
      </p>
      <template v-else-if="detail">
        <p class="muted">
          question_id={{ detail.question_id }}｜answer_id={{ detail.answer_id }}｜
          提问时间 {{ fmtTime(detail.ask_time) }}
        </p>

        <h3 class="sub">问题</h3>
        <p class="q">{{ detail.question_text }}</p>

        <h3 class="sub">图谱路径可用性</h3>
        <p class="warnbox">
          本题<strong>{{ detail.graph_path_available ? '曾' : '未' }}使用图谱扩展</strong>
          （graph_path_available = {{ detail.graph_path_available ? 'true' : 'false' }}）。
          按设计，回看<strong>不重新渲染当时的图谱路径视图</strong>；
          如需查看图谱，请到「图谱查看」页按节点自行查询。
        </p>

        <h3 class="sub">答案（按四个固定段头渲染）</h3>
        <AnswerSections :answer-text="detail.answer_text" />

        <h3 class="sub">证据（按四类分组）</h3>
        <EvidenceList :items="detail.evidence" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 12px; }
.head h2 { margin: 0; }
.head .btn { margin-left: auto; }
.note { margin: 10px 0; font-size: 13px; }
.summary {
  max-width: 460px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pager { display: flex; gap: 10px; margin-top: 12px; }
.sub { margin: 14px 0 6px; font-size: 14px; }
.q { margin: 0; font-weight: 600; }
</style>

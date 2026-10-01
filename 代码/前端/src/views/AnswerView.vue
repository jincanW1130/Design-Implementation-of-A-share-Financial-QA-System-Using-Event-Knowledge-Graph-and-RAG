<script setup>
// 代码\前端\src\views\AnswerView.vue —— 屏② 答案与证据（第 9 阶段 T9／F2～F5）
//
// 取数（三个后端接口，各司其职）：
//   * `GET /api/qa/answers/{answer_id}`              → answer_text／graph_path／is_graph_extended／元信息
//   * `GET /api/evidence/{answer_id}`                → 四类分组计数 groups ＋ 证据明细 items
//   * `GET /api/evidence/{answer_id}/graph-path`     → 图谱路径（落库原文解析；不重建）
//   数据截至取自 `/api/config/meta`（App.vue 拉取后 provide）。
//
// 版式按原型屏②：qhead（问题＋口径标签行）→ 四段 `.aSec`（回答／证据来源／知识图谱路径／数据截至与判定区间）。
// 正文 [证据N] 可点，跳到证据卡并高亮。外部链接 target=_blank rel=noopener「查看原文 ↗」。

import { computed, inject, ref, watch } from 'vue'
import { getAnswer, getEvidence, getGraphPath } from '../api.js'
import AnswerSections from '../components/AnswerSections.vue'
import EvidenceList from '../components/EvidenceList.vue'
import GraphPathPanel from '../components/GraphPathPanel.vue'

const props = defineProps({ answerId: { type: [String, Number], required: true } })
const appMeta = inject('appMeta', null)

const loading = ref(false)
const error = ref(null)
const answer = ref(null)
const evidence = ref({ groups: {}, items: [] })
const graphPath = ref({ is_graph_extended: 0, paths: null, display_mode: 'not_used' })
const graphOn = ref(true)
const flashId = ref('')
let flashTimer = null

const cutoff = computed(() => {
  const iso = appMeta && appMeta.dataCutoffTime ? appMeta.dataCutoffTime : ''
  return iso ? iso.slice(0, 10) : '—'
})

const extended = computed(() => Number(graphPath.value.is_graph_extended) === 1)
const evCount = computed(() => (evidence.value.items || []).length)

// 路径统计（全部从落库载荷现算，不补写）
const pathMeta = computed(() => {
  const paths = Array.isArray(graphPath.value.paths) ? graphPath.value.paths : []
  const totalRel = paths.reduce((a, p) => a + ((p.relations || p.edges || []).length), 0)
  const depth = paths.reduce((a, p) => {
    const hops = (p.depth != null) ? Number(p.depth) : ((p.relations || p.edges || []).length || 0)
    return Math.max(a, hops)
  }, 0)
  const nodes = new Set()
  for (const p of paths) {
    if (Array.isArray(p.nodes)) { for (const n of p.nodes) nodes.add(typeof n === 'string' ? n : (n.name || n.node_id || n.id)) }
    else { if (p.start != null) nodes.add(p.start); if (p.end != null) nodes.add(p.end) }
  }
  return { count: paths.length, depth: depth || null, nodesEdges: paths.length ? `${nodes.size} · ${totalRel}` : '—', triples: null }
})

// 判定区间：从第 4 段的「本题相对时间判定区间：」行取；取不到就显示「不适用／未给出」
const windowLabel = computed(() => {
  const t = (answer.value && answer.value.answer_text) || ''
  const m = t.match(/本题相对时间判定区间[：:]\s*(.*)/)
  return m && m[1].trim() ? m[1].trim() : (extended.value ? '随回答落库（见下方叙述）' : '不适用／未给出')
})

const windowCells = computed(() => [
  { label: '数据版本', value: (appMeta && appMeta.datasetVersion) || '—' },
  { label: '数据截止时间', value: (appMeta && appMeta.dataCutoffTime) || '—' },
  { label: '判定区间', value: windowLabel.value },
  { label: '召回证据', value: `${evCount.value} 条` },
  { label: '图谱扩展', value: extended.value ? '已启用 · 深度 1～2 跳' : '未启用' },
  { label: '生成模型', value: (answer.value && answer.value.model_name) || '—' },
  { label: 'Prompt 版本', value: (answer.value && answer.value.prompt_version) || '—' },
  { label: '输出方式', value: '单轮一次生成' },
])

const sessionShort = computed(() => {
  // 会话号：取本地 session 前 8 位（仅展示用途，不含任何库名／凭据）
  try { const sid = window.localStorage.getItem('qa-console-session-id') || ''; return sid ? sid.slice(0, 8) : '本地会话' }
  catch (e) { return '本地会话' }
})

async function load() {
  loading.value = true
  error.value = null
  answer.value = null
  evidence.value = { groups: {}, items: [] }
  graphPath.value = { is_graph_extended: 0, paths: null, display_mode: 'not_used' }
  graphOn.value = true
  try {
    const [ans, ev, gp] = await Promise.all([
      getAnswer(props.answerId),
      getEvidence(props.answerId),
      getGraphPath(props.answerId),
    ])
    answer.value = ans
    evidence.value = { groups: (ev && ev.groups) || {}, items: (ev && ev.items) || [] }
    graphPath.value = gp || graphPath.value
  } catch (e) {
    error.value = { code: e.code, message: e.message }
  } finally {
    loading.value = false
  }
}

watch(() => props.answerId, load, { immediate: true })

function onJump(id) {
  flashId.value = id
  const el = document.getElementById(id)
  if (el) {
    const host = el.closest('.aSec') || el
    if (host.getBoundingClientRect().top < 0) {
      window.scrollTo({ top: window.pageYOffset + host.getBoundingClientRect().top - 110, behavior: 'smooth' })
    }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => { flashId.value = '' }, 2400)
}
</script>

<template>
  <section class="view is-on" id="view-answer" role="tabpanel" aria-labelledby="nav-answer">
    <div class="wrap">
      <div v-if="loading" class="sec"><p class="small">正在读取答案与证据…</p></div>

      <div v-else-if="error" class="sec">
        <div class="graphOff" style="border-color:var(--accent-line)">
          <b>读取失败</b>
          <span v-if="error.code !== undefined && error.code !== null" class="mono small">［code={{ error.code }}］</span>
          <p class="small" style="margin-top:8px">{{ error.message }}</p>
          <p v-if="error.code === 2001" class="small">该 answer_id 在库中不存在，请回提问页重新提问。</p>
        </div>
      </div>

      <template v-else-if="answer">
        <div class="qhead reveal">
          <div class="qhead__l">
            <span class="label">02 / 答案与证据</span>
            <h1 class="h1 qhead__q">{{ answer.question_text }}</h1>
            <div class="tagrow" style="margin-top:16px">
              <span class="tag">会话 {{ sessionShort }}</span>
              <span class="tag">模型 {{ answer.model_name || '—' }}</span>
              <span class="tag">Prompt {{ answer.prompt_version || '—' }}</span>
              <span class="tag">数据集 {{ (appMeta && appMeta.datasetVersion) || '—' }}</span>
              <span class="tag">数据截止 {{ (appMeta && appMeta.dataCutoffTime) || '—' }}</span>
              <span class="tag" :class="extended ? 'tag--red' : 'tag--muted'">图谱扩展 {{ extended ? '已启用' : '未启用' }}</span>
            </div>
          </div>
          <div class="qhead__r">
            <span class="tag tag--red">真实记录 · 取自本系统落库六表</span>
          </div>
        </div>

        <AnswerSections
          :answer-text="answer.answer_text"
          :is-graph-extended="graphPath.is_graph_extended"
          :graph-on="graphOn"
          :evidence-count="evCount"
          :path-meta="pathMeta"
          :window-cells="windowCells"
          @toggle-graph="graphOn = !graphOn"
          @jump="onJump">
          <template #evidence>
            <EvidenceList :items="evidence.items" :groups="evidence.groups" :flash-id="flashId" />
          </template>
          <template #path>
            <GraphPathPanel :is-graph-extended="graphPath.is_graph_extended" :graph-path="graphPath.paths" />
          </template>
        </AnswerSections>

        <p class="small" style="margin:34px 0 0;max-width:100ch">
          answer_id={{ answer.answer_id }} · question_id={{ answer.question_id }} ·
          生成时间 {{ (answer.create_time || '—') }} · 语料口径与实时口径分开显示（实时区只作展示、不进问答证据链）。
        </p>
      </template>
    </div>
  </section>
</template>

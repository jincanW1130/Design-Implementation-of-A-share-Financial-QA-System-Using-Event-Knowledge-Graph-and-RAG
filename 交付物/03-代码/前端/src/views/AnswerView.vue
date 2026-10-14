<script setup>
// 交付物/03-代码\前端\src\views\AnswerView.vue —— 屏② 答案与证据（第 9 阶段 T9／F2～F5）
//
// 取数（三个后端接口，各司其职）：
//   * `GET /api/qa/answers/{answer_id}`              → answer_text／graph_path／is_graph_extended／元信息
//   * `GET /api/evidence/{answer_id}`                → 四类分组计数 groups ＋ 证据明细 items
//   * `GET /api/evidence/{answer_id}/graph-path`     → 图谱路径（落库原文解析；不重建）
//   数据截至取自 `/api/config/meta`（App.vue 拉取后 provide）。
//
// 版式按原型屏②：qhead（问题＋口径标签行）→ 四段 `.aSec`（回答／证据来源／知识图谱路径／数据截至与判定区间）。
// 正文 [证据N] 可点，跳到证据卡并高亮。外部链接 target=_blank rel=noopener「查看原文 ↗」。

import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAnswer, getEvidence, getGraphPath } from '../api.js'
import { mountGraph } from '../lib/graph.js'
import { buildReplayDataset, collectPathNodes, enrichNames, firstCompanyOf } from '../lib/replay.js'
import AnswerSections from '../components/AnswerSections.vue'
import EvidenceList from '../components/EvidenceList.vue'
import GraphPathPanel from '../components/GraphPathPanel.vue'

const router = useRouter()
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

// 2026-10-14：落库路径补名（编号 → 实体名）＋ 本回答路径可视化
const nameMap = ref({})                 // 节点编号 → 实体名（文本链路与画布共用）
const graphHost = ref(null)
const graphAnchor = ref('')             // 路径起点公司实体（跳屏③的锚点）
let replayG = null

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
  // 画布容器只在 loading 结束后才渲染，故补名＋挂载放到 loading 翻 false 之后（nextTick 等容器出现）
  if (!error.value && Number(graphPath.value.is_graph_extended) === 1
      && Array.isArray(graphPath.value.paths) && graphPath.value.paths.length) {
    await nextTick()
    await mountAnswerGraph(graphPath.value)
  } else {
    teardownAnswerGraph()
  }
}

/** 按落库载荷在答案页挂载本回答的图谱路径（补名后渲染；与历史回看同一套渲染器）。 */
async function mountAnswerGraph(payload) {
  teardownAnswerGraph()
  nameMap.value = {}
  graphAnchor.value = firstCompanyOf(payload) || ''
  try {
    // 先补名供文本链路用；buildReplayDataset 内部也会补一次（3 并发、详情接口有 HTTP 缓存，
    // 重复请求浏览器层即返回，不额外打限流窗口）
    nameMap.value = Object.fromEntries(await enrichNames(collectPathNodes(payload)))
    const ds = await buildReplayDataset(payload)
    if (!ds) return
    await nextTick()                       // 等 v-if 的 graphHost 渲染出来
    if (!graphHost.value) return
    const el = document.createElement('div')
    graphHost.value.appendChild(el)
    const first = ds.nodes.slice().sort((a, b) => (b.deg - a.deg) || (a.id < b.id ? -1 : 1))[0]
    // modes:false／不传 provider —— 与回看一致，按载荷渲染、不重新查询图谱拓扑
    replayG = mountGraph(el, {
      ds, modes: false, select: first ? first.id : null, depth: 2,
      tag: '本回答的 answer.graph_path 载荷 · 路径还原',
    })
  } catch (e) {
    // 可视化失败不影响文本四段（证据与文字链路仍完整可读）
    teardownAnswerGraph()
  }
}
function teardownAnswerGraph() {
  if (replayG && replayG.destroy) replayG.destroy()
  replayG = null
  if (graphHost.value) graphHost.value.innerHTML = ''
}

/** 跳到屏③并以本回答路径的起点实体为锚点（屏③读 query.entity，不再固定 600519）。 */
function goGraphPage() {
  if (graphAnchor.value) router.push({ name: 'graph', query: { entity: graphAnchor.value } })
  else router.push({ name: 'graph' })
}

watch(() => props.answerId, load, { immediate: true })
onBeforeUnmount(teardownAnswerGraph)

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
            <GraphPathPanel :is-graph-extended="graphPath.is_graph_extended"
                           :graph-path="graphPath.paths" :name-map="nameMap" />
            <!-- 2026-10-14：本回答图谱路径可视化（按落库载荷还原，节点补实体名，不重新查拓扑） -->
            <div v-if="extended && graphOn && Array.isArray(graphPath.paths) && graphPath.paths.length"
                 class="agraph">
              <div class="agraph__bar">
                <span class="label">本回答的图谱路径 · 按落库载荷还原（节点已补实体名；拓扑不重查）</span>
                <button v-if="graphAnchor" class="chip" type="button"
                        @click="goGraphPage"
                        title="到「事件知识图谱」页以该实体为锚点查看实时邻居与两跳路径">
                  在知识图谱页查看 {{ graphAnchor }} →
                </button>
              </div>
              <div ref="graphHost" class="agraph__host"></div>
            </div>
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

<style scoped>
/* 本回答图谱路径可视化（2026-10-14）：与历史回看表四同一高度口径 */
.agraph { margin-top: 14px; padding-top: 13px; border-top: 1px solid var(--border); }
.agraph__bar { display: flex; align-items: center; justify-content: space-between; gap: 10px;
              flex-wrap: wrap; margin-bottom: 10px; }
.agraph__host { min-height: 420px; }
</style>

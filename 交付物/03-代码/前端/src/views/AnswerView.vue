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

// Neo4j 离线检测：健康检查里 neo4j 块的 ok 为 false 时，图谱路径按落库载荷降级渲染
const neo4jOffline = computed(() => {
  const h = appMeta && appMeta.health
  return !!(h && h.neo4j && h.neo4j.ok === false)
})

// 2026-10-16 第二轮回归：问题文本可长达 500 字，h1 固定大字号会把长问题撑成十几屏。
// 按字数分档降级字号；超长档限高并可纵向滚动，完整问题仍可查看（title 也给全文）。
const qClass = computed(() => {
  const len = (answer.value && answer.value.question_text || '').trim().length
  if (len > 140) return 'qhead__q--xl'
  if (len > 60) return 'qhead__q--lg'
  if (len > 30) return 'qhead__q--md'
  return ''
})

// 路径深度上限（跳）：**全页唯一来源**＝落库载荷现算值。第 3 段的「路径深度上限」卡片、
// 概览里的「图谱扩展」格、第 3 段说明文字三处共用此值（2026-10-17）。
// 实测 answer 1 的载荷：4 条路径各 1 条关系边、每条 path.depth=1 → 本值为 1 跳；
// 原概览与第 3 段说明里写死的「1～2 跳」是应用层的配置上限，不是这条回答的实际记录，已移除。
const pathDepthNum = computed(() => {
  const paths = Array.isArray(graphPath.value.paths) ? graphPath.value.paths : []
  const depth = paths.reduce((a, p) => {
    const hops = (p.depth != null) ? Number(p.depth) : ((p.relations || p.edges || []).length || 0)
    return Math.max(a, hops)
  }, 0)
  return depth > 0 ? depth : null
})

// 路径统计（全部从落库载荷现算，不补写）；depth 复用上面同一份现算值，保证同屏读数唯一
const pathMeta = computed(() => {
  const paths = Array.isArray(graphPath.value.paths) ? graphPath.value.paths : []
  const totalRel = paths.reduce((a, p) => a + ((p.relations || p.edges || []).length), 0)
  const nodes = new Set()
  for (const p of paths) {
    if (Array.isArray(p.nodes)) { for (const n of p.nodes) nodes.add(typeof n === 'string' ? n : (n.name || n.node_id || n.id)) }
    else { if (p.start != null) nodes.add(p.start); if (p.end != null) nodes.add(p.end) }
  }
  return { count: paths.length, depth: pathDepthNum.value, nodesEdges: paths.length ? `${nodes.size} · ${totalRel}` : '—', triples: null }
})

// 判定区间：只读正文里的实际说法（2026-10-17 修，缺陷 3）。
// 原实现匹配不到「本题相对时间判定区间：」时按 extended 回落成「随回答落库（见下方叙述）」，
// 与同一屏第 4 段正文可能写着的「本题不含相对时间表述，无判定区间。」互相矛盾（实测 43 条里
// 只有 14 条含该行，answer 45 的正文即写着「无判定区间。」）。现在三级取数：匹配值 → 正文明确
// 的否定说法 → 显式的「记录未给出」占位，不再出现「见下方叙述」这种指代。
const windowLabel = computed(() => {
  const t = (answer.value && answer.value.answer_text) || ''
  const m = t.match(/本题相对时间判定区间[：:]\s*(.*)/)
  if (m && m[1].trim()) return m[1].trim()
  const neg = t.match(/[^\n。]*无(?:单独的)?判定区间[^\n。]*。/)
  if (neg) return neg[0].trim()
  return '—（记录未给出单独的判定区间行）'
})

// 「图谱扩展」一格的读数：与第 3 段同一唯一来源＝落库载荷现算值（pathMeta）。
// 2026-10-17 修（缺陷 1）：原写死「已启用 · 深度 1～2 跳」——"1～2" 是配置上限（应用层按 2 跳取路径），
// 不是这条回答的实际记录；实测 GET /api/qa/answers/1 的图谱路径载荷每条 depth 都是 1，
// 同屏第 3 段据同一载荷现算的「路径深度上限」也是 1 跳，两处必须一致。取不到就写「未给出」，不猜。
const graphExtLabel = computed(() => {
  if (!extended.value) return '未启用'
  const n = pathDepthNum.value
  if (n != null) return `已启用 · 路径深度上限 ${n} 跳`
  return pathMeta.value.count ? '已启用 · 深度未给出' : '已启用'
})

// 第 3 段说明文字里的深度读数（逐字机检口径：原「深度为 1～2 跳」必须消失）。取不到写「未给出」。
const pathDepthText = computed(() => (pathDepthNum.value != null ? pathDepthNum.value + ' 跳' : '未给出'))

// 复制引用信息用的「判定区间」读数：answer_text 正则取数 → 正文明确说法 → 未给出（不跟随 extended 回落）
const expectedRangeText = computed(() => {
  const t = (answer.value && answer.value.answer_text) || ''
  const m = t.match(/本题相对时间判定区间[：:]\s*(.*)/)
  if (m && m[1].trim()) return m[1].trim()
  const neg = t.match(/[^\n。]*无(?:单独的)?判定区间[^\n。]*。/)
  if (neg) return neg[0].trim()
  return '未给出'
})

const windowCells = computed(() => [
  { label: '数据版本', value: (appMeta && appMeta.datasetVersion) || '—' },
  { label: '数据截止时间', value: (appMeta && appMeta.dataCutoffTime) || '—' },
  { label: '判定区间', value: windowLabel.value },
  { label: '召回证据', value: `${evCount.value} 条` },
  { label: '图谱扩展', value: graphExtLabel.value },
  { label: '生成模型', value: (answer.value && answer.value.model_name) || '—' },
  { label: 'Prompt 版本', value: (answer.value && answer.value.prompt_version) || '—' },
  { label: '输出方式', value: '单轮一次生成' },
])

// --------------------------------------------------------------------------
// 复制／引用（2026-10-17 新增，缺陷 4）：研究生要把一条答案引用进论文／表格时的最小可用入口。
// 三个动作全部**只读**：只读当前已拿到的接口数据，不改动任何数据、不写库、不新增依赖。
// --------------------------------------------------------------------------
const NOT_GIVEN = '记录未给出'
const COPY_FEEDBACK_MS = 2000
const copiedKey = ref('')          // 当前显示「已复制」的按钮
const copyFailedKey = ref('')      // 当前显示「复制失败」的按钮
let copyTimer = null

/** 反馈统一走一个 2 秒定时器：新点击重置上一次的计时，文案 2 秒后还原。 */
function flashCopy(key, ok) {
  copiedKey.value = ok ? key : ''
  copyFailedKey.value = ok ? '' : key
  window.clearTimeout(copyTimer)
  copyTimer = window.setTimeout(() => { copiedKey.value = ''; copyFailedKey.value = '' }, COPY_FEEDBACK_MS)
}

/** 字段缺值时的统一占位：按缺陷 4 的口径写「记录未给出」，不补写、不省略列。 */
function cellOf(v) {
  if (v === undefined || v === null) return NOT_GIVEN
  const s = String(v).trim()
  return s === '' ? NOT_GIVEN : s
}

/** 日期归一（发布日期／生成时间）：截到日期或「日期 时:分:秒」，切不动就原样返回。 */
function dateStr(v) {
  const s = cellOf(v)
  if (s === NOT_GIVEN) return NOT_GIVEN
  return s.length >= 19 ? s.slice(0, 10) + ' ' + s.slice(11, 19) : s.slice(0, 10)
}

/**
 * 复制文本：优先 navigator.clipboard.writeText；不可用（非安全上下文／未授权／旧浏览器）时
 * 降级为临时 textarea ＋ document.execCommand('copy')。两条路径都失败就返回 false —— 由调用方
 * 明确提示「复制失败」，绝不静默无反应。
 */
async function copyText(text) {
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (e) { /* 落到下面的降级路径 */ }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', 'readonly')
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return !!ok
  } catch (e) {
    return false
  }
}

/** 复制答案全文：**后端原样返回的 answer.answer_text**（不复制页面可见文本——段二／段三被插槽替换过）。 */
async function copyFullAnswer() {
  const text = (answer.value && answer.value.answer_text) || ''
  const ok = await copyText(text)
  flashCopy('full', ok)
}

/**
 * 复制证据清单：制表符分隔（TSV，可直接贴进 Excel／Word 表格）。
 * 列序＝证据号／类别／标题／来源网站／发布日期／doc_id／chunk_id／原文链接（首行表头）；
 * 逐行一条证据，缺字段写「记录未给出」，不补写。
 */
async function copyEvidenceList() {
  const items = (evidence.value && evidence.value.items) || []
  const lines = [['证据号', '类别', '标题', '来源网站', '发布日期', 'doc_id', 'chunk_id', '原文链接'].join('\t')]
  for (const it of items) {
    lines.push([
      it.rank != null ? '证据' + it.rank : NOT_GIVEN,
      cellOf(it.evidence_type),
      cellOf(it.title),
      cellOf(it.source),
      dateStr(it.publish_time),
      cellOf(it.doc_id),
      cellOf(it.chunk_id),
      cellOf(it.url),
    ].join('\t'))
  }
  const ok = await copyText(lines.join('\n'))
  flashCopy('evidence', ok)
}

/** 复制引用信息：一段可读纯文本，字段全部取真实接口值，缺值写「记录未给出」。 */
async function copyCitationInfo() {
  const a = answer.value || {}
  const paths = Array.isArray(graphPath.value.paths) ? graphPath.value.paths : []
  const facts = [
    '问题原文：' + cellOf(a.question_text),
    'answer_id：' + cellOf(a.answer_id),
    '生成时间：' + dateStr(a.create_time),
    '模型 / Prompt 版本：' + cellOf(a.model_name) + ' / ' + cellOf(a.prompt_version),
    '数据版本：' + cellOf(appMeta && appMeta.datasetVersion),
    '数据截止：' + cellOf(appMeta && appMeta.dataCutoffTime),
    '召回证据：' + evCount.value + ' 条',
    '图谱扩展：' + (extended.value
      ? `已启用 · 路径 ${paths.length} 条 · hop 数上限 ${pathDepthNum.value != null ? pathDepthNum.value + ' 跳' : '未给出'}`
      : '未启用'),
    '判定区间：' + expectedRangeText.value,
  ]
  const text = [
    '【引用信息】牛势问答 · A 股事件知识图谱与 RAG',
    ...facts,
    '说明：以上字段均取自本系统落库记录与 /api 接口返回，未做补写或换算。',
  ].join('\n')
  const ok = await copyText(text)
  flashCopy('citation', ok)
}

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
            <h1 class="h1 qhead__q" :class="qClass" :title="answer.question_text">{{ answer.question_text }}</h1>
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
            <!-- 2026-10-17 新增（缺陷 4）：三个**只读**的复制入口，给要逐条核对并引用进论文的用户。
                 三个动作只读当前已拿到的接口数据；失败时明确显示「复制失败」，不静默。 -->
            <div class="copyrow">
              <button class="btn btn--ghost btn--sm" type="button" title="复制后端原样返回的 answer_text 全文（不是页面可见文本）"
                      @click="copyFullAnswer">
                {{ copiedKey === 'full' ? '已复制答案全文' : (copyFailedKey === 'full' ? '复制失败' : '复制答案全文') }}
              </button>
              <button class="btn btn--ghost btn--sm" type="button" title="复制证据清单（TSV：证据号／类别／标题／来源网站／发布日期／doc_id／chunk_id／原文链接），可直接贴进 Excel／Word 表格"
                      @click="copyEvidenceList">
                {{ copiedKey === 'evidence' ? '已复制证据清单' : (copyFailedKey === 'evidence' ? '复制失败' : '复制证据清单') }}
              </button>
              <button class="btn btn--ghost btn--sm" type="button" title="复制引用信息（问题／answer_id／生成时间／模型与 Prompt 版本／数据版本与截止／证据条数／图谱路径读数）"
                      @click="copyCitationInfo">
                {{ copiedKey === 'citation' ? '已复制引用信息' : (copyFailedKey === 'citation' ? '复制失败' : '复制引用信息') }}
              </button>
            </div>
          </div>
        </div>

        <AnswerSections
          :answer-text="answer.answer_text"
          :is-graph-extended="graphPath.is_graph_extended"
          :graph-on="graphOn"
          :evidence-count="evCount"
          :path-meta="pathMeta"
          :path-depth-text="pathDepthText"
          :window-cells="windowCells"
          @toggle-graph="graphOn = !graphOn"
          @jump="onJump">
          <template #evidence>
            <EvidenceList :items="evidence.items" :groups="evidence.groups" :flash-id="flashId" />
          </template>
          <template #path>
            <div v-if="neo4jOffline && extended" class="notice notice--calm" style="margin-bottom:10px">
              <svg aria-hidden="true"><use href="#i-alert"></use></svg>
              <span>图谱后端（Neo4j）当前离线，下方路径按落库载荷降级还原，节点名称可能显示为编号；恢复服务后可在知识图谱页查看实时两跳路径。</span>
            </div>
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
/* 复制按钮组（2026-10-17）：qhead__r 已是 flex＋wrap 容器，这里只让它单独占满一行、靠右排 */
.copyrow { flex: 1 1 100%; display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
</style>

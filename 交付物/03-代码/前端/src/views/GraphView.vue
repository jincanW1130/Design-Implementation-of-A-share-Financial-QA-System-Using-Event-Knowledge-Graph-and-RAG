<script setup>
// 交付物/03-代码\前端\src\views\GraphView.vue —— 屏③ 事件知识图谱（第 9 阶段 T9）
//
// 设计语言唯一真源＝原型 index.html 的屏③：本视图只负责**取数与接线**，
// 画布渲染／去遮挡／标签规划／命中测试／属性面板／实体证据区全部由
// `../lib/graph.js` 的 mountGraph（逐字移植自原型）完成。
//
// 两套数据集（都由真实接口返回构造，页面下方分段控件切换）：
//   * 「1 跳邻居」GET /api/graph/entities/{id}/neighbors?with_evidence=1
//   * 「2 跳路径」GET /api/graph/paths?from_node={id}&relation=PARTICIPATES_IN&hop=2&with_evidence=1
//     （按后端约束：无 to_node 时 hop=2 必须带 relation，否则 400 / code 1002）
//
// 属性面板两块（实体档案 / 本视图关系）＋ 实体证据区四块，均由 mountGraph 内的
// provider 异步拉取真实接口：entity→getEntity、evidence→getEntityEvidence、event→getEventDetail；
// 「查看上下文」的正文由 fetchChunk→getChunk 拉取。本视图不臆造任何字段。
//
// 时间轴：只在**记录里真实出现过**的月份上取值——文档节点取边的 evidence.publish_time、
// 事件节点取 GET /api/graph/events/{id} 的 event_time（为空则不落到轴上，与原型一致）。
//
// 2026-10-17：修本页搜索区三处实测缺陷（搜不到时旧锚点仍留在画布／属性面板上、点选候选后
// 「我搜的是什么」没有任何留痕、检索失败被当成「（无结果）」），另把候选区计数改成如实回报
// 接口返回的 total 与已显示数、候选 chip 补上 stock_code／node_id 作可区分标识。改动只在本文件内。

import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getChunk, getEntity, getEntityEvidence, getEventDetail, getNeighbors, getPaths, listEntities,
} from '../api.js'
import { buildDataset, mountGraph, typeOfLabel, TKEYS, TYPE } from '../lib/graph.js'

const appMeta = inject('appMeta', null)
const route = useRoute()
const router = useRouter()

// 2026-10-14：锚点支持由答案页带入（?entity=600887）；无参数时保持默认 600519。
const DEFAULT_ANCHOR = '600519'
const anchor = ref(String(route.query.entity || DEFAULT_ANCHOR))
const loading = ref(false)
const error = ref('')
const note = ref('')

// 2026-10-16 P3-4：错误提示不再暴露服务器内部路径，并区分「图数据库（Neo4j）离线」与「后端服务不可达」两种情形。
const graphOffline = computed(() => /\b3001\b/.test(error.value) || /图谱服务不可用|Neo4j|图数据库|7687/i.test(error.value))
const graphHint = computed(() => (graphOffline.value
  ? '图谱服务（Neo4j 图数据库）当前不可用，通常是图数据库未启动或连接超时。问答与证据功能不受影响，仍可在「答案与证据」页查看已落库的图谱路径；图数据库恢复后刷新本页即可。'
  : '暂时无法连接后端服务，请确认服务已正常运行后重试，或更换一个锚点实体。'))

const graphWrap = ref(null)
const tlSvg = ref(null)
const tlRange = ref('')
const months = ref([])

// —— 搜索区状态（2026-10-17 修屏③三处实测缺陷）——
// 实测事实：① 锚点是 600519 时搜一个不存在的关键词，接口返回 {total:0,items:[]}（HTTP 200），
// 但旧代码只写 results，画布与属性面板仍完整显示 600519 的 11 节点 11 边，用户会以为
// 「搜到的就是这个」并据此去引用错标的（600519）的数据；② useAnchor 里 kw.value='' 让「我搜的是什么」
// 页面内再无留痕（「当前锚点」显示的是 node_id，不是用户输入的词）；③ doSearch 的 catch 把
// results 清空，于是「后端限流 429／网络失败」被显示成「（无结果）」，等于把「被限流」误报成
// 「库里没有这家公司」。
const SEARCH_PAGE = 8         // 每次请求的候选条数；后端真正认的参数名是 page_size（实测 limit 会被忽略）
const SEARCH_PAGE_MAX = 200   // 后端 api\graph.py 的 PAGE_SIZE_MAX，超出会返回 1002
const kw = ref('')
const results = ref([])
const searching = ref(false)
const pageSize = ref(SEARCH_PAGE)
const searchTotal = ref(null)      // 接口实返的 total：候选计数一律用它，不拿 items.length 冒充总数
const lastSearchQ = ref(String(route.query.q || '').trim())  // 缺陷2：搜索词留痕（URL 的 q ＋ 常显文案）
const searchErr = ref('')          // 缺陷3：检索失败的实返 code＋message，与「真的搜不到」分开呈现
const emptyQ = ref('')             // 缺陷1：把画布清空的那次检索词，必须在空态文案里回显给用户
const emptyTotal = ref(null)
const cleared = ref(false)         // 缺陷1：画布已被清空（空结果态）；翻回 false 只在 renderGraph 真重建画布时

// 候选区计数：出现的每个数字都能指回某个接口字段——总数用 d.total，已显示数用本次真实拿到的 items
const resultSummary = computed(() => {
  const n = results.value.length
  if (!n) return ''
  const t = searchTotal.value
  if (t === null || t === undefined) return '本次返回 ' + n + ' 个候选（接口未返回 total，不推算总数）'
  return t > n ? '共 ' + t + ' 个匹配，已显示前 ' + n + ' 个' : '共 ' + t + ' 个匹配，已全部显示'
})
const canShowMore = computed(() => results.value.length > 0
  && typeof searchTotal.value === 'number' && searchTotal.value > results.value.length
  && pageSize.value + SEARCH_PAGE <= SEARCH_PAGE_MAX)
// 缺陷1 的空态文案：把用户输入的词原样回显，并给出可操作的下一步
const emptyMessage = computed(() => '未检索到与「' + emptyQ.value + '」匹配的实体（接口实返 total = '
  + (emptyTotal.value === null ? '—（空）' : emptyTotal.value) + '、items = 0，是 HTTP 200 的空结果）：画布已清空，'
  + '上一次锚点的节点、边、路径列表与属性面板的选择态一并清除，不会再把旧图当成「这次搜到的结果」。'
  + '可改用 6 位股票代码（如 600519）或更短的公司简称重试。')
// 缺陷3 的提示：检索失败不动画布，这里如实说明画布上还留着什么
const searchErrHint = computed(() => (anchor.value
  ? '画布保持上一次成功加载的锚点「' + anchor.value + '」不变（检索失败不清空画布）。'
  : '画布保持上一步的空状态（当前没有已加载的锚点）。')
  + '错误码与提示都原样来自接口返回，未改写；稍后重试即可，无需刷新页面。')

let G = null
const DOC_TIME = {}                 // 文档节点 id → 'YYYY-MM-DD'（取自边的 evidence.publish_time）
const EVT_TIME = {}                 // 事件节点 id → 'YYYY-MM-DD' 或 ''（取自事件详情接口）
const TL = { i0: 0, i1: 0, W: 1160, PAD: 34, step: 0, X: null }
let tlDrag = null

function recDoc(ev) {
  if (ev && ev.doc_id !== undefined && ev.doc_id !== null && ev.publish_time) {
    DOC_TIME[String(ev.doc_id)] = String(ev.publish_time).slice(0, 10)
  }
}
function dedupeById(list) {
  const m = new Map()
  list.forEach((n) => { if (n && n.node_id !== undefined && !m.has(String(n.node_id))) m.set(String(n.node_id), n) })
  return [...m.values()]
}
function toNodes(arr) {
  return arr.map((n) => ({
    id: String(n.node_id),
    eid: String(n.node_id),
    type: typeOfLabel(n.label),
    name: n.name || String(n.node_id),
    code: n.stock_code || '',
    sub: '',
    time: null,
  }))
}
function edgeObj(e, f, t, src) {
  const noev = e.relation === 'EVIDENCED_BY' || !!e.note
  return {
    f: String(f), t: String(t), rel: e.relation, role: e.role || '',
    conf: (e.confidence === undefined ? null : e.confidence),
    sdoc: (e.source_doc_id === undefined ? null : e.source_doc_id),
    schunk: (e.source_chunk_id === undefined ? null : e.source_chunk_id),
    noev: noev ? 1 : 0, src,
  }
}

function dsFromNeighbors(d, anchorId) {
  const list = dedupeById([d.node].concat(d.nodes || []).filter(Boolean))
  const nodes = toNodes(list)
  const edges = (d.edges || []).map((e) => {
    const nb = String(e.neighbor)
    const f = e.direction === 'in' ? nb : String(anchorId)
    const t = e.direction === 'in' ? String(anchorId) : nb
    if (e.evidence) recDoc(e.evidence)
    return edgeObj(e, f, t, 'neighbors')
  })
  return buildDataset('neighbors', nodes, edges)
}
function dsFromPaths(d) {
  const map = new Map()
  const edges = []
  for (const p of (d.paths || [])) {
    for (const n of (p.nodes || [])) if (n && n.node_id !== undefined && !map.has(String(n.node_id))) map.set(String(n.node_id), n)
    const ids = p.node_ids || (p.nodes || []).map((x) => x.node_id)
    ;(p.edges || []).forEach((e, i) => {
      let f = ids[i], t = ids[i + 1]
      if (f === undefined || f === null || t === undefined || t === null) return
      if (e.direction === 'in') { const tmp = f; f = t; t = tmp }
      if (e.evidence) recDoc(e.evidence)
      edges.push(edgeObj(e, f, t, 'paths'))
    })
  }
  const nodes = toNodes([...map.values()])
  if (!nodes.length) return null
  return buildDataset('paths', nodes, edges)
}

// 事件时间只为**时间轴落点**服务：限量（≤10 个）小并发拉取，避免把后端 60 次/分钟的限流窗口打满。
async function prefetchEvents(dss) {
  const ids = new Set()
  dss.forEach((ds) => { if (ds) ds.nodes.forEach((n) => { if (n.type === 'event' && !(n.id in EVT_TIME)) ids.add(n.id) }) })
  const list = [...ids].slice(0, 10)
  const CONC = 3
  for (let i = 0; i < list.length; i += CONC) {
    await Promise.all(list.slice(i, i + CONC).map(async (id) => {
      try { const d = await getEventDetail(id); EVT_TIME[id] = String((d && d.event && d.event.event_time) || '').slice(0, 10) }
      catch (e) { EVT_TIME[id] = '' }
    }))
  }
}
function timeForNode(n) {
  if (n.type === 'event') return EVT_TIME[n.id] || null
  if (n.type === 'doc') return DOC_TIME[n.id] || null
  return null
}
function applyTimes(ds) {
  if (!ds) return
  ds.nodes.forEach((n) => {
    const t = timeForNode(n)
    n.time = t || null
    n.ti = t ? months.value.indexOf(t.slice(0, 7)) : null
  })
}
function computeMonths(dss) {
  const set = new Set()
  dss.forEach((ds) => { if (ds) ds.nodes.forEach((n) => { const t = timeForNode(n); if (t) set.add(t.slice(0, 7)) }) })
  return [...set].sort()
}

async function load(anchorId) {
  loading.value = true
  error.value = ''
  try {
    const [nb, pa] = await Promise.all([
      getNeighbors(anchorId, { with_evidence: 1 }),
      getPaths({ from_node: anchorId, relation: 'PARTICIPATES_IN', hop: 2, with_evidence: 1 }),
    ])
    const dsA = dsFromNeighbors(nb, anchorId)
    const dsB = dsFromPaths(pa)
    await prefetchEvents([dsA, dsB])
    months.value = computeMonths([dsA, dsB])
    TL.i0 = 0
    TL.i1 = Math.max(0, months.value.length - 1)
    renderGraph(anchorId, dsA, dsB)
  } catch (e) {
    error.value = `${e && e.code ? '[' + e.code + '] ' : ''}${(e && e.message) || e}`
  } finally {
    loading.value = false
  }
}

function renderGraph(anchorId, dsA, dsB) {
  if (!graphWrap.value) return
  if (G && G.destroy) G.destroy()
  graphWrap.value.innerHTML = ''
  const el = document.createElement('div')
  graphWrap.value.appendChild(el)
  // 缺陷1 配套：画布由真实数据集重建成功，才解除「空结果态」（清空与恢复只在画布真正重建时翻转）
  cleared.value = false
  emptyQ.value = ''
  emptyTotal.value = null

  const modes = (dsB && dsB.nodes.length) ? [
    { key: 'neighbors', label: '1 跳邻居', ds: dsA, select: anchorId,
      note: '中心实体 ＋ 一跳邻居 ＋ 逐条关系边（GET /api/graph/entities/{id}/neighbors?with_evidence=1）' },
    { key: 'paths', label: '2 跳路径', ds: dsB, select: anchorId,
      note: '从该实体出发的 2 跳路径（GET /api/graph/paths?from_node=…&relation=PARTICIPATES_IN&hop=2&with_evidence=1）' },
  ] : null
  const primary = modes ? modes[0].ds : dsA

  G = mountGraph(el, {
    ds: primary,
    modes,
    select: anchorId,
    tag: '真实接口返回 · 载荷不含演示数据',
    provider: {
      entity: getEntity,
      evidence: (id, depth) => getEntityEvidence(id, depth),
      event: getEventDetail,
    },
    fetchChunk: getChunk,
    months: months.value.length >= 2 ? months.value : null,
    modeName: modes ? modes[0].label : '1 跳邻居',
    depth: 2,
    onReset: () => setRange(0, months.value.length - 1),
    onDataset: (DS) => { applyTimes(DS); paintTimeline(); setRange(TL.i0, TL.i1) },
    jumpEvidence: (chunk) => {
      note.value = '已按 source_chunk_id ' + (chunk || '（无）') + ' 触发「跳到对应证据」：'
        + '本图谱屏不承载某一条回答的证据清单，请在屏②「答案与证据」里按同一 source_chunk_id 定位该证据卡（图谱屏的证据区只展示所选实体的证据，两者口径不同）。'
    },
  })
  applyTimes(G.ds())
  paintTimeline()
  setRange(0, months.value.length - 1)
}

function paintTimeline() {
  const svg = tlSvg.value
  if (!svg) return
  if (!G || months.value.length < 2) { svg.innerHTML = ''; return }
  const PAD = 34, W = 1160, step = (W - PAD * 2) / (months.value.length - 1)
  const X = (i) => PAD + i * step
  TL.W = W; TL.PAD = PAD; TL.step = step; TL.X = X
  const DS = G.ds()
  let out = ''
  out += '<line class="tl__base" x1="' + PAD + '" y1="66" x2="' + (W - PAD) + '" y2="66"/>'
  for (let i = 0; i < months.value.length; i++) {
    const major = months.value[i].slice(5) === '01'
    out += '<line class="tl__tick" x1="' + X(i).toFixed(1) + '" y1="' + (major ? 58 : 62) + '" x2="' + X(i).toFixed(1) + '" y2="72"/>'
    if (months.value.length <= 6 || i % 3 === 0 || major || i === months.value.length - 1) {
      out += '<text class="tl__tlab" x="' + X(i).toFixed(1) + '" y="90" text-anchor="middle">' + months.value[i] + '</text>'
    }
  }
  DS.nodes.forEach((n) => {
    if (n.ti === null || n.ti === undefined) return
    const ly = 44 - (TKEYS.indexOf(n.type) % 6) * 7
    const inR = n.ti >= TL.i0 && n.ti <= TL.i1
    out += '<circle class="tl__dot' + (inR ? '' : ' out') + '" data-dot="' + n.id + '" cx="' + X(n.ti).toFixed(1)
      + '" cy="' + ly + '" r="3.6" fill="' + TYPE[n.type].c + '" fill-opacity=".85"/>'
  })
  const x0 = X(TL.i0), x1 = X(TL.i1)
  out += '<rect class="tl__bar" x="' + x0.toFixed(1) + '" y="24" width="' + Math.max(x1 - x0, 1).toFixed(1) + '" height="66" rx="3"/>'
  out += '<rect class="tl__handle" data-h="0" x="' + (x0 - 3).toFixed(1) + '" y="24" width="6" height="66" rx="3"/>'
  out += '<rect class="tl__handle" data-h="1" x="' + (x1 - 3).toFixed(1) + '" y="24" width="6" height="66" rx="3"/>'
  svg.innerHTML = '<rect class="tl__track" x="0" y="0" width="' + W + '" height="128" fill="transparent"/>' + out
}

function setRange(a, b) {
  const n = months.value.length
  if (n < 2) {
    tlRange.value = '本次数据集未携带可用于时间轴的 event_time／publish_time，时间轴无刻度'
    paintTimeline()
    if (G) G.setTimeRange(0, 0)
    return
  }
  TL.i0 = Math.max(0, Math.min(a, n - 1))
  TL.i1 = Math.max(TL.i0, Math.min(b, n - 1))
  tlRange.value = months.value[TL.i0] + ' → ' + months.value[TL.i1] + '（共 ' + (TL.i1 - TL.i0 + 1) + ' 个月）'
  paintTimeline()
  if (G) G.setTimeRange(TL.i0, TL.i1)
}

function tlIdx(clientX) {
  const svg = tlSvg.value
  const r = svg.getBoundingClientRect()
  const vx = (clientX - r.left) / r.width * TL.W
  const i = Math.round((vx - TL.PAD) / TL.step)
  return Math.max(0, Math.min(months.value.length - 1, i))
}
function tlDown(e) {
  if (months.value.length < 2) return
  const h = e.target.getAttribute && e.target.getAttribute('data-h')
  const i = tlIdx(e.clientX)
  if (h === '0') { tlDrag = { h: 0 }; setRange(i, TL.i1) }
  else if (h === '1') { tlDrag = { h: 1 }; setRange(TL.i0, i) }
  else { tlDrag = { h: null, a: i }; setRange(i, i) }
  if (tlSvg.value.setPointerCapture) tlSvg.value.setPointerCapture(e.pointerId)
  e.preventDefault()
}
function tlMove(e) {
  if (!tlDrag) return
  const i = tlIdx(e.clientX)
  if (tlDrag.h === 0) setRange(Math.min(i, TL.i1), TL.i1)
  else if (tlDrag.h === 1) setRange(TL.i0, Math.max(i, TL.i0))
  else setRange(Math.min(tlDrag.a, i), Math.max(tlDrag.a, i))
}
function tlUp(e) {
  tlDrag = null
  const svg = tlSvg.value
  if (svg && svg.releasePointerCapture && e.pointerId !== undefined && svg.hasPointerCapture && svg.hasPointerCapture(e.pointerId)) {
    svg.releasePointerCapture(e.pointerId)
  }
}

// ---------------------------------------------------------------------------
// 搜索区：检索候选 → 点选锚点（2026-10-17 修缺陷 1／2／3／4，逐处注释见函数内）
// ---------------------------------------------------------------------------
/**
 * 检索实体候选。
 * @param {string} [term] 检索词；省略时取输入框内容（「显示更多」用上一次的词扩容重查）
 * @param {number} [size] 本次请求的 page_size（后端参数名，1～PAGE_SIZE_MAX）
 */
async function doSearch(term, size) {
  const k = String(term === undefined || term === null ? kw.value : term).trim()
  if (!k) return
  const ps = Math.min(Math.max(Number(size) || SEARCH_PAGE, 1), SEARCH_PAGE_MAX)
  searching.value = true
  searchErr.value = ''
  results.value = []
  searchTotal.value = null
  // 缺陷2：先把用户搜的词记下来——检索失败时也要能看出「我搜的是什么」
  lastSearchQ.value = k
  try {
    // 缺陷4：后端实测只认 page／page_size（原来传的 limit: 8 会被直接忽略），所以这里按 page_size 取候选，
    // 候选区再按实返 total 说明「总共多少个、这次显示了几个」，不再让用户以为「只有 8 个相关实体」。
    const d = await listEntities({ keyword: k, page: 1, page_size: ps })
    const items = (d && d.items) || []
    results.value = items
    searchTotal.value = (d && typeof d.total === 'number') ? d.total : null
    pageSize.value = ps
    if (!items.length) clearCanvasForEmpty(k, searchTotal.value)
  } catch (e) {
    // 缺陷3：后端限流（60 次/60 秒/来源 IP，HTTP 429 ＋ code 1004）与网络层失败都落到这里。
    // 旧代码在这里把 results 清空 → 页面显示「（无结果）」，等于把「被限流」误报成「库里没有这家公司」。
    // 现在：① 画布保持原图不动（检索失败 ≠ 没有这家公司）；② 把接口实返的 code 与 message 原样贴出——
    // api.js 已把「，请约 N 秒后重试」拼进 message，这里不丢弃、不改写。
    const code = (e && e.code !== undefined && e.code !== null) ? e.code : 0
    searchErr.value = '错误码 ' + code + ' · ' + ((e && e.message) || String(e))
  } finally {
    searching.value = false
  }
}

/**
 * 缺陷1：检索到 0 条时清掉旧锚点的全部呈现。
 * 实测：锚点 600519（贵州茅台）时搜「zzzz不存在的实体xyz」，旧代码下画布仍是该锚点的 11 个节点
 * 与 11 条边、属性面板仍写着「已选中 · 贵州茅台 600519」，属事实性误导。这里走与 renderGraph()
 * 相同的销毁路径（G.destroy() ＋ 清空 graphWrap），但**不重建**，让画布真的空下来。
 */
function clearCanvasForEmpty(word, total) {
  cleared.value = true
  emptyQ.value = word
  emptyTotal.value = (typeof total === 'number') ? total : null
  anchor.value = ''                       // 「当前锚点」不能再指向上一家
  if (G && G.destroy) G.destroy()         // G 在 document 上挂了 Esc 监听，一并卸掉
  G = null
  if (graphWrap.value) graphWrap.value.innerHTML = ''   // 节点／边／属性面板／证据区都在这个容器里，一次清干净
  months.value = []                       // 时间轴的月份与落点都由上一个锚点算出来，必须一起清
  TL.i0 = 0
  TL.i1 = 0
  tlRange.value = '画布已清空（本次检索 total=' + (emptyTotal.value === null ? '—（空）' : emptyTotal.value) + '），时间轴无可用数据集'
  paintTimeline()                         // G 已为 null → 直接清空时间轴 svg，不留旧刻度与落点
  note.value = ''
  // URL 也要如实：画布上已经没有这个锚点了，刷新／分享都不该把它带回来；同时把检索词写进 q 留痕。
  // 这次 replace 会让 route.query.entity 变成 undefined，而下方 watcher 只对「非空且与 anchor 不同」的
  // entity 反应，所以不会触发重复加载。
  const next = { ...route.query, q: word }
  delete next.entity
  router.replace({ query: next }).catch(() => {})
}

/** 缺陷4 配套：候选区扩容重查（用**上一次检索的词**，避免用户改了输入框却换了一批候选）。 */
function showMore() {
  if (searching.value) return
  const next = pageSize.value + SEARCH_PAGE
  if (next > SEARCH_PAGE_MAX) return
  doSearch(lastSearchQ.value, next)
}

function useAnchor(id, term) {
  results.value = []
  searchErr.value = ''
  note.value = ''
  // 缺陷2：旧代码在这里写 kw.value = ''，点选候选后输入框被清空，而「当前锚点」显示的是 node_id（如 600519），
  // 页面再无任何「我搜的是什么」的留痕。现在：① 输入框保留原词（不写 kw.value = ''）；② 搜索区常显
  // 「上次搜索」；③ 把 entity ＋ q 写进 URL query，刷新／分享都能回看是搜哪个词得到的这张图。
  // 注意顺序：先把 anchor 落好再改 URL —— watch(route.query.entity) 里 «id !== anchor.value» 不成立，
  // 所以这次 replace 不会触发第二次 load（浏览器实测：点选候选后 neighbors 只请求 1 次）。
  if (term !== undefined && term !== null && String(term).trim()) lastSearchQ.value = String(term).trim()
  anchor.value = id
  const next = { ...route.query, entity: id }
  if (lastSearchQ.value) next.q = lastSearchQ.value
  else delete next.q
  router.replace({ query: next }).catch(() => {})
  load(id)
}

onMounted(() => {
  if (tlSvg.value) {
    tlSvg.value.addEventListener('pointerdown', tlDown)
    tlSvg.value.addEventListener('pointermove', tlMove)
    tlSvg.value.addEventListener('pointerup', tlUp)
    tlSvg.value.addEventListener('pointercancel', tlUp)
  }
  load(anchor.value)
})
// 2026-10-14：屏③已挂载时从答案页带 entity 跳入（同组件复用，onMounted 不再触发）
watch(() => route.query.entity, (v) => {
  const id = String(v || '').trim()
  if (id && id !== anchor.value) useAnchor(id)
})
onBeforeUnmount(() => {
  if (G && G.destroy) G.destroy()
  G = null
})
</script>

<template>
  <section class="view is-on" id="view-graph" role="tabpanel" aria-labelledby="nav-graph">
    <div class="wrap">
      <div class="sec__head reveal">
        <div class="sec__head-l">
          <span class="label">03 / 事件知识图谱</span>
          <h1 class="h1">从公司出发，把事件连成能走的路</h1>
          <p class="body" style="max-width:70ch">
            节点按实体类型区分形状、半径按连接数分级（14～30px 钳位）；布局是确定性的分层环形——中心实体在圆心、1 跳内环、2 跳外环，同环等角分布。边为有向箭头，<b>默认不显示文字</b>，悬停或选中才出现「中文关系名 ＋ 置信度」；线宽与透明度双编码 confidence。
            支持类型复选筛选、深度 1 跳／2 跳切换、按 event_time 的时间区间过滤，以及缩放、平移、适应窗口与一键重置。
            下方「实体档案／本视图关系」两块与「实体证据」四块，全部取自真实接口返回，缺失字段一律「—（空）」，不补写、不推算。
          </p>
        </div>
        <span class="label">节点／边全部来自真实接口返回</span>
      </div>

      <div class="gbar reveal gsearch">
        <span class="label">锚点实体</span>
        <input v-model="kw" class="gsearch__in" type="text" placeholder="公司名／股票代码／实体编号，如 贵州茅台、600519、EVT-0288"
               aria-label="搜索实体作为图谱锚点" @keyup.enter="doSearch()">
        <button class="chip" type="button" @click="doSearch()">搜索</button>
        <span class="label">当前锚点 <b>{{ anchor || '—（无 · 画布已清空）' }}</b></span>
        <!-- 缺陷2：搜索词常显——点选候选后输入框不再被清空，这里再留一份「上次搜索」，?q= 刷新后也能回看 -->
        <span v-if="lastSearchQ" class="label gsearch__q">上次搜索 <b>{{ lastSearchQ }}</b></span>
        <!-- 缺陷5：同名实体靠 label（英文类型名）分不开，chip 上补 stock_code／node_id 作可区分标识 -->
        <template v-for="r in results" :key="r.node_id">
          <button class="chip chip--mini" type="button" @click="useAnchor(r.node_id, lastSearchQ)">
            {{ r.name }} · {{ r.label }}<template v-if="r.stock_code || r.node_id"> · {{ r.stock_code || r.node_id }}</template>
          </button>
        </template>
        <span v-if="searching" class="label">搜索中…</span>
        <template v-else-if="resultSummary">
          <!-- 缺陷4：总数用接口实返 total，已显示数用本次真实拿到的候选条数 -->
          <span class="label gsearch__sum">{{ resultSummary }}</span>
          <button v-if="canShowMore" class="chip chip--mini" type="button" @click="showMore">显示更多</button>
        </template>
      </div>

      <!-- 缺陷3：检索失败（网络错误／后端 429 限流）单独成条，把接口实返的 code 与 message 原样展示；
           这里不动画布（检索失败 ≠ 没有这家公司），避免把「被限流」误报成「库里没有」 -->
      <div v-if="searchErr" class="graphOff" style="border-color:var(--accent-line)" role="alert">
        <b>实体检索失败：是「这次检索没成功」，不是「库里没有这家公司」</b>
        <p class="small" style="margin-top:8px">{{ searchErr }}</p>
        <p class="small">{{ searchErrHint }}</p>
      </div>

      <div v-if="loading" class="sec"><p class="small">正在从真实接口读取图谱数据…</p></div>
      <div v-else-if="error" class="graphOff" style="border-color:var(--accent-line)">
        <b>图谱数据读取失败</b>
        <p class="small" style="margin-top:8px">{{ error }}</p>
        <p class="small">{{ graphHint }}</p>
      </div>
      <div v-else-if="cleared" class="graphOff" style="border-color:var(--accent-line)" role="status">
        <!-- 缺陷1：检索到 0 条时画布已被清空（节点／边／属性面板都销毁），这里把用户输入的词回显出来并说明旧图已清除 -->
        <b>未检索到与「{{ emptyQ }}」匹配的实体</b>
        <p class="small" style="margin-top:8px">{{ emptyMessage }}</p>
        <p class="small">画布上目前没有任何节点：从上面的候选里点选一个实体，或用 6 位股票代码重新搜索，即可重新载入图谱。</p>
      </div>

      <!-- 图谱本体（图例／工具条／属性面板／实体证据区／路径列表／孤立节点／准确性声明）由 mountGraph 渲染 -->
      <div v-show="!loading && !error && !cleared" ref="graphWrap" class="reveal" style="--d:70ms"></div>

      <div v-show="!loading && !error && !cleared" class="tl reveal" style="--d:140ms">
        <div class="tl__head">
          <div class="sec__title">
            <span class="label">时间轴 · 按 event_time／publish_time 过滤</span>
            <span class="tl__range">{{ tlRange }}</span>
          </div>
          <div class="glegend">
            <span class="lg"><i style="background:#E63946;width:8px;height:8px;border-radius:50%"></i>区间内</span>
            <span class="lg"><i style="background:rgba(255,255,255,.22);width:8px;height:8px;border-radius:50%"></i>区间外</span>
            <button class="chip" type="button" @click="setRange(0, months.length - 1)">重置区间</button>
          </div>
        </div>
        <svg ref="tlSvg" viewBox="0 0 1160 128" role="img" aria-label="时间轴筛选器，可拖动按 event_time 选择时间区间"></svg>
      </div>

      <p v-if="note" class="small reveal" style="margin-top:16px;max-width:106ch;color:var(--accent-ink)">{{ note }}</p>

      <p v-show="!loading && !error" class="small reveal" style="margin-top:16px;max-width:106ch">
        时间轴只在记录里真正出现过的月份上取值：文档节点取该文档接口返回的
        <span class="mono">publish_time</span>，事件节点取 <span class="mono">GET /api/graph/events/{id}</span> 的
        <span class="mono">event_time</span>；<b>event_time 为空的事件节点落不到轴上、不参与时间筛选</b>（属性面板显示「—（空）」，与原型一致）。
        公司、人物、机构本身没有事件时间，同样不参与时间筛选、始终显示（是否在跳数范围内由深度切换单独决定）。切换数据集即重算，不共用上一套的时间状态。
        数据截止时间 {{ (appMeta && appMeta.dataCutoffTime) || '—' }}。
      </p>
      <p v-show="!loading && !error" class="small reveal" style="margin-top:10px;max-width:106ch">
        <b>去遮挡怎么核验</b>：半径 14～30px 钳位；标签只给高优先级节点并按矩形相交检测自动隐藏冲突项，画布下方状态条如实报出「已隐藏 N 个标签」；图例、工具条、属性面板全部移出绘图区；同类多边用贝塞尔曲率分叉；初始 fit-to-view，节点可拖动且边实时跟随；脚本每帧对节点圆与标签矩形做两两相交自检，结果打印在状态条里——<b>消不掉就如实显示真实数字，不写 0</b>。
      </p>
    </div>
  </section>
</template>

<style scoped>
.gsearch { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 6px 0 18px; }
.gsearch__in {
  min-width: 260px; flex: 1 1 260px; max-width: 420px;
  background: rgba(255, 255, 255, .03); border: 1px solid var(--border); border-radius: 8px;
  color: var(--fg); font-size: 13px; padding: 8px 11px; font-family: var(--f-body);
}
.gsearch__in::placeholder { color: var(--faint); }
.gsearch__in:focus { outline: none; border-color: var(--accent); }
/* 缺陷2：搜索词常显（弱化底色，避免与「当前锚点」抢视线） */
.gsearch__q { color: var(--muted); }
.gsearch__q b { color: var(--fg); font-weight: 600; max-width: 24ch; overflow-wrap: anywhere; }
/* 缺陷4：候选计数 —— 数字用等宽体，与页面上其它计数口径一致 */
.gsearch__sum { color: var(--muted); font-variant-numeric: tabular-nums; }
</style>

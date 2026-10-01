<script setup>
// 代码\前端\src\views\GraphView.vue —— 屏③ 事件知识图谱（第 9 阶段 T9）
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

import { inject, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  getChunk, getEntity, getEntityEvidence, getEventDetail, getNeighbors, getPaths, listEntities,
} from '../api.js'
import { buildDataset, mountGraph, typeOfLabel, TKEYS, TYPE } from '../lib/graph.js'

const appMeta = inject('appMeta', null)

const anchor = ref('600519')
const loading = ref(false)
const error = ref('')
const note = ref('')

const graphWrap = ref(null)
const tlSvg = ref(null)
const tlRange = ref('')
const months = ref([])

const kw = ref('')
const results = ref([])
const searching = ref(false)

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

async function doSearch() {
  const k = kw.value.trim()
  if (!k) return
  searching.value = true
  results.value = []
  try {
    const d = await listEntities({ keyword: k, limit: 8 })
    results.value = (d && d.items) || []
  } catch (e) {
    results.value = []
  } finally {
    searching.value = false
  }
}
function useAnchor(id) {
  results.value = []
  kw.value = ''
  note.value = ''
  anchor.value = id
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
               aria-label="搜索实体作为图谱锚点" @keyup.enter="doSearch">
        <button class="chip" type="button" @click="doSearch">搜索</button>
        <span class="label">当前锚点 <b>{{ anchor }}</b></span>
        <template v-for="r in results" :key="r.node_id">
          <button class="chip chip--mini" type="button" @click="useAnchor(r.node_id)">{{ r.name }} · {{ r.label }}</button>
        </template>
        <span v-if="searching" class="label">搜索中…</span>
        <span v-else-if="kw && !results.length" class="label">（无结果）</span>
      </div>

      <div v-if="loading" class="sec"><p class="small">正在从真实接口读取图谱数据…</p></div>
      <div v-else-if="error" class="graphOff" style="border-color:var(--accent-line)">
        <b>图谱数据读取失败</b>
        <p class="small" style="margin-top:8px">{{ error }}</p>
        <p class="small">请确认后端已启动（python "代码\后端\run.py"，端口 8000），并换一个锚点实体重试。</p>
      </div>

      <!-- 图谱本体（图例／工具条／属性面板／实体证据区／路径列表／孤立节点／准确性声明）由 mountGraph 渲染 -->
      <div v-show="!loading && !error" ref="graphWrap" class="reveal" style="--d:70ms"></div>

      <div v-show="!loading && !error" class="tl reveal" style="--d:140ms">
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
</style>

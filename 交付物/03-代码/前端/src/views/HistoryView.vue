<script setup>
// 交付物/03-代码\前端\src\views\HistoryView.vue —— 屏④ 历史记录（第 9 阶段 T9）
//
// 版式按原型屏④：大行列表（编号／问题／时间／证据数）＋ 回看抽屉四段
//   （表一 问题 / 表二 答案四段 / 表三 证据表 / 表四 图谱路径可视化）。
//
// 取数：
//   * GET /api/history?session_id=…&page=&page_size=  → 列表（会话隔离 FR-06，session 由 api.js 自动带）
//   * GET /api/history/{question_id}?session_id=…     → 回看（问题／答案正文／证据／graph_path_available）
//   * GET /api/evidence/{answer_id}/graph-path        → **当时记录的路径载荷**（回看还原的来源）
//
// **回看不重新查询图谱拓扑**：表四只用 `answer.graph_path` 记录载荷重新渲染一遍，
// 不调用任何 /api/graph/paths、neighbors 等拓扑查询接口。
// 载荷里只存节点编号；画布挂载前用**单实体详情接口**把编号批量补成实体名
//（2026-10-14 修正：先补名、再 buildDataset，见 lib/replay.js），补名不改路径拓扑。
//
// 空列表是正常业务状态（2002 语义），给「未检索到匹配记录」提示，不是错误。

import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { listHistory, getHistoryDetail, getGraphPath } from '../api.js'
import { mountGraph, EXT, DOMAIN } from '../lib/graph.js'
import { buildReplayDataset } from '../lib/replay.js'

const appMeta = inject('appMeta', null)

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const error = ref('')

const drawerOn = ref(false)
const drawerPanel = ref(null)
let drawerReturnFocus = null
/* M13（2026-10-11）：回看抽屉的焦点管理。openRow 记录触发元素并把焦点移入抽屉面板；
   closeDrawer 把焦点还原到触发元素；trapDrawerTab 在抽屉内做 Tab 循环，
   键盘焦点不会落到被 aria-modal 遮住的背景内容上（WCAG 2.4.3／2.1.2）。 */
const current = ref(null)
const detail = ref(null)
const gp = ref(null)
/* 缺陷 2（诚实性）：表二那张图（answer.graph_path）的读取失败**不再静默吞掉**。
   实测限流确实会发生（后端 60 次／60 秒／来源 IP，而打开一次抽屉约 7 个请求，
   本次用户测试在历史页与答案页都实测到 429／code 1004）；api.js 的 request() 已把
   「，请约 N 秒后重试」拼进 e.message，这里记下来并展示，不再让用户把「被限流」
   误读成「这条记录本来就没有图谱路径」。 */
const gpError = ref('')
const cutoffLabel = computed(() => (appMeta && appMeta.dataCutoffTime) || '—')
const drawerLoading = ref(false)
const drawerError = ref('')
const graphHost = ref(null)
let replayG = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

async function load() {
  error.value = ''
  loading.value = true
  try {
    const data = await listHistory(page.value, pageSize.value)
    items.value = (data && data.items) || []
    total.value = (data && data.total) || 0
  } catch (e) {
    items.value = []
    total.value = 0
    error.value = `${e && e.code ? '[' + e.code + '] ' : ''}${(e && e.message) || e}`
  } finally {
    loading.value = false
  }
}
function go(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  load()
}
function fmtTime(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 19) : '—' }
function fmtDate(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 10) : '—' }

// —— 回看抽屉 ——
const qRows = computed(() => {
  const d = detail.value
  if (!d) return []
  return [
    ['question_id', d.question_id],
    ['question_text', d.question_text],
    ['ask_time', fmtTime(d.ask_time)],
    ['answer_id', d.answer_id],
  ]
})
// 与屏②同一套段头口径（逐字对齐 AnswerSections.vue 的 HEADERS，不导入、不改造那个组件）
const SECTION_HEADERS = ['【回答】', '【证据来源】', '【知识图谱路径】', '【数据截至与判定区间】']

/**
 * 按固定段头把 answer_text 切成四段：返回每段的 present 与 body（已 trim），
 * 切分口径与屏② AnswerSections.vue 的 sections 完全一致（纯文本定位，不改写内容）。
 * @param {string} text 答案正文
 */
function splitSections(text) {
  const t = typeof text === 'string' ? text : ''
  const indexes = SECTION_HEADERS.map((h) => t.indexOf(h))
  const out = []
  for (let i = 0; i < SECTION_HEADERS.length; i++) {
    const header = SECTION_HEADERS[i]
    const start = indexes[i]
    if (start < 0) { out.push({ header, body: '', present: false }); continue }
    let end = t.length
    for (let j = 0; j < SECTION_HEADERS.length; j++) {
      const pos = indexes[j]
      if (pos > start && pos < end) end = pos
    }
    out.push({ header, body: t.slice(start + header.length, end).trim(), present: true })
  }
  return out
}

/**
 * 缺陷 1（诚实性，实测 43／43 条 refsCount 与证据条数不符）：
 * 旧实现对**整段** answer_text 做 /\[证据(\d+)\]/g 全局匹配，把【证据来源】段里那
 * 10 行清单本身也数了进去 —— 例如 answer 1 显示 12 处（【回答】段内实际只有 2 处）、
 * answer 5 显示 23 处（【回答】段内 13 处），数字被虚增 20%～130%。
 * 这里改为**只统计【回答】段**（与屏②同一套段头口径）；
 * 段头缺失导致截取失败时返回 count=null，由模板如实退化为「段头缺失，无法按段统计」，
 * 不静默按全文数。
 */
const refsStat = computed(() => {
  const d = detail.value
  if (!d) return { count: null, sectionPresent: false }
  const sec = splitSections(d.answer_text || '')[0]
  if (!sec.present) return { count: null, sectionPresent: false }
  const m = sec.body.match(/\[证据(\d+)\]/g)
  return { count: m ? m.length : 0, sectionPresent: true }
})
const pathCount = computed(() => {
  const p = gp.value && gp.value.paths
  return Array.isArray(p) ? p.length : '—'
})

/* 缺陷 2：表二那张图（graph_path）一格要**如实区分**三种状态 —— ①载荷已读到；
   ②载荷读取失败（把 e.code 与 e.message 原样摆出，含 1004 限流时的重试秒数）；
   ③记录里本来就没有路径载荷（graph_path_available = false）。绝不把 ② 说成 ③。 */
const graphPathNote = computed(() => {
  if (gp.value) return `原始 JSON 文本 · ${pathCount.value} 条路径 · 深度上限见载荷 —— 即下方「表四」的还原来源`
  if (gpError.value) return `路径载荷读取失败 —— 路径条数如实记「—」（未能取到「原始 JSON 文本」，故不写条数、不猜条数）：${gpError.value}`
  return '本次记录未存路径载荷（graph_path_available = false），表四只给固定文案，不补画节点或边'
})

async function openRow(row) {
  current.value = row
  drawerReturnFocus = document.activeElement        // M13：记录触发元素，关闭时还原
  drawerOn.value = true
  document.body.setAttribute('data-drawer', 'on')
  detail.value = null
  gp.value = null
  gpError.value = ''
  drawerError.value = ''
  drawerLoading.value = true
  try {
    const d = await getHistoryDetail(row.question_id)
    detail.value = d
    if (d && d.graph_path_available && d.answer_id) {
      // 缺陷 2：这里过去是 `catch (e) { gp.value = null }` —— 错误被整个丢掉，
      // 表四随之留白、表二那格还写着「原始 JSON 文本」，用户会把限流（429／1004）
      // 误读成「这条记录本来就没有图谱路径」。现在记下 code 与 message 并在页面上展示。
      try {
        gp.value = await getGraphPath(d.answer_id)
      } catch (e) {
        gp.value = null
        gpError.value = `${e && e.code ? '[' + e.code + '] ' : ''}${(e && e.message) || e}`
      }
    }
  } catch (e) {
    drawerError.value = `${e && e.code ? '[' + e.code + '] ' : ''}${(e && e.message) || e}`
  } finally {
    drawerLoading.value = false
  }
  await nextTick()
  await mountReplay()
  if (drawerPanel.value) drawerPanel.value.focus()   // M13：焦点移入抽屉
}

function closeDrawer() {
  if (replayG && replayG.destroy) replayG.destroy()
  replayG = null
  drawerOn.value = false
  document.body.removeAttribute('data-drawer')
  // M13：焦点还原到打开抽屉的那一行（元素可能已被翻页卸载，故判空）
  if (drawerReturnFocus && typeof drawerReturnFocus.focus === 'function') {
    drawerReturnFocus.focus()
  }
  drawerReturnFocus = null
}

function trapDrawerTab(e) {
  // M13：Tab／Shift+Tab 在抽屉的可聚焦元素间循环（不逃逸到被遮住的页面背景）
  if (e.key !== 'Tab' || !drawerOn.value) return
  const panel = drawerPanel.value
  if (!panel) return
  const list = Array.from(
    panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
  ).filter((el) => !el.disabled && el.offsetParent !== null)
  if (!list.length) return
  const first = list[0]
  const last = list[list.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    last.focus(); e.preventDefault()
  } else if (!e.shiftKey && document.activeElement === last) {
    first.focus(); e.preventDefault()
  }
}

// 节点编号 → 类型／边构造／补名均在 lib/replay.js（2026-10-14 与答案页共用，避免两处漂移）。
async function mountReplay() {
  if (!graphHost.value) return
  if (replayG && replayG.destroy) replayG.destroy()
  replayG = null
  graphHost.value.innerHTML = ''
  // 先补名（实体详情接口，3 并发）、再 buildDataset——画布标签天然是实体名
  const ds = await buildReplayDataset(gp.value)
  if (!ds) return
  const el = document.createElement('div')
  graphHost.value.appendChild(el)
  const first = ds.nodes.slice().sort((a, b) => (b.deg - a.deg) || (a.id < b.id ? -1 : 1))[0]
  // modes:false —— 回看固定用「会话载荷子图」；不传 provider —— 回看不重新查询图谱拓扑
  replayG = mountGraph(el, { ds, modes: false, select: first ? first.id : null, depth: 2, tag: '载荷 answer.graph_path · 回看还原' })
}

function onKey(e) {
  if ((e.key === 'Escape' || e.key === 'Esc') && drawerOn.value) closeDrawer()
}

onMounted(() => {
  load()
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  if (replayG && replayG.destroy) replayG.destroy()
  document.body.removeAttribute('data-drawer')
})
</script>

<template>
  <section class="view is-on" id="view-history" role="tabpanel" aria-labelledby="nav-history">
    <div class="wrap">
      <div class="sec__head reveal">
        <div class="sec__head-l">
          <span class="label">04 / 历史记录</span>
          <h1 class="h1">每一次提问都留痕</h1>
          <p class="body" style="max-width:68ch">
            一行一次会话（按当前会话隔离，只列出本会话的提问）。点开回看按当时记录的路径载荷还原四段：
            问题 → 答案四段 → 证据表 → 图谱路径可视化。图谱一节复用屏③同一套渲染器、同一张图例与同一句准确性声明，且<b>不重新查询图谱</b>。
          </p>
        </div>
        <span class="label">共 {{ total }} 条 · 第 {{ page }} / {{ totalPages }} 页</span>
      </div>

      <div class="hstats reveal">
        <div class="hstat"><span class="label">本会话记录</span><b>{{ total }}</b></div>
        <div class="hstat"><span class="label">当前页</span><b>{{ items.length }}</b></div>
        <div class="hstat"><span class="label">图谱深度上限</span><b>2 跳</b></div>
        <div class="hstat"><span class="label">数据截止</span><b style="font-size:13px">{{ cutoffLabel }}</b></div>
      </div>

      <div v-if="error" class="graphOff" style="border-color:var(--accent-line)">
        <b>历史记录读取失败</b>
        <p class="small" style="margin-top:8px">{{ error }}</p>
      </div>
      <p v-else-if="loading" class="small">正在读取历史记录…</p>
      <div v-else-if="!items.length" class="graphOff">
        <b>未检索到匹配记录</b>
        <p class="small" style="margin-top:8px">本会话暂无历史记录（这是正常空结果，不是错误）。去「提问台」提一个问题即可留痕。</p>
        <!-- 缺陷 4（可操作性）：会话隔离（FR-06）是设计行为，但新访客／答辩评委第一眼看到
             「没有历史」会判成功能缺失。这里只在空态补一句可操作说明，把「为什么空」和
             「哪里有数据」讲清楚；**不**去读别的会话的数据，隔离照旧。 -->
        <p class="small" style="margin-top:8px">
          本页按浏览器会话隔离（FR-06）：这里的记录只属于当前会话。库中既有的历史记录属于会话 <span class="mono">S-001</span>，需要查看时可在地址栏把本页改为 <span class="mono">/history?session_id=S-001</span>。
        </p>
      </div>

      <div v-else class="hrows">
        <article v-for="(it, i) in items" :key="it.question_id" class="hrow" :data-session="it.question_id">
          <span class="hrow__no">{{ String((page - 1) * pageSize + i + 1).padStart(2, '0') }}</span>
          <div>
            <h3 class="hrow__q">{{ it.question_text }}</h3>
            <div class="hrow__sub">
              <span class="tag">{{ fmtTime(it.ask_time) }}</span>
              <span class="tag tag--muted">question_id {{ it.question_id }} · answer_id {{ it.answer_id }}</span>
            </div>
            <p class="small" style="margin-top:9px;max-width:74ch">{{ it.answer_summary || '（本次记录未给出答案摘要）' }}</p>
          </div>
          <div class="hrow__meta">
            <div class="hrow__nums">
              <b>{{ it.evidence_count }}</b><span class="small">条证据</span>
            </div>
            <span class="label">点开回看</span>
          </div>
          <span class="hrow__sweep"></span>
          <button class="hrow__open" type="button" :aria-label="'回看会话：' + it.question_text" @click="openRow(it)"></button>
        </article>
      </div>

      <div v-if="!error && items.length" class="pagerx" style="display:flex;gap:10px;margin-top:18px">
        <button class="btn btn--ghost btn--sm" type="button" :disabled="page <= 1 || loading" @click="go(page - 1)">上一页</button>
        <button class="btn btn--ghost btn--sm" type="button" :disabled="page >= totalPages || loading" @click="go(page + 1)">下一页</button>
      </div>

      <!-- ===== 回看抽屉：四段（问题 / 答案 / 证据表 / 图谱路径可视化）===== -->
      <!-- 2026-10-11（M13）：补焦点管理——打开时焦点移入抽屉面板、Tab 循环困在抽屉内、
           关闭后焦点还原到触发行（WCAG 2.4.3 顺序 ／ 2.1.2 无键盘陷阱的对话框配套）。 -->
      <div class="drawer" :class="{ on: drawerOn }" :hidden="!drawerOn" role="dialog" aria-modal="true" aria-labelledby="drawerTitle" @keydown="trapDrawerTab">
        <div class="drawer__scrim" @click="closeDrawer"></div>
        <div ref="drawerPanel" class="drawer__panel" tabindex="-1">
          <div class="drawer__head">
            <div style="min-width:0">
              <span class="label">回看 · 会话 <span class="mono">{{ current ? current.question_id : '—' }}</span></span>
              <h2 class="h2" id="drawerTitle" style="margin-top:10px">{{ current ? current.question_text : '' }}</h2>
            </div>
            <button class="btn btn--ghost btn--sm" type="button" @click="closeDrawer">关闭</button>
          </div>

          <div class="drawer__body">
            <div class="notice notice--calm">
              <svg aria-hidden="true"><use href="#i-alert"></use></svg>
              <span><strong style="color:#fff;font-weight:600">按当时记录的路径载荷还原 · 不重新查询图谱</strong>（看到的是当时的真实结果，不是图谱的当前状态）。本系统把图谱路径原样存进了 <span class="mono">answer.graph_path</span>，回看只是把这份载荷重新渲染一遍，不调用任何 <span class="mono">/api/graph/*</span> 查询接口。</span>
            </div>

            <p v-if="drawerLoading" class="small">正在还原会话记录…</p>
            <div v-else-if="drawerError" class="graphOff" style="border-color:var(--accent-line)">
              <b>回看失败</b><p class="small" style="margin-top:8px">{{ drawerError }}</p>
            </div>

            <template v-else-if="detail">
              <!-- 表一 · 问题表 -->
              <div class="tblWrap">
                <div class="tblWrap__h"><span class="label">表一 · 问题表 question</span><span class="label">1 行</span></div>
                <table class="tbl">
                  <thead><tr><th>字段</th><th>值</th></tr></thead>
                  <tbody>
                    <tr v-for="(r, i) in qRows" :key="i"><td class="k mono">{{ r[0] }}</td><td>{{ r[1] }}</td></tr>
                  </tbody>
                </table>
              </div>

              <!-- 表二 · 答案表 -->
              <div class="tblWrap">
                <div class="tblWrap__h"><span class="label">表二 · 答案表 answer</span><span class="label">1 行</span></div>
                <table class="tbl">
                  <thead><tr><th>字段</th><th>值</th></tr></thead>
                  <tbody>
                    <tr><td class="k mono">answer_text</td><td class="ans" style="white-space:pre-wrap">{{ detail.answer_text }}</td></tr>
                     <!-- 缺陷 1：只数【回答】段内的引用，并把「不含证据清单行」写进文案 -->
                     <tr><td class="k mono">refs_in_text</td>
                       <td v-if="refsStat.count !== null">【回答】段内 <span class="mono">[证据n]</span> 共 {{ refsStat.count }} 处（不含【证据来源】清单行）</td>
                       <td v-else>—（段头缺失，无法按段统计）</td></tr>
                    <tr><td class="k mono">graph_path</td>
                       <td class="mono">{{ graphPathNote }}</td></tr>
                    <tr><td class="k mono">output_mode</td><td>单轮一次生成（非流式，没有逐字输出过程）</td></tr>
                  </tbody>
                </table>
              </div>

              <!-- 表三 · 证据表 -->
              <div class="tblWrap">
                <div class="tblWrap__h"><span class="label">表三 · 证据表 evidence</span><span class="label">{{ (detail.evidence || []).length }} 行</span></div>
                <table class="tbl">
                  <thead><tr><th>证据号</th><th>类别</th><th>标题</th><th>来源网站</th><th>发布日期</th><th>文档号</th><th>块号</th><th>原文</th></tr></thead>
                  <tbody>
                    <tr v-for="ev in (detail.evidence || [])" :key="ev.rank">
                      <td class="mono">{{ ev.rank }}</td>
                      <td>{{ ev.evidence_type }}</td>
                      <td class="k">{{ ev.title || '—' }}</td>
                      <td>{{ ev.source ? (ev.source + (DOMAIN[ev.source] ? ' · ' + DOMAIN[ev.source] : '')) : '—' }}</td>
                      <td class="mono">{{ fmtDate(ev.publish_time) }}</td>
                      <td class="mono">doc_id {{ ev.doc_id }}</td>
                      <td class="mono">chunk_id {{ ev.chunk_id }}</td>
                      <td>
                        <a v-if="ev.url" class="ev__link ev__link--sm" :href="ev.url" target="_blank" rel="noopener"
                           :aria-label="'查看原文：' + (ev.title || '') + '（新窗口打开）'"><span v-html="EXT"></span>查看原文 ↗</a>
                        <span v-else class="ev__nolink ev__nolink--sm">记录未给出</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p class="small" style="margin-top:10px">证据表的「原文」列与屏②证据卡同源，url 逐字取自真实接口返回，未改写、未拼接。</p>
              </div>

              <!-- 表四 · 图谱路径可视化 -->
              <!-- 缺陷 2／5：表四的显示条件扩到「记录里有载荷」「读过载荷但失败了」两种；
                   失败时**显式写出「路径载荷读取失败：…」**（含 e.code 与含重试秒数的 e.message），
                   不许留白；成功时把 getGraphPath 的载荷原样放进默认折叠的 <details><pre>。 -->
              <div class="dsub" :hidden="!detail.graph_path_available && !gpError">
                <div class="dsub__h">
                  <span class="label">表四 · 图谱路径可视化</span>
                  <span class="label">与屏③同一套渲染器 · 同一张图例 · 同一句准确性声明</span>
                </div>
                <!-- 读取失败：这一块不留白，把失败原因与重试提示写在原地 -->
                <div v-if="gpError" class="graphOff" style="border-color:var(--accent-line)">
                  <b>路径载荷读取失败：{{ gpError }}</b>
                  <p class="small" style="margin-top:8px">
                    这条记录<b>当时是否存了路径载荷</b>见上表 <span class="mono">graph_path_available</span>；
                    此处的空不是「本来没有路径」，而是<b>这一次没能把载荷读上来</b>。
                    按提示秒数稍后重开这一条即可重试（重开抽屉会重新请求）。
                  </p>
                </div>
                <div v-if="detail.graph_path_available && gp" ref="graphHost" class="dgraph"></div>
                <p v-if="detail.graph_path_available && gp" class="small" style="margin-top:10px">
                  路径载荷里只存节点编号（拓扑与边原样）；画布挂载前按编号前缀判类（PER-＝人物、EVT-＝事件、INST-／ORG-＝机构、六位数字＝公司，判不出的按文档处理、不猜），并经<b>单实体详情接口</b>把编号补成实体名（3 并发防限流，单个失败保持编号）；<b>不重新查询图谱路径</b>，拓扑仍 100% 来自当时载荷。
                </p>
                <!-- 缺陷 5：「原始 JSON 文本」此前一个 JSON 字符都不给；这里把已有载荷原样摊开
                     （默认折叠、不美化、不重排、不截断），拿不到就不渲染，绝不显示空 <pre>。 -->
                <details v-if="gp" class="dsub__raw">
                  <summary class="small">原始 JSON 文本（<span class="mono">GET /api/evidence/{answer_id}/graph-path</span> 的返回载荷，原样、未改写）</summary>
                  <pre class="dsub__pre mono">{{ JSON.stringify(gp, null, 0) }}</pre>
                </details>
              </div>
              <div v-if="!detail.graph_path_available && !gpError" class="notice">
                <svg aria-hidden="true"><use href="#i-alert"></use></svg>
                <span>本次记录未存 <span class="mono">answer.graph_path</span> 载荷，表四只给固定文案，不补画任何节点或边。</span>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hrow__q { font-family: var(--f-display); font-weight: 700; letter-spacing: -.032em; line-height: 1.06; }
.hrow__meta .small { color: var(--faint); }
.tblWrap { margin-top: 16px; }
.dsub { margin-top: 16px; }
.dgraph { min-height: 420px; }
/* 缺陷 5：「原始 JSON 文本」的原样文本块。只显示用到的 4 个变量，不新增设计令牌 */
.dsub__raw { margin-top: 14px; }
.dsub__pre {
  margin: 8px 0 0; white-space: pre-wrap; word-break: break-word; max-height: 420px; overflow: auto;
  font-size: 11.5px; line-height: 1.7; color: var(--muted); background: var(--surface);
  border: 1px solid var(--border-soft); border-radius: 7px; padding: 10px 12px;
}
</style>

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
// **回看不重新查询图谱**：表四只用 `answer.graph_path` 记录载荷重新渲染一遍，不调用任何 /api/graph/* 查询接口。
// 载荷里只存了节点编号（未存实体名），故节点按编号显示，不另行查图补名——就地标注。
//
// 空列表是正常业务状态（2002 语义），给「未检索到匹配记录」提示，不是错误。

import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { listHistory, getHistoryDetail, getGraphPath } from '../api.js'
import { buildDataset, mountGraph, EXT, DOMAIN } from '../lib/graph.js'

const appMeta = inject('appMeta', null)

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const error = ref('')

const drawerOn = ref(false)
const current = ref(null)
const detail = ref(null)
const gp = ref(null)
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
const refsCount = computed(() => {
  const t = (detail.value && detail.value.answer_text) || ''
  const m = t.match(/\[证据(\d+)\]/g)
  return m ? m.length : 0
})
const pathCount = computed(() => {
  const p = gp.value && gp.value.paths
  return Array.isArray(p) ? p.length : (detail.value && detail.value.graph_path_available ? '—' : 0)
})

async function openRow(row) {
  current.value = row
  drawerOn.value = true
  document.body.setAttribute('data-drawer', 'on')
  detail.value = null
  gp.value = null
  drawerError.value = ''
  drawerLoading.value = true
  try {
    const d = await getHistoryDetail(row.question_id)
    detail.value = d
    if (d && d.graph_path_available && d.answer_id) {
      try { gp.value = await getGraphPath(d.answer_id) } catch (e) { gp.value = null }
    }
  } catch (e) {
    drawerError.value = `${e && e.code ? '[' + e.code + '] ' : ''}${(e && e.message) || e}`
  } finally {
    drawerLoading.value = false
  }
  await nextTick()
  mountReplay()
}

function closeDrawer() {
  if (replayG && replayG.destroy) replayG.destroy()
  replayG = null
  drawerOn.value = false
  document.body.removeAttribute('data-drawer')
}

// 节点编号 → 画布类型（载荷里只存编号，故按编号前缀判别；判不出的一律按「文档」处理，不猜）
function typeOfId(id) {
  const s = String(id)
  if (/^PER-/.test(s)) return 'person'
  if (/^EVT-/.test(s)) return 'event'
  if (/^INST-|^ORG-/.test(s)) return 'org'
  if (/^POL-/.test(s)) return 'policy'
  if (/^IND-/.test(s)) return 'industry'
  if (/^\d{6}$/.test(s)) return 'company'
  return 'doc'
}
function replayDs(payload) {
  const paths = (payload && payload.paths) || []
  if (!Array.isArray(paths) || !paths.length) return null
  const nodeSet = new Set()
  const edges = []
  for (const p of paths) {
    const nodes = p.nodes || []
    ;(p.relations || []).forEach((rel, i) => {
      const a = nodes[i]
      const b = rel.neighbor
      if (a === undefined || b === undefined) return
      nodeSet.add(String(a)); nodeSet.add(String(b))
      const inEdge = rel.direction === 'in'
      const ev = rel.evidence || {}
      const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))
      edges.push({
        f: String(inEdge ? b : a),
        t: String(inEdge ? a : b),
        rel: rel.relation,
        role: rel.role || '',
        conf: num(ev.confidence),
        sdoc: ev.source_doc_id !== undefined ? ev.source_doc_id : null,
        schunk: ev.source_chunk_id !== undefined ? ev.source_chunk_id : null,
        noev: rel.relation === 'EVIDENCED_BY' ? 1 : 0,
        src: 'answer.graph_path',
      })
    })
    if (!nodes.length) { if (p.start) nodeSet.add(String(p.start)); if (p.end) nodeSet.add(String(p.end)) }
  }
  if (!nodeSet.size) return null
  const nodes = [...nodeSet].map((id) => ({ id, eid: id, type: typeOfId(id), name: id, code: '', sub: '', time: null }))
  return buildDataset('replay', nodes, edges)
}
function mountReplay() {
  if (!graphHost.value) return
  if (replayG && replayG.destroy) replayG.destroy()
  replayG = null
  graphHost.value.innerHTML = ''
  const ds = replayDs(gp.value)
  if (!ds) return
  const el = document.createElement('div')
  graphHost.value.appendChild(el)
  const first = ds.nodes.slice().sort((a, b) => (b.deg - a.deg) || (a.id < b.id ? -1 : 1))[0]
  // modes:false —— 回看固定用「会话载荷子图」；不传 provider —— 回看不重新查询图谱
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
        <div class="hstat"><span class="label">图谱深度上限</span><b>标记载荷</b></div>
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
      <div class="drawer" :class="{ on: drawerOn }" :hidden="!drawerOn" role="dialog" aria-modal="true" aria-labelledby="drawerTitle">
        <div class="drawer__scrim" @click="closeDrawer"></div>
        <div class="drawer__panel">
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
                    <tr><td class="k mono">refs_in_text</td><td>[证据n] 共 {{ refsCount }} 处，与证据清单的 rank 一一对应</td></tr>
                    <tr><td class="k mono">graph_path</td>
                      <td class="mono">{{ detail.graph_path_available ? ('原始 JSON 文本 · ' + pathCount + ' 条路径 · 深度上限见载荷 —— 即下方「表四」的还原来源') : '本次记录未存路径载荷（graph_path_available = false），表四只给固定文案，不补画节点或边' }}</td></tr>
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
              <div class="dsub" :hidden="!detail.graph_path_available">
                <div class="dsub__h">
                  <span class="label">表四 · 图谱路径可视化</span>
                  <span class="label">与屏③同一套渲染器 · 同一张图例 · 同一句准确性声明</span>
                </div>
                <div ref="graphHost" class="dgraph"></div>
                <p class="small" style="margin-top:10px">
                  载荷里只存了节点编号（未存实体名），故节点按编号显示，<b>不另行查询图谱补名</b>；节点形状按编号前缀判类（PER-＝人物、EVT-＝事件、INST-＝机构、六位数字＝公司、其余数字＝文档），判不出的一律按文档处理、不猜。
                </p>
              </div>
              <div v-if="!detail.graph_path_available" class="notice">
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
</style>

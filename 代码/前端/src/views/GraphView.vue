<script setup>
// 代码\前端\src\views\GraphView.vue —— 图谱查看页（第 9 阶段 T10）
//
// 四块功能（对应 `/api/graph/*` 五个接口）：
//   ① 按 keyword ＋ type 查实体      → GET /api/graph/entities
//   ② 选一个实体看一跳邻居           → GET /api/graph/entities/{node_id}/neighbors
//   ③ 多跳路径（可切 1／2 跳）        → GET /api/graph/paths
//   ④ 按事件类型与时间区间查事件、看详情 → GET /api/graph/events[/{event_id}]
//
// **可视化用轻量自绘 SVG**（环形布局，聚焦节点居中），**不引入任何大型可视化库**
// （《24》格式决策 5；《02》第8.4节 技术栈约束）。节点／边可点击，右侧栏展示其证据属性。
//
// 规模上限：环形布局在 40 个节点内可读性良好；超过 60 个节点标签会拥挤（见 README「已知限制」）。

import { computed, reactive, ref } from 'vue'
import { listEntities, getNeighbors, getPaths, listEvents, getEventDetail } from '../api.js'

// —— 字典（与后端 api\graph.py 的常量逐字对齐）——
const ENTITY_TYPES = [
  { value: '', label: '（不限）' },
  { value: 'Company', label: 'Company 公司' },
  { value: 'Person', label: 'Person 人员' },
  { value: 'Industry', label: 'Industry 行业' },
  { value: 'Institution', label: 'Institution 机构' },
  { value: 'Event', label: 'Event 事件' },
  { value: 'Policy', label: 'Policy 政策' },
]
const RELATIONS = ['BELONGS_TO', 'SUPPLIES', 'CUSTOMER_OF', 'COMPETES_WITH', 'HAS_EXECUTIVE',
  'PARTICIPATES_IN', 'ISSUED_BY', 'RELATED_TO', 'EVIDENCED_BY']
const EVENT_TYPES = ['业绩', '监管', '股权', '投资并购', '重大合同', '产品', '政策', '重大经营']

// —— ① 实体检索 ——
const entKeyword = ref('')
const entType = ref('')
const entities = ref([])
const entLoading = ref(false)
const entError = ref(null)
const entEmpty = ref(false)

async function searchEntities() {
  entError.value = null
  entEmpty.value = false
  entities.value = []
  entLoading.value = true
  try {
    const params = {}
    if (entKeyword.value.trim()) params.keyword = entKeyword.value.trim()
    if (entType.value) params.type = entType.value
    const data = await listEntities(params)
    entities.value = (data && data.items) || []
    // 2002 语义：HTTP 200 的空结果 —— 正常业务状态，不是错误
    entEmpty.value = entities.value.length === 0
  } catch (e) {
    entError.value = { code: e.code, message: e.message }
  } finally {
    entLoading.value = false
  }
}

// —— ② 一跳邻居 ——
const neighbors = ref(null)
const nbLoading = ref(false)
const nbError = ref(null)

async function loadNeighbors(nodeId) {
  nbError.value = null
  nbLoading.value = true
  try {
    neighbors.value = await getNeighbors(nodeId)
    paths.value = null
    events.value = []
    eventDetail.value = null
    selected.value = null
    visMode.value = 'neighbors'
  } catch (e) {
    neighbors.value = null
    nbError.value = { code: e.code, message: e.message }
  } finally {
    nbLoading.value = false
  }
}

// —— ③ 多跳路径 ——
const pathForm = reactive({ from_node: '', to_node: '', relation: '', hop: '1' })
const paths = ref(null)
const pathLoading = ref(false)
const pathError = ref(null)
const pathEmpty = ref(false)

async function runPaths() {
  pathError.value = null
  pathEmpty.value = false
  paths.value = null
  const from = pathForm.from_node.trim()
  if (!from) { pathError.value = { code: '', message: '请填写 from_node（起点节点 id）。' }; return }
  const to = pathForm.to_node.trim()
  if (!to && !pathForm.relation) {
    pathError.value = { code: '', message: '请给出 to_node，或选择 relation（二者至少其一）。' }
    return
  }
  pathLoading.value = true
  try {
    const params = { from_node: from, hop: pathForm.hop }
    if (to) params.to_node = to
    if (pathForm.relation) params.relation = pathForm.relation
    const data = await getPaths(params)
    paths.value = data
    const arr = (data && data.paths) || []
    pathEmpty.value = arr.length === 0
    neighbors.value = null
    events.value = []
    eventDetail.value = null
    selected.value = null
    visMode.value = 'paths'
  } catch (e) {
    pathError.value = { code: e.code, message: e.message }
  } finally {
    pathLoading.value = false
  }
}

// —— ④ 事件查询 ——
const evForm = reactive({ event_type: '', stock_code: '', start_time: '', end_time: '' })
const events = ref([])
const evLoading = ref(false)
const evError = ref(null)
const evEmpty = ref(false)
const eventDetail = ref(null)
const detailLoading = ref(false)
const detailError = ref(null)

async function searchEvents() {
  evError.value = null
  evEmpty.value = false
  events.value = []
  eventDetail.value = null
  evLoading.value = true
  try {
    const params = {}
    if (evForm.event_type) params.event_type = evForm.event_type
    if (evForm.stock_code.trim()) params.stock_code = evForm.stock_code.trim()
    if (evForm.start_time) params.start_time = evForm.start_time
    if (evForm.end_time) params.end_time = evForm.end_time
    const data = await listEvents(params)
    events.value = (data && data.items) || []
    evEmpty.value = events.value.length === 0
  } catch (e) {
    evError.value = { code: e.code, message: e.message }
  } finally {
    evLoading.value = false
  }
}

async function openEvent(eventId) {
  detailError.value = null
  eventDetail.value = null
  detailLoading.value = true
  try {
    eventDetail.value = await getEventDetail(eventId)
  } catch (e) {
    detailError.value = { code: e.code, message: e.message }
  } finally {
    detailLoading.value = false
  }
}

/** 事件详情里的多来源证据按 publish_time 升序（任务要求 4）。 */
const detailEvidences = computed(() => {
  const list = (eventDetail.value && eventDetail.value.evidences) || []
  return [...list].sort((a, b) => String(a.publish_time || '').localeCompare(String(b.publish_time || '')))
})

// ------------------------------------------------------------------
// SVG 可视化（轻量自绘，环形布局）
// ------------------------------------------------------------------
const visMode = ref('')          // 'neighbors' | 'paths' | ''
const selected = ref(null)       // {kind:'node'|'edge', data}

const LABEL_COLORS = {
  Company: '#1a56db', Person: '#7a3db8', Industry: '#0e7c66', Institution: '#b26a00',
  Event: '#c0392b', Policy: '#2b6cb0', Document: '#6b7280',
}
function colorOf(label) { return LABEL_COLORS[label] || '#57606a' }

/** 把当前视图（邻居或路径）归一成 {nodes:[{id,label,name}], edges:[{from,to,relation,attrs}]}。 */
const visGraph = computed(() => {
  const nodes = new Map()
  const edges = []
  const addNode = (id, label, name) => {
    if (id === undefined || id === null || id === '') return
    const key = String(id)
    if (!nodes.has(key)) nodes.set(key, { id: key, label: label || '', name: name || '' })
    else if (name && !nodes.get(key).name) nodes.get(key).name = name
  }

  if (visMode.value === 'neighbors' && neighbors.value) {
    const focus = neighbors.value.node || {}
    const fid = String(focus.node_id ?? '')
    addNode(fid, focus.label, focus.name)
    for (const n of neighbors.value.nodes || []) addNode(n.node_id, n.label, n.name)
    for (const e of neighbors.value.edges || []) {
      const nb = String(e.neighbor ?? '')
      addNode(nb, e.neighbor_label, '')
      const from = e.direction === 'in' ? nb : fid
      const to = e.direction === 'in' ? fid : nb
      edges.push({ from, to, relation: e.relation, attrs: e })
    }
    return { nodes: [...nodes.values()], edges, focusId: fid }
  }

  if (visMode.value === 'paths' && paths.value) {
    for (const p of paths.value.paths || []) {
      const ids = p.node_ids || (p.nodes || []).map((x) => (typeof x === 'object' ? x.node_id : x))
      ;(p.nodes || []).forEach((n) => {
        if (typeof n === 'object') addNode(n.node_id, n.label, n.name)
        else addNode(n, '', '')
      })
      ;(p.edges || []).forEach((e, i) => {
        edges.push({ from: String(ids[i]), to: String(ids[i + 1]), relation: e.relation, attrs: e })
      })
    }
    const first = (paths.value.paths || [])[0]
    return { nodes: [...nodes.values()], edges, focusId: first ? String(first.start) : '' }
  }

  return { nodes: [], edges: [], focusId: '' }
})

const SVG_W = 660
const SVG_H = 440

/** 环形布局：有 focusId 时聚焦节点居中，其余均布圆周；否则全部均布圆周。 */
const positions = computed(() => {
  const { nodes, focusId } = visGraph.value
  const cx = SVG_W / 2
  const cy = SVG_H / 2
  const pos = {}
  const hasFocus = focusId && nodes.some((n) => n.id === focusId)
  if (hasFocus) pos[focusId] = { x: cx, y: cy }
  const ring = hasFocus ? nodes.filter((n) => n.id !== focusId) : nodes
  const R = Math.min(SVG_W, SVG_H) / 2 - 64
  ring.forEach((n, i) => {
    const r = ring.length <= 1 ? 0 : R
    const ang = (2 * Math.PI * i) / Math.max(1, ring.length) - Math.PI / 2
    pos[n.id] = { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) }
  })
  return pos
})

function nodePos(id) { return positions.value[String(id)] || { x: 0, y: 0 } }

function shortName(node) {
  const t = node.name || node.id
  return t.length > 12 ? t.slice(0, 11) + '…' : t
}
function edgeMid(e) {
  const a = nodePos(e.from)
  const b = nodePos(e.to)
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}
function selectNode(n) { selected.value = { kind: 'node', data: n } }
function selectEdge(e) { selected.value = { kind: 'edge', data: e } }

const scaleNote = computed(() => {
  const n = visGraph.value.nodes.length
  if (n > 60) return `当前图有 ${n} 个节点，标签较拥挤（布局上限约 60）。`
  if (n > 0) return `当前图有 ${n} 个节点、${visGraph.value.edges.length} 条边。`
  return ''
})
</script>

<template>
  <div>
    <!-- ① 实体检索 -->
    <div class="card">
      <h2>① 实体检索</h2>
      <div class="row">
        <input type="text" v-model="entKeyword" placeholder="keyword：实体名或股票代码（如 601633）"
               @keyup.enter="searchEntities" />
        <select v-model="entType" class="narrow">
          <option v-for="t in ENTITY_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <button class="btn primary" :disabled="entLoading" @click="searchEntities">
          {{ entLoading ? '查询中…' : '查询实体' }}
        </button>
      </div>
      <p v-if="entError" class="err">{{ entError.code ? '[' + entError.code + '] ' : '' }}{{ entError.message }}</p>
      <div v-else-if="entEmpty" class="empty">未检索到匹配结果（空结果，非错误）。</div>
      <table v-else-if="entities.length" class="grid">
        <thead><tr><th>node_id</th><th>label</th><th>name</th><th>stock_code</th><th></th></tr></thead>
        <tbody>
          <tr v-for="e in entities" :key="e.node_id">
            <td class="mono">{{ e.node_id }}</td>
            <td>{{ e.label }}</td>
            <td>{{ e.name }}</td>
            <td class="mono">{{ e.stock_code || '—' }}</td>
            <td><button class="btn" @click="loadNeighbors(e.node_id)">看一跳邻居</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ② 一跳邻居 -->
    <div class="card" v-if="nbLoading || nbError || neighbors">
      <h2>② 一跳邻居</h2>
      <p v-if="nbLoading" class="muted">加载中…</p>
      <p v-else-if="nbError" class="err">
        {{ nbError.code ? '[' + nbError.code + '] ' : '' }}{{ nbError.message }}
      </p>
      <template v-else-if="neighbors">
        <p class="focus">
          中心节点：<strong>{{ neighbors.node.name || neighbors.node.node_id }}</strong>
          <span class="tag">{{ neighbors.node.label }}</span>
          <span class="tag mono">{{ neighbors.node.node_id }}</span>
          <span class="muted">｜ 邻居 {{ neighbors.total }} 条</span>
        </p>
        <table class="grid" v-if="(neighbors.edges || []).length">
          <thead><tr><th>关系</th><th>方向</th><th>邻居</th><th>role</th><th>confidence</th>
            <th>source_doc_id</th><th>source_chunk_id</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in neighbors.edges" :key="i">
              <td>{{ e.relation }}</td>
              <td>{{ e.direction === 'in' ? '入' : '出' }}</td>
              <td>{{ e.neighbor }} <span class="muted">({{ e.neighbor_label }})</span></td>
              <td>{{ e.role || '—' }}</td>
              <td>{{ e.confidence ?? '—' }}</td>
              <td class="mono">{{ e.source_doc_id ?? '—' }}</td>
              <td class="mono">{{ e.source_chunk_id ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <button class="btn" @click="loadNeighbors(neighbors.node.node_id)">重绘于下方可视化</button>
      </template>
    </div>

    <!-- ③ 多跳路径 -->
    <div class="card">
      <h2>③ 多跳路径</h2>
      <div class="row wrap">
        <input type="text" v-model="pathForm.from_node" placeholder="from_node（起点 id，如 601633）" />
        <input type="text" v-model="pathForm.to_node" placeholder="to_node（终点 id，可空）" />
        <select v-model="pathForm.relation" class="narrow">
          <option value="">（不限关系）</option>
          <option v-for="r in RELATIONS" :key="r" :value="r">{{ r }}</option>
        </select>
        <label class="hop"><input type="radio" value="1" v-model="pathForm.hop" /> 1 跳</label>
        <label class="hop"><input type="radio" value="2" v-model="pathForm.hop" /> 2 跳</label>
        <button class="btn primary" :disabled="pathLoading" @click="runPaths">
          {{ pathLoading ? '查询中…' : '查路径' }}
        </button>
      </div>
      <p class="muted hint">
        规则：必须给 from_node；再给 to_node（定点模式）或 relation（定关系模式），二者至少其一。
      </p>
      <p v-if="pathError" class="err">{{ pathError.code ? '[' + pathError.code + '] ' : '' }}{{ pathError.message }}</p>
      <div v-else-if="pathEmpty" class="empty">未检索到匹配路径（空结果，非错误）。</div>
      <template v-else-if="paths && (paths.paths || []).length">
        <p class="muted">共 {{ paths.paths.length }} 条路径（hop={{ paths.hop }}）。</p>
        <ol class="path-list">
          <li v-for="(p, i) in paths.paths" :key="i">
            <span class="mono">
              <template v-for="(n, j) in (p.node_ids || [])" :key="j">
                <span class="pill">{{ n }}</span>
                <span v-if="j < p.edges.length" class="rel-arrow">
                  —{{ p.edges[j].relation }}→
                </span>
              </template>
            </span>
          </li>
        </ol>
      </template>
    </div>

    <!-- ④ 事件查询 -->
    <div class="card">
      <h2>④ 事件查询</h2>
      <div class="row wrap">
        <select v-model="evForm.event_type" class="narrow">
          <option value="">（不限事件类型）</option>
          <option v-for="t in EVENT_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
        <input type="text" v-model="evForm.stock_code" placeholder="stock_code（可空，如 601633）" />
        <input type="date" v-model="evForm.start_time" />
        <span class="muted">至</span>
        <input type="date" v-model="evForm.end_time" />
        <button class="btn primary" :disabled="evLoading" @click="searchEvents">
          {{ evLoading ? '查询中…' : '查事件' }}
        </button>
      </div>
      <p v-if="evError" class="err">{{ evError.code ? '[' + evError.code + '] ' : '' }}{{ evError.message }}</p>
      <div v-else-if="evEmpty" class="empty">未检索到匹配事件（空结果，非错误）。</div>
      <table v-else-if="events.length" class="grid">
        <thead><tr><th>event_id</th><th>类型</th><th>事件名</th><th>时间</th><th>confidence</th><th></th></tr></thead>
        <tbody>
          <tr v-for="e in events" :key="e.event_id">
            <td class="mono">{{ e.event_id }}</td>
            <td>{{ e.event_type }}</td>
            <td>{{ e.event_name }}</td>
            <td class="mono">{{ e.event_time || '—' }}</td>
            <td>{{ e.confidence ?? '—' }}</td>
            <td><button class="btn" @click="openEvent(e.event_id)">看详情</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 事件详情 -->
    <div class="card" v-if="detailLoading || detailError || eventDetail">
      <h2>事件详情</h2>
      <p v-if="detailLoading" class="muted">加载中…</p>
      <p v-else-if="detailError" class="err">
        {{ detailError.code ? '[' + detailError.code + '] ' : '' }}{{ detailError.message }}
      </p>
      <template v-else-if="eventDetail">
        <h3 class="sub">{{ eventDetail.event.event_name }}</h3>
        <p class="muted">
          {{ eventDetail.event.event_id }}｜类型 {{ eventDetail.event.event_type }}｜
          时间 {{ eventDetail.event.event_time || '—' }}｜confidence {{ eventDetail.event.confidence ?? '—' }}
        </p>
        <p class="desc">{{ eventDetail.event.description }}</p>

        <h4 class="sub2">参与者</h4>
        <ul class="mini">
          <li v-for="p in eventDetail.participants" :key="p.node_id + p.role">
            <strong>{{ p.name }}</strong>（{{ p.node_id }}／{{ p.label }}）
            — role={{ p.role || '—' }}、confidence={{ p.confidence ?? '—' }}、
            source_doc_ids={{ (p.source_doc_ids || []).join(',') || '—' }}、
            source_chunk_ids={{ (p.source_chunk_ids || []).join(',') || '—' }}
          </li>
          <li v-if="!(eventDetail.participants || []).length" class="muted">（无参与者）</li>
        </ul>

        <h4 class="sub2">发布机构</h4>
        <ul class="mini">
          <li v-for="s in (eventDetail.issuers || [])" :key="s.node_id">
            <strong>{{ s.name }}</strong>（{{ s.node_id }}／{{ s.label }}）
          </li>
          <li v-if="!(eventDetail.issuers || []).length" class="muted">
            {{ eventDetail.issuer ? eventDetail.issuer.name || eventDetail.issuer : '（无发布机构）' }}
          </li>
        </ul>

        <h4 class="sub2">相关政策</h4>
        <ul class="mini">
          <li v-for="p in (eventDetail.policies || [])" :key="p.node_id">
            <strong>{{ p.name }}</strong>（{{ p.node_id }}）— 关系 {{ p.relation }}
          </li>
          <li v-if="!(eventDetail.policies || []).length" class="muted">（无相关政策）</li>
        </ul>

        <h4 class="sub2">多来源证据（按 publish_time 升序）</h4>
        <table class="grid" v-if="detailEvidences.length">
          <thead><tr><th>doc_id</th><th>chunk_id</th><th>标题</th><th>来源</th><th>发布时间</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in detailEvidences" :key="i">
              <td class="mono">{{ e.doc_id }}</td>
              <td class="mono">{{ e.chunk_id }}</td>
              <td>{{ e.title }}</td>
              <td>{{ e.source }}</td>
              <td class="mono">{{ (e.publish_time || '').replace('T', ' ').slice(0, 16) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">（无证据）</p>
      </template>
    </div>

    <!-- ⑤ 轻量自绘 SVG 可视化 -->
    <div class="card">
      <h2>⑤ 图谱可视化（轻量自绘 SVG）</h2>
      <p class="muted hint">
        {{ scaleNote || '先执行「看一跳邻居」或「查路径」，下方将绘制对应的节点—关系图。' }}
        点击节点或边，右侧展示其证据属性。
      </p>
      <div class="vis-wrap" v-if="visGraph.nodes.length">
        <svg :viewBox="`0 0 ${SVG_W} ${SVG_H}`" class="vis" role="img">
          <!-- 边 -->
          <g>
            <line v-for="(e, i) in visGraph.edges" :key="'e' + i"
                  :x1="nodePos(e.from).x" :y1="nodePos(e.from).y"
                  :x2="nodePos(e.to).x" :y2="nodePos(e.to).y"
                  :class="['edge', { sel: selected && selected.kind === 'edge' && selected.data === e }]"
                  @click="selectEdge(e)" />
            <text v-for="(e, i) in visGraph.edges" :key="'el' + i"
                  :x="edgeMid(e).x" :y="edgeMid(e).y" class="edge-label" @click="selectEdge(e)">
              {{ e.relation }}
            </text>
          </g>
          <!-- 节点 -->
          <g>
            <circle v-for="n in visGraph.nodes" :key="'n' + n.id"
                    :cx="nodePos(n.id).x" :cy="nodePos(n.id).y" r="9"
                    :fill="colorOf(n.label)"
                    :class="['node', { sel: selected && selected.kind === 'node' && selected.data.id === n.id }]"
                    @click="selectNode(n)" />
            <text v-for="n in visGraph.nodes" :key="'nt' + n.id"
                  :x="nodePos(n.id).x" :y="nodePos(n.id).y - 13" class="node-label"
                  @click="selectNode(n)">
              {{ shortName(n) }}
            </text>
          </g>
        </svg>

        <aside class="inspector">
          <div v-if="!selected" class="muted">未选中元素。</div>
          <template v-else-if="selected.kind === 'node'">
            <h4>节点属性</h4>
            <p><strong>{{ selected.data.name || '—' }}</strong></p>
            <p class="mono muted">node_id = {{ selected.data.id }}</p>
            <p class="muted">label = {{ selected.data.label || '—' }}</p>
          </template>
          <template v-else>
            <h4>边属性</h4>
            <p><strong>{{ selected.data.relation }}</strong></p>
            <p class="mono muted">{{ selected.data.from }} → {{ selected.data.to }}</p>
            <ul class="attr">
              <li>direction = {{ selected.data.attrs.direction ?? '—' }}</li>
              <li>role = {{ selected.data.attrs.role ?? '—' }}</li>
              <li>confidence = {{ selected.data.attrs.confidence ?? '—' }}</li>
              <li>source_doc_id = {{ selected.data.attrs.source_doc_id ?? '—' }}</li>
              <li>source_chunk_id = {{ selected.data.attrs.source_chunk_id ?? '—' }}</li>
              <li>evidence_doc_id = {{ selected.data.attrs.evidence_doc_id ?? '—' }}</li>
            </ul>
          </template>
          <p class="legend-title muted">图例</p>
          <p class="legend">
            <span v-for="(c, k) in LABEL_COLORS" :key="k" class="legend-item">
              <i :style="{ background: c }"></i>{{ k }}
            </span>
          </p>
        </aside>
      </div>
      <div v-else class="empty">暂无可视化数据。</div>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; gap: 8px; align-items: center; }
.row.wrap { flex-wrap: wrap; }
.row input { flex: 1 1 200px; }
.row select.narrow { flex: 0 0 168px; }
.hop { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; white-space: nowrap; }
.hint { font-size: 12px; margin: 8px 0 0; }
.focus { margin: 0 0 10px; }
.sub { margin: 12px 0 4px; font-size: 14px; }
.sub2 { margin: 12px 0 4px; font-size: 13px; color: var(--ink-soft); }
.desc { margin: 4px 0 0; }
ul.mini { margin: 0; padding-left: 18px; font-size: 13px; }
.path-list { margin: 6px 0 0; padding-left: 20px; font-size: 13px; }
.pill {
  display: inline-block; background: var(--accent-soft); border: 1px solid #c7d7f8;
  border-radius: 4px; padding: 0 6px; font-weight: 600;
}
.rel-arrow { color: #7a5b00; font-weight: 600; }
.vis-wrap { display: flex; gap: 14px; align-items: flex-start; }
.vis {
  flex: 1 1 auto; background: #fbfcfe; border: 1px solid var(--line); border-radius: 6px;
  height: 440px;
}
.edge { stroke: #b7c0cc; stroke-width: 1.4; cursor: pointer; }
.edge.sel { stroke: var(--accent); stroke-width: 3; }
.edge-label { font-size: 10px; fill: #7a5b00; cursor: pointer; text-anchor: middle; }
.node { stroke: #fff; stroke-width: 2; cursor: pointer; }
.node.sel { stroke: #111; stroke-width: 3; }
.node-label { font-size: 11px; fill: var(--ink); text-anchor: middle; cursor: pointer; }
.inspector {
  flex: 0 0 250px; border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px;
  background: #fff; min-height: 120px;
}
.inspector h4 { margin: 0 0 6px; font-size: 13px; }
.inspector p { margin: 3px 0; font-size: 13px; }
ul.attr { margin: 6px 0 0; padding-left: 16px; font-size: 12px; }
.legend-title { margin-top: 12px; font-size: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; }
.legend-item { display: inline-flex; align-items: center; gap: 4px; }
.legend-item i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
</style>

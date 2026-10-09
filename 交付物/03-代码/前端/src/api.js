// 交付物/03-代码\前端\src\api.js —— 前端与后端的**唯一**通信层（第 9 阶段 T9）
//
// 职责（《24》第4.3节 与 第4 条任务要求）：
//   1. 拼 URL：所有请求一律以 `/api` 开头，由 Vite dev server 代理到后端 8000；
//   2. 解析后端信封：成功取 `{data, meta}`，失败取 `{code, message}`；
//   3. 把 `{code, message}` 变成**可展示的错误**（`ApiError`，带 code／message／httpStatus）；
//   4. 会话：首次访问用 `crypto.randomUUID()` 生成 `session_id` 存 `localStorage`，
//      此后所有需要会话的请求自动带上（格式决策 6；第一版不启用登录，无登录入口）。
//
// 三条纪律：
//   * 本文件**不含任何密钥、模型端点、数据库连接串**（硬约束 2／14）——只出现相对路径 `/api/*`。
//   * 后端错误响应的 `message` **可直接展示**（后端已保证响应体只有 code／message，无 detail）。
//   * `2002` 的语义是 **HTTP 200 的空结果**，不是错误：`get()` 照常返回 data，
//     由调用方按「空结果」（不是异常）分支处理。

const API_PREFIX = '/api'          // 后端路由前缀（不写后端主机名，交由代理转发）
const SESSION_KEY = 'qa-console-session-id'   // localStorage 键名（仅前端本地，不含任何库名／凭据）

// --------------------------------------------------------------------------
// 1. 可展示的错误类型
// --------------------------------------------------------------------------
export class ApiError extends Error {
  /**
   * @param {number} code   后端错误码（1001／1002／…／9999）；网络层失败时用 0
   * @param {string} message 可直接展示给用户的文本（来自后端 message，或本层的兜底文案）
   * @param {number} [httpStatus] HTTP 状态码；网络层失败时 undefined
   */
  constructor(code, message, httpStatus) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

// --------------------------------------------------------------------------
// 2. 会话标识（格式决策 6）
// --------------------------------------------------------------------------
/** 取得（必要时生成）会话标识。首次访问用 `crypto.randomUUID()` 生成并落 localStorage。 */
export function getSessionId() {
  let sid = null
  try {
    sid = window.localStorage.getItem(SESSION_KEY)
  } catch (e) {
    // localStorage 被禁用（隐私模式等）：退化为内存态会话，仍可完成单页会话内的问答
    sid = null
  }
  if (!sid) {
    // crypto.randomUUID 在安全上下文（http://127.0.0.1 属安全上下文）可用；
    // 兜底：手工拼一个 UUID v4 形态的 36 字符串，满足 question.session_id 的 CHAR(36)
    sid = (window.crypto && typeof window.crypto.randomUUID === 'function')
      ? window.crypto.randomUUID()
      : fallbackUuid()
    try {
      window.localStorage.setItem(SESSION_KEY, sid)
    } catch (e) {
      /* 落不了盘就用内存里的这一份，不阻断功能 */
    }
  }
  return sid
}

/** `crypto.randomUUID` 不可用时的兜底：拼一个 UUID v4 形态的字符串（36 字符）。 */
function fallbackUuid() {
  const hex = '0123456789abcdef'
  let out = ''
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) { out += '-'; continue }
    if (i === 14) { out += '4'; continue }
    const r = Math.floor(Math.random() * 16)
    out += (i === 19) ? hex[(r & 0x3) | 0x8] : hex[r]
  }
  return out
}

// --------------------------------------------------------------------------
// 3. 核心请求
// --------------------------------------------------------------------------
/** 把查询参数对象拼成 query string（跳过 undefined／null；空串保留，交由后端判非法）。 */
function qs(params) {
  if (!params) return ''
  const parts = []
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

/**
 * 统一 fetch：返回后端信封里的 `data`。
 * 失败（HTTP 非 2xx／响应体含 code）时抛 `ApiError`，其 `message` 可直接展示。
 *
 * @param {string} path  形如 `/qa/ask`（相对 `/api`）
 * @param {{method?:string, body?:object, params?:object, withSession?:boolean}} [opts]
 */
export async function request(path, opts = {}) {
  const { method = 'GET', body, params, withSession = false } = opts
  const query = { ...(params || {}) }
  if (withSession) query.session_id = getSessionId()
  const url = `${API_PREFIX}${path}${qs(query)}`

  const init = { method, headers: {} }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let resp
  try {
    resp = await fetch(url, init)
  } catch (e) {
    // 网络层失败（后端未起／代理不通／断网）：给一个可展示的错误，code 用 0 标记「非后端错误码」
    throw new ApiError(0, `无法连接后端服务（${method} ${url}）：${e.message || e}`, undefined)
  }

  let payload = null
  const text = await resp.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch (e) {
      // 后端异常时偶发的非 JSON 响应（如代理 502 页面）：原文摘要进错误消息
      throw new ApiError(0, `后端返回了非 JSON 响应（HTTP ${resp.status}）：${text.slice(0, 300)}`,
        resp.status)
    }
  }

  // 错误响应：HTTP 非 2xx，或响应体带 `code` 字段（后端错误一律 {code, message}）
  if (!resp.ok || (payload && typeof payload.code === 'number')) {
    const code = payload && typeof payload.code === 'number' ? payload.code : resp.status
    const message = (payload && payload.message) || `请求失败（HTTP ${resp.status}）`
    throw new ApiError(code, message, resp.status)
  }

  // 成功响应：取 data（后端成功信封为 {data, meta}）
  return payload ? payload.data : null
}

/** 成功信封里的 `meta`（dataset_version／data_cutoff_time）；供顶栏显示数据截至。 */
export async function requestMeta(path, opts = {}) {
  const query = { ...((opts && opts.params) || {}) }
  if (opts && opts.withSession) query.session_id = getSessionId()
  const url = `${API_PREFIX}${path}${qs(query)}`
  const resp = await fetch(url, { method: (opts && opts.method) || 'GET' })
  const text = await resp.text()
  const payload = text ? JSON.parse(text) : null
  if (!resp.ok || (payload && typeof payload.code === 'number')) {
    throw new ApiError(payload && payload.code, (payload && payload.message) || `HTTP ${resp.status}`,
      resp.status)
  }
  return { data: payload ? payload.data : null, meta: payload ? payload.meta : null }
}

// --------------------------------------------------------------------------
// 4. 接口清单（与后端表 4-13 的路径一一对应）
// --------------------------------------------------------------------------

// —— 问答与配置（api\qa.py）——
/** POST /api/qa/ask —— 提问（固定 C 组）。体只允许 {question, session_id}（硬约束 9）。 */
export function askQuestion(question) {
  return request('/qa/ask', { method: 'POST', body: { question, session_id: getSessionId() } })
}
/** GET /api/qa/answers/{answer_id} —— 单条回答（含证据与图谱路径）。 */
export function getAnswer(answerId) {
  return request(`/qa/answers/${encodeURIComponent(answerId)}`)
}
/** GET /api/config/meta —— 只读元信息（含 data_cutoff_time）。 */
export function getConfigMeta() {
  return requestMeta('/config/meta')
}

// —— 证据与原文（api\evidence.py）——
/** GET /api/evidence/{answer_id} —— 四类分组计数 ＋ 证据明细。 */
export function getEvidence(answerId) {
  return request(`/evidence/${encodeURIComponent(answerId)}`)
}
/** GET /api/evidence/{answer_id}/graph-path —— is_graph_extended／paths／display_mode。 */
export function getGraphPath(answerId) {
  return request(`/evidence/${encodeURIComponent(answerId)}/graph-path`)
}
/** GET /api/documents/{doc_id}/chunks/{chunk_id} —— 正文与相邻块。 */
export function getChunk(docId, chunkId) {
  return request(`/documents/${encodeURIComponent(docId)}/chunks/${encodeURIComponent(chunkId)}`)
}

// —— 历史记录（api\history.py）——
/** GET /api/history —— 按会话分页列出（强制带 session_id）。 */
export function listHistory(page = 1, pageSize = 20) {
  return request('/history', { params: { page, page_size: pageSize }, withSession: true })
}
/** GET /api/history/{question_id} —— 回看一条（只还原三表内容，不重渲染图谱路径）。 */
export function getHistoryDetail(questionId) {
  return request(`/history/${encodeURIComponent(questionId)}`, { withSession: true })
}

// —— 图谱（api\graph.py）——
/** GET /api/graph/entities —— 按 keyword／type 查实体。 */
export function listEntities(params = {}) {
  return request('/graph/entities', { params })
}
/** GET /api/graph/entities/{node_id}/neighbors —— 一跳邻居。 */
export function getNeighbors(nodeId, params = {}) {
  return request(`/graph/entities/${encodeURIComponent(nodeId)}/neighbors`, { params })
}
/** GET /api/graph/paths —— 多跳路径（from_node ＋ to_node 或 relation、hop）。 */
export function getPaths(params = {}) {
  return request('/graph/paths', { params })
}
/** GET /api/graph/events —— 按事件类型／股票代码／时间窗查事件。 */
export function listEvents(params = {}) {
  return request('/graph/events', { params })
}
/** GET /api/graph/events/{event_id} —— 事件详情（参与者／发布机构／政策／多来源证据）。 */
export function getEventDetail(eventId) {
  return request(`/graph/events/${encodeURIComponent(eventId)}`)
}
/**
 * GET /api/graph/entities/{node_id} —— 单个实体详情。
 * 返回 `{node{node_id,label,name,stock_code}, properties, property_keys, property_notes,
 * degree{out,in_,total}, counts{neighbors,relations,documents,chunks}, params, scope, source}`。
 * 「实体档案」块直接渲染 properties（键序＝property_keys），**不派生、不推测**。
 */
export function getEntity(nodeId) {
  return request(`/graph/entities/${encodeURIComponent(nodeId)}`)
}
/**
 * GET /api/graph/entities/{node_id}/evidence —— 实体证据（depth=1 一跳 / 2 两跳）。
 * 返回 `{node, counts{neighbors,relations,documents,chunks}, documents[]{doc_id,title,source,
 * publish_time,url,category,support_relations,missing,chunks[]{chunk_id,chunk_index,
 * relations[]{relation,neighbor,role,confidence}}}, documents_total, chunks_total,
 * relations_without_evidence[]{relation,neighbor,note}, depth, params, scope}`。
 */
export function getEntityEvidence(nodeId, depth = 1, params = {}) {
  return request(`/graph/entities/${encodeURIComponent(nodeId)}/evidence`,
    { params: { depth, ...params } })
}

// —— 实时数据区（api\market.py · 四条只读接口 · scope=display_only）——
// 三条纪律：只作展示、不进问答证据链；外部源不可达时 connected=false 仍返回 HTTP 200；
// 页面按 connected／reason **如实显示「未接入」**，绝不编造价格／涨跌幅／新闻。
/** GET /api/market/quote —— 实时行情（codes 缺省取后端默认股）。 */
export function getMarketQuote(codes) {
  return request('/market/quote', { params: codes ? { codes } : {} })
}
/** GET /api/market/announcements —— 个股公告（code 必填）。 */
export function getMarketAnnouncements(code, params = {}) {
  return request('/market/announcements', { params: { code, ...params } })
}
/** GET /api/market/news —— 个股新闻（keyword 必填）。 */
export function getMarketNews(keyword, params = {}) {
  return request('/market/news', { params: { keyword, ...params } })
}
/** GET /api/market/reports —— 语料内近一周文档（不依赖外部源，降级形态常驻）。 */
export function getMarketReports(params = {}) {
  return request('/market/reports', { params })
}

/**
 * 健康检查（用于顶栏「后端状态」提示；非表 4-13 接口，见《24》格式决策 9）。
 *
 * 注意：`/api/health` 的响应体**不是** `{data, meta}` 信封，而是直接返回
 * `{status, mysql, neo4j, vector_index, model_config}`（见 `交付物/03-代码\后端\main.py`），
 * 故这里单独取原始对象，不走 `request()` 的取 `data` 逻辑。
 */
export async function getHealth() {
  const resp = await fetch(`${API_PREFIX}/health`)
  if (!resp.ok) throw new ApiError(resp.status, `健康检查失败（HTTP ${resp.status}）`, resp.status)
  return resp.json()
}

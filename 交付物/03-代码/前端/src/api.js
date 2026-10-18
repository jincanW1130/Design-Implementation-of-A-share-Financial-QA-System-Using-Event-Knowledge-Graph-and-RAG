// 交付物/03-代码\前端\src\api.js —— 前端与后端的**唯一**通信层（第 9 阶段 T9）
//
// 职责（《24》第4.3节 与 第4 条任务要求）：
//   1. 拼 URL：所有请求一律以 `/api` 开头，由 Vite dev server 代理到后端 8000；
//   2. 解析后端信封：成功取 `{data, meta}`，失败取 `{code, message}`；
//   3. 把 `{code, message}` 变成**可展示的错误**（`ApiError`，带 code／message／httpStatus）；
//   4. 会话：首次访问用 `crypto.randomUUID()` 生成 `session_id` 存 `localStorage`，
//      此后所有需要会话的请求自动带上（格式决策 6；第一版不启用登录，无登录入口）。
//   5. 只读端点做 60 秒短期缓存 ＋ 并发合并（第 4 节）：依据真实浏览器的请求账，
//      省掉一次会话内对**同一份不可变数据**的重复请求——省的是限流额度，不改动任何数据与呈现。
//
// 三条纪律：
//   * 本文件**不含任何密钥、模型端点、数据库连接串**（硬约束 2／14）——只出现相对路径 `/api/*`。
//   * 后端错误响应的 `message` **可直接展示**（后端已保证响应体只有 code／message，无 detail）。
//   * `2002` 的语义是 **HTTP 200 的空结果**，不是错误：`get()` 照常返回 data，
//     由调用方按「空结果」（不是异常）分支处理。
//
// 2026-10-18（第 3 轮）：补「取消等待」与前端超时。
//   · 后端问答链路单次最长 300 秒（`config.ANSWER.timeout_seconds`），前端在 320 秒处兜底；
//   · 取消只停止**浏览器等待**，不终止后端子进程（HTTP 没有反向取消通道）——界面文案
//     必须如实说明「后端可能仍会完成并写进本会话历史」，不能假装已彻底中止。

const API_PREFIX = '/api'          // 后端路由前缀（不写后端主机名，交由代理转发）
const SESSION_KEY = 'qa-console-session-id'   // localStorage 键名（仅前端本地，不含任何库名／凭据）

/** 提问的前端等待上限：后端链路超时 300 秒，前端留 20 秒余量（毫秒）。 */
export const ASK_TIMEOUT_MS = 320 * 1000

// --------------------------------------------------------------------------
// 1. 可展示的错误类型
// --------------------------------------------------------------------------
export class ApiError extends Error {
  /**
   * @param {number} code   后端错误码（1001／1002／…／9999）；网络层失败时用 0
   * @param {string} message 可直接展示给用户的文本（来自后端 message，或本层的兜底文案）
   * @param {number} [httpStatus] HTTP 状态码；网络层失败时 undefined
   * @param {boolean} [aborted] 是否由调用方取消或前端超时导致（不是后端错误，也不是断网）
   */
  constructor(code, message, httpStatus, aborted = false) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
    this.aborted = !!aborted
  }
}

/** AbortController.abort() 触发的异常在各运行时的形态：一律按「已取消」处理。 */
function isAbortError(e) {
  return !!e && (e.name === 'AbortError' || e.code === 20 || e.code === 'ABORT_ERR')
}

// --------------------------------------------------------------------------
// 1.1 错误码 → 面向用户的文案（2026-10-18 第 8 轮：拒答矩阵前端联动）
// --------------------------------------------------------------------------
// 后端 `errors.CODES` 的 message 是**诊断／管理口径**（例如 3004 的「装配账目守卫未通过
// （上游一致性守卫，非图谱或模型故障）」），直接展示给普通用户只会造成误解。
// 这里只做**展示层翻译**：错误码、HTTP 状态、后端 message 与响应体语义一律不改；
// 需要排查时，页面仍保留错误码，原文可展开查看（见 AskView／AnswerView 的「技术信息」）。
// 2002（无证据）不是错误：它走 HTTP 200＋empty，由调用方按空结果提示，不进入本表。
export const FRIENDLY_ERRORS = Object.freeze({
  1001: '问题格式不对：不能为空、不能超过 500 字，也不能包含看不见的控制字符。请修改后再试。',
  1002: '请求参数格式不正确。请检查筛选条件或链接后重试。',
  1003: '缺少必填信息，请补全后再试。',
  1004: '请求太频繁：每分钟最多 60 次。请稍等约 1 分钟再试；页面已自动重试过一次。',
  1005: '当前操作方式不受支持，请使用页面上的按钮重试。',
  2001: '没有找到这条记录：可能已被清理，或不属于当前浏览器会话。',
  2003: '这份文档已被历史回答引用，不能直接修改或删除；如需更新，请以新文档版本导入。',
  3001: '知识图谱服务暂时不可用，本次无法补充图谱路径。请稍后重试；已检索到的文字证据不会丢失。',
  3002: '大模型响应超时，本次没有生成答案。请稍后重试，或把问题拆小一些。',
  3003: '检索服务（向量索引）暂时不可用，本次无法完成检索。请稍后重试。',
  3004: '这次生成的答案没有通过系统的可信性校验，已被拦截、不会展示给用户。请换一种问法重试；若反复出现，请联系管理员。',
  4001: '管理员凭据无效或未配置，请检查令牌与配置。',
  4002: '当前身份没有执行这个操作的权限。',
  9999: '服务内部出现异常，请稍后重试；若反复出现，请联系管理员。',
})

/**
 * 取错误码对应的**用户可读**文案：命中映射表用映射文案；未登记的错误码与网络层错误
 * （code=0）沿用调用方给的兜底文本（通常已是可直接展示的后端／网络 message）。
 *
 * @param {number|string} code 后端错误码（0 表示网络层／取消）
 * @param {string} [fallback] 未命中映射时的兜底文案
 * @returns {string} 可直接展示给用户的文本
 */
export function friendlyMessageOf(code, fallback) {
  const text = FRIENDLY_ERRORS[Number(code)]
  if (text) return text
  return fallback || '请求没有成功，请稍后重试。'
}

// --------------------------------------------------------------------------
// 2. 会话标识（格式决策 6）
// --------------------------------------------------------------------------
/** 生成一个新的会话标识（36 字符 UUID 形态，满足 `question.session_id` 的 CHAR(36)）。 */
function newSessionId() {
  // crypto.randomUUID 在安全上下文（http://127.0.0.1 属安全上下文）可用；
  // 兜底：手工拼一个 UUID v4 形态的 36 字符串
  return (window.crypto && typeof window.crypto.randomUUID === 'function')
    ? window.crypto.randomUUID()
    : fallbackUuid()
}

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
    sid = newSessionId()
    try {
      window.localStorage.setItem(SESSION_KEY, sid)
    } catch (e) {
      /* 落不了盘就用内存里的这一份，不阻断功能 */
    }
  }
  return sid
}

/**
 * 重置会话：生成新会话号写回 localStorage，并清空只读缓存。
 *
 * **只换浏览器本地会话号，不删除任何服务端记录**——旧会话的 question／answer／evidence
 * 仍留在库里，只是不再出现在本浏览器的历史页（会话隔离 FR-06 的正常结果）。
 * 返回值是新会话号，供界面立即显示。
 */
export function resetSessionId() {
  const sid = newSessionId()
  try {
    window.localStorage.setItem(SESSION_KEY, sid)
  } catch (e) {
    /* localStorage 不可用时：本次调用返回的新号只对调用方可见，不阻断 */
  }
  clearApiCache()
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
// 3. 限流（429／1004）韧性：一次性退避重试 ＋ 受限态订阅
// --------------------------------------------------------------------------
// 为什么加这一层（依据实测事实，不是推测）：
//   · 后端 `RateLimitMiddleware` 是**按来源 IP 的全局滑动窗口**（窗口 60 秒／上限 60 次，
//     仅 `/api/health` 豁免）。该参数是第 9 阶段验收门禁锁定的登记值，前端不得改它；
//   · 一次真实浏览器走查（首屏 → 提问页 → 图谱页 → 搜两次 → 历史页 → 看一条记录）实测发出
//     **84 次** `/api/*` 请求，其中图谱页单独约占 38 次——所以正常使用约 40 秒后整站开始 429，
//     后端日志里 `/api/config/meta`、`/api/history`、`/api/market/quote`、
//     `/api/graph/entities/{id}/evidence` 等**全都**被 429 拒过；
//   · 旧行为是调用点把 429 静默吞成「（无结果）／未检索到／未接入」，用户读到的是
//     「没有这家公司／没有这段数据」——方向性误读。
// 因此这里只做两件事，取值一律保守：① 幂等请求的**一次、且仅一次**退避重试；
// ② 把「正在退避」这一事实以极小的订阅接口暴露给界面，使限流**可感知**。
// 不引入任何新的网络依赖、不新增 npm 包（对应《02》「不引入任何被排除的技术」）。

/** 退避等待上限（毫秒）：无论 `Retry-After` 给多大，都钳到 5 秒以内（保守值）。 */
const RETRY_WAIT_CAP_MS = 5000
/** `Retry-After` 缺失或不可解析（如 HTTP-date 形态）时的兜底等待（毫秒）。 */
const RETRY_WAIT_FALLBACK_MS = 1500
/** 受限态倒计时刷新间隔（毫秒）：够界面看到秒数在走，又不至于高频重渲染。 */
const THROTTLE_TICK_MS = 250

const throttleSubs = new Set()   // 订阅者（界面的限流横幅等）；订阅方的异常不影响请求主流程
let throttleUntil = 0            // 受限态的「解除时刻」（Date.now() 毫秒）；0＝未受限
let throttleEpisodeStart = 0     // 本轮受限态的起点：用于把整轮等待钳在 5 秒内（不叠加）
let throttleTick = null          // 受限期间的单一定时器：并发退避共用同一个，不各起一个
let throttleLastSec = 0          // 已广播过的整秒读数：只在读数变化时才广播，避免无谓重渲染
let throttleWaiters = 0          // 正在退避等待的请求数：>0 时不因「别的请求成功」而抹掉受限态

/**
 * 只读快照。**不含任何敏感信息**（无后端地址、无密钥、无库名／模型名），
 * `message` 面向用户、可直接展示。
 * @returns {{active:boolean, retryAfterSeconds:number, message:string}}
 */
export function throttleState() {
  const left = throttleUntil - Date.now()
  const active = left > 0
  return {
    active,
    // 受限期间恒 ≥1（向上取整，界面不会显示「还需 0 秒」）；未受限为 0
    retryAfterSeconds: active ? Math.max(1, Math.ceil(left / 1000)) : 0,
    message: active
      ? '每分钟请求数已达上限，正在自动重试；此期间的空白不代表数据不存在，不是数据缺失。'
      : '',
  }
}

/**
 * 订阅受限态变化：订阅时立即回放一次当前态，此后仅在「进入／离开受限态」或「整秒读数变化」
 * 时回调。
 * @param {(s:{active:boolean,retryAfterSeconds:number,message:string})=>void} fn
 * @returns {() => void} 取消订阅函数
 */
export function onThrottleChange(fn) {
  if (typeof fn !== 'function') return () => {}
  throttleSubs.add(fn)
  try { fn(throttleState()) } catch (e) { /* 订阅方自己的异常不该拖垮请求 */ }
  return () => { throttleSubs.delete(fn) }
}

/** 广播当前受限态；读数未变则不广播（受限期间读数每秒一定在变）。 */
function broadcastThrottle() {
  const snap = throttleState()
  const sec = snap.active ? snap.retryAfterSeconds : 0
  if (sec === throttleLastSec) return
  throttleLastSec = sec
  for (const fn of Array.from(throttleSubs)) {
    try { fn(snap) } catch (e) { /* 同上：订阅方异常只被吞掉，不影响通信层 */ }
  }
}

/**
 * 进入受限态并等待相应时长。
 * **不叠加**：并发退避只共享一个「解除时刻」与一个定时器，且整轮受限态被钳在
 * `RETRY_WAIT_CAP_MS`（5 秒）以内——不会出现 429 一来就把等待一段段累加上去的情况。
 * 等待期间若受限态被提前解除（例如到期由定时器收尾、或没有其它等待者时被一次成功请求清零），
 * 循环会立刻放行。
 */
async function waitThrottleRelease(waitMs) {
  const now = Date.now()
  if (throttleUntil <= now) throttleEpisodeStart = now   // 新一轮受限态
  const target = now + Math.max(0, waitMs)
  if (target > throttleUntil) throttleUntil = target
  const episodeCap = throttleEpisodeStart + RETRY_WAIT_CAP_MS
  if (throttleUntil > episodeCap) throttleUntil = episodeCap
  if (!throttleTick) {
    throttleTick = setInterval(() => {
      if (Date.now() >= throttleUntil) exitThrottle()
      else broadcastThrottle()
    }, THROTTLE_TICK_MS)
  }
  throttleWaiters += 1
  broadcastThrottle()
  while (Date.now() < throttleUntil) {
    const left = throttleUntil - Date.now()
    await new Promise((r) => setTimeout(r, Math.min(left, THROTTLE_TICK_MS)))
  }
  throttleWaiters -= 1
  // 退避结束即离开受限态（无论随后的重试是否成功）
  if (throttleWaiters <= 0) exitThrottle()
}

/** 离开受限态：清掉共享定时器并广播一次。 */
function exitThrottle() {
  throttleUntil = 0
  if (throttleTick) { clearInterval(throttleTick); throttleTick = null }
  broadcastThrottle()
}

/**
 * 「有请求成功了」时调用。实测场景里图谱页会并发发出几十条请求：若一次限流退避期间
 * 任何一条其它请求成功就立刻抹掉受限态，横幅会在被限流的一瞬间就被清掉、根本看不见——
 * 所以只在**没有请求正在退避等待**时才离开受限态；有等待者的那一轮，由退避结束来收尾。
 */
function exitThrottleIfIdle() {
  if (throttleWaiters <= 0) exitThrottle()
}

/**
 * 由响应头 `Retry-After` 计算退避时长：按秒解析 → 毫秒后**上限钳到 5 秒**；
 * 缺失／不可解析（含 HTTP-date 形态）时用 1.5 秒兜底。
 */
function retryWaitMs(rawRetryAfter) {
  const sec = Number(rawRetryAfter)
  if (!Number.isFinite(sec) || sec <= 0) return RETRY_WAIT_FALLBACK_MS
  return Math.min(sec * 1000, RETRY_WAIT_CAP_MS)
}

/** 读响应头：测试替身与个别环境可能没有 `headers`，缺失一律回 null。 */
function headerValue(resp, name) {
  return (resp && resp.headers && typeof resp.headers.get === 'function')
    ? resp.headers.get(name) : null
}

/**
 * 可重试判据——**只对「重试不会产生副作用或额外成本」的请求重试**：
 *   · `GET`（本文件绝大多数接口）；
 *   · 任何带 `body.query` 的请求（本项目的「查询型 POST」都走这个字段）；
 *   · **`POST /api/qa/ask`**（2026-10-17 用户测试后补）。
 *
 * 为什么把 `/qa/ask` 也算进来（有实测依据，不是想当然）：
 *   429／1004 **是限流中间件在 `main.py:182-194` 直接拒掉的**，`return response` 发生在
 *   `await call_next(request)` **之前**——也就是说被限流的这次请求**根本没有进入业务逻辑、
 *   没有触发任何模型调用**（模型调用在 `services/qa_service.ask` 里）。所以对「被限流」的
 *   `/qa/ask` 重试一次，既不会重复扣费，也不会重复落库。
 *
 * 反过来，**非限流**的失败（超时 3002／模型侧错误）**仍然绝不重试**：那种情况下模型可能已经
 * 调用过、`qa_service` 也可能已经落库，重试会带来重复成本与重复记录。判据在 `sendRequest()`
 * 里由「`resp.status === 429 || code === 1004`」把住，与这里的分档是两道独立闸门。
 *
 * 实测背景：最终一轮 UAT 里 `/qa/ask` 撞上限流后，旧行为是按钮卡在「生成中…」达 481.8 s
 * （脚本 8 分钟兜底才结束），用户完全不知道要重试——这是把「可重试」判得过窄的直接后果。
 */
function isIdempotentRequest(method, body, path) {
  const m = String(method).toUpperCase()
  if (m === 'GET') return true
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'query')) return true
  return m === 'POST' && typeof path === 'string' && /^\/qa\/ask\/?$/.test(path)
}

// --------------------------------------------------------------------------
// 4. 不可变只读端点的短期缓存（TTL ＋ 容量上限 ＋ LRU ＋ 并发合并）
// --------------------------------------------------------------------------
// 为什么加这一层（依据实测事实，不是推测）：
//   · 后端 `RateLimitMiddleware` 是**按来源 IP 的全局滑动窗口**（60 次／60 秒，仅
//     `/api/health` 豁免），整站共用一份额度。`测试/uat/测请求预算.mjs` 在真实浏览器里
//     量到一次完整走查共发出 **75 次** `/api/*`（①首屏 5 ②提问页 5 ③图谱页 16
//     ④图谱页内搜一次实体 28 ⑤再搜一次 1 ⑥历史页 14 ⑦点开一条 6），超出窗口 15 次、
//     实测 **19 条 429**；逐页明细见 `测试/uat/证据/优化前/请求预算.json`；
//   · 其中大量是同一次会话里对**同一份不可变数据**的重复请求：
//       - 第 ③ 步 16 次里，`GET /api/graph/events/EVT-0288…EVT-0842` 这 7 个事件详情各 1 次
//         （`GraphView.vue` 的 `prefetchEvents` 为时间轴落点拉事件时间）；
//       - 第 ④ 步 28 次里，`/api/graph/entities/600519`、`/api/graph/entities/600519/evidence`、
//         `/api/graph/entities/600519/neighbors`、`/api/graph/paths` 与同一批 7 个 `EVT-*`
//         **各自又被完整请求了一遍**（第 ③ 步刚刚请求过、载荷一模一样，间隔只有几秒）；
//     这些端点返回的都是**落库的只读数据**（一次会话内不会变），故只给它们做「短期记忆」，
//     其余端点一律不缓存（负向口径见 `CACHEABLE_READ_PATH_PATTERNS` 下方注释）。
//
// 四条保守取值（全部可核对）：
//   · TTL ＝ 60 秒（与后端限流窗口同量级：覆盖一次走查里的重复请求，又不至于长期藏住更新）；
//   · 容量上限 ＝ 200 条，超限按「最久未使用」（LRU）淘汰；
//   · **失败绝不入缓存**：429／1004／500／非 JSON／网络层失败一律不写缓存，被缓存的只有
//     成功信封里的 `data`——空结果（2002）与字段缺失照原始载荷原样返回，不改写、不补写；
//   · 只对 `GET` 生效，且**任何带 `body` 的请求不进缓存**。
// 与第 3 节的关系：缓存命中时根本不发请求（连退避都不会触发）；未命中时走的仍是同一条
// `sendRequest` 主干（限流退避重试一次 ＋ 受限态订阅的语义原样保留，两件事互不冲突）。

/** 缓存 TTL（毫秒）：60 秒，与后端限流窗口（60 次／60 秒）同量级。 */
const CACHE_TTL_MS = 60 * 1000
/** 缓存容量上限（条）：超出时淘汰「最久未使用」的一条。 */
const CACHE_MAX_ENTRIES = 200

/** 「未命中」哨兵：`data` 本身允许是 null，不能用 null 表示未命中。 */
const CACHE_MISS = Symbol('cache-miss')

/**
 * 可缓存的**只读端点白名单**：逐条按 `path`（**不含 query string**）整串锚定匹配。
 * 判据按 path、缓存键却用「完整 URL」——同一个 path 带上不同 query（例如
 * `/graph/entities/{id}/evidence?depth=1` 与 `depth=2`）是**不同的**数据，必须分开缓存。
 */
const CACHEABLE_READ_PATH_PATTERNS = [
  // 实体详情：严格三段 `/graph/entities/{id}`。实体搜索列表 `/graph/entities?keyword=…`
  // 没有第四段、匹配不到它——搜索必须始终打真实接口（后端数据集更新要立刻看得见）。
  /^\/graph\/entities\/[^/]+$/,
  // 一跳邻居：实测第 ④ 步对该路径重复请求 2 次
  /^\/graph\/entities\/[^/]+\/neighbors$/,
  // 实体证据：实测第 ④ 步对该路径重复请求 2 次
  /^\/graph\/entities\/[^/]+\/evidence$/,
  // 事件详情：严格 `/graph/events/{id}`；事件列表 `/graph/events?event_type=…` 匹配不到它。
  // 实测第 ③ 步 7 次、第 ④ 步同一批又是 14 次（7 个 id 各被再请求 2 次）。
  /^\/graph\/events\/[^/]+$/,
  // 多跳路径（实测第 ④ 步重复请求 2 次；参数不同＝不同缓存键）
  /^\/graph\/paths$/,
  // 正文块
  /^\/documents\/[^/]+\/chunks\/[^/]+$/,
  // 回答的图谱路径（新答案入库由 clearApiCache() 兜底失效，见其注释）
  /^\/evidence\/[^/]+\/graph-path$/,
]
// 白名单之外的端点**一律不缓存**（负向口径逐条写明，避免将来「顺手加一条」）：
//   · `/graph/entities`（实体搜索列表）：关键词检索必须始终打真实接口；
//   · `/graph/events`（事件列表）：同上，列表查询要反映当前库状态；
//   · `/qa/ask`（一次模型调用，有成本）、`/qa/answers/*`（本条改动未登记为白名单端点）；
//   · `/history`、`/history/*`（按会话分页，会随新提问变化）；
//   · `/market/*`（实时行情／公告／新闻：绝不能拿缓存假装实时）；
//   · `/config/meta`（数据截至时间要如实反映当前库）、`/health`（后端状态）。

/**
 * 只读端点判据：`path` 命中白名单、方法是 `GET`、且**不带 `body`**。
 * 三个条件缺一不可，判据只读入参、无副作用。
 */
function isCacheableReadRequest(path, method, body) {
  if (body !== undefined) return false
  if (String(method).toUpperCase() !== 'GET') return false
  return CACHEABLE_READ_PATH_PATTERNS.some((re) => re.test(path))
}

// 缓存表（键＝完整请求 URL）与在途登记表（键＝完整请求 URL）。
// Map 的插入序即「最近使用」序：取用时**先 delete 再 set** 把该条提到队尾，
// 于是队首恒为「最久未使用」，超容量时淘汰队首即可（这就是 LRU 的实现，不引第三方库）。
const readCache = new Map()     // url -> { data, expiresAt }
const readInflight = new Map()  // url -> Promise（同一 URL 尚未返回的请求只有一个）
// 缓存代际：clearApiCache() 自增。用于挡住「清空之前发起、清空之后才返回」的在途响应，
// 避免它把失效前的旧数据又回填进清空后的缓存。
let cacheGeneration = 0

/**
 * 取缓存：命中且未过期则返回 `data`（并把该条提到队尾实现 LRU 提位）；否则返回 `CACHE_MISS`。
 * 过期条目在读取时惰性删除（不等定时器，也不起定时器）。
 */
function cacheTake(url) {
  const hit = readCache.get(url)
  if (!hit) return CACHE_MISS
  if (Date.now() >= hit.expiresAt) { readCache.delete(url); return CACHE_MISS }
  readCache.delete(url)
  readCache.set(url, hit)
  return hit.data
}

/** 写缓存（**只在成功时调用**）：超容量时按 LRU 淘汰队首（最久未使用）的那一条。 */
function cachePut(url, data) {
  readCache.delete(url)
  readCache.set(url, { data, expiresAt: Date.now() + CACHE_TTL_MS })
  while (readCache.size > CACHE_MAX_ENTRIES) {
    readCache.delete(readCache.keys().next().value)
  }
}

/**
 * 清空整个只读端点缓存，返回被清掉的条目数。
 *
 * 用途：① 调试（控制台里直接调，看「现在到底存了什么、清掉多少条」）；
 *       ② 将来给界面加「手动刷新」入口时，由该入口调用本函数做整表失效。
 * 自动清空的时机只有一个：**一次成功的 `POST /api/qa/ask`**（新答案入库后
 * `/evidence/{answer_id}/graph-path` 之类的只读数据可能变，见 `sendRequest` 里的调用点）。
 * `GET /history*` 成功**不**清空——历史列表本身不在缓存白名单里，清不清看不到差别；
 * 按「判断不了就不自动清」的保守口径，只认 `POST /api/qa/ask` 这一条。
 *
 * 实现口径：只清缓存表，**不**动在途登记表 `readInflight`——
 *   · 在途响应由代际号（`cacheGeneration`）挡住，不会回填到清空后的缓存里；
 *   · 若连在途登记一起清，同一路径的并发请求会立刻再发一次 fetch，与「并发合并」的初衷相反。
 */
export function clearApiCache() {
  const cleared = readCache.size
  readCache.clear()
  cacheGeneration += 1
  return cleared
}

/**
 * 发起（或复用在途的）一次可缓存只读请求——第 4 节的核心：**并发合并**。
 * 同一 URL 在首次请求尚未返回时又来了请求，直接复用同一个 Promise，**不再发一次 fetch**
 * （实测第 ④ 步的重复请求就发生在第 ③ 步之后的几秒内，缓存与合并两者都要有才够用）。
 * 失败（含 429／1004／500）由 `sendRequest` 原样抛出 → **不写缓存**，下一次请求重新打接口。
 * 真正的网络请求在 `sendRequest`（第 5 节）：本函数只负责查在途表、回填缓存、撤登记。
 */
function startCacheableRead(url, method, init, idempotent) {
  const pending = readInflight.get(url)
  if (pending) return pending
  const gen = cacheGeneration
  const p = sendRequest(url, method, init, idempotent, false, {}).then((data) => {
    // 只有仍属同一代际的响应才回填：clearApiCache() 之后返回的在途响应不写回旧数据
    if (gen === cacheGeneration) cachePut(url, data)
    return data
  })
  const settle = () => { if (readInflight.get(url) === p) readInflight.delete(url) }
  p.then(settle, settle)   // 成功／失败都要撤登记，否则这条 URL 会被永久合并到一个已结束的 Promise
  readInflight.set(url, p)
  return p
}

/**
 * 缓存命中／并发合并命中时返回**浅拷贝**，避免多个调用方共享同一个顶层对象引用。
 * 依据：现有调用方（GraphView／AnswerView／HistoryView 等）实测都只读渲染，但「所有调用方
 * 永远只读」这一点本文件无法逐一确认，故宁可多一次浅拷贝，也不让任何调用方把缓存载荷改脏。
 * 边界（如实说明）：只做**顶层**浅拷贝（对象展开／数组 slice），嵌套对象仍是共享引用——
 * 不深拷贝是为了避免大载荷上的无谓开销；调用方要就地改深层字段时应先自行深拷贝。
 * null／数字／字符串等非对象原样返回（结构与「再打一次接口拿到的 data」等价）。
 */
function copyReadData(data) {
  if (Array.isArray(data)) return data.slice()
  if (data && typeof data === 'object') return { ...data }
  return data
}

// --------------------------------------------------------------------------
// 5. 核心请求
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
 * 发一次 fetch，并在调用方要求时接入「外部取消信号 ＋ 前端超时」。
 *
 * 返回 `{resp, finish, timedOut}`：`finish()` 必须在该响应体读完或放弃时调用，
 * 用来清掉定时器与事件监听（避免长页面里泄漏监听器）。`timedOut()` 用于区分
 * 「超时」与「用户主动取消」两种 abort 原因——对外都是 `ApiError.aborted = true`。
 */
async function fetchWithCancel(url, init, signal, timeoutMs) {
  const method = String(init.method || 'GET').toUpperCase()
  if (!signal && !timeoutMs) {
    try {
      return { resp: await fetch(url, init), finish: () => {}, timedOut: () => false }
    } catch (e) {
      if (isAbortError(e)) throw new ApiError(0, '请求已取消', undefined, true)
      throw new ApiError(0, `无法连接后端服务（${method} ${url}）：${e.message || e}`, undefined)
    }
  }
  const ctrl = new AbortController()
  let timedOut = false
  let timer = null
  const onAbort = () => ctrl.abort()
  if (signal) {
    if (signal.aborted) ctrl.abort()
    else if (typeof signal.addEventListener === 'function') {
      signal.addEventListener('abort', onAbort, { once: true })
    }
  }
  if (timeoutMs > 0) {
    timer = setTimeout(() => { timedOut = true; ctrl.abort() }, timeoutMs)
  }
  const finish = () => {
    if (timer) { clearTimeout(timer); timer = null }
    if (signal && typeof signal.removeEventListener === 'function') {
      signal.removeEventListener('abort', onAbort)
    }
  }
  try {
    const resp = await fetch(url, { ...init, signal: ctrl.signal })
    return { resp, finish, timedOut: () => timedOut }
  } catch (e) {
    finish()
    if (isAbortError(e)) {
      const message = timedOut
        ? `请求超时（等待超过 ${Math.round(timeoutMs / 1000)} 秒仍未返回）`
        : '请求已取消'
      throw new ApiError(0, message, undefined, true)
    }
    // 网络层失败（后端未起／代理不通／断网）：可展示错误，code 用 0 标记「非后端错误码」
    throw new ApiError(0, `无法连接后端服务（${method} ${url}）：${e.message || e}`, undefined)
  }
}

/**
 * 真正发一次请求：返回后端信封里的 `data`。
 * 失败（HTTP 非 2xx／响应体含 code）时抛 `ApiError`，其 `message` 可直接展示。
 * 限流（HTTP 429 或 `code === 1004`）且请求幂等时，先退避等待再**重试一次**（见第 3 节）。
 * 2026-10-18：新增可选的 `abortOpts = {signal, timeoutMs}`——只影响「这一次等待」，
 * 限流退避、缓存与错误文案的既有语义不变。取消/超时抛 `ApiError(0, …, aborted=true)`。
 *
 * @param {string} url 已拼好的相对 URL（形如 `/api/config/meta?…`）
 * @param {string} method HTTP 方法（用于错误文案）
 * @param {object} init fetch 的第二个参数（headers／body）
 * @param {boolean} idempotent 是否允许「限流 → 退避 → 重试一次」（判据见 isIdempotentRequest）
 * @param {boolean} clearsReadCacheOnSuccess 成功时是否清空只读缓存（只有 `POST /qa/ask` 为真）
 * @param {{signal?:AbortSignal, timeoutMs?:number}} [abortOpts] 取消信号与超时（毫秒）
 */
async function sendRequest(url, method, init, idempotent, clearsReadCacheOnSuccess, abortOpts = {}) {
  const signal = abortOpts.signal
  const timeoutMs = abortOpts.timeoutMs
  for (let attempt = 0; ; attempt++) {
    // 取消信号在两次尝试之间（例如退避等待中）到达时，不再发起下一次请求。
    if (signal && signal.aborted) throw new ApiError(0, '请求已取消', undefined, true)

    // fetchWithCancel 已把 abort／断网翻译成可直接展示的 ApiError
    const { resp, finish, timedOut } = await fetchWithCancel(url, init, signal, timeoutMs)

    // 响应体**只读一次**：下面的限流判据与错误 message 都复用这一份解析结果，
    // 不再二次读 body（重试时二次 `resp.text()` 只会拿到空串，反而误判成「空结果」）。
    let payload = null
    let text
    try {
      text = await resp.text()
    } catch (e) {
      finish()
      if (isAbortError(e)) {
        const message = timedOut()
          ? `请求超时（等待超过 ${Math.round(timeoutMs / 1000)} 秒仍未返回）`
          : '请求已取消'
        throw new ApiError(0, message, undefined, true)
      }
      throw new ApiError(0, `读取响应失败（HTTP ${resp.status}）：${e.message || e}`, resp.status)
    }
    finish()
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
      // 限流识别：HTTP 429，或后端错误码 1004（`RateLimitMiddleware` 的固定响应体）。
      // 判据全部取自上面**已解析**的 status／payload，不碰响应体。
      if ((resp.status === 429 || code === 1004) && idempotent && attempt === 0) {
        await waitThrottleRelease(retryWaitMs(headerValue(resp, 'Retry-After')))
        continue   // 一次、且仅一次：第二次的响应无论成败都按下文原样处理（抛错文案与现状一致）
      }
      let message = (payload && payload.message) || `请求失败（HTTP ${resp.status}）`
      // 2026-10-14：1004 限流时把 Retry-After 秒数带给用户（后端限流响应带该头），
      // 避免「只说超限、不说要等多久」的体验空洞。
      const retryAfter = Number(headerValue(resp, 'Retry-After'))
      if (code === 1004 && Number.isFinite(retryAfter) && retryAfter > 0) {
        message += `，请约 ${Math.ceil(retryAfter)} 秒后重试`
      }
      throw new ApiError(code, message, resp.status)
    }

    // 成功响应：取 data（后端成功信封为 {data, meta}）；并按订阅语义离开受限态
    exitThrottleIfIdle()
    // 新答案入库（`POST /api/qa/ask` 成功）：只读缓存里 `/evidence/*/graph-path`
    // 之类的条目可能已过期，整表清空（保守做法：只认这一条，见 clearApiCache 注释）。
    if (clearsReadCacheOnSuccess) clearApiCache()
    return payload ? payload.data : null
  }
}

/**
 * 统一请求入口：返回后端信封里的 `data`（失败抛 `ApiError`，`message` 可直接展示）。
 *
 * 两条主干：
 *   · **可缓存只读端点**（第 4 节白名单，且是 GET、不带 body）：先查 60 秒短期缓存；
 *     未命中时若同一 URL 已有在途请求，就复用同一个 Promise（并发合并，不再发 fetch）；
 *     返回前一律过一遍浅拷贝（见 `copyReadData` 的边界说明）。
 *   · 其余端点：与改动前**完全一致**，直接走 `sendRequest`（含限流退避重试一次）。
 *
 * @param {string} path  形如 `/qa/ask`（相对 `/api`）
 * @param {{method?:string, body?:object, params?:object, withSession?:boolean,
 *          signal?:AbortSignal, timeoutMs?:number}} [opts]
 *   `signal`／`timeoutMs` 只对**非缓存**请求生效：可缓存只读请求会被多方并发合并，
 *   单个调用方取消会把共享 Promise 一起拒掉，故带取消/超时的调用一律绕过缓存直连。
 */
export async function request(path, opts = {}) {
  const { method = 'GET', body, params, withSession = false, signal, timeoutMs } = opts
  const query = { ...(params || {}) }
  if (withSession) query.session_id = getSessionId()
  const url = `${API_PREFIX}${path}${qs(query)}`

  const init = { method, headers: {} }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  // 可重试判据在循环外算一次：整条请求最多两次尝试，第二次只可能由「第一次被限流」触发。
  // 2026-10-17：判据现在也接受 `POST /api/qa/ask`（限流是在中间件层拒的，没进业务逻辑、没调模型，
  // 见 isIdempotentRequest 的注释）；因此必须把 path 传进去，否则这一档永远走不到。
  const idempotent = isIdempotentRequest(method, body, path)
  // 一次成功的 `POST /api/qa/ask` ＝ 新答案已入库：只读缓存可能已过期，整表清空
  const clearsReadCacheOnSuccess = String(method).toUpperCase() === 'POST' && path === '/qa/ask'
  const abortOpts = { signal, timeoutMs }
  const wantsAbort = !!signal || !!timeoutMs

  if (wantsAbort || !isCacheableReadRequest(path, method, body)) {
    // 不在白名单／带 body／非 GET／要求取消或超时：不缓存、不合并
    return sendRequest(url, method, init, idempotent, clearsReadCacheOnSuccess, abortOpts)
  }

  const cached = cacheTake(url)
  if (cached !== CACHE_MISS) return copyReadData(cached)
  return copyReadData(await startCacheableRead(url, method, init, idempotent))
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
// 6. 接口清单（与后端表 4-13 的路径一一对应）
// --------------------------------------------------------------------------

// —— 问答与配置（api\qa.py）——
/**
 * POST /api/qa/ask —— 提问（固定 C 组）。体只允许 {question, session_id}（硬约束 9）。
 *
 * 2026-10-18：支持 `{signal, timeoutMs}`。默认超时 `ASK_TIMEOUT_MS`（320 秒，后端链路
 * 上限 300 秒 + 20 秒余量）。取消/超时抛出 `aborted=true` 的 ApiError，调用方应把它
 * 当作「本次等待结束」而不是「后端报错」——后端可能仍会跑完并写进本会话历史。
 */
export function askQuestion(question, opts = {}) {
  const timeoutMs = (opts && opts.timeoutMs != null) ? opts.timeoutMs : ASK_TIMEOUT_MS
  return request('/qa/ask', {
    method: 'POST',
    body: { question, session_id: getSessionId() },
    signal: opts && opts.signal,
    timeoutMs,
  })
}
/** GET /api/qa/answers/{answer_id} —— 单条回答（含证据与图谱路径）。 */
export function getAnswer(answerId) {
  return request(`/qa/answers/${encodeURIComponent(answerId)}`)
}
/** GET /api/config/meta —— 只读元信息（含 data_cutoff_time）。 */
export function getConfigMeta() {
  return requestMeta('/config/meta')
}

// —— 关键词召回（api\search.py · 工程增强，不在论文实验口径内）——
/**
 * GET /api/search/keywords —— BM25／字符 n-gram 关键词召回（只读）。
 *
 * 返回 `{items, total, took_ms, index_ready}`；每条含 `{chunk_id, doc_id, title,
 * snippet, score}`。**不属于证据链**：只作补充提示，不作为答案依据。
 * 该路径不在只读缓存白名单里，每次调用都直连后端（关键词命中要反映当前索引状态）。
 */
export function searchKeywords(q, k = 5) {
  return request('/search/keywords', { params: { q, k } })
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
/**
 * GET /api/graph/entities —— 按 keyword／type 查实体（实体搜索列表，**不在缓存白名单**）。
 *
 * 参数名口径（2026-10-17 复核，结论：本函数**无需改动**）：后端只认 `page`／`page_size`，
 * 未定义参数（如旧调用方传的 `limit: 8`）会被后端直接忽略、退化成默认页——实测
 * `GET /api/graph/entities?keyword=宁德时代&limit=8` 实返 `page_size: 20`。本函数对 `params`
 * 是**原样透传**（既不白名单过滤、也不做 `limit→page_size` 的隐式改写：改写会凭空发明一个
 * 调用方没写的语义，属越权），参数名正确与否由调用方负责；GraphView 已改用 `page/page_size`。
 */
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

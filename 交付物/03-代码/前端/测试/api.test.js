// 交付物/03-代码\前端\测试\api.test.js —— G 组：`src/api.js` 的单元测试（P1-12 补测）
//
// 覆盖评审 B-06 建议的那一类用例（`api.js` 的 `ApiError` 分支），并顺带把
// 「会话标识」「信封解析」「query 拼装」「接口清单路径」四条契约钉住。
//
// 三条纪律：
//   1. **离线**：`fetch` 一律用 `vi.stubGlobal` 装替身，绝不发真实请求
//      （对应 Python 侧 `conftest.forbid_network` 的同一条纪律）；
//   2. **不留状态**：每个用例前清 `localStorage`、恢复 `crypto`，避免跨用例串味；
//   3. **负向标定**：关键分支都配一条"换掉实现就会红"的对照。
//
// 被测文件不写死任何后端地址：只出现相对路径 `/api/*`（硬约束 2／14），
// 测试里也一样——断言 URL 一律以 `/api` 开头。

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  ApiError,
  getSessionId,
  request,
  requestMeta,
  askQuestion,
  getAnswer,
  getConfigMeta,
  getEvidence,
  getGraphPath,
  getChunk,
  listHistory,
  getHistoryDetail,
  listEntities,
  getNeighbors,
  getPaths,
  listEvents,
  getEventDetail,
  getEntity,
  getEntityEvidence,
  getMarketQuote,
  getMarketAnnouncements,
  getMarketNews,
  getMarketReports,
  getHealth,
} from '../src/api.js'

// --------------------------------------------------------------------------
// 替身：把 fetch 换成一个"按脚本回消息"的函数
// --------------------------------------------------------------------------
/** 造一个 fetch 替身：`handler(url, init) -> {status, ok, body}`（body 为字符串）。 */
function stubFetch(handler) {
  const calls = []
  const fake = vi.fn(async (url, init) => {
    calls.push({ url, init })
    const reply = handler(url, init) || {}
    const status = reply.status === undefined ? 200 : reply.status
    const ok = reply.ok === undefined ? (status >= 200 && status < 300) : reply.ok
    const text = reply.body === undefined ? '' : reply.body
    return {
      status,
      ok,
      text: async () => text,
      json: async () => JSON.parse(text),
    }
  })
  vi.stubGlobal('fetch', fake)
  return { fake, calls }
}

/** 成功信封：`{data, meta}`。 */
function okEnvelope(data, meta = null) {
  return JSON.stringify({ data, meta })
}

/** 失败信封：后端错误一律 `{code, message}`。 */
function errEnvelope(code, message) {
  return JSON.stringify({ code, message })
}

beforeEach(() => {
  window.localStorage.clear()
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ==========================================================================
// G1 组 · ApiError 类型本身
// ==========================================================================
describe('ApiError', () => {
  it('是 Error 的子类，且带上 code / httpStatus（可直接展示 message）', () => {
    const e = new ApiError(1001, '问题为空', 400)
    expect(e).toBeInstanceOf(Error)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.name).toBe('ApiError')
    expect(e.code).toBe(1001)
    expect(e.httpStatus).toBe(400)
    expect(e.message).toBe('问题为空')
  })

  it('网络层失败时 httpStatus 可为 undefined、code 用 0', () => {
    const e = new ApiError(0, '无法连接后端服务', undefined)
    expect(e.code).toBe(0)
    expect(e.httpStatus).toBeUndefined()
  })
})

// ==========================================================================
// G2 组 · request() 的三条失败路径（评审 B-06 点名的分支）
// ==========================================================================
describe('request() 的失败分支', () => {
  it('fetch 抛异常（后端未起/断网）→ ApiError(code=0)，message 可展示且带方法与 URL', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('ECONNREFUSED') }))
    await expect(request('/qa/ask', { method: 'POST', body: { question: 'x' } }))
      .rejects.toMatchObject({ name: 'ApiError', code: 0 })
    try {
      await request('/qa/ask', { method: 'POST', body: { question: 'x' } })
    } catch (e) {
      expect(e.httpStatus).toBeUndefined()
      expect(e.message).toContain('无法连接后端服务')
      expect(e.message).toContain('POST')
      expect(e.message).toContain('/api/qa/ask')
      expect(e.message).toContain('ECONNREFUSED')
    }
  })

  it('响应体不是 JSON（代理 502 页面）→ ApiError(code=0)，原文摘要进 message，带 HTTP 状态', async () => {
    stubFetch(() => ({ status: 502, body: '<html>Bad Gateway</html>' }))
    await expect(request('/config/meta')).rejects.toMatchObject({ name: 'ApiError', code: 0 })
    try {
      await request('/config/meta')
    } catch (e) {
      expect(e.httpStatus).toBe(502)
      expect(e.message).toContain('非 JSON 响应')
      expect(e.message).toContain('502')
      expect(e.message).toContain('Bad Gateway')
    }
  })

  it('HTTP 非 2xx 且响应体带 code → 取后端 code 与 message，并带 httpStatus', async () => {
    stubFetch(() => ({ status: 404, body: errEnvelope(2001, '回答不存在') }))
    try {
      await request('/qa/answers/nope')
      throw new Error('应当抛错')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect(e.code).toBe(2001)         // 后端 code 优先于 HTTP 状态
      expect(e.message).toBe('回答不存在')
      expect(e.httpStatus).toBe(404)
    }
  })

  it('HTTP 200 但响应体带 code → 仍判为错误（后端错误信封一律 {code,message}）', async () => {
    stubFetch(() => ({ status: 200, body: errEnvelope(3001, '图谱依赖不可用') }))
    await expect(request('/graph/paths')).rejects.toMatchObject({
      name: 'ApiError', code: 3001, message: '图谱依赖不可用', httpStatus: 200,
    })
  })

  it('HTTP 非 2xx 但没有可解析的 message → 用兜底文案「请求失败（HTTP xxx）」，code 取 HTTP 状态', async () => {
    stubFetch(() => ({ status: 500, body: JSON.stringify({}) }))
    try {
      await request('/x')
      throw new Error('应当抛错')
    } catch (e) {
      expect(e.code).toBe(500)
      expect(e.message).toBe('请求失败（HTTP 500）')
      expect(e.httpStatus).toBe(500)
    }
  })

  it('负向标定：HTTP 200 且无 code 字段 → 正常返回 data（不得误判为错误）', async () => {
    stubFetch(() => ({ status: 200, body: okEnvelope({ hello: 'world' }) }))
    await expect(request('/config/meta')).resolves.toEqual({ hello: 'world' })
  })
})

// ==========================================================================
// G3 组 · request() 的成功路径与 query 拼装
// ==========================================================================
describe('request() 的成功路径', () => {
  it('成功信封取 data；空响应体返回 null', async () => {
    stubFetch(() => ({ status: 200, body: okEnvelope([1, 2, 3]) }))
    await expect(request('/graph/events')).resolves.toEqual([1, 2, 3])

    stubFetch(() => ({ status: 204, body: '' }))
    await expect(request('/x')).resolves.toBeNull()
  })

  it('GET 默认不带 body、不带 Content-Type', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await request('/config/meta')
    expect(calls[0].init.method).toBe('GET')
    expect(calls[0].init.body).toBeUndefined()
    expect(calls[0].init.headers['Content-Type']).toBeUndefined()
  })

  it('带 body 时自动加 Content-Type 并 JSON 序列化', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await request('/qa/ask', { method: 'POST', body: { question: '甲', session_id: 's' } })
    expect(calls[0].init.method).toBe('POST')
    expect(calls[0].init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(calls[0].init.body)).toEqual({ question: '甲', session_id: 's' })
  })

  it('query 拼装：跳过 undefined/null，保留空串并编码', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await request('/graph/entities', { params: { keyword: '甲 公司', type: 'Company', page: undefined, x: null, blank: '' } })
    const url = calls[0].url
    expect(url.startsWith('/api/graph/entities?')).toBe(true)
    expect(url).toContain('keyword=%E7%94%B2%20%E5%85%AC%E5%8F%B8')   // 空格编码为 %20
    expect(url).toContain('type=Company')
    expect(url).not.toContain('page=')
    expect(url).not.toContain('x=')
    expect(url).toContain('blank=')
  })

  it('无参时不加「?」', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await request('/config/meta')
    expect(calls[0].url).toBe('/api/config/meta')
  })

  it('withSession=true 时自动带上 session_id', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope([]) }))
    await request('/history', { params: { page: 1 }, withSession: true })
    expect(calls[0].url).toMatch(/session_id=[0-9a-f-]{36}/)
  })

  it('URL 前缀恒为 /api（前端只调相对路径，硬约束 2／14）', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await request('/qa/ask', { method: 'POST', body: {} })
    expect(calls[0].url.startsWith('/api/')).toBe(true)
    expect(calls[0].url).not.toMatch(/^https?:/)
  })
})

// ==========================================================================
// G4 组 · requestMeta()（顶栏要用 meta，但成功路径与 request 不同）
// ==========================================================================
describe('requestMeta()', () => {
  it('返回 {data, meta}，不丢 meta', async () => {
    stubFetch(() => ({ status: 200, body: JSON.stringify({ data: { v: 1 }, meta: { dataset_version: 'v2.1' } }) }))
    await expect(requestMeta('/config/meta')).resolves.toEqual({
      data: { v: 1 }, meta: { dataset_version: 'v2.1' },
    })
  })

  it('失败时抛 ApiError（code/message/httpStatus 与 request 同形）', async () => {
    stubFetch(() => ({ status: 500, body: errEnvelope(9999, '未知错误') }))
    await expect(requestMeta('/config/meta')).rejects.toMatchObject({
      name: 'ApiError', code: 9999, message: '未知错误', httpStatus: 500,
    })
  })

  it('withSession=true 时带 session_id', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: JSON.stringify({ data: null, meta: null }) }))
    await requestMeta('/config/meta', { withSession: true })
    expect(calls[0].url).toMatch(/session_id=[0-9a-f-]{36}/)
  })
})

// ==========================================================================
// G5 组 · getHealth()（特例：响应体不是 {data,meta} 信封）
// ==========================================================================
describe('getHealth()', () => {
  it('返回原始对象（非信封）——健康检查体是 {status, mysql, neo4j, …}', async () => {
    const payload = { status: 'ok', mysql: true, neo4j: false, vector_index: true, model_config: 'x' }
    stubFetch(() => ({ status: 200, body: JSON.stringify(payload) }))
    await expect(getHealth()).resolves.toEqual(payload)
  })

  it('非 2xx → 抛 ApiError（code=HTTP 状态，message 带「健康检查失败」）', async () => {
    stubFetch(() => ({ status: 503, body: '' }))
    await expect(getHealth()).rejects.toMatchObject({
      name: 'ApiError', code: 503, httpStatus: 503,
    })
  })
})

// ==========================================================================
// G6 组 · 会话标识 getSessionId()
// ==========================================================================
describe('getSessionId()', () => {
  it('首次生成 36 字符 UUID 并落 localStorage，第二次读到同一值', () => {
    const a = getSessionId()
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
    expect(a).toHaveLength(36)
    expect(window.localStorage.getItem('qa-console-session-id')).toBe(a)
    expect(getSessionId()).toBe(a)
  })

  it('已有会话时直接复用，不再生成', () => {
    window.localStorage.setItem('qa-console-session-id', 'fixed-session-id-1234')
    expect(getSessionId()).toBe('fixed-session-id-1234')
  })

  it('crypto.randomUUID 不可用时走兜底，仍是 36 字符 UUID v4 形态', () => {
    window.localStorage.clear()
    const saved = window.crypto
    // 移除 randomUUID 模拟旧环境
    vi.stubGlobal('crypto', {})
    const sid = getSessionId()
    expect(sid).toHaveLength(36)
    expect(sid[14]).toBe('4')                                    // 版本位固定为 4
    expect('89ab').toContain(sid[19])                            // 变体位 ∈ {8,9,a,b}
    expect(sid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    vi.stubGlobal('crypto', saved)
  })

  it('localStorage 被禁用时退化为内存态（不抛错，仍返回可用 id）', () => {
    const original = window.localStorage
    const throwing = {
      getItem() { throw new Error('disabled') },
      setItem() { throw new Error('disabled') },
      removeItem() { throw new Error('disabled') },
      clear() {},
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: throwing })
    try {
      const sid = getSessionId()
      expect(sid).toHaveLength(36)
    } finally {
      Object.defineProperty(window, 'localStorage', { configurable: true, value: original })
    }
  })
})

// ==========================================================================
// G7 组 · 接口清单的 URL 形态（与后端表 4-13 一一对应）
// ==========================================================================
describe('接口清单的路径与参数', () => {
  it('问答三接口', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await askQuestion('甲公司业绩如何？')
    await getAnswer('A/1')          // 需 URL 编码
    await getConfigMeta()
    expect(calls[0].url).toBe('/api/qa/ask')
    expect(JSON.parse(calls[0].init.body).question).toBe('甲公司业绩如何？')
    expect(JSON.parse(calls[0].init.body).session_id).toHaveLength(36)
    expect(calls[1].url).toBe('/api/qa/answers/A%2F1')
    expect(calls[2].url).toBe('/api/config/meta')
  })

  it('证据与原文接口（含 graph-path 与 chunk）', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await getEvidence('a 1')
    await getGraphPath('a 1')
    await getChunk('d/1', 'c 2')
    expect(calls[0].url).toBe('/api/evidence/a%201')
    expect(calls[1].url).toBe('/api/evidence/a%201/graph-path')
    expect(calls[2].url).toBe('/api/documents/d%2F1/chunks/c%202')
  })

  it('历史接口强制带 session_id 与分页参数', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope([]) }))
    await listHistory(2, 50)
    await getHistoryDetail('q 1')
    expect(calls[0].url).toContain('/api/history?')
    expect(calls[0].url).toContain('page=2')
    expect(calls[0].url).toContain('page_size=50')
    expect(calls[0].url).toMatch(/session_id=/)
    expect(calls[1].url).toContain('/api/history/q%201')
  })

  it('图谱接口（实体/邻居/路径/事件/详情/证据）', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await listEntities({ keyword: '甲', type: 'Company' })
    await getNeighbors('N 1', { hop: 1 })
    await getPaths({ from_node: 'A', to_node: 'B' })
    await listEvents({ event_type: '业绩' })
    await getEventDetail('EV 1')
    await getEntity('N 1')
    await getEntityEvidence('N 1', 2, { limit: 5 })
    expect(calls[0].url).toContain('/api/graph/entities?')
    expect(calls[1].url).toContain('/api/graph/entities/N%201/neighbors?hop=1')
    expect(calls[2].url).toContain('/api/graph/paths?from_node=A&to_node=B')
    expect(calls[3].url).toContain('/api/graph/events?event_type=')
    expect(calls[4].url).toBe('/api/graph/events/EV%201')
    expect(calls[5].url).toBe('/api/graph/entities/N%201')
    expect(calls[6].url).toContain('/api/graph/entities/N%201/evidence?depth=2&limit=5')
  })

  it('实时数据区四接口（scope=display_only，不进问答证据链）', async () => {
    const { calls } = stubFetch(() => ({ status: 200, body: okEnvelope(1) }))
    await getMarketQuote()
    await getMarketQuote('000001,000002')
    await getMarketAnnouncements('000001', { page: 1 })
    await getMarketNews('人工智能', { limit: 10 })
    await getMarketReports()
    expect(calls[0].url).toBe('/api/market/quote')
    expect(calls[1].url).toBe('/api/market/quote?codes=000001%2C000002')
    expect(calls[2].url).toContain('/api/market/announcements?code=000001&page=1')
    expect(calls[3].url).toContain('/api/market/news?keyword=')
    expect(calls[4].url).toBe('/api/market/reports')
  })
})

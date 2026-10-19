// 交付物/03-代码\前端\测试\graph_xss.test.js —— 图谱渲染的存储型 XSS 回归（独立审查 2026-10-19）
//
// 背景：`src/lib/graph.js` 把上游图谱数据（节点名／关系名／文档标题／URL／接口错误信息）
// 直接拼进 innerHTML/SVG。文档标题与实体名来自第三方公告原文，是可被投毒的存储型载体。
// 本文件不测布局细节，只验证一个安全不变量：
//   **任何上游字符串都只能以文本出现，不能变成元素、属性或可执行 URL。**
//
// 覆盖出口：paint（画布节点/边）、renderPaths、renderIso、panelNode、panelEdge、
// renderEvidence（计数/关系表/文档聚合/事件四项）、loadCtx（首屏与成功/失败分支）。
// 负向标定：输入的载荷若被按 HTML 解析，jsdom 会生成 `<img>`／`<script>` 或
// `javascript:` href；断言这些都不存在，同时断言载荷以转义文本原样可见。

import { describe, it, expect, afterEach } from 'vitest'
import { buildDataset, esc, mountGraph, safeUrl } from '../src/lib/graph.js'

const XSS = '<img src=x onerror="window.__xss=1">'
const HREF_XSS = 'javascript:window.__xss=1'

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function makeDataset() {
  return buildDataset('t', [
    { id: 'n1', name: XSS, type: 'event' },
    { id: 'n2', name: '正常公司', type: 'company', code: '" onmouseover="window.__xss=1' },
    { id: 'n3', name: '孤立节点', type: 'person', code: XSS, time: XSS },
  ], [
    { f: 'n1', t: 'n2', rel: XSS, role: XSS, conf: 0.9, sdoc: XSS, schunk: XSS, src: XSS },
  ])
}

function makeProvider(overrides) {
  return Object.assign({
    entity: async () => ({
      property_keys: [XSS],
      properties: { [XSS]: XSS },
      counts: { neighbors: 1, relations: 1, documents: 1, chunks: 1 },
      degree: { in_: 0, out: 1, total: 1 },
    }),
    evidence: async () => ({
      counts: { neighbors: 1, relations: 1, documents: 1, chunks: 1 },
      documents_total: 1,
      documents: [{
        doc_id: XSS, title: XSS, source: XSS, publish_time: XSS, url: HREF_XSS,
        chunks: [{
          chunk_id: XSS,
          relations: [{ neighbor: 'n2', relation: XSS, confidence: 0.9, role: XSS }],
        }],
      }],
      relations_without_evidence: [{ neighbor: XSS, relation: XSS }],
    }),
    event: async () => ({
      participants: [{ name: XSS, role: XSS }],
      issuer: { name: XSS },
      policies: [{ name: XSS }],
      evidences: [{
        doc_id: XSS, chunk_id: XSS, title: XSS, source: XSS, url: HREF_XSS, publish_time: XSS,
      }],
    }),
  }, overrides || {})
}

function mount(provider, fetchChunk) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const G = mountGraph(host, {
    ds: makeDataset(),
    provider,
    select: 'n1',
    modeName: XSS,
    tag: XSS,
    fetchChunk: fetchChunk || (async () => ({ chunk_content: XSS, neighbor_chunks: [{ chunk_id: XSS }] })),
  })
  return { host, G }
}

function expectNoExecutableMarkup(host) {
  expect(host.querySelector('img')).toBeNull()
  expect(host.querySelector('script')).toBeNull()
  for (const el of host.querySelectorAll('*')) {
    // 任何 on* 事件属性都不应由上游字符串生成（模板自身的 aria-* 等不受影响）
    for (const attr of Array.from(el.attributes)) {
      expect(attr.name.toLowerCase().startsWith('on')).toBe(false)
    }
  }
  for (const a of host.querySelectorAll('a[href]')) {
    expect(safeUrl(a.getAttribute('href'))).not.toBeNull()
  }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('输出编码垫片', () => {
  it('esc 转义 HTML/SVG 元字符，且先处理 & 不产生二次实体', () => {
    expect(esc(XSS)).toBe('&lt;img src=x onerror=&quot;window.__xss=1&quot;&gt;')
    expect(esc('&<>"\'')).toBe('&amp;&lt;&gt;&quot;&#39;')
  })

  it('safeUrl 只放行 http/https，挡住 javascript:/data: 与大小写绕过', () => {
    expect(safeUrl(HREF_XSS)).toBeNull()
    expect(safeUrl('JavaScript:alert(1)')).toBeNull()
    expect(safeUrl('  data:text/html,<script>alert(1)</script>')).toBeNull()
    expect(safeUrl('https://example.com/a?x=1&y=2')).toBe('https://example.com/a?x=1&y=2')
    expect(safeUrl('HTTP://example.com')).toBe('HTTP://example.com')
  })
})

describe('图谱 DOM 出口的 XSS 不变量', () => {
  it('初次挂载：画布/路径/孤立节点/属性面板/证据区均不生成可执行标记', async () => {
    const { host } = mount(makeProvider())
    await flush()
    await flush()
    expectNoExecutableMarkup(host)
    // 载荷以文本形式可见（说明是转义而非静默丢弃）
    expect(host.textContent).toContain('<img src=x')
  })

  it('边属性面板不执行上游关系名/role/source', () => {
    const { host } = mount(makeProvider())
    const geline = host.querySelector('[data-edge]')
    expect(geline).not.toBeNull()
    geline.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expectNoExecutableMarkup(host)
    expect(host.textContent).toContain('<img src=x')
  })

  it('「查看上下文」首屏、成功与失败分支都不执行上游内容/异常信息', async () => {
    const { host } = mount(makeProvider())
    await flush()
    await flush()
    const btn = host.querySelector('[data-ctx]')
    expect(btn).not.toBeNull()
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expectNoExecutableMarkup(host)
    expect(host.textContent).toContain('<img src=x')

    // 失败分支：错误消息本身也来自网络层，同样必须转义
    const failing = mount(makeProvider(), async () => { throw new Error(XSS) })
    await flush()
    await flush()
    const btn2 = failing.host.querySelector('[data-ctx]')
    btn2.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expectNoExecutableMarkup(failing.host)
  })

  it('接口错误信息进入属性面板/证据区时被转义', async () => {
    const { host } = mount(makeProvider({
      entity: async () => { throw new Error(XSS) },
      evidence: async () => { throw new Error(XSS) },
      event: async () => { throw new Error(XSS) },
    }))
    await flush()
    await flush()
    expectNoExecutableMarkup(host)
  })
})

// 交付物/03-代码\前端\测试\url_safety.test.js —— 外部 url 的协议白名单回归（独立审查 2026-10-19）
//
// 背景：图谱之外的三个出口（证据卡、历史回看表三、提问页实时新闻／报告）曾把接口返回的
// `url` 原样绑到 `:href`。上游文档／新闻记录一旦出现 `javascript:` / `data:` 等协议，
// 点击即执行脚本，构成存储型 XSS。
//
// 修复口径统一复用 lib/graph.js 的 safeUrl()：只放行 http(s)，其余不渲染为可点击链接。
// 本文件用 jsdom 直接断言最终 DOM：恶意 url 不得产生任何 <a href>，且不能丢失「未给出」提示。

import { describe, it, expect, afterEach, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../src/api.js', () => ({
  askQuestion: vi.fn(),
  listHistory: vi.fn(async () => ({ items: [], total: 0 })),
  friendlyMessageOf: vi.fn((_code, fallback) => fallback || '请求失败'),
  getHistoryDetail: vi.fn(),
  getGraphPath: vi.fn(),
  getSessionId: vi.fn(() => 'session-test'),
  resetSessionId: vi.fn(() => 'session-test-2'),
}))

import EvidenceList from '../src/components/EvidenceList.vue'
import HistoryView from '../src/views/HistoryView.vue'
import AskView from '../src/views/AskView.vue'
import { getHistoryDetail, getGraphPath, getSessionId, listHistory } from '../src/api.js'

const BAD = 'javascript:window.__url_xss=1'
const GOOD = 'https://example.com/doc/1'

let app = null
let host = null

function mount(component, options) {
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp(component, options)
  app.mount(host)
}

function anchors() {
  return Array.from(host.querySelectorAll('a[href]'))
}

function assertNoUnsafeHref() {
  for (const a of anchors()) {
    const href = a.getAttribute('href') || ''
    expect(href.startsWith('javascript:'), `不得出现 javascript: 链接：${href}`).toBe(false)
    expect(href.startsWith('data:'), `不得出现 data: 链接：${href}`).toBe(false)
  }
}

afterEach(() => {
  if (app) app.unmount()
  app = null
  document.body.innerHTML = ''
  delete window.__url_xss
  vi.clearAllMocks()
})

describe('EvidenceList · 证据 url 协议白名单', () => {
  it('javascript: url 不渲染链接，合法 https 正常渲染', async () => {
    mount(EvidenceList, {
      items: [
        {
          rank: 1, evidence_type: '回答来源', title: '恶意正文', source: '巨潮资讯',
          doc_id: 1001, chunk_id: 1, url: BAD,
        },
        {
          rank: 2, evidence_type: '回答来源', title: '正常正文', source: '巨潮资讯',
          doc_id: 1002, chunk_id: 2, url: GOOD,
        },
      ],
    })
    await nextTick()

    assertNoUnsafeHref()
    const links = anchors()
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('href')).toBe(GOOD)
    // 恶意条目退化为「记录未给出」，并明确说明不猜链接
    expect(host.textContent).toContain('本条未返回 url，不猜链接')
    expect(host.textContent).toContain('记录未给出')
  })
})

describe('HistoryView · 回看表三证据 url 协议白名单', () => {
  it('抽屉里的 javascript: url 不渲染链接，合法 https 正常渲染', async () => {
    listHistory.mockResolvedValue({
      items: [{ question_id: 1, question_text: '测试问题', ask_time: '2026-10-19T10:00:00+08:00', evidence_count: 2 }],
      total: 1,
    })
    getHistoryDetail.mockResolvedValue({
      question_id: 1,
      answer_id: 1,
      question_text: '测试问题',
      ask_time: '2026-10-19T10:00:00+08:00',
      answer_text: '【回答】测试。\n【证据来源】\n[证据1] 恶意\n[证据2] 正常',
      graph_path_available: false,
      evidence: [
        {
          rank: 1, evidence_type: '回答来源', title: '恶意正文', source: '巨潮资讯',
          publish_time: '2026-10-01T00:00:00+08:00', doc_id: 1001, chunk_id: 1, url: BAD,
        },
        {
          rank: 2, evidence_type: '回答来源', title: '正常正文', source: '巨潮资讯',
          publish_time: '2026-10-02T00:00:00+08:00', doc_id: 1002, chunk_id: 2, url: GOOD,
        },
      ],
    })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    await router.isReady()

    host = document.createElement('div')
    document.body.appendChild(host)
    app = createApp(HistoryView)
    app.use(router)
    app.provide('appMeta', { dataCutoffTime: '2026-09-25T23:59:59+08:00' })
    app.mount(host)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(getSessionId).toHaveBeenCalled()
    expect(listHistory).toHaveBeenCalled()

    const openBtn = host.querySelector('.hrow__open')
    expect(openBtn, '历史列表应渲染回看按钮').toBeTruthy()
    openBtn.click()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(getHistoryDetail).toHaveBeenCalledWith(1)
    expect(getGraphPath).not.toHaveBeenCalled()

    assertNoUnsafeHref()
    const links = anchors().filter((a) => a.classList.contains('ev__link'))
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('href')).toBe(GOOD)
    expect(host.textContent).toContain('记录未给出')
  })
})

describe('AskView · 实时新闻／报告 url 协议白名单', () => {
  it('新闻与报告中的 javascript: url 不渲染链接，合法 https 正常渲染', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'ask', component: { template: '<div />' } },
        { path: '/answer/:answerId', name: 'answer', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    await router.isReady()

    host = document.createElement('div')
    document.body.appendChild(host)
    app = createApp(AskView)
    app.use(router)
    app.provide('appMeta', {
      dataCutoffTime: '2026-09-25T23:59:59+08:00',
      vectorCount: 5018,
      health: null,
    })
    app.provide('market', {
      on: true,
      news: {
        connected: true,
        items: [
          { time: '10:00', title: '恶意新闻', media: '测试源', url: BAD },
          { time: '10:01', title: '正常新闻', media: '测试源', url: GOOD },
        ],
      },
      reports: {
        items: [
          { publish_time: '2026-10-01T00:00:00+08:00', title: '恶意报告', source: '语料库', category: '公告', url: BAD },
          { publish_time: '2026-10-02T00:00:00+08:00', title: '正常报告', source: '语料库', category: '公告', url: GOOD },
        ],
      },
    })
    app.mount(host)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()

    expect(host.textContent).toContain('恶意新闻')
    expect(host.textContent).toContain('恶意报告')

    assertNoUnsafeHref()
    const links = anchors().filter((a) => a.classList.contains('rt__go'))
    expect(links.length).toBeGreaterThan(0)
    for (const a of links) expect(a.getAttribute('href')).toBe(GOOD)
    // 恶意条目的提示仍是「未给出」，不能因为协议不合法就静默消失
    expect(host.textContent).toContain('未给出')
    expect(host.textContent).toContain('本次未取到原文 URL')
  })
})

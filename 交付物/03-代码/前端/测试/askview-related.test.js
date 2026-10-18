// 交付物/03-代码\前端\测试\askview-related.test.js —— 提问页空态里的「关键词相关原文」
//
// 覆盖（工程增强，不在论文实验口径内）：
//   ① 后端空结果带 `related_chunks` 时，AskView 渲染「关键词相关原文（工程增强，非正式证据）」
//      区块，且逐条显示 title / chunk_id / snippet；
//   ② 区块明确标注「不属于证据链」——不能让人误以为它是正式证据；
//   ③ `related_chunks` 为空／缺失时**不渲染**该区块，原有空态文案保持不变。
//
// 离线纪律：`../src/api.js` 整体用 `vi.mock` 替换，不建 socket、不发真实请求。
// 前端未安装 @vue/test-utils，这里用 `createApp` + `createRouter(createMemoryHistory)`
// 手工挂载（与仓库现有测试的依赖面一致）。

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../src/api.js', () => ({
  askQuestion: vi.fn(),
  listHistory: vi.fn(async () => ({ items: [] })),
  friendlyMessageOf: vi.fn((code, fallback) => fallback || '请求失败'),
}))

import { askQuestion, listHistory } from '../src/api.js'
import AskView from '../src/views/AskView.vue'

const EMPTY_NOTICE = '未检索到可引用的证据：这个问题在现有数据里找不到能支撑回答的原文。'

let app = null
let host = null

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'ask', component: { template: '<div />' } },
      { path: '/answer/:answerId', name: 'answer', component: { template: '<div />' } },
    ],
  })
}

async function mountAskView() {
  const router = makeRouter()
  await router.push('/')
  await router.isReady()
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp(AskView)
  app.use(router)
  app.provide('appMeta', {
    datasetVersion: 'v2.1',
    dataCutoffTime: '2026-09-25T23:59:59+08:00',
    vectorCount: 5018,
    vectorDim: 512,
    modelName: 'stub-model',
    promptVersion: 'p1',
    health: null,
  })
  app.provide('market', { on: false })
  app.mount(host)
  await nextTick()
}

/** 填入问题并点「提问」，等异步 submit 走完。 */
async function ask(questionText) {
  const textarea = host.querySelector('#q')
  textarea.value = questionText
  textarea.dispatchEvent(new Event('input'))
  await nextTick()
  const submitBtn = Array.from(host.querySelectorAll('button'))
    .find((b) => b.textContent.trim() === '提问')
  expect(submitBtn, '应能找提问按钮').toBeTruthy()
  submitBtn.click()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

beforeEach(() => {
  vi.clearAllMocks()
  listHistory.mockResolvedValue({ items: [] })
})

afterEach(() => {
  if (app) app.unmount()
  app = null
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('AskView 空态 · 关键词相关原文（工程增强）', () => {
  it('渲染标题、口径说明、title / chunk_id / snippet，并标注不属于证据链', async () => {
    askQuestion.mockResolvedValue({
      empty: true,
      notice: EMPTY_NOTICE,
      related_chunks: [
        { chunk_id: 1001001, doc_id: 1001, title: '长城汽车股份有限公司关于股票期权的公告',
          snippet: '公司2023年股票期权激励计划首次授予股票期权于2026年1月26日进入第二个行权期。',
          score: 336.06 },
        { chunk_id: 1048011, doc_id: 1048, title: '关于2023年第一期股票期权激励计划的议案',
          snippet: '第二个行权期符合行权条件的议案。', score: 263.96 },
      ],
      engineering_enhancement: true,
    })

    await mountAskView()
    await ask('长城汽车第二个行权期的有效期是什么？')

    const block = host.querySelector('[data-testid="related-chunks"]')
    expect(block, '有 related_chunks 时应渲染区块').toBeTruthy()
    const text = block.textContent
    expect(text).toContain('关键词相关原文（工程增强，非正式证据）')
    expect(text).toContain('不属于证据链')
    expect(text).toContain('不是正式证据，也不作为答案依据')
    expect(text).toContain('长城汽车股份有限公司关于股票期权的公告')
    expect(text).toContain('chunk_id=1001001')
    expect(text).toContain('公司2023年股票期权激励计划首次授予股票期权')
    expect(block.querySelectorAll('li')).toHaveLength(2)

    // 原有空态提示仍在，且不是错误红字
    const notice = host.querySelector('[data-testid="empty-notice"]')
    expect(notice.textContent).toContain('未检索到可引用的证据')
    expect(host.querySelector('[data-testid="ask-error"]')).toBeNull()
  })

  it('related_chunks 为空时保持原文案不变、不渲染区块', async () => {
    askQuestion.mockResolvedValue({
      empty: true,
      notice: EMPTY_NOTICE,
      related_chunks: [],
      engineering_enhancement: true,
    })

    await mountAskView()
    await ask('一个没有关键词命中的问题')

    expect(host.querySelector('[data-testid="related-chunks"]')).toBeNull()
    expect(host.querySelector('[data-testid="empty-notice"]').textContent)
      .toContain('未检索到可引用的证据')
  })
})

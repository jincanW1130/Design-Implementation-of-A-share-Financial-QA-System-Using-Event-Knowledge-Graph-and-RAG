// 工具\边界体验核对.mjs —— 第三轮优先级 5（4.1／4.4）真实浏览器核对
//
// 用真实 Chromium 驱动已启动的前端（默认 http://127.0.0.1:5173），只做四件事：
//   ① 500 字上限：输入 501 字，确认前端拦截且**不发** /api/qa/ask；
//   ② 控制字符：输入含 NUL 的问题，确认前端拦截且**不发** /api/qa/ask；
//   ③ 2002 空结果：拦截该请求并返回与后端同构的 200＋empty，确认中性提示（非红字错误）；
//   ④ 真实长问答「取消等待」：现场发起一次真实提问，2 秒后点「取消等待」，记录界面文案；
//      同时验证前端 320 秒超时分支的文案（用 init script 把 ≥300s 的定时器缩短到 1.2s，
//      仅用于走通超时分支，不伪装成真实等待 320 秒）。
//
// 边界：
//   * ③ 是**响应替身**，只验证前端呈现，不声称后端返回了 2002；
//   * ④ 会真实调用模型并可能落库。脚本本身不删库；运行后用
//     `python 工具\链路耗时取证.py` 的清理口径人工核对/清理 question_id>30。
//   * 不记录任何密钥；报告只保留界面可见文本与请求计数。
//
// 用法：
//   node 工具\边界体验核对.mjs
//   node 工具\边界体验核对.mjs --base=http://127.0.0.1:5173

import { chromium } from '../交付物/03-代码/前端/测试/uat/node_modules/playwright/index.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')
const argv = process.argv.slice(2)
const argOf = (k, d) => {
  const hit = argv.find((a) => a.startsWith(`--${k}=`))
  return hit ? hit.slice(k.length + 3) : d
}
const BASE = argOf('base', process.env.UAT_BASE || 'http://127.0.0.1:5173')
const OUT_DIR = join(ROOT, '交付物', '06-实验与评测', '系统指标', '证据_第三轮边界')
mkdirSync(OUT_DIR, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim()

const result = {
  at: new Date().toISOString(),
  base: BASE,
  browser: null,
  cases: [],
  notes: [
    '500 字与控制字符用例走前端校验，不应发出 /api/qa/ask。',
    '2002 用例使用响应替身，仅核对前端呈现，不声称后端在该次请求中返回 2002。',
    '超时用例把前端 ≥300000ms 的定时器缩短为 1200ms，只用于走通超时分支；文案中的「320 秒」为真实配置值。',
    '真实取消用例会调用模型并可能写库；脚本不删库，运行后需按 question_id>30 核对清理。',
  ],
}

const browser = await chromium.launch({ headless: true })
result.browser = `chromium ${browser.version()}`

async function newPage(opts = {}) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    ...(opts.context || {}),
  })
  if (opts.initScript) await ctx.addInitScript(opts.initScript)
  const page = await ctx.newPage()
  const reqs = []
  const failures = []
  page.on('request', (r) => {
    if (r.url().includes('/api/qa/ask')) reqs.push({ method: r.method(), url: r.url() })
  })
  page.on('requestfailed', (r) => {
    if (r.url().includes('/api/qa/ask')) {
      failures.push({ url: r.url(), error: r.failure()?.errorText || '' })
    }
  })
  await page.goto(BASE + '/ask', { waitUntil: 'networkidle', timeout: 60000 })
  return { ctx, page, reqs, failures }
}

async function readVisible(page, selector) {
  const loc = page.locator(selector)
  if (!(await loc.count())) return ''
  return clean(await loc.first().innerText())
}

async function shot(page, name) {
  const file = join(OUT_DIR, name + '.png')
  await page.screenshot({ path: file, fullPage: false }).catch(() => {})
  return file
}

// ---------------------------------------------------------------- ① 500 字
{
  const { ctx, page, reqs } = await newPage()
  const q = page.locator('#q')
  await q.fill('字'.repeat(501))
  await sleep(200)
  const counter = clean(await page.locator('p.small', { hasText: '/ 500 字' }).first().innerText())
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await sleep(500)
  const err = await readVisible(page, '[data-testid=ask-error]')
  const png = await shot(page, '01-500字上限')
  result.cases.push({
    id: 'over_500',
    title: '输入 501 字提交',
    ui: { counter, error: err },
    ask_requests: reqs.length,
    passed: reqs.length === 0 && err.includes('超过上限 500 字') && counter.includes('超出上限'),
    screenshot: png,
  })
  await ctx.close()
}

// ---------------------------------------------------------------- ② 控制字符
{
  const { ctx, page, reqs } = await newPage()
  await page.locator('#q').fill('正常问题\u0000尾巴')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await sleep(500)
  const err = await readVisible(page, '[data-testid=ask-error]')
  const png = await shot(page, '02-控制字符')
  result.cases.push({
    id: 'control_char',
    title: '输入含 NUL 控制字符的问题',
    ui: { error: err },
    ask_requests: reqs.length,
    passed: reqs.length === 0 && err.includes('控制字符'),
    screenshot: png,
  })
  await ctx.close()
}

// ---------------------------------------------------------------- ③ 2002 空结果（响应替身）
{
  const { ctx, page, reqs } = await newPage()
  const notice = '未检索到可引用的证据：这个问题在现有数据里找不到能支撑回答的原文。可以换一种问法，或指明公司、时间与事件类型后再试。'
  await page.route('**/api/qa/ask', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json; charset=utf-8',
      body: JSON.stringify({ data: { empty: true, empty_reason: 'no_citable_evidence', reused: false, notice, answer_id: null, question_id: null }, meta: null }),
    })
  })
  await page.locator('#q').fill('一个当前语料无法回答的问题')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await page.waitForSelector('[data-testid=empty-notice]', { timeout: 10000 })
  const shown = await readVisible(page, '[data-testid=empty-notice]')
  const errCount = await page.locator('[data-testid=ask-error]').count()
  const png = await shot(page, '03-2002空结果')
  result.cases.push({
    id: 'empty_2002',
    title: '后端 200＋empty（响应替身）',
    ui: { notice: shown, has_red_error: errCount > 0 },
    ask_requests: reqs.length,
    passed: shown.includes('未检索到可引用的证据') && errCount === 0,
    screenshot: png,
  })
  await ctx.close()
}

// ---------------------------------------------------------------- ④a 320 秒超时分支（缩短定时器）
{
  const { ctx, page, reqs } = await newPage({
    initScript: () => {
      const orig = window.setTimeout
      window.setTimeout = function (fn, ms, ...args) {
        const fixed = (typeof ms === 'number' && ms >= 300000) ? 1200 : ms
        return orig(fn, fixed, ...args)
      }
    },
  })
  await page.route('**/api/qa/ask', async () => { /* 永不返回，让前端超时生效 */ })
  await page.locator('#q').fill('超时分支核对')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await page.waitForSelector('[data-testid=empty-notice]', { timeout: 15000 })
  const shown = await readVisible(page, '[data-testid=empty-notice]')
  const png = await shot(page, '04-超时文案')
  result.cases.push({
    id: 'timeout_320s',
    title: '前端 320 秒超时分支（定时器缩短为 1.2 秒）',
    ui: { notice: shown },
    ask_requests: reqs.length,
    passed: shown.includes('请求超时（等待超过 320 秒仍未返回）') && shown.includes('后端可能仍会完成生成'),
    screenshot: png,
  })
  await ctx.close()
}

// ---------------------------------------------------------------- ④b 真实长问答取消等待
{
  const { ctx, page, reqs, failures } = await newPage()
  const question = '平安银行与伊利股份共同参与的事件是什么？'
  await page.locator('#q').fill(question)
  const startedAt = Date.now()
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await page.waitForSelector('button:has-text("取消等待")', { timeout: 10000 })
  const loadingText = clean(await page.locator('p.small', { hasText: '正在生成答案' }).first().innerText())
  await sleep(2000)
  await page.getByRole('button', { name: '取消等待' }).click()
  await page.waitForSelector('[data-testid=empty-notice]', { timeout: 10000 })
  const shown = await readVisible(page, '[data-testid=empty-notice]')
  const cancelButtonGone = (await page.getByRole('button', { name: '取消等待' }).count()) === 0
  const askButtonEnabled = await page.getByRole('button', { name: '提问', exact: true }).isEnabled()
  const png = await shot(page, '05-真实取消等待')
  result.cases.push({
    id: 'real_cancel',
    title: '真实长问答中点击「取消等待」',
    ui: {
      question_chars: question.length,
      loading_text: loadingText,
      notice: shown,
      cancel_button_gone: cancelButtonGone,
      ask_button_enabled_after: askButtonEnabled,
    },
    ask_requests: reqs.length,
    aborted_requests: failures,
    elapsed_before_cancel_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
    passed: shown.includes('请求已取消') && shown.includes('后端可能仍会完成生成')
      && cancelButtonGone && askButtonEnabled && reqs.length === 1,
    screenshot: png,
    note: '取消只停止浏览器等待；后端可能继续完成并落库，脚本不删库，需另行核对 30/30/293 基线。',
  })
  await ctx.close()
}

await browser.close()

const passed = result.cases.filter((c) => c.passed).length
result.summary = { total: result.cases.length, passed,
                   all_passed: passed === result.cases.length }
const out = join(ROOT, '交付物', '06-实验与评测', '系统指标', '边界体验核对_第三轮.json')
writeFileSync(out, JSON.stringify(result, null, 2), 'utf8')

console.log('='.repeat(72))
console.log('边界与体验核对（第三轮）')
console.log('='.repeat(72))
for (const c of result.cases) {
  console.log(`${c.passed ? '通过' : '失败'}  ${c.id}  ${c.title}`)
  if (c.ui.error) console.log('       错误区：' + c.ui.error)
  if (c.ui.notice) console.log('       提示区：' + c.ui.notice)
  console.log('       ask 请求数：' + c.ask_requests)
}
console.log(`合计：${passed}/${result.cases.length} 通过`)
console.log('报告：' + out)
console.log('截图：' + OUT_DIR)

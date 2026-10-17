// 交付物/03-代码/前端/测试/uat/测请求预算.mjs
//
// 量化「一次页面访问要花掉多少后端请求额度」。
// 后端 main.py 的 RateLimitMiddleware 是**按来源 IP 的全局滑动窗口**（window_seconds=60、
// max_requests=60，/api/health 豁免），所以整站共用一份 60 次／分钟的额度。
// 本脚本用真实浏览器逐页计数，输出每页请求数、总量、以及是否触发 429。
//
// 用法：node 交付物/03-代码/前端/测试/uat/测请求预算.mjs [--tag=优化前]

import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.UAT_BASE || 'http://127.0.0.1:5173'
const TAG = (process.argv.find((a) => a.startsWith('--tag=')) || '--tag=首轮').slice(6)
const OUT = join(__dirname, '证据', TAG)
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
const page = await ctx.newPage()

let bucket = []
const all = []
page.on('request', (r) => {
  const u = r.url()
  if (!u.includes('/api/')) return
  const p = u.replace(BASE, '').split('?')[0]
  bucket.push(p)
  all.push(p)
})

async function step(name, fn, settleMs = 3500) {
  bucket = []
  const t = Date.now()
  await fn()
  await sleep(settleMs)
  const byPath = bucket.reduce((a, p) => (a[p] = (a[p] || 0) + 1, a), {})
  const rows = Object.entries(byPath).sort((a, b) => b[1] - a[1])
  console.log(`\n### ${name}  —— /api 请求 ${bucket.length} 次，耗时 ${((Date.now() - t) / 1000).toFixed(1)}s`)
  rows.forEach(([p, n]) => console.log(`    ${String(n).padStart(3)} × ${p}`))
  return { name, count: bucket.length, byPath, rows }
}

const results = []
results.push(await step('① 冷启动首屏（/，App.vue mount）', async () => {
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
}))
results.push(await step('② 进入提问页 /ask', async () => {
  await page.goto(BASE + '/ask', { waitUntil: 'networkidle', timeout: 60000 })
}))
results.push(await step('③ 进入图谱页 /graph（锚点 600519 默认）', async () => {
  await page.goto(BASE + '/graph', { waitUntil: 'networkidle', timeout: 60000 })
}, 20000))   // 图谱页有 prefetchEvents 分批拉取，给足结算时间
results.push(await step('④ 图谱页内搜一次实体（宁德时代）', async () => {
  const box = page.locator('input[type=text]').first()
  await box.fill('宁德时代')
  await page.keyboard.press('Enter')
}, 4000))
const resp429 = []
page.on('response', (r) => { if (r.status() === 429) resp429.push(r.url().replace(BASE, '').split('?')[0]) })
results.push(await step('⑤ 图谱页内再搜一次（不存在的实体）', async () => {
  const box = page.locator('input[type=text]').first()
  await box.fill('zzzz不存在的实体xyz')
  await page.keyboard.press('Enter')
}, 4000))
results.push(await step('⑥ 切到历史页 /history', async () => {
  await page.goto(BASE + '/history', { waitUntil: 'networkidle', timeout: 60000 })
}, 3000))
results.push(await step('⑦ 点开一条历史记录回看', async () => {
  const link = page.locator('a[href*="/answer/"]').first()
  if (await link.count()) await link.click()
}, 4000))

const total = all.length
const total429 = resp429.length
const now = await page.evaluate(() => document.body.innerText.slice(0, 400))

const report = {
  tag: TAG, base: BASE, at: new Date().toISOString(),
  steps: results.map((r) => ({ name: r.name, count: r.count, byPath: r.byPath })),
  totalApiRequests: total,
  budget: { window_seconds: 60, max_requests: 60, scope: '所有 /api/*（/api/health 豁免），按来源 IP 全局计数' },
  overBudget: total > 60,
  responses429: total429,
  sample429: resp429.slice(0, 12),
  note: '一次完整走查（首屏→提问→图谱→搜两次→历史→回看）消耗的额度；后端上限是 60 次／60 秒／来源 IP。',
}
writeFileSync(join(OUT, '请求预算.json'), JSON.stringify(report, null, 2), 'utf8')

console.log('\n================ 结论 ================')
console.log(`一次完整走查共发出 /api 请求：${total} 次`)
console.log(`后端额度：60 次／60 秒／来源 IP（全站共用，/api/health 豁免）`)
console.log(`是否超预算：${total > 60 ? '是 —— 一次走查就会把整站额度打满' : '否'}`)
console.log(`本次实测 429 响应：${total429} 条`)
if (total429) console.log(`  受影响端点样例：${[...new Set(resp429)].slice(0, 8).join('、')}`)
console.log(`报告落盘：${join(OUT, '请求预算.json')}`)

await browser.close()

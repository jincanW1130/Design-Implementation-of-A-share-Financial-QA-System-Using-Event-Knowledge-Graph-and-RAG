// 跨浏览器 × 移动设备走查装置（UAT 补充装置）
//
// 目的：把「只测过 Chromium」这条限制补上——用同一套断言在 Chromium／Firefox／WebKit
// （Safari 的引擎）三个内核上各走一遍，并且除桌面 1440×900 外，再用真实设备描述符
// （Pixel 5 ／ iPhone 13：含 isMobile／hasTouch／deviceScaleFactor／mobile UA）走一遍小屏，
// 而不是仅用一个 390×844 的视口模拟。
//
// 断言（与《跑UAT.mjs》同源，但只保留跨引擎可比的部分）：
//   ① 页面可达（HTTP 200）
//   ② 无横向溢出（documentElement.scrollWidth － clientWidth ≤ 0）
//   ③ 主标题存在且非空（h1）
//   ④ 可见文本非空（去空白后 ≥ 20 字）
//   ⑤ 浏览器控制台无错误（429 单列为「环境限流」，不计入缺陷——后端 60 次／60 秒是门禁锁定值）
//   ⑥ 截图留证（每引擎 × 每设备 × 每页一张）
//
// 用法：
//   node 跨浏览器走查.mjs                 # 三引擎 ＋ 桌面／移动，共 18 次页面访问
//   node 跨浏览器走查.mjs --engines=firefox,webkit
//
// 说明：本装置**不改产品代码、不改后端限流参数**；为了不撞 60 次／60 秒的全局额度，
// 页与页之间固定间隔 4 秒、设备档之间固定间隔 25 秒。

import { chromium, firefox, webkit, devices } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const argOf = (k, dflt) => {
  const hit = argv.find((a) => a.startsWith(`--${k}=`))
  return hit ? hit.slice(k.length + 3) : dflt
}
const BASE = argOf('base', 'http://127.0.0.1:5173')
const ENGINES = argOf('engines', 'chromium,firefox,webkit').split(',').map((s) => s.trim()).filter(Boolean)
const TAG = argOf('tag', '跨浏览器')
const GAP_PAGE = Number(argOf('gap-page', '4000'))
const GAP_PROFILE = Number(argOf('gap-profile', '25000'))

const OUT = path.join(HERE, '证据', TAG)
fs.mkdirSync(OUT, { recursive: true })

const LAUNCHERS = { chromium, firefox, webkit }
const PROFILES = [
  { id: 'desktop-1440x900', label: '桌面 1440×900', viewport: { width: 1440, height: 900 } },
  { id: 'pixel5', label: 'Pixel 5（Android 设备描述符）', device: 'Pixel 5' },
  { id: 'iphone13', label: 'iPhone 13（iOS 设备描述符）', device: 'iPhone 13' },
]
// WebKit 上跑 iPhone 描述符、Chromium/Firefox 上跑 Pixel 描述符更接近真实；三者互相交叉并不必要，
// 因此每个引擎跑「桌面 ＋ 一个最贴近该引擎的手机描述符」，共 3 × 2 × 3 页 = 18 次访问。
const PROFILE_MAP = {
  chromium: ['desktop-1440x900', 'pixel5'],
  firefox: ['desktop-1440x900', 'pixel5'],
  webkit: ['desktop-1440x900', 'iphone13'],
}

// 答案页用哪条回答：**动态解析**，不写死。
// 2026-10-18 全面审查（第二轮）修复：原先写死 `/answer/40`，而 40 号是当时临时跑出来的
// 问答；数据库按交付基线清回 30 条后该页 404，跨引擎走查直接掉 22 个 major——是**夹具过期**，
// 不是产品回归。现改为：先问 `/api/history?session_id=S-001` 取第一条真实回答，
// 取不到再退回基线里的 16 号（`ask_time` 最新的一条导入记录）。
async function resolveAnswerId() {
  try {
    const r = await fetch(`${BASE}/api/history?session_id=S-001&page=1&page_size=1`)
    const j = await r.json()
    const items = (j && j.data && j.data.items) || []
    if (items.length && items[0].answer_id != null) return Number(items[0].answer_id)
  } catch { /* 回落 */ }
  return 16
}
const ANSWER_ID = await resolveAnswerId()
console.log(`答案页夹具：/answer/${ANSWER_ID}（自 /api/history?session_id=S-001 解析）`)

const PAGES = [
  { id: 'ask', url: '/ask', name: '提问台', expect: 'hasAskBox', label: '提问框 #q', settledSel: '#q', settledLabel: '提问框 #q' },
  { id: 'answer', url: `/answer/${ANSWER_ID}`, name: '答案与证据', expect: 'hasAnswer', label: '答案段头【回答】', settledSel: 'text=【回答】', settledLabel: '答案段头【回答】' },
  { id: 'graph', url: '/graph', name: '知识图谱', expect: 'hasAnchor', label: '「当前锚点」或 ≥1 个 .gnode', settledSel: '.gnode', settledLabel: '图谱节点 .gnode' },
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const findings = []
const shots = []
const record = (level, engine, profile, page, msg) =>
  findings.push({ level, engine, profile, page, msg })
const isRateLimit = (t) => /429|Too Many Requests/.test(t)

let currentEngine = ''
let currentProfile = ''

for (const engineId of ENGINES) {
  const launcher = LAUNCHERS[engineId]
  if (!launcher) { record('error', engineId, '', '', '未知引擎，跳过'); continue }
  currentEngine = engineId
  let browser
  try {
    browser = await launcher.launch({ headless: true })
  } catch (e) {
    record('error', engineId, '', '', '启动失败：' + e.message.split('\n')[0])
    continue
  }
  record('info', engineId, '', '', `引擎启动成功（${browser.version()}）`)

  for (const profId of PROFILE_MAP[engineId] || ['desktop-1440x900']) {
    const prof = PROFILES.find((p) => p.id === profId)
    currentProfile = profId
    const ctxOpts = prof.device
      ? { ...devices[prof.device] }
      : { viewport: prof.viewport }
    const context = await browser.newContext({ ...ctxOpts, locale: 'zh-CN', timezoneId: 'Asia/Shanghai' })

    for (const pg of PAGES) {
      const page = await context.newPage()
      const consoleErrors = []
      const pageErrors = []
      page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
      page.on('pageerror', (e) => pageErrors.push(String(e.message || e)))

      const url = BASE + pg.url
      let status = 0
      let settled = false
      const t0 = Date.now()
      try {
        const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 })
        status = resp ? resp.status() : 0
        // 2026-10-18 改：原先固定等 2.5 秒，移动档（DPR 2.75／3）渲染慢，2.5 秒时图谱页只到
        // 757 字、0 个节点，会被误判成异常。改为**按该页就绪标志等待**，再补 800ms 收尾。
        try {
          await page.waitForSelector(pg.settledSel, { timeout: 20000 })
          settled = true
        } catch {
          settled = false
        }
        await page.waitForTimeout(800)
      } catch (e) {
        record('error', engineId, profId, pg.id, `打开失败：${e.message.split('\n')[0]}`)
      }
      const ms = Date.now() - t0
      if (!settled) record('major', engineId, profId, pg.id, `20 秒内未出现就绪标志「${pg.settledLabel}」（疑似加载失败或错误态）`)

      if (status !== 200) {
        record('error', engineId, profId, pg.id, `HTTP ${status}`)
      } else {
        record('pass', engineId, profId, pg.id, `HTTP 200（${ms} ms）`)
      }

      let metrics = {}
      try {
        metrics = await page.evaluate(() => {
          const de = document.documentElement
          const h1 = document.querySelector('h1')
          const cs = h1 ? getComputedStyle(h1) : null
          return {
            vw: de.clientWidth,
            sw: de.scrollWidth,
            overflow: de.scrollWidth - de.clientWidth,
            dpr: window.devicePixelRatio,
            ua: navigator.userAgent,
            hasTouch: 'ontouchstart' in window,
            title: document.title,
            h1: h1 ? (h1.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60) : '',
            h1Font: cs ? `${cs.fontSize}/${cs.fontWeight}` : '',
            textLen: (document.body.innerText || '').replace(/\s+/g, '').length,
            canvas: document.querySelectorAll('canvas').length,
            svg: document.querySelectorAll('svg').length,
            gnode: document.querySelectorAll('.gnode').length,
            // 2026-10-18 补：逐页「内容达标」判据。
            // 起因：本装置原先只判「可见文本 ≥20 字」，于是一次图谱页因请求失败退化成错误态
            // （仅 757 字、0 个节点）仍被判 pass——判据太松会把坏页面记成好页面。
            hasAskBox: !!document.querySelector('#q'),
            hasAnswer: (document.body.innerText || '').includes('【回答】'),
            hasAnchor: (document.body.innerText || '').includes('当前锚点') || document.querySelectorAll('.gnode').length > 0,
          }
        })
      } catch (e) {
        record('error', engineId, profId, pg.id, '取指标失败：' + e.message.split('\n')[0])
      }

      if (metrics.overflow !== undefined) {
        if (metrics.overflow <= 0) record('pass', engineId, profId, pg.id, `无横向溢出（视口 ${metrics.vw}px，滚动宽 ${metrics.sw}px）`)
        else record('major', engineId, profId, pg.id, `横向溢出 ${metrics.overflow}px（视口 ${metrics.vw}／滚动 ${metrics.sw}）`)
      }
      if (metrics.h1 !== undefined) {
        if (metrics.h1) record('pass', engineId, profId, pg.id, `主标题非空：${metrics.h1}`)
        else record('major', engineId, profId, pg.id, '主标题（h1）缺失或为空')
      }
      if (metrics.textLen !== undefined) {
        if (metrics.textLen >= 20) record('pass', engineId, profId, pg.id, `可见文本 ${metrics.textLen} 字`)
        else record('major', engineId, profId, pg.id, `可见文本仅 ${metrics.textLen} 字（疑似白屏）`)
      }
      if (metrics[pg.expect] !== undefined) {
        if (metrics[pg.expect]) record('pass', engineId, profId, pg.id, `内容达标：${pg.label}`)
        else record('major', engineId, profId, pg.id, `未渲染预期内容（疑似错误态）：缺少 ${pg.label}；可见文本 ${metrics.textLen} 字`)
      }
      if (metrics.dpr !== undefined) {
        record('info', engineId, profId, pg.id,
          `DPR=${metrics.dpr}｜touch=${metrics.hasTouch}｜h1=${metrics.h1Font}｜canvas=${metrics.canvas}｜svg=${metrics.svg}｜gnode=${metrics.gnode}`)
      }

      const realErrors = consoleErrors.filter((t) => !isRateLimit(t))
      const limited = consoleErrors.filter(isRateLimit)
      if (realErrors.length === 0) record('pass', engineId, profId, pg.id, '控制台无错误（429 另计）')
      else record('major', engineId, profId, pg.id, `控制台错误 ${realErrors.length} 条：${realErrors.slice(0, 2).join(' ｜ ')}`)
      if (limited.length) record('info', engineId, profId, pg.id, `环境限流 429 共 ${limited.length} 条（后端 60 次／60 秒，非缺陷）`)
      if (pageErrors.length) record('major', engineId, profId, pg.id, `未捕获异常 ${pageErrors.length} 条：${pageErrors[0].slice(0, 120)}`)

      const file = path.join(OUT, `${engineId}-${profId}-${pg.id}.png`)
      try {
        await page.screenshot({ path: file, fullPage: false })
        shots.push({ engine: engineId, profile: profId, page: pg.id, file })
      } catch { /* 截图失败不阻断 */ }

      await page.close()
      await sleep(GAP_PAGE)
    }
    await context.close()
    await sleep(GAP_PROFILE)
  }
  await browser.close()
}

const count = (lv) => findings.filter((f) => f.level === lv).length
const summary = {
  tag: TAG,
  base: BASE,
  startedAt: new Date().toISOString(),
  engines: ENGINES,
  profiles: PROFILE_MAP,
  counts: { pass: count('pass'), info: count('info'), major: count('major'), error: count('error') },
  findings,
  shots,
}
fs.writeFileSync(path.join(OUT, '跨浏览器-结果.json'), JSON.stringify(summary, null, 2), 'utf8')

const txt = []
txt.push(`# 跨浏览器 × 移动设备走查（${TAG}）`)
txt.push('')
txt.push(`- 目标：${BASE}`)
txt.push(`- 引擎／设备：${ENGINES.map((e) => `${e}(${PROFILE_MAP[e].join(' + ')})`).join('；')}`)
txt.push(`- 汇总：通过 ${summary.counts.pass}｜记录 ${summary.counts.info}｜严重 ${summary.counts.major}｜错误 ${summary.counts.error}`)
txt.push('')
for (const f of findings) {
  if (f.level === 'info' && !/DPR=/.test(f.msg)) continue
  txt.push(`[${f.level}] ${f.engine}/${f.profile} ${f.page} | ${f.msg}`)
}
fs.writeFileSync(path.join(OUT, '跨浏览器-完整跑.txt'), txt.join('\n'), 'utf8')

console.log(txt.join('\n'))
console.log('')
console.log(`=== 结束 === pass=${summary.counts.pass} info=${summary.counts.info} major=${summary.counts.major} error=${summary.counts.error}`)
console.log('证据目录：' + OUT)
process.exit(summary.counts.major + summary.counts.error > 0 ? 1 : 0)

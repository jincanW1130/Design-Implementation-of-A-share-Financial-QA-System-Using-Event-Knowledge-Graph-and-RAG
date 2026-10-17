// 交付物/03-代码/前端/测试/uat/跑UAT.mjs
//
// 用户验收测试（UAT）装置：用 Playwright 驱动真实 Chromium，按「参与者 × 任务」走查
// A 股信息披露问答系统的四条页面，逐步截图、记录控制台错误与失败请求，落到 uat/证据/ 下。
//
// 用法：
//   node 交付物/03-代码/前端/测试/uat/跑UAT.mjs                # 跑全部任务
//   node .../跑UAT.mjs --only=T1,T4                           # 只跑指定任务
//   node .../跑UAT.mjs --tag=优化前                            # 证据目录后缀（优化前 / 优化后）
//   node .../跑UAT.mjs --slow                                 # 放慢操作（录屏友好）
//   node .../跑UAT.mjs --pace=18000                            # 任务间隔毫秒（默认 18000；=0 复现「密集爆发」）
//
// 环境变量：
//   UAT_BASE  默认 http://127.0.0.1:5173
//
// 设计约束（都来自本课题的既有硬约束，不得违逆）：
//   · 只读 + 提问：脚本不改后端数据、不写入任何凭据；
//   · 提问任务会真实调用大模型（需后端与模型可用），耗时以分钟计；
//   · 每一步都截图，失败也要截图——截图是本次用户测试的原始证据。

import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.UAT_BASE || 'http://127.0.0.1:5173'

// ---------------------------------------------------------------- 参数
const argv = process.argv.slice(2)
const argOf = (k, d) => {
  const hit = argv.find((a) => a.startsWith(`--${k}=`))
  return hit ? hit.slice(k.length + 3) : d
}
const TAG = argOf('tag', '首轮')
const ONLY = argOf('only', '').split(',').map((s) => s.trim()).filter(Boolean)
const SLOW = argv.includes('--slow')
const EVID = join(__dirname, '证据', TAG)
mkdirSync(EVID, { recursive: true })

// ---------------------------------------------------------------- 记录器
const findings = []
const shots = []
let stepNo = 0
const t0 = Date.now()

function note(level, task, msg, extra = {}) {
  const rec = { t: ((Date.now() - t0) / 1000).toFixed(1) + 's', level, task, msg, ...extra }
  findings.push(rec)
  const tag = { blocker: '阻断', major: '严重', minor: '轻微', throttle: '限流', info: '记录', pass: '通过' }[level] || level
  console.log(`[${rec.t}] ${tag} | ${task} | ${msg}`)
}

async function shot(page, name, full = true) {
  stepNo += 1
  const file = join(EVID, `${String(stepNo).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path: file, fullPage: full }).catch(() => {})
  shots.push({ name, file })
  return file
}

// ---------------------------------------------------------------- 页面探针（注入到浏览器里）
// 采集「用户能看见什么」的结构化事实：可见文本、可聚焦元素、可点元素、对比度采样点等。
const PROBE = () => {
  const vis = (el) => {
    const r = el.getBoundingClientRect()
    const s = getComputedStyle(el)
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05
  }
  const label = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 40)
  const focusables = [...document.querySelectorAll('a,button,input,textarea,select,[tabindex]')]
    .filter(vis)
    .map((el) => ({ tag: el.tagName.toLowerCase(), label: label(el), disabled: !!el.disabled, tabindex: el.getAttribute('tabindex') }))
  const clickables = [...document.querySelectorAll('a,button,[role=button],[role=tab],.hrow,.gnode,.chip,summary')]
    .filter(vis).map(label).filter(Boolean)
  // 小字号 / 低对比风险：收集所有可见文本节点的字号
  const fontSizes = {}
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    if (!hasText) continue
    const px = parseFloat(getComputedStyle(el).fontSize) || 0
    fontSizes[px] = (fontSizes[px] || 0) + 1
  }
  const smallText = Object.entries(fontSizes).filter(([px]) => Number(px) < 12)
    .reduce((a, [px, n]) => a + n, 0)
  const totalText = Object.values(fontSizes).reduce((a, b) => a + b, 0)
  // 横向溢出（小屏适配）
  const overflowX = document.documentElement.scrollWidth - document.documentElement.clientWidth
  // 空占位 / 死链
  const deadLinks = [...document.querySelectorAll('a[href="#"]')].filter(vis).map(label)
  return {
    title: document.title,
    url: location.href,
    bodyText: document.body.innerText.replace(/\n{3,}/g, '\n\n').slice(0, 12000),
    textLen: document.body.innerText.length,
    focusables, clickables, fontSizes, smallText, totalText, overflowX, deadLinks,
    h: document.documentElement.scrollHeight,
    ariaLabelled: [...document.querySelectorAll('[aria-labelledby]')].map((el) => el.getAttribute('aria-labelledby')),
    ids: [...document.querySelectorAll('[id]')].map((el) => el.id),
  }
}

// ---------------------------------------------------------------- 主流程
const ctx = { shots, findings, evidenceDir: EVID }

function mkPage(browser, errors) {
  return browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    deviceScaleFactor: 1,
  }).then(async (c) => {
    const page = await c.newPage()
    page.on('console', (m) => { if (m.type() === 'error') errors.push({ kind: 'console', text: m.text().slice(0, 400), url: page.url() }) })
    page.on('pageerror', (e) => errors.push({ kind: 'pageerror', text: String(e).slice(0, 400), url: page.url() }))
    page.on('requestfailed', (r) => errors.push({ kind: 'requestfailed', text: `${r.method()} ${r.url()} — ${r.failure()?.errorText}`, url: page.url() }))
    page.on('response', (r) => { if (r.status() >= 400) errors.push({ kind: 'http', text: `${r.status()} ${r.request().method()} ${r.url()}`, url: page.url() }) })
    return { context: c, page }
  })
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function goto(page, path, task) {
  const errors = []
  const url = BASE + path
  try {
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 })
    note(resp && resp.ok() ? 'pass' : 'major', task, `打开 ${path} → HTTP ${resp && resp.status()}`)
  } catch (e) {
    note('blocker', task, `打开 ${path} 失败：${e.message.split('\n')[0]}`)
  }
  await sleep(SLOW ? 1200 : 600)
  return errors
}

async function probe(page, task, name) {
  const p = await page.evaluate(PROBE)
  await shot(page, name)
  writeFileSync(join(EVID, `${String(stepNo).padStart(2, '0')}-${name}.json`), JSON.stringify(p, null, 2), 'utf8')
  return p
}

// ================================================================ 任务定义
const TASKS = {}

// T1 新访客首屏：60 秒内能不能自己搞明白「这是什么、能问什么、从哪开始」
TASKS.T1 = {
  name: 'T1 新访客首屏自解释性',
  persona: 'P4 首次来访者',
  async run(page, errors) {
    const T = 'T1'
    await goto(page, '/', T)
    await page.waitForTimeout(1500)
    const p = await probe(page, T, 'T1-首屏')
    note(p.textLen > 400 ? 'pass' : 'major', T, `首屏可见文本 ${p.textLen} 字`)
    if (p.smallText / Math.max(1, p.totalText) > 0.35) note('minor', T, `小字号（<12px）文本块占比 ${(100 * p.smallText / p.totalText).toFixed(0)}%`)
    if (p.overflowX > 2) note('major', T, `页面横向溢出 ${p.overflowX}px（1440 宽视口）`)
    note('info', T, `可聚焦元素 ${p.focusables.length} 个；可点元素 ${p.clickables.length} 个`)
    if (p.deadLinks.length) note('minor', T, `href="#" 占位链接 ${p.deadLinks.length} 个：${[...new Set(p.deadLinks)].slice(0, 8).join('、')}`)
    // 首屏是否给出「可以直接问什么」——示例问题是否存在且可点击
    const chips = await page.locator('.chip, [data-cursor-label], .ex, .example, button').allInnerTexts().catch(() => [])
    const haveExample = chips.some((s) => /[？?]/.test(s))
    note(haveExample ? 'pass' : 'major', T, haveExample ? '首屏存在可点击的示例问题' : '首屏未发现可点击的示例问题（新访客不知道能问什么）')
    ctx.T1 = { probe: p, chips }
  },
}

// T2 提问主链路：用真实问题走一次完整问答，量各阶段耗时与中间态
TASKS.T2 = {
  name: 'T2 提问主链路（真实大模型）',
  persona: 'P1 投研分析师',
  question: '宁德时代和比亚迪在动力电池领域有哪些竞争关系？',
  async run(page, errors) {
    const T = 'T2'
    await goto(page, '/ask', T)
    const p0 = await probe(page, T, 'T2-提问页')
    if (p0.overflowX > 2) note('major', T, `提问页横向溢出 ${p0.overflowX}px`)

    // 找输入框。**必须锚到 id="q"**：页面上另有 hero 的「开始提问」（只做 scrollIntoView）与示例 chip，
    // 宽泛的 `textarea, input, button` 选择器会先取到别的元素（本装置首版就取到 `.btn--primary`＝「开始提问」，
    // 于是点击只滚动页面、不触发 POST，后端从未收到 /api/qa/ask —— 那是装置缺陷，不是产品缺陷）。
    const box = page.locator('#q')
    if (!(await box.count())) { note('blocker', T, '提问页找不到输入框 #q'); return }
    const submit = page.locator('button.btn--quiet', { hasText: '提问' }).first()
    note((await submit.count()) ? 'pass' : 'blocker', T, (await submit.count()) ? '找到提交按钮（#q ＋ button.btn--quiet）' : '找不到提交按钮')

    const tStart = Date.now()
    // **必须按「URL 进入 /answer/」判定答案到达**：提问页 textarea 的 placeholder 里就含「…事件是什么？」，
    // 而正文常出现「【回答】」字样（首版用 /【回答】/ 判到，0.6 s 就误报「答案出现」）。
    let sawPost = null
    const onReq = (r) => { if (r.url().includes('/api/qa/ask')) sawPost = Date.now() }
    page.on('request', onReq)
    await box.click()
    await box.type(this.question, { delay: SLOW ? 40 : 5 })
    await shot(page, 'T2-已输入问题')
    // 键盘可达性：回车能不能提交
    await submit.click()

    // 观察中间态：有没有 loading / 阶段提示
    const seen = new Set()
    const deadline = Date.now() + 8 * 60 * 1000
    let firstAnswerAt = null
    while (Date.now() < deadline) {
      const state = await page.evaluate(() => {
        const txt = document.body.innerText
        const btn = document.querySelector('button.btn--quiet')
        return {
          url: location.href,
          onAnswerPage: /\/answer\//.test(location.pathname),
          loading: !!document.querySelector('.loading, .spinner, [aria-busy=true], .skeleton, .pulse, .breathe'),
          busyText: (txt.match(/(正在|检索中|生成中|思考中|请稍候|排队|已等待)[^\n]{0,28}/g) || []).slice(0, 3),
          // 提交已经结束（按钮回到「提问」且可点）——用于**在失败时立即收尾**，
          // 而不是像首版那样一路等到 8 分钟兜底（实测那次把「429 后卡在生成中」记成了「过慢」，
          // 掩盖了真正的结论：请求已经失败、用户应看到可重试的提示）。
          submitDone: !!(btn && !btn.disabled && /^\s*提问\s*$/.test(btn.innerText || '')),
          errText: (txt.match(/\[1004\][^\n]{0,80}|请求频率超出限制[^\n]{0,40}|复制失败|生成失败|超时[^\n]{0,30}/g) || []).slice(0, 2),
        }
      })
      ;(state.busyText || []).forEach((s) => seen.add(s.trim()))
      if (state.loading) seen.add('存在加载态元素')
      if (state.onAnswerPage && !firstAnswerAt) {
        firstAnswerAt = Date.now()
        note('pass', T, `进入答案页，端到端 ${((firstAnswerAt - tStart) / 1000).toFixed(1)}s`)
        await page.waitForTimeout(2500)
        await shot(page, 'T2-答案出现')
        break
      }
      if (state.submitDone && !state.onAnswerPage) {
        // 提交已结束但没进答案页＝这次提问失败（最常见是被限流 1004）
        note('major', T, `提问失败：提交结束但未进入答案页，耗时 ${((Date.now() - tStart) / 1000).toFixed(1)}s；页面上的错误提示：${(state.errText || []).join(' / ') || '（未捕获到错误文案）'}`)
        await shot(page, 'T2-提问失败')
        break
      }
      await page.waitForTimeout(1500)
    }
    page.off('request', onReq)
    if (!sawPost) note('blocker', T, '点击提交后后端从未收到 POST /api/qa/ask —— 提交链路断了（本装置已锚定 #q 与「提问」按钮）')
    else note('pass', T, `POST /api/qa/ask 已发出（提交后 ${((sawPost - tStart) / 1000).toFixed(1)}s）`)
    const totalS = (Date.now() - tStart) / 1000
    note(seen.size ? 'pass' : 'major', T, `等待期间用户可见的进度反馈：${[...seen].join(' | ') || '无（纯白等）'}`)
    note(totalS < 90 ? 'pass' : (totalS < 240 ? 'minor' : 'major'), T, `端到端总耗时 ${totalS.toFixed(1)}s（${totalS < 90 ? '流畅' : totalS < 240 ? '偏慢但可忍' : '过慢，用户会离开'}）`)

    const pA = await probe(page, T, 'T2-答案页')
    if (pA.overflowX > 2) note('major', T, `答案页横向溢出 ${pA.overflowX}px`)
    note(pA.textLen > 200 ? 'pass' : 'major', T, `答案页可见文本 ${pA.textLen} 字`)
    const idHit = page.url().match(/\/answer\/(\d+)/)
    ctx.T2 = { probe: pA, totalS, firstAnswerS: firstAnswerAt ? (firstAnswerAt - tStart) / 1000 : null, feedback: [...seen], answerId: idHit ? idHit[1] : null }
    note(ctx.T2.answerId ? 'pass' : 'major', T, ctx.T2.answerId ? `本次提问落 answer_id=${ctx.T2.answerId}（后续 T3／T7 直接复用它）` : '未从 URL 取到 answer_id')
  },
}

// T3 答案可追溯性：四段结构 + 证据回原文 + 图谱路径
TASKS.T3 = {
  name: 'T3 答案可追溯性与证据回原文',
  persona: 'P2 研究生（写作防幻觉）',
  async run(page, errors) {
    const T = 'T3'
    // 优先直接用 T2 刚产生的 answer_id（同会话），否则退回历史列表第一条
    const direct = ctx.T2 && ctx.T2.answerId
    if (direct) {
      await goto(page, `/answer/${direct}`, T)
      await page.waitForTimeout(2500)
      note('pass', T, `直接打开本次提问的答案 /answer/${direct}`)
    } else {
      await goto(page, '/history', T)
      const pH0 = await probe(page, T, 'T3-历史页')
      const rows = page.locator('.hrow, a[href*="/answer/"]')
      const n = await rows.count()
      note(n > 0 ? 'pass' : 'major', T, `历史页可回看条目 ${n} 个`)
      if (!n) { ctx.T3 = { pH: pH0 }; return }
      const links = page.locator('a[href*="/answer/"]')
      if (await links.count()) await links.first().click()
      else await rows.first().click()
      await page.waitForTimeout(2500)
      note(page.url().includes('/answer/') ? 'pass' : 'major', T, `跳转到 ${page.url().replace(BASE, '')}`)
    }
    const pH = null
    const pA = await probe(page, T, 'T3-答案详情')

    // 四段结构检查
    for (const seg of ['【回答】', '【证据来源】', '【知识图谱路径】', '【数据截至与判定区间】']) {
      const has = pA.bodyText.includes(seg)
      note(has ? 'pass' : 'major', T, `段落 ${seg} ${has ? '存在' : '缺失'}`)
    }

    // 证据条目 → 查看原文上下文
    const evBtn = page.locator('button:has-text("查看原文"), button:has-text("原文"), summary:has-text("证据")').first()
    if (await evBtn.count()) {
      await evBtn.click().catch(() => {})
      await page.waitForTimeout(2000)
      const pE = await probe(page, T, 'T3-原文上下文')
      const ok = /原文|上下文|chunk|文档/i.test(pE.bodyText)
      note(ok ? 'pass' : 'major', T, ok ? '证据可回看原文上下文' : '点了「查看原文」但看不到原文')
    } else {
      note('major', T, '答案页找不到「查看原文上下文」入口')
    }
    ctx.T3 = { pH, pA }
  },
}

// T4 图谱页可用性：能不能检索到实体、看到邻居与路径、空结果是否友好
TASKS.T4 = {
  name: 'T4 知识图谱浏览可用性',
  persona: 'P3 合规/风控与 P2',
  async run(page, errors) {
    const T = 'T4'
    await goto(page, '/graph', T)
    const p0 = await probe(page, T, 'T4-图谱首屏')
    if (p0.overflowX > 2) note('major', T, `图谱页横向溢出 ${p0.overflowX}px`)

    const box = page.locator('input[type=text], input[type=search], textarea').first()
    if (!(await box.count())) { note('blocker', T, '图谱页没有检索输入框'); return }
    // 正向：存在的公司名
    await box.click(); await box.fill('宁德时代')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(3000)
    const p1 = await probe(page, T, 'T4-检索宁德时代')
    note(/宁德时代/.test(p1.bodyText) ? 'pass' : 'major', T, /宁德时代/.test(p1.bodyText) ? '实体检索命中' : '实体检索无结果')

    // 空结果友好度：乱码查询
    await box.click(); await box.fill('zzzz不存在的实体xyz')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(2500)
    const p2 = await probe(page, T, 'T4-空结果')
    // 判据要窄：页面上有大量合规性说明文案本身就含「失败」二字（例如「接口请求失败：…」的兜底提示），
    // 首版用宽泛的 /失败|错误/ 会把说明文字误判成「像报错」。
    const friendly = /未检索到|无匹配|没有找到|无结果/.test(p2.bodyText)
    const looksError = /\[1004\]|\[1002\]|\[3001\]|1004 请求频率|请求频率超出限制|TypeError|Internal Server Error/.test(p2.bodyText)
    // 空结果时画布是否还留着上一个锚点的数据（这是本次测试要抓的核心缺陷）
    const canvasStillStale = /已选中\s*·/.test(p2.bodyText) || /已选中/.test(p2.bodyText)
    note(friendly && !looksError ? 'pass' : (looksError ? 'major' : 'minor'), T,
      friendly && !looksError ? '空结果有友好提示且不像报错' : `空结果呈现：${looksError ? '像报错' : '无明确提示'}`)
    note(canvasStillStale ? 'major' : 'pass', T, canvasStillStale
      ? '搜不到实体时，主画布与属性面板仍留着上一个锚点的数据（用户会以为「搜到的就是这个」）'
      : '搜不到实体时画布没有留下上一个锚点的数据')

    // 节点点击 → 邻居
    const node = page.locator('.gnode').first()
    if (await node.count()) {
      await node.click().catch(() => {})
      await page.waitForTimeout(2000)
      const p3 = await probe(page, T, 'T4-节点详情')
      note(p3.textLen > p1.textLen * 0.8 ? 'pass' : 'minor', T, '点击节点后有详情/邻居展开')
    } else {
      note('minor', T, '图谱页未渲染可点节点（.gnode 不存在）')
    }
    ctx.T4 = { p0, p1, p2 }
  },
}

// T5 键盘与无障碍：只用键盘能不能完成提问
TASKS.T5 = {
  name: 'T5 键盘可达性与无障碍',
  persona: 'P5 键盘/无障碍用户',
  async run(page, errors) {
    const T = 'T5'
    await goto(page, '/ask', T)
    const seq = []
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press('Tab')
      const cur = await page.evaluate(() => {
        const el = document.activeElement
        if (!el) return null
        const s = getComputedStyle(el)
        return {
          tag: el.tagName.toLowerCase(),
          label: (el.innerText || el.getAttribute('aria-label') || el.placeholder || el.id || '').trim().slice(0, 30),
          outline: s.outlineStyle + ' ' + s.outlineWidth + ' ' + s.outlineColor,
          boxShadow: s.boxShadow.slice(0, 60),
        }
      })
      if (cur) seq.push(cur)
    }
    const invisible = seq.filter((s) => /none/.test(s.outline) && /none/.test(s.boxShadow))
    note(seq.length >= 8 ? 'pass' : 'minor', T, `Tab 序列前 ${seq.length} 步：${seq.map((s) => s.tag + ':' + s.label).slice(0, 10).join(' → ')}`)
    note(invisible.length === 0 ? 'pass' : 'major', T,
      invisible.length === 0 ? '所有焦点元素都有可见焦点样式' : `${invisible.length} 个焦点元素无可见焦点样式：${invisible.map((s) => s.tag + ':' + s.label).join('、')}`)
    // ARIA 断裂引用
    const broken = await page.evaluate(() => {
      const ids = new Set([...document.querySelectorAll('[id]')].map((e) => e.id))
      return [...document.querySelectorAll('[aria-labelledby],[aria-describedby]')]
        .flatMap((el) => (el.getAttribute('aria-labelledby') || el.getAttribute('aria-describedby') || '').split(/\s+/))
        .filter((x) => x && !ids.has(x))
    })
    note(broken.length === 0 ? 'pass' : 'minor', T, broken.length === 0 ? '无 ARIA 断裂引用' : `ARIA 断裂引用：${[...new Set(broken)].join('、')}`)
    // 语言与标题
    const meta = await page.evaluate(() => ({ lang: document.documentElement.lang, title: document.title, h1: [...document.querySelectorAll('h1')].map((e) => e.innerText.trim()) }))
    note(meta.lang ? 'pass' : 'minor', T, `lang=${meta.lang || '（缺失）'}，title=${meta.title || '（缺失）'}，h1=${meta.h1.join(' / ') || '（无）'}`)
    ctx.T5 = { seq, broken, meta }
  },
}

// T6 小屏适配（手机宽度）与缩放
TASKS.T6 = {
  name: 'T6 小屏与窄窗适配',
  persona: 'P4 手机端访客',
  async run(page, errors) {
    const T = 'T6'
    await page.setViewportSize({ width: 390, height: 844 })
    for (const [path, name] of [['/ask', 'T6-390提问'], ['/graph', 'T6-390图谱'], ['/history', 'T6-390历史']]) {
      await goto(page, path, T)
      await page.waitForTimeout(1200)
      const p = await probe(page, T, name)
      const over = p.overflowX
      note(over <= 2 ? 'pass' : (over <= 16 ? 'minor' : 'major'), T, `${path} @390px：横向溢出 ${over}px`)
      // 触控目标尺寸
      const small = await page.evaluate(() => {
        const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.display !== 'none' }
        return [...document.querySelectorAll('a,button')].filter(vis)
          .map((el) => { const r = el.getBoundingClientRect(); return { label: (el.innerText || '').trim().slice(0, 20), w: Math.round(r.width), h: Math.round(r.height) } })
          .filter((x) => x.h < 32 && x.label)
      })
      note(small.length <= 3 ? 'pass' : 'minor', T, `${path} @390px：高<32px 的触控目标 ${small.length} 个${small.length ? '（如 ' + small.slice(0, 4).map((s) => s.label + '(' + s.w + '×' + s.h + ')').join('、') + '）' : ''}`)
    }
    await page.setViewportSize({ width: 1440, height: 900 })
    ctx.T6 = true
  },
}

// T7 长答案可读性 / 信息密度（依赖 T2 刚生成的答案，直接访问最新答案）
TASKS.T7 = {
  name: 'T7 答案页信息密度与阅读体验',
  persona: 'P1 投研分析师（速读）',
  async run(page, errors) {
    const T = 'T7'
    const direct = ctx.T2 && ctx.T2.answerId
    if (direct) {
      await goto(page, `/answer/${direct}`, T)
    } else {
      await goto(page, '/history', T)
      const link = page.locator('a[href*="/answer/"]').first()
      if (!(await link.count())) { note('major', T, '无可回看答案，跳过'); return }
      await link.click()
    }
    await page.waitForTimeout(2500)
    const p = await probe(page, T, 'T7-长答案')
    const lines = p.bodyText.split('\n').filter(Boolean)
    const longest = lines.reduce((a, b) => (b.length > a.length ? b : a), '')
    note(longest.length < 220 ? 'pass' : 'minor', T, `最长单行 ${longest.length} 字${longest.length >= 220 ? '（无换行的长段落，速读困难）' : ''}`)
    note(p.smallText / Math.max(1, p.totalText) < 0.25 ? 'pass' : 'minor', T, `小字号文本块占比 ${(100 * p.smallText / p.totalText).toFixed(0)}%`)
    if (p.overflowX > 2) note('major', T, `答案页横向溢出 ${p.overflowX}px`)
    // 是否提供了「复制/导出」这类二次使用入口
    const util = await page.evaluate(() => [...document.querySelectorAll('button,a')].map((e) => (e.innerText || '').trim()).filter((t) => /复制|导出|下载|分享|打印|引用/.test(t)))
    note(util.length ? 'pass' : 'minor', T, util.length ? `提供二次使用入口：${util.join('、')}` : '答案页没有「复制/导出/引用」入口（研究生要手抄到论文里）')
    ctx.T7 = { p, util }
  },
}

// ================================================================ 执行
const browser = await chromium.launch({ headless: true })
const allErrors = []

const order = ['T1', 'T4', 'T5', 'T6', 'T2', 'T3', 'T7']
const toRun = (ONLY.length ? order.filter((k) => ONLY.includes(k)) : order).filter((k) => TASKS[k])

console.log(`\n=== UAT 开始 ===  证据目录：${EVID}`)
console.log(`目标：${BASE}    任务：${toRun.join('、')}\n`)

// T2／T3／T7 共用同一个浏览器上下文：会话标识（localStorage 的 UUID）决定历史记录归属，
// 三条任务分别在独立上下文里跑会互相看不见对方产生的记录 —— 首版 T3／T7 就因此拿到空历史而空转。
const SHARED = new Set(['T2', 'T3', 'T7'])

let sharedCtx = null
let sharedPage = null

// 2026-10-17 新增：任务间隔（默认 18 秒，可用 --pace=<ms> 覆盖，0 表示不等待）。
// 为什么要有：验收标准《01》把「请求预算」定义在**一次完整走查**（60 次／60 秒）上；
// 而本装置会把 7 个任务压进同一个窗口里连跑，实测约 100 次请求／78 秒，**必然**撞上限流，
// 于是答案页自身也会被 429 拒绝，后续断言随之变成「段落缺失」——那测的是装置的爆发速度，
// 不是页面是否正确。加间隔后，每个任务各自落在预算内，装置测的才是「页面能不能用」。
// 若确实想看「密集爆发下会怎样」，用 `--pace=0` 原样复现；产品在该场景下的表现是
// 「读取失败［code=1004］请求频率超出限制，请约 N 秒后重试 ＋ 重试入口」，不是空态（已实测）。
const PACE_MS = Number(argOf('pace', '18000'))
let firstTask = true

for (const key of toRun) {
  if (!firstTask && PACE_MS > 0) {
    note('info', key, `任务间隔 ${(PACE_MS / 1000).toFixed(0)} 秒（对齐《01》的「一次走查 60 次／60 秒」预算）`)
    await new Promise((r) => setTimeout(r, PACE_MS))
  }
  firstTask = false
  const task = TASKS[key]
  console.log(`\n--- ${task.name}（${task.persona}）---`)
  let context
  let page
  const useShared = SHARED.has(key) && toRun.some((k) => SHARED.has(k))
  if (useShared) {
    if (!sharedCtx) {
      const made = await mkPage(browser, allErrors)
      sharedCtx = made.context
      sharedPage = made.page
      note('info', key, '本节任务共用同一个浏览器会话（localStorage 会话标识一致，历史记录可互见）')
    }
    context = sharedCtx
    page = sharedPage
    console.log('    （复用共享会话上下文）')
  } else {
    const made = await mkPage(browser, allErrors)
    context = made.context
    page = made.page
  }
  const errBefore = allErrors.length
  try {
    await task.run(page, allErrors)
    note('info', key, `任务完成（耗时 ${((Date.now() - t0) / 1000).toFixed(0)}s 累计）`)
  } catch (e) {
    note('blocker', key, `任务执行抛错：${String(e).split('\n')[0]}`)
    await shot(page, `${key}-异常`).catch(() => {})
  }
  const newErrs = allErrors.slice(errBefore)
  // 2026-10-17 口径修正（与 `跨浏览器走查.mjs` 统一）：
  //   429 = **环境限流**（后端 60 次／60 秒／来源 IP，第 9 阶段门禁锁定的登记参数），不是产品缺陷。
  //   产品在这条路径上的承诺是「被限流时不得显示为空态／不得卡死，要有横幅与一次退避重试」，
  //   那条由 T2 主链路与本文件外的《04 复测对照与验收》单独断言。
  //   此前本装置把 429 计入「严重」，而同一事实在跨浏览器装置里是「记录」——两套装置判定不一致；
  //   现统一：429 单列 `throttle`（仍然计数、仍然写 JSON、仍然打印端点），`major` 只留给真错误。
  const isThrottle = (e) => /429|Too Many Requests/i.test(String(e.text) + ' ' + String(e.url || ''))
  const throttleErrs = newErrs.filter(isThrottle)
  const realErrs = newErrs.filter((e) => !isThrottle(e))
  if (newErrs.length) {
    writeFileSync(join(EVID, `${key}-浏览器错误.json`), JSON.stringify(newErrs, null, 2), 'utf8')
  }
  if (realErrs.length) {
    note('major', key, `浏览器侧错误 ${realErrs.length} 条（另 ${throttleErrs.length} 条为环境限流，详见 ${key}-浏览器错误.json）：` + realErrs.slice(0, 3).map((e) => e.kind + ' ' + e.text.slice(0, 90)).join(' ｜ '))
  } else if (throttleErrs.length) {
    const eps = [...new Set(throttleErrs.map((e) => String(e.url || e.text).replace(/^http 429 GET /, '').split('?')[0]))]
    note('throttle', key, `环境限流 429 共 ${throttleErrs.length} 条（后端 60 次／60 秒／来源 IP，非缺陷；端点：${eps.slice(0, 4).join('、')}）`)
  } else {
    note('pass', key, '浏览器控制台/网络无错误')
  }
  if (!useShared) await context.close()
}

if (sharedCtx) await sharedCtx.close()

await browser.close()

// ---------------------------------------------------------------- 汇总
const report = {
  meta: {
    tag: TAG,
    base: BASE,
    startedAt: new Date(t0).toISOString(),
    durationS: ((Date.now() - t0) / 1000).toFixed(1),
    tasks: toRun,
    shots: shots.length,
  },
  counts: findings.reduce((a, f) => (a[f.level] = (a[f.level] || 0) + 1, a), {}),
  findings,
  browserErrors: allErrors,
  shots,
}
writeFileSync(join(EVID, 'UAT-结果.json'), JSON.stringify(report, null, 2), 'utf8')

const sum = Object.entries(report.counts).map(([k, v]) => `${k}=${v}`).join('  ')
console.log(`\n=== UAT 结束 ===  ${sum}`)
console.log(`证据：${EVID}`)
console.log(`汇总：${join(EVID, 'UAT-结果.json')}`)

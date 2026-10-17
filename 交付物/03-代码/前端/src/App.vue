<script setup>
// 交付物/03-代码\前端\src\App.vue —— 应用外壳（逐字对齐 阶段09 前端设计原型的「吸顶 + header + 页脚」）
//
// 结构：吸顶（数据新鲜度两口径 ＋ header）→ <RouterView/> → 页脚；另加背景股票曲线画布、
// 点击热区遮罩与自定义光标（全部与原型同一套设计语言）。
//
// 顶栏固定渲染「数据截至：YYYY-MM-DD」（日期取自 GET /api/config/meta 的 data_cutoff_time，
// 《24》硬约束 12／F3）。模型名 / Prompt 版本 / 向量条数一律**从接口动态取**，
// 不在源码里写死任何模型名或库名（硬约束 2：源码／产物零敏感字面量）。
//
// 两会话级共享状态（provide 下发给四个页面）：
//   · appMeta —— 语料口径：数据集版本、数据截止时间、模型名、Prompt 版本、向量条数、后端健康
//   · market  —— 实时口径：三块数据源（行情 / 新闻 / 语料内近一周），display_only、不进证据链

import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getConfigMeta, getHealth,
  getMarketQuote, getMarketNews, getMarketReports,
  onThrottleChange, throttleState,
} from './api.js'
import { mountField } from './lib/field.js'
import { initReveal, kickReveal } from './lib/reveal.js'

const route = useRoute()
const router = useRouter()

// --------------------------------------------------------------------------
// 共享状态
// --------------------------------------------------------------------------
const appMeta = reactive({
  datasetVersion: '',
  dataCutoffTime: '',   // 原始 ISO 字符串（带 +08:00 偏移）
  modelName: '',        // 从接口动态取，源码不写死
  promptVersion: '',
  vectorCount: null,
  vectorDim: null,
  backendOk: null,      // true／false／null（未知）
  health: null,
  error: '',
})
provide('appMeta', appMeta)

const market = reactive({
  on: false,            // 两态总开关：未接入（默认）／接入中
  quote: null,          // { connected, items[], reason, updated_at, ... }
  news: null,
  reports: null,
  loading: false,
  error: '',
})
provide('market', market)
provide('reloadMarket', () => loadMarket())

// --------------------------------------------------------------------------
// 限流横幅（2026-10-17 新增）
// --------------------------------------------------------------------------
// 为什么必须把「限流」显式讲出来：本次实测一次真实浏览器走查共发出 84 次 `/api/*` 请求
// （其中图谱页单独约占 38 次），而后端 `RateLimitMiddleware` 是「窗口 60 秒／上限 60 次」的
// **按来源 IP 全局滑动窗口**，于是正常使用约 40 秒后整站开始 429。此时搜索结果会被调用点吞成
// 「（无结果）」、历史页图谱写「未检索到」、实时区显示「未接入」——用户读到的是
// 「没有这家公司／没有这段数据」，属于方向性误读。横幅只补一件事：把「这是后端限流，
// 不是数据缺失」讲清楚，并给出一个可点的重试入口；既有渲染逻辑与文案一律不动。
const throttle = reactive({ active: false, retryAfterSeconds: 0, message: '' })
let offThrottle = null

/** 把 api.js 的受限态只读快照落到本地响应式对象（字段名与快照一一对应，无派生、无推测）。 */
function syncThrottle(s) {
  throttle.active = !!s.active
  throttle.retryAfterSeconds = s.retryAfterSeconds || 0
  throttle.message = s.message || ''
}

/**
 * 横幅「立即重试」：复用既有的两个刷新入口（元信息 + 实时区三块），不新造加载路径。
 * `loadMarket()` 不触碰 `market.on`，所以 `data-market` 属性与「未接入」两态文案都不受影响。
 */
function retryThrottled() {
  loadMeta()
  loadMarket()
  syncThrottle(throttleState())   // 顺手把读数刷到最新，点击后界面立刻有反馈
}

/** 取 ISO 时间的日期部分（`2026-09-25T23:59:59+08:00` → `2026-09-25`）。 */
function datePart(iso) {
  return typeof iso === 'string' && iso.length >= 10 ? iso.slice(0, 10) : '—'
}

const nav = [
  { key: 'ask', label: '提问台', to: '/ask' },
  { key: 'answer', label: '答案与证据', to: '/answer' },
  { key: 'graph', label: '知识图谱', to: '/graph' },
  { key: 'history', label: '历史记录', to: '/history' },
]
const cur = computed(() => {
  const n = route.name
  return (n === 'ask' || n === 'answer' || n === 'graph' || n === 'history') ? n : 'ask'
})

function go(key) {
  const item = nav.find((n) => n.key === key)
  if (key === 'answer') { router.push('/history'); return }   // 无具体 answer_id 时答案页落到历史
  if (item) router.push(item.to)
}

// --------------------------------------------------------------------------
// 模型 / 健康 / 实时区
// --------------------------------------------------------------------------
async function loadMeta() {
  try {
    const { data } = await getConfigMeta()
    appMeta.datasetVersion = (data && data.dataset_version) || ''
    appMeta.dataCutoffTime = (data && data.data_cutoff_time) || ''
    appMeta.modelName = (data && data.model_name) || ''
    appMeta.promptVersion = (data && data.prompt_version) || ''
  } catch (e) {
    appMeta.error = `读取配置元信息失败：${e.message}`
  }
  try {
    const health = await getHealth()
    appMeta.health = health
    appMeta.backendOk = !!(health && health.status === 'ok')
    const mc = (health && health.model_config) || {}
    if (mc.model_name) appMeta.modelName = mc.model_name
    if (mc.prompt_version) appMeta.promptVersion = mc.prompt_version
    // 向量条数 / 维度：只从 interface 的 info 里**提取数字**，不原样渲染 info 文本
    const vi = (health && health.vector_index) || {}
    const info = String(vi.info || '')
    const mN = info.match(/([\d,]+)\s*条/)
    const mD = info.match(/维度\s*(\d+)/)
    if (mN) appMeta.vectorCount = Number(mN[1].replace(/,/g, ''))
    if (mD) appMeta.vectorDim = Number(mD[1])
  } catch (e) {
    appMeta.backendOk = false
  }
}

// 实时区三块：行情（外部源）／新闻（外部源）／语料内近一周（同源语料，降级常驻）
async function loadMarket() {
  market.loading = true
  market.error = ''
  const [q, n, r] = await Promise.allSettled([
    getMarketQuote(),
    getMarketNews('平安银行'),
    getMarketReports(),
  ])
  market.quote = q.status === 'fulfilled' ? q.value : null
  market.news = n.status === 'fulfilled' ? n.value : null
  market.reports = r.status === 'fulfilled' ? r.value : null
  const errs = [q, n, r].filter((x) => x.status === 'rejected')
  if (errs.length === 3) market.error = '实时接口全部请求失败（后端或代理不可达）'
  market.loading = false
}

// 跑马灯（与原型同一组词，纯展示装饰）
const MQ = ['事件知识图谱', '证据可追溯', '路径可视化', '判定区间可回查', '多源数据治理', 'A 股财经问答']

// 行情跳带：只显示接口**实际返回**的报价；未接入/空则不显示任何价格
const tickerQuotes = computed(() => {
  const q = market.quote
  if (!q || !q.connected) return null
  return (q.items || []).map((it) => ({
    code: it.code || '',
    name: it.name || '',
    price: it.price != null ? String(it.price) : '—',
    chg: it.change_pct != null ? Number(it.change_pct) : null,
  }))
})
const quoteReason = computed(() => (market.quote && market.quote.reason) || '外部行情接口当前未接入')

const clock = ref('')
let clockT = null
function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  clock.value = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// --------------------------------------------------------------------------
// 反馈与建议（2026-10-17 新增）：把页脚「关于」列表里那条占位死链
// `<a href="#" @click.prevent>反馈与建议</a>` 换成**真正可用**的本地入口。
// 三条纪律：① 纯本地离线表单，提交内容只写 window.localStorage，不发任何网络请求；
// ② 只改这一条链接的行为，页脚其余文案与结构一概不动；
// ③ 无障碍做法与站内既有抽屉一致：打开时焦点移入弹层、Esc 可关、关闭后焦点还原到触发元素。
// --------------------------------------------------------------------------
const FEEDBACK_KEY = 'od.ashare.feedback'
const fbOpen = ref(false)
const fbText = ref('')
const fbMsg = ref('')
const fbDialog = ref(null)
const fbTextarea = ref(null)
let fbReturnFocus = null

/** 读取已保存在本机的反馈条数；localStorage 不可用（隐私模式等）按 0 条如实计。 */
function readLocalFeedback() {
  try {
    const arr = JSON.parse(window.localStorage.getItem(FEEDBACK_KEY) || '[]')
    return Array.isArray(arr) ? arr : []
  } catch (e) {
    return []
  }
}

/** 打开弹层：先按本机已存档的条数给出状态，再把焦点移入文本域（与抽屉的焦点做法一致）。 */
async function openFeedback() {
  fbReturnFocus = document.activeElement
  const n = readLocalFeedback().length
  fbMsg.value = n ? `已保存到本机（共 ${n} 条）` : '本机还没有保存过反馈（共 0 条）'
  fbOpen.value = true
  await nextTick()
  if (fbDialog.value && typeof fbDialog.value.showModal === 'function') fbDialog.value.showModal()
  else if (fbDialog.value) fbDialog.value.setAttribute('open', '')   // 旧内核兜底：仍可看见弹层
  if (fbTextarea.value) fbTextarea.value.focus()
}

/**
 * 关闭弹层：真正把 <dialog> 也关掉（Esc／点「关闭」／点遮罩三条路都走这里），
 * 再把焦点还原到页脚那条「反馈与建议」。注意必须调原生 close()：只把 v-if／open 翻掉
 * 并不会退出 top-layer，弹层会留在屏幕上。
 */
function closeFeedback() {
  fbOpen.value = false
  const d = fbDialog.value
  if (d && d.open && typeof d.close === 'function') d.close()
  if (fbReturnFocus && typeof fbReturnFocus.focus === 'function') fbReturnFocus.focus()
}

/**
 * 保存到本地：只写 window.localStorage（键 `od.ashare.feedback`），不调用 api.js、
 * 不发起任何请求。成功／失败都给出可见反馈；成功时汇报**本机累计条数 N**。
 */
function saveFeedback() {
  const text = (fbText.value || '').trim()
  if (!text) {
    fbMsg.value = '内容为空，未保存（本表单只把文字写入本机，不写空条目）'
    return
  }
  const list = readLocalFeedback()
  list.push({ text, saved_at: new Date().toISOString() })
  try {
    window.localStorage.setItem(FEEDBACK_KEY, JSON.stringify(list))
    fbText.value = ''
    fbMsg.value = `已保存到本机（共 ${list.length} 条）`
  } catch (e) {
    // 存不进去（配额／隐私模式）也如实说，不假装保存成功
    fbMsg.value = `保存失败（本机 localStorage 不可用）：${(e && e.message) || e}`
  }
}

function toggleMarket() {
  market.on = !market.on
}
watch(() => market.on, (on) => {
  document.body.setAttribute('data-market', on ? 'on' : 'off')
  try { window.localStorage.setItem('od.ashare.market', on ? 'on' : 'off') } catch (e) { /* noop */ }
  if (on) { loadMarket(); stamp(); if (!clockT) clockT = window.setInterval(stamp, 1000) }
  else if (clockT) { window.clearInterval(clockT); clockT = null }
})

// --------------------------------------------------------------------------
// 背景画布 / 光标 / 入场 / 视图属性
// --------------------------------------------------------------------------
let field = null
let cursorCleanup = null

function initCursor() {
  const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)')
  const fineMQ = matchMedia('(hover:hover) and (pointer:fine)')
  if (!fineMQ.matches || reduceMQ.matches) return null
  const c = document.getElementById('cursor')
  if (!c) return null
  const lab = c.querySelector('.cursor__label')
  let x = innerWidth / 2, y = innerHeight / 2, tx = x, ty = y, sc = 1, tsc = 1, on = false, raf = 0
  document.documentElement.classList.add('cursor-custom')
  function loop() {
    x += (tx - x) * 0.22; y += (ty - y) * 0.22; sc += (tsc - sc) * 0.2
    c.style.setProperty('--x', x.toFixed(1) + 'px')
    c.style.setProperty('--y', y.toFixed(1) + 'px')
    c.style.setProperty('--s', sc.toFixed(3))
    if (Math.abs(tx - x) > 0.4 || Math.abs(ty - y) > 0.4 || Math.abs(tsc - sc) > 0.01) raf = requestAnimationFrame(loop)
    else raf = 0
  }
  function kick() { if (!raf) raf = requestAnimationFrame(loop) }
  const onMove = (e) => {
    if (e.pointerType === 'touch') return
    tx = e.clientX; ty = e.clientY
    if (!on) { on = true; c.classList.add('on'); x = tx; y = ty }
    const t = e.target.closest ? e.target.closest('a,button,[data-cursor-label],.hrow,.gnode,textarea') : null
    const lbl = t ? (t.getAttribute('data-cursor-label') || (t.classList.contains('gnode') ? '节点'
      : (t.classList.contains('hrow') ? '回看'
      : (t.tagName === 'TEXTAREA' ? '输入' : (t.classList.contains('btn--primary') ? '开始' : '点开'))))) : ''
    const hot = !!t
    if (hot !== c.classList.contains('hot')) { c.classList.toggle('hot', hot); tsc = hot ? 1.9 : 1 }
    if (hot) lab.textContent = lbl
    kick()
  }
  const onDown = () => { tsc = 1; c.classList.add('hot'); kick() }
  const onUp = () => { tsc = 1; c.classList.remove('hot'); kick() }
  const onLeave = () => c.classList.remove('on')
  const onBlur = () => c.classList.remove('on')
  document.addEventListener('pointermove', onMove, { passive: true })
  document.addEventListener('pointerdown', onDown, { passive: true })
  document.addEventListener('pointerup', onUp, { passive: true })
  document.addEventListener('pointerleave', onLeave)
  window.addEventListener('blur', onBlur)
  return () => {
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerdown', onDown)
    document.removeEventListener('pointerup', onUp)
    document.removeEventListener('pointerleave', onLeave)
    window.removeEventListener('blur', onBlur)
    document.documentElement.classList.remove('cursor-custom')
  }
}

// 视图属性：body[data-view] 驱动屏③/抽屉把背景曲线降到 .14（theme.css 已定义）
watch(cur, (v) => {
  document.body.setAttribute('data-view', v)
  nextTick(() => kickReveal())
}, { immediate: true })

onMounted(async () => {
  // 先订阅再发请求：否则首屏那批请求若立刻被限流，横幅会错过第一个受限态
  offThrottle = onThrottleChange(syncThrottle)
  document.body.setAttribute('data-market', market.on ? 'on' : 'off')
  field = mountField()
  initReveal()
  cursorCleanup = initCursor()
  try { market.on = (window.localStorage.getItem('od.ashare.market') === 'on') } catch (e) { /* noop */ }
  await loadMeta()
  loadMarket()          // 语料内近一周常驻；行情/新闻按 connected 如实显示
  nextTick(() => kickReveal())
})

onBeforeUnmount(() => {
  if (field) field.destroy && field.destroy()
  if (cursorCleanup) cursorCleanup()
  if (offThrottle) { offThrottle(); offThrottle = null }
  if (clockT) { window.clearInterval(clockT); clockT = null }
})
</script>

<template>
  <!-- 牛头 / 告警 / 搜索：徽标、空状态、加载态共用一份 symbol 定义 -->
  <svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
    <symbol id="bull" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.6"
            stroke-linecap="round" stroke-linejoin="round">
      <path d="M18.6 20.6C12.4 18.5 8.1 13.2 7.6 5.3c6.1 1.3 10.3 4.9 12.7 10.2"/>
      <path d="M45.4 20.6c6.2-2.1 10.5-7.4 11-15.3-6.1 1.3-10.3 4.9-12.7 10.2"/>
      <path d="M21 24.2c-2.7-.9-4.8-3-5.8-5.8M43 24.2c2.7-.9 4.8-3 5.8-5.8"/>
      <path d="M20 17.9h24c1.2 8.8.3 16.8-3.6 22.6-3 4.5-6 6.8-8.4 6.8s-5.4-2.3-8.4-6.8c-3.9-5.8-4.8-13.8-3.6-22.6Z"/>
      <circle cx="25.6" cy="28.6" r="2.1" fill="currentColor" stroke="none"/>
      <circle cx="38.4" cy="28.6" r="2.1" fill="currentColor" stroke="none"/>
      <path d="M27.4 38.7h9.2v3.6a4.6 4.6 0 0 1-9.2 0v-3.6Z"/>
      <path d="M30.3 41.8h.02M33.7 41.8h.02" stroke-width="3.2"/>
    </symbol>
    <symbol id="i-alert" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round">
      <path d="M8 2.6 14.4 13.4H1.6L8 2.6Z"/><path d="M8 6.8v2.9M8 11.9h.02"/>
    </symbol>
    <symbol id="i-search" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round">
      <circle cx="7" cy="7" r="4.6"/><path d="M10.6 10.6 14 14"/>
    </symbol>
  </defs></svg>

  <canvas id="field" aria-hidden="true"></canvas>
  <div id="veil" aria-hidden="true"></div>
  <div class="cursor" id="cursor" aria-hidden="true"><span class="cursor__label"></span></div>

  <div class="topstack">
    <div class="fresh" aria-label="数据新鲜度：语料口径与行情口径">
      <div class="fresh__inner wrap">
        <span class="fresh__corpus" :title="`语料截止 ${datePart(appMeta.dataCutoffTime)} · 数据集 ${appMeta.datasetVersion || '—'}`">
          <i class="fresh__dot" aria-hidden="true"></i>
          <span class="fresh__k">语料截止</span>
          <b>{{ datePart(appMeta.dataCutoffTime) }}</b>
          <span aria-hidden="true">·</span>
          <span class="fresh__k">数据集</span>
          <b>{{ appMeta.datasetVersion || '—' }}</b>
          <span class="fresh__note">重跑采集与向量化前不变</span>
        </span>

        <i class="fresh__bar" aria-hidden="true"></i>

        <span class="fresh__mk">
          <span class="mk-off">
            <span class="tag tag--muted">实时区未接入</span>
            <span class="fresh__note">外部行情与新闻接口未接入；语料内近一周文档块始终可用</span>
          </span>
          <span class="mk-on">
            <span class="tag tag--red">已接入 · 按接口实返</span>
            <span class="mkt">
              <span class="mkt__track">
                <template v-if="tickerQuotes">
                  <template v-for="(it, i) in tickerQuotes" :key="i">
                    <span class="mkt__item"><span class="idx">{{ it.code }}</span><b>{{ it.name }}</b>
                      <span>{{ it.price }}</span>
                      <span :class="it.chg >= 0 ? 'up' : 'down'">{{ it.chg >= 0 ? '+' : '−' }}{{ it.chg != null ? Math.abs(it.chg).toFixed(2) : '—' }}%</span>
                    </span><i class="mkt__sep"></i>
                  </template>
                </template>
                <span v-else class="mkt__item"><b>行情数据源未接入</b></span>
              </span>
            </span>
            <span class="mkt__time">更新于 <i>{{ clock || '—' }}</i></span>
          </span>
        </span>

        <button class="switch fresh__switch" type="button" role="switch" :aria-checked="market.on ? 'true' : 'false'"
                aria-labelledby="mkSwitchLab" :title="market.on ? '切回未接入态' : '尝试接入实时区（按接口实返，行情源不可达时如实显示未接入）'"
                @click="toggleMarket">
          <span class="switch__track" aria-hidden="true"><i class="switch__knob"></i></span>
          <span class="switch__lab" id="mkSwitchLab">实时接入</span>
        </button>
      </div>
    </div>

    <header class="topbar wrap">
      <a class="brand" href="#" data-cursor-label="提问台" @click.prevent="go('ask')">
        <span class="brand__mark"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg></span>
        <span>
          <span class="brand__name">牛势问答</span>
          <span class="brand__sub">A 股事件知识图谱 · RAG</span>
        </span>
      </a>

      <nav class="nav" role="tablist" aria-label="主导航">
        <!-- 2026-10-11（M13）：补 :id="nav-&lt;key&gt;" —— 四个视图 tabpanel 的
             aria-labelledby="nav-ask／nav-answer／nav-graph／nav-history" 此前引用了
             不存在的 id（ARIA 断裂引用），本 id 与之一一对应。 -->
        <button v-for="n in nav" :key="n.key" :id="'nav-' + n.key" class="nav__btn" role="tab"
                :aria-selected="cur === n.key ? 'true' : 'false'" @click="go(n.key)">{{ n.label }}</button>
      </nav>

      <div class="topbar__right">
        <span class="topbar__cut">数据截至：{{ datePart(appMeta.dataCutoffTime) }}</span>
        <!-- 2026-10-17 用户测试后改（产品口径决定 D：让文案追上实现）。
             原来写「新建会话」，但它的实现自始至终只是 `go('ask')` —— 跳到提问页，
             localStorage 里的 session_id（qa-console-session-id）**一个字都没变**。
             本系统是单轮问答、没有多会话侧边栏，「新建会话」那套语义在这里并不存在；
             如果一个按钮点了和「去提问」没有任何区别，就不该这样叫它。
             故改名为「去提问」并加 title 说明它到底做什么（没有隐藏功能，只是把承诺说准）。 -->
        <button class="btn btn--primary btn--sm" @click="go('ask')"
                title="回到提问页；本系统是单轮问答，不维护多会话列表，历史记录按浏览器会话隔离（FR-06）">去提问</button>
      </div>
    </header>

    <!-- 2026-10-17 新增：限流横幅。仅当受限态为真时渲染，且只补「正在等待的秒数 +
         「是后端限流，不是数据缺失」 + 立即重试」这三件事；上方「数据新鲜度条 + 顶栏」与
         下方各页的渲染逻辑、文案、data-market 属性一概不动。 -->
    <div v-if="throttle.active" class="throttle wrap" role="status" aria-live="polite">
      <span class="tag tag--red">后端限流</span>
      <span class="throttle__text">
        预计还需 <b class="mono">{{ throttle.retryAfterSeconds }}</b> 秒：{{ throttle.message }}
      </span>
      <button class="btn btn--quiet btn--sm throttle__btn" type="button" @click="retryThrottled">立即重试</button>
    </div>
  </div>

  <main>
    <RouterView />
  </main>

  <footer class="footer">
    <div class="wrap">
      <div class="footer__top">
        <div class="footer__col">
          <div class="brand">
            <span class="brand__mark"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg></span>
            <span><span class="brand__name">牛势问答</span><span class="brand__sub">A 股事件知识图谱 · RAG</span></span>
          </div>
          <p class="small" style="margin-top:16px;max-width:36ch">面向 A 股财经信息的事件知识图谱与检索增强问答系统，回答可溯源、路径可回查。</p>
          <span class="seal" style="margin-top:20px" aria-hidden="true">牛</span>
        </div>
        <div class="footer__col">
          <h4 class="label">产品</h4>
          <ul>
            <li><a href="#" @click.prevent="go('ask')">提问台</a></li>
            <li><a href="#" @click.prevent="router.push('/history')">答案与证据</a></li>
            <li><a href="#" @click.prevent="go('graph')">事件知识图谱</a></li>
            <li><a href="#" @click.prevent="go('history')">历史记录</a></li>
          </ul>
        </div>
        <div class="footer__col">
          <h4 class="label">数据源</h4>
          <ul>
            <li><a href="#" @click.prevent>上海证券交易所</a></li>
            <li><a href="#" @click.prevent>深圳证券交易所</a></li>
            <li><a href="#" @click.prevent>巨潮资讯网</a></li>
            <li><a href="#" @click.prevent>部委与行业协会政策库</a></li>
          </ul>
        </div>
        <div class="footer__col">
          <h4 class="label">关于</h4>
          <ul>
            <li><a href="#" @click.prevent>技术白皮书</a></li>
            <li><a href="#" @click.prevent>事件抽取口径</a></li>
            <li><a href="#" @click.prevent>更新日志</a></li>
            <!-- 2026-10-17：原先这里是占位死链（href="#" + @click.prevent，点了没反应）；
                 现在只改这一条链接的行为，打开本地离线反馈弹层；页脚其余项与结构不动。 -->
            <li><a href="#" @click.prevent="openFeedback">反馈与建议</a></li>
          </ul>
        </div>
      </div>
      <div class="footer__bottom">
        <p class="footer__legal">本页的证据条目、图谱路径、事件三元组、数据版本与截止时间，取自一次真实问答输出，原样呈现，未做改写。行情数据源当前未接入：默认显示「行情数据源未接入」，其间不含任何报价；外部源可达时按接口实返显示，并就地标注。语料口径与行情口径分属两套时间基准，不可混用。不构成任何投资建议。</p>
        <span class="label">© 2026 牛势问答 · A 股事件知识图谱与检索增强问答</span>
      </div>
    </div>
  </footer>

  <!-- 2026-10-17 新增：页脚「反馈与建议」的本地离线弹层。
       <dialog> ＋ showModal()：原生把焦点困在弹层内、原生挡住背景交互，并**原生支持 Esc 关闭**
       （@cancel.prevent 复用同一套关闭逻辑，@close 负责把焦点还原到页脚那条链接）。
       本弹层不向任何服务器发请求：内容只写 window.localStorage，键 `od.ashare.feedback`。 -->
  <dialog ref="fbDialog" class="fb" aria-labelledby="fbTitle" @cancel.prevent="closeFeedback" @close="closeFeedback">
    <div class="fb__head">
      <h2 class="h2" id="fbTitle">反馈与建议</h2>
      <button class="btn btn--ghost btn--sm" type="button" @click="closeFeedback">关闭</button>
    </div>
    <p class="small" style="margin-top:12px">
      本表单为本地离线表单，提交内容只写入浏览器本地存储，不会上传到任何服务器。
    </p>
    <label class="label" for="fbText">反馈内容</label>
    <textarea id="fbText" ref="fbTextarea" v-model="fbText" class="fb__text" rows="5"
              placeholder="例如：某条证据的标题看不全、某个数字不好核对……（内容只留在本机）"></textarea>
    <div class="fb__acts">
      <button class="btn btn--primary btn--sm" type="button" @click="saveFeedback">保存到本地</button>
      <span class="small"><span class="mono">od.ashare.feedback</span> · {{ fbMsg }}</span>
    </div>
    <p class="small" style="margin-top:10px">按 Esc 或点「关闭」退出；再次打开时，本机已存的反馈条数照实显示，内容不做改写、不合并。</p>
  </dialog>
</template>

<style scoped>
/* 2026-10-17 新增：限流横幅的窄带样式。配色一律取 theme.css 已有的令牌，
   按钮／标签直接复用已有类名风格（.tag--red／.btn--quiet／.mono），
   不在 App.vue 里另造一套设计语言，也不写大段新 CSS。 */
.throttle{
  display:flex;align-items:center;gap:12px;
  /* 只加垂直内边距：水平内边距继续由 .wrap 提供，横幅与顶栏左右对齐 */
  padding-top:7px;padding-bottom:7px;
  border-top:1px solid var(--border-soft);
  background:var(--accent-soft);
  font-size:12px;line-height:1.5;color:var(--muted);
}
.throttle__text{flex:1;min-width:0}
.throttle__text b{color:var(--accent-ink);font-weight:600}
.throttle__btn{flex:none}

/* 2026-10-17 新增：反馈弹层的样式。配色／圆角一律取 theme.css 已有的令牌，
   标题与按钮直接复用已有类名（.h2／.btn--primary／.btn--ghost／.small／.label／.mono），
   这里只补弹层自身的定位、遮罩与新引入的 textarea 两个必需样式。 */
.fb{
  position:fixed;inset:0;margin:auto;width:min(620px,92vw);height:max-content;max-height:88vh;
  overflow:auto;padding:24px 26px 22px;background:var(--bg-deep);color:var(--fg);
  border:1px solid var(--border);border-radius:var(--r-lg);
  box-shadow:0 40px 80px -40px rgba(0,0,0,.9);
}
.fb::backdrop{background:rgba(8,8,9,.72);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)}
.fb__head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
.fb__text{
  width:100%;margin-top:8px;min-height:120px;resize:vertical;padding:10px 12px;
  background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:7px;
  font-family:var(--f-mono);font-size:12.5px;line-height:1.7;
}
.fb__acts{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}
</style>

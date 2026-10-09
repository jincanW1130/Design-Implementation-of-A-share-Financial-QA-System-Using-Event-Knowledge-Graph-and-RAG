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
            <span class="fresh__note">外部行情与新闻接口未接入；语料内近一周一块始终可用，见屏①「实时区 · 三块数据源」</span>
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
        <button v-for="n in nav" :key="n.key" class="nav__btn" role="tab"
                :aria-selected="cur === n.key ? 'true' : 'false'" @click="go(n.key)">{{ n.label }}</button>
      </nav>

      <div class="topbar__right">
        <span class="topbar__cut">数据截至：{{ datePart(appMeta.dataCutoffTime) }}</span>
        <button class="btn btn--primary btn--sm" @click="go('ask')">新建会话</button>
      </div>
    </header>
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
            <li><a href="#" @click.prevent>反馈与建议</a></li>
          </ul>
        </div>
      </div>
      <div class="footer__bottom">
        <p class="footer__legal">本页的证据条目、图谱路径、事件三元组、数据版本与截止时间，取自一次真实问答输出，原样呈现，未做改写。行情数据源当前未接入：默认显示「行情数据源未接入」，其间不含任何报价；外部源可达时按接口实返显示，并就地标注。语料口径与行情口径分属两套时间基准，不可混用。不构成任何投资建议。</p>
        <span class="label">© 2026 牛势问答 · A 股事件知识图谱与检索增强问答</span>
      </div>
    </div>
  </footer>
</template>

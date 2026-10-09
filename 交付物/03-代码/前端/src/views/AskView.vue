<script setup>
// 交付物/03-代码\前端\src\views\AskView.vue —— 屏① 提问台（逐字对齐 阶段09 前端设计原型）
//
// 结构：hero（标题 / 引导 / CTA / 四条元信息）→ 提问框 ＋ 运行状态（四探针）
//       → 实时区（三块数据源 · 两态）→ 跑马灯带 → 产品界面 mockup → 能力四卡。
//
// 取数：
//   · 提问              → POST /api/qa/ask（体只含 question ＋ session_id，固定 C 组）
//   · 运行状态 / 元信息 → provide 进来的 appMeta（/api/config/meta 与 /api/health）
//   · 实时区            → provide 进来的 market（/api/market/quote|news|reports，scope=display_only）
//
// 三条纪律（与后端一致）：实时区只作展示、不进问答证据链；外部源不可达时**如实显示「未接入」**，
// 绝不编造价格 / 涨跌幅 / 新闻；语料口径（截止 2026-09-25）与行情口径分属两套时间基准，不混用。

import { computed, inject, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { askQuestion } from '../api.js'

const router = useRouter()
const appMeta = inject('appMeta', null)
const market = inject('market', null)

// —— hero / meta ——
const cutoff = computed(() => {
  const iso = appMeta && appMeta.dataCutoffTime ? appMeta.dataCutoffTime : ''
  return iso ? iso.slice(0, 10) : '—'
})
const vecCount = computed(() => (appMeta && appMeta.vectorCount != null)
  ? appMeta.vectorCount.toLocaleString('en-US') : '—')

// —— 提问 ——
const qEl = ref(null)
const question = ref('')
const loading = ref(false)
const elapsed = ref(0)
const error = ref(null)
let timer = null
function startTimer() { elapsed.value = 0; timer = window.setInterval(() => { elapsed.value += 1 }, 1000) }
function stopTimer() { if (timer) { window.clearInterval(timer); timer = null } }

async function submit() {
  const text = question.value.trim()
  error.value = null
  if (!text) { error.value = { code: '', message: '请输入问题后再提交。' }; return }
  if (loading.value) return
  loading.value = true
  startTimer()
  try {
    const data = await askQuestion(text)
    stopTimer()
    loading.value = false
    if (data && data.answer_id !== undefined && data.answer_id !== null) {
      router.push({ name: 'answer', params: { answerId: String(data.answer_id) } })
    } else {
      error.value = { code: '', message: '后端未返回 answer_id，无法跳转到答案页。' }
    }
  } catch (e) {
    stopTimer()
    loading.value = false
    error.value = { code: e.code, message: e.message }
  }
}

// 跑马灯文字带（逐字取自原型：第 3 项「路径可视化」用 em 高亮）
const MQ = ['事件知识图谱', '证据可追溯', '路径可视化', '判定区间可回查', '多源数据治理', 'A 股财经问答']

const examples = [
  '平安银行与伊利股份共同参与的事件是什么？',
  '伊利股份收到的《接受注册通知书》涉及哪个机构？',
  '伊利股份 2026 年 8 月的关联交易公告披露了什么？',
  '平安银行有哪些任职关系记录？',
]
function useExample(t) { question.value = t; submit() }

function focusAsk() {
  nextTick(() => { if (qEl.value) { qEl.value.focus(); qEl.value.scrollIntoView({ block: 'center', behavior: 'smooth' }) } })
}

// —— 运行状态四探针（取自 /api/health，只渲染 ok 与安全标签，不原样输出 info）——
const probes = computed(() => {
  const h = appMeta && appMeta.health
  const ok = (o) => (h && o && o.ok) ? '正常' : (h ? '异常' : '未知')
  const mc = (h && h.model_config) || {}
  return [
    { name: 'MySQL · 事件库', k: 'event 表', v: h ? ok(h.mysql) : '未知', live: !!(h && h.mysql && h.mysql.ok) },
    { name: 'Neo4j · 事件图谱', k: '实体与关系', v: h ? ok(h.neo4j) : '未知', live: !!(h && h.neo4j && h.neo4j.ok) },
    { name: '向量索引', k: appMeta && appMeta.vectorCount != null ? `${appMeta.vectorCount.toLocaleString('en-US')} 条 · ${appMeta.vectorDim || '—'} 维` : '—', v: h ? ok(h.vector_index) : '未知', live: !!(h && h.vector_index && h.vector_index.ok) },
    { name: '模型 · ' + ((appMeta && appMeta.modelName) || '—'), k: 'Prompt ' + ((appMeta && appMeta.promptVersion) || '—'), v: h ? ok(mc) : '未知', live: !!(h && mc && mc.ok) },
  ]
})

// —— 实时区 ——
const on = computed(() => !!(market && market.on))
const quoteReason = computed(() => (market && market.quote && market.quote.reason) || '外部行情接口当前未接入')
const quoteConnected = computed(() => !!(market && market.quote && market.quote.connected))
const quoteItems = computed(() => (market && market.quote && market.quote.items) || [])
const newsItems = computed(() => (market && market.news && market.news.items) || [])
const newsConnected = computed(() => !!(market && market.news && market.news.connected))
const newsReason = computed(() => (market && market.news && market.news.reason) || '外部新闻公告接口未接入')

const reports = computed(() => (market && market.reports && market.reports.items) || [])
const reportCutoff = computed(() => (market && market.reports && market.reports.corpus_cutoff) || cutoff.value)
const reportDays = computed(() => (market && market.reports && market.reports.days) || 7)
const rtype = ref('all')
const BUCKET = { '公告': '公告', '财经新闻': '新闻', '政策文件': '政策', '新闻': '新闻', '政策': '政策' }
function bucketOf(c) { return BUCKET[c] || '其他' }
const reportCounts = computed(() => {
  const c = { all: reports.value.length, 公告: 0, 新闻: 0, 政策: 0 }
  reports.value.forEach((r) => { const b = bucketOf(r.category); if (c[b] != null) c[b]++ })
  return c
})
const shownReports = computed(() => rtype.value === 'all' ? reports.value : reports.value.filter((r) => bucketOf(r.category) === rtype.value))

function fmtTime(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 16) : '—' }
function fmtDate(t) { return typeof t === 'string' ? t.slice(0, 10) : '—' }

onMounted(() => { if (appMeta && !appMeta.health) { /* health 由 App.vue 拉取 */ } })
</script>

<template>
  <section class="view is-on" id="view-ask" role="tabpanel" aria-labelledby="nav-ask">
    <div class="wrap">

      <!-- hero -->
      <div class="hero">
        <span class="badge reveal"><i class="badge__dot"></i>预览版</span>
        <h1 class="d1 hero__title reveal" style="--d:70ms">A 股财经信息智能问答<br><em>现在，开箱即用</em></h1>
        <p class="lead hero__lead reveal" style="--d:140ms">把公告、新闻、研报与部委政策切成可检索的证据块，再用事件知识图谱把公司、人物、机构、事件与行业连起来。每一次回答都带着来源网站、文档号与图谱路径，可以逐条回查。</p>
        <div class="hero__cta reveal" style="--d:210ms">
          <button class="btn btn--primary" @click="focusAsk">开始提问</button>
          <button class="btn btn--ghost" @click="router.push('/history')">查看一条示例答案</button>
        </div>
        <div class="hero__meta reveal" style="--d:280ms">
          <div class="hero__meta-item"><span class="label">语料截止</span><b>{{ cutoff }}</b></div>
          <div class="hero__meta-item"><span class="label">数据集版本</span><b>{{ (appMeta && appMeta.datasetVersion) || '—' }}</b></div>
          <div class="hero__meta-item"><span class="label">向量索引</span><b>{{ vecCount }}</b><span class="small">条 · {{ (appMeta && appMeta.vectorDim) || '—' }} 维</span></div>
          <div class="hero__meta-item"><span class="label">图谱路径</span><b>1～2</b><span class="small">跳</span></div>
        </div>
      </div>

      <!-- 提问框 + 运行状态 -->
      <div class="ask sec--tight">
        <div>
          <div class="askbox reveal">
            <div class="askbox__top">
              <span class="label">提问</span>
              <span class="label">单轮问答 · 一次生成一份答案 · 图谱扩展默认开启（最多 2 跳）</span>
            </div>
            <label for="q" class="label" style="position:absolute;left:-9999px">财经问题输入框</label>
            <textarea id="q" ref="qEl" v-model="question" rows="3" :disabled="loading"
                      placeholder="请输入你的财经问题，例如：平安银行与伊利股份共同参与的事件是什么？"
                      @keydown.ctrl.enter="submit" @keydown.meta.enter="submit"></textarea>
            <div class="askbox__foot">
              <div class="askbox__hints">
                <span class="tag">数据集 {{ (appMeta && appMeta.datasetVersion) || '—' }}</span>
                <span class="tag">图谱扩展 开</span>
                <span class="tag">路径深度 1～2 跳</span>
              </div>
              <button class="btn btn--quiet" :disabled="loading" @click="submit">
                {{ loading ? '生成中…' : '提问' }}
              </button>
            </div>
            <p v-if="loading" class="small" style="margin-top:10px">正在生成答案，已等待 {{ elapsed }} 秒（链路约 10～30 s，请勿关闭页面）</p>
            <p v-if="error" class="small" style="margin-top:10px;color:var(--accent-ink)">
              <span v-if="error.code !== '' && error.code !== undefined && error.code !== null">[{{ error.code }}] </span>{{ error.message }}
            </p>
          </div>
          <div class="chips reveal" style="--d:80ms">
            <button v-for="(t, i) in examples" :key="i" class="chip" :disabled="loading" @click="useExample(t)">{{ t }}</button>
          </div>
        </div>

        <aside class="status reveal" style="--d:140ms">
          <div class="status__head">
            <span class="label">运行状态</span>
            <span class="seal" aria-hidden="true">牛</span>
          </div>
          <div class="status__cut">
            <span class="label label--red">数据截至</span>
            <b>{{ cutoff }}</b>
            <span class="small">数据集 {{ (appMeta && appMeta.datasetVersion) || '—' }} · 重跑采集与向量化前不变</span>
          </div>
          <div class="probes">
            <div class="probe" v-for="(p, i) in probes" :key="i">
              <i class="probe__dot" :class="p.live ? 'probe__dot--live' : ''"></i>
              <span class="probe__name">{{ p.name }}<span class="probe__k">{{ p.k }}</span></span>
              <span class="probe__v">{{ p.v }}</span>
            </div>
          </div>
        </aside>
      </div>

      <!-- 实时区：三块数据源 · 两态 -->
      <div class="sec">
        <div class="sec__head reveal">
          <div class="sec__head-l">
            <span class="label">03 / 实时区</span>
            <h2 class="h2">实时区 · 三块数据源</h2>
            <p class="body" style="max-width:82ch">实时区只作展示、不进入问答证据链；答案仍锚定语料截止 {{ cutoff }}。三块各自标注来源与时间口径，绝不与语料口径混用。</p>
          </div>
          <div class="gbar">
            <span class="tag tag--muted">实时接入 · {{ on ? '已接入（按接口实返）' : '未接入（默认）' }}</span>
          </div>
        </div>

        <div class="rt">
          <!-- 区块①：实时行情（外部行情接口） -->
          <article class="rt__blk rt__blk--a reveal">
            <div class="rt__head">
              <div>
                <span class="rt__no">01</span>
                <h3 class="rt__t">实时行情</h3>
                <div class="rt__meta">
                  <span class="tag">数据来源 · 外部行情接口</span>
                  <span class="tag tag--muted mk-off">未接入</span>
                  <span class="tag tag--red mk-on">按接口实返</span>
                  <span class="tag mk-on" v-if="on && quoteConnected">更新于 <b class="mono">{{ fmtTime(market.quote.updated_at) }}</b></span>
                </div>
              </div>
              <p class="rt__src">时间口径 <i>实时</i> · 当前状态 <b>{{ quoteConnected ? '已接入' : '未接入' }}</b>。{{ quoteConnected ? '价格、涨跌幅、成交额均取自接口实返。' : '接入后显示价格、涨跌幅、成交额与更新时间戳；未接入时这一块不显示任何数字。' }}</p>
            </div>

            <div class="mk-off">
              <div class="rt__empty">
                <svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>
                <div>
                  <b>行情数据源未接入</b>
                  <p>外部行情接口当前未接入，因此这一块不显示任何价格、涨跌幅与成交额。语料侧不受影响 —— 文本、证据与图谱路径的数据截止为 {{ cutoff }}（数据集 {{ (appMeta && appMeta.datasetVersion) || '—' }}）。</p>
                </div>
              </div>
            </div>

            <div class="mk-on">
              <template v-if="quoteConnected && quoteItems.length">
                <div style="display:flex;flex-wrap:wrap;gap:18px">
                  <div v-for="(it, i) in quoteItems" :key="i" class="kband__id" style="margin-bottom:10px">
                    <span class="h3">{{ it.name }}</span>
                    <span class="mono small">{{ it.code }}</span>
                    <span class="kband__px" :class="Number(it.change_pct) >= 0 ? 'up' : 'down'">{{ it.price }}</span>
                    <span class="mono small" :class="Number(it.change_pct) >= 0 ? 'up' : 'down'">{{ Number(it.change_pct) >= 0 ? '+' : '−' }}{{ Math.abs(Number(it.change_pct)).toFixed(2) }}%</span>
                    <span class="mono small" style="color:var(--muted)">成交额 {{ it.amount != null ? it.amount : '—' }}</span>
                  </div>
                </div>
              </template>
              <div v-else class="rt__empty">
                <svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>
                <div>
                  <b>行情数据源未接入</b>
                  <p>接口实返 connected=false：{{ quoteReason }}。本块如实显示「未接入」，不编造任何报价。</p>
                </div>
              </div>
            </div>
          </article>

          <!-- 区块②：当时重大新闻（外部新闻公告接口） -->
          <article class="rt__blk rt__blk--b reveal" style="--d:70ms">
            <div class="rt__head">
              <div>
                <span class="rt__no">02</span>
                <h3 class="rt__t">当时重大新闻</h3>
                <div class="rt__meta">
                  <span class="tag">数据来源 · 外部新闻公告接口</span>
                  <span class="tag tag--muted mk-off">未接入</span>
                  <span class="tag tag--red mk-on">按接口实返</span>
                </div>
              </div>
              <p class="rt__src">时间口径 <i>抓取时刻</i>。条目逐条来自接口实返；<b>实时区不进入问答证据链</b>。</p>
            </div>
            <div class="mk-off">
              <div class="rt__empty">
                <svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>
                <div>
                  <b>外部新闻公告接口未接入</b>
                  <p>未接入时不显示任何新闻条目。切到「已接入」后按接口实返显示；若源不可达，同样如实显示「未接入」与原因。</p>
                </div>
              </div>
            </div>
            <div class="mk-on">
              <div class="rt__list">
                <template v-if="newsConnected && newsItems.length">
                  <div v-for="(o, i) in newsItems" :key="i" class="rt__item">
                    <span class="rt__time">{{ o.time || o.date || '—' }}</span>
                    <span class="rt__ttl"><span class="tag" v-if="o.type" style="margin-right:7px">{{ o.type }}</span>{{ o.title }}
                      <span class="rt__site">{{ o.media || o.source || '东方财富' }}{{ o.url ? '' : ' · 本次未取到原文 URL' }}</span></span>
                    <a v-if="o.url" class="rt__go" :href="o.url" target="_blank" rel="noopener" :aria-label="'打开原文：' + o.title">原文 ↗</a>
                    <span v-else class="rt__go rt__go--off">未给出</span>
                  </div>
                </template>
                <div v-else class="rt__empty" style="min-height:110px">
                  <svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>
                  <div><b>新闻源当前不可达</b><p>接口实返 connected=false：{{ newsReason }}。不编造任何条目。</p></div>
                </div>
              </div>
            </div>
          </article>

          <!-- 区块③：相关股近一周的重要报告（本系统语料库 · 降级常驻） -->
          <article class="rt__blk rt__blk--c reveal" style="--d:140ms">
            <div class="rt__head">
              <div>
                <span class="rt__no">03</span>
                <h3 class="rt__t">相关股近一周的重要报告</h3>
                <div class="rt__meta">
                  <span class="tag">数据来源 · 本系统语料库</span>
                  <span class="tag tag--red">不依赖外部源</span>
                  <span class="tag">语料内近 {{ reportDays }} 天 · {{ reportCounts.all }} 篇</span>
                </div>
              </div>
              <div class="rt__seg" role="group" aria-label="按类型筛选近一周报告">
                <button class="chip" type="button" :aria-pressed="rtype === 'all'" @click="rtype = 'all'">全部<em class="chip__n">{{ reportCounts.all }}</em></button>
                <button class="chip" type="button" :aria-pressed="rtype === '公告'" @click="rtype = '公告'">公告<em class="chip__n">{{ reportCounts['公告'] }}</em></button>
                <button class="chip" type="button" :aria-pressed="rtype === '新闻'" @click="rtype = '新闻'">新闻<em class="chip__n">{{ reportCounts['新闻'] }}</em></button>
                <button class="chip" type="button" :aria-pressed="rtype === '政策'" @click="rtype = '政策'">政策<em class="chip__n">{{ reportCounts['政策'] }}</em></button>
              </div>
            </div>
            <div class="rt__list">
              <template v-if="shownReports.length">
                <div v-for="(o, i) in shownReports" :key="i" class="rt__item">
                  <span class="rt__time">{{ fmtDate(o.publish_time) }}</span>
                  <span class="rt__ttl"><span class="tag" v-if="o.category" style="margin-right:7px">{{ o.category }}</span>{{ o.title }}
                    <span class="rt__site">{{ o.source || '语料库' }}{{ o.url ? '' : ' · 本次未取到原文 URL' }}</span></span>
                  <a v-if="o.url" class="rt__go" :href="o.url" target="_blank" rel="noopener" :aria-label="'打开原文：' + o.title">原文 ↗</a>
                  <span v-else class="rt__go rt__go--off">未给出</span>
                </div>
              </template>
              <div v-else class="rt__empty" style="min-height:110px">
                <svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>
                <div><b>该类型近一周没有收录条目</b><p>语料库取数为接口实返，本块只列出接口返回的真实条目，不覆盖全部语料。</p></div>
              </div>
            </div>
            <p class="rt__note">
              口径：语料截止 <b>{{ reportCutoff }}</b>，向前 {{ reportDays }} 天。本块为<b>不依赖外部源</b>的降级形态，两态下都常驻；
              条目标题／日期／原文直链逐字取自数据层，未编造。
            </p>
          </article>
        </div>
      </div>

      <!-- 跑马灯带 -->
      <div class="mqband" aria-hidden="true">
        <div class="mqband__track">
          <template v-for="(t, i) in [...MQ, ...MQ]" :key="i">
            <span class="mqband__item"><em v-if="i % MQ.length === 2">{{ t }}</em><template v-else>{{ t }}</template><s></s></span>
          </template>
        </div>
      </div>

      <!-- 产品界面 mockup（界面示意，不含真实会话数据） -->
      <div class="sec">
        <div class="sec__head reveal">
          <div class="sec__head-l">
            <span class="label">04 / 产品界面</span>
            <h2 class="h2">一次提问，四份可回查的产物</h2>
            <p class="body" style="max-width:60ch">回答正文、证据清单、图谱路径与判定区间同时产出，四者互相索引。</p>
          </div>
          <a class="more" href="#" @click.prevent="router.push('/history')">了解更多</a>
        </div>

        <div class="mock reveal">
          <div class="mock__bar">
            <span class="mock__dots" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="mock__url">产品界面示意 · 非真实会话</span>
          </div>
          <div class="mock__body">
            <div class="mock__side">
              <div class="mock__grp">
                <span class="label">会话列表 · 最近提问</span>
                <div class="mock__sess">
                  <div class="mock__sitem on">平安银行与伊利股份共同参与的事件是什么？<time>本次会话</time></div>
                  <div class="mock__sitem">伊利股份收到的《接受注册通知书》涉及哪个机构？<time>示例</time></div>
                  <div class="mock__sitem">伊利股份 2026 年 8 月的关联交易公告披露了什么？<time>示例</time></div>
                </div>
              </div>
              <div class="mock__grp">
                <span class="label">运行状态</span>
                <div class="mock__probe"><i class="on"></i><span>MySQL · 事件库</span><em>正常</em></div>
                <div class="mock__probe"><i class="on"></i><span>Neo4j · 事件图谱</span><em>正常</em></div>
                <div class="mock__probe"><i class="on"></i><span>向量索引</span><em>{{ vecCount }} · {{ (appMeta && appMeta.vectorDim) || '—' }} 维</em></div>
                <div class="mock__probe"><i class="on"></i><span>{{ (appMeta && appMeta.modelName) || '模型' }}</span><em>正常</em></div>
              </div>
              <div class="mock__grp">
                <span class="label">数据口径说明</span>
                <div class="mock__cut">
                  <div class="mock__cutrow"><span>数据集</span><i>{{ (appMeta && appMeta.datasetVersion) || '—' }}</i></div>
                  <div class="mock__cutrow"><span>语料截止</span><i>{{ cutoff }}</i></div>
                  <div class="mock__cutrow"><span>Prompt</span><i>{{ (appMeta && appMeta.promptVersion) || '—' }}</i></div>
                  <div class="mock__cutrow"><span>行情</span><i>{{ quoteConnected ? '已接入' : '未接入' }}</i></div>
                </div>
              </div>
            </div>

            <div class="mock__main">
              <div class="msg">
                <span class="msg__ava">我</span>
                <div>
                  <div class="msg__name"><span class="label">单轮问答</span></div>
                  <p class="bubble bubble--user">平安银行与伊利股份共同参与的事件是什么？</p>
                </div>
              </div>
              <div class="msg">
                <span class="msg__ava msg__ava--ai"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg></span>
                <div>
                  <div class="msg__name">
                    <span class="label label--red">{{ (appMeta && appMeta.modelName) || '模型' }}</span>
                    <span class="label">一次性生成 · 非流式</span>
                  </div>
                  <div class="bubble">
                    <b>【回答】</b>把公开披露的公告、新闻与政策切成证据块，用事件知识图谱补全实体间关系，正文 [证据N] 与证据清单的 rank 一一对应，点开即可回查原块与相邻块。
                    <div class="mock__srcs">
                      <span class="tag">证据可回查</span>
                      <span class="tag tag--red">图谱路径 · 深度 1～2</span>
                      <span class="tag">判定区间随答案落库</span>
                    </div>
                  </div>
                </div>
              </div>
              <p class="mock__rule">答案一次性生成，没有流式过程提示；正文 [证据N] 与证据清单的 rank 一一对应，点开证据可看该块与相邻块。</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 能力四卡 -->
      <div class="sec">
        <div class="sec__head reveal">
          <div class="sec__head-l">
            <span class="label">05 / 能力</span>
            <h2 class="h2">面向 A 股的事件口径与证据链</h2>
          </div>
          <a class="more" href="#" @click.prevent="router.push('/graph')">了解更多</a>
        </div>

        <div class="caps">
          <article class="cap card reveal">
            <span class="cap__no">01</span>
            <h3 class="h3">事件抽取与对齐</h3>
            <p class="small">从公告、新闻与研报中抽取主体、事件类型、发生时间与置信度，统一到同一套事件口径。</p>
            <div class="cap__viz" aria-hidden="true">
              <svg viewBox="0 0 240 74" fill="none">
                <path d="M34 22h44M34 52h44M120 22l26 15M120 52l26-15M162 37h44" stroke="rgba(255,255,255,.18)" stroke-width="1.2"/>
                <circle cx="26" cy="22" r="8" stroke="#8792A8" stroke-width="1.6"/>
                <circle cx="26" cy="52" r="8" stroke="#8792A8" stroke-width="1.6"/>
                <polygon points="120,14 133,37 120,60 107,37" stroke="#A06CD5" stroke-width="1.6"/>
                <rect x="152" y="27" width="20" height="20" rx="5" stroke="#3E93B8" stroke-width="1.6"/>
                <circle cx="212" cy="37" r="9" stroke="#E63946" stroke-width="1.8"/>
                <circle cx="212" cy="37" r="3" fill="#E63946"/>
              </svg>
            </div>
          </article>
          <article class="cap card reveal" style="--d:70ms">
            <span class="cap__no">02</span>
            <h3 class="h3">证据可追溯</h3>
            <p class="small">每条结论都挂着来源网站、发布日期、文档号与块序号，正文 [证据N] 一点即定位到原块。</p>
            <div class="cap__viz" aria-hidden="true">
              <svg viewBox="0 0 240 74" fill="none">
                <rect x="18" y="12" width="150" height="14" rx="4" stroke="rgba(255,255,255,.16)" stroke-width="1.2"/>
                <rect x="18" y="32" width="204" height="14" rx="4" stroke="#E63946" stroke-width="1.8" fill="rgba(230,57,70,.14)"/>
                <rect x="18" y="52" width="120" height="14" rx="4" stroke="rgba(255,255,255,.16)" stroke-width="1.2"/>
                <path d="M178 39h22" stroke="#E63946" stroke-width="1.6"/><circle cx="206" cy="39" r="4" fill="#E63946"/>
              </svg>
            </div>
          </article>
          <article class="cap card reveal" style="--d:140ms">
            <span class="cap__no">03</span>
            <h3 class="h3">图谱路径推理</h3>
            <p class="small">从公司出发做实体检索与一跳邻居查询，最多走 2 跳，把没有直接共现的信息补进上下文。</p>
            <div class="cap__viz" aria-hidden="true">
              <svg viewBox="0 0 240 74" fill="none">
                <path d="M46 37 92 15M92 15 140 37M140 37 190 20M46 37 190 58" stroke="rgba(255,255,255,.18)" stroke-width="1.2"/>
                <path d="M46 37 140 37" stroke="#E63946" stroke-width="1.8"/>
                <circle cx="46" cy="37" r="11" stroke="#E63946" stroke-width="1.8"/>
                <polygon points="92,4 103,15 92,26 81,15" stroke="#A06CD5" stroke-width="1.6"/>
                <rect x="129" y="26" width="22" height="22" rx="6" stroke="#3E93B8" stroke-width="1.6"/>
                <polygon points="190,9 202,20 196,33 184,33 178,20" stroke="#8792A8" stroke-width="1.6"/>
                <polygon points="190,46 202,58 178,58" stroke="#C3CBD8" stroke-width="1.6"/>
              </svg>
            </div>
          </article>
          <article class="cap card reveal" style="--d:210ms">
            <span class="cap__no">04</span>
            <h3 class="h3">多源数据治理</h3>
            <p class="small">交易所公告、财经媒体与部委政策分源入库，去重、时效衰减与冲突消解在入库阶段完成。</p>
            <div class="cap__viz" aria-hidden="true">
              <svg viewBox="0 0 240 74" fill="none">
                <rect x="20" y="13" width="42" height="20" rx="5" stroke="#3E93B8" stroke-width="1.6"/>
                <rect x="72" y="13" width="42" height="20" rx="5" stroke="#8792A8" stroke-width="1.6"/>
                <rect x="124" y="13" width="42" height="20" rx="5" stroke="#6C7BE0" stroke-width="1.6"/>
                <rect x="176" y="13" width="42" height="20" rx="5" stroke="rgba(255,255,255,.16)" stroke-width="1.2"/>
                <path d="M20 45h198" stroke="rgba(255,255,255,.2)" stroke-width="1.2"/>
                <path d="M41 45v6M93 45v6M145 45v6M197 45v6" stroke="rgba(255,255,255,.2)" stroke-width="1.2"/>
                <rect x="20" y="51" width="198" height="12" rx="4" stroke="#E63946" stroke-width="1.8" fill="rgba(230,57,70,.12)"/>
              </svg>
            </div>
          </article>
        </div>
      </div>

    </div>
  </section>
</template>

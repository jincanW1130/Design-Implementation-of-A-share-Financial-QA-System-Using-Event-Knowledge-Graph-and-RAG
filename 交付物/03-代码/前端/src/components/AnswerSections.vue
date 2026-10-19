<script setup>
// 交付物/03-代码\前端\src\components\AnswerSections.vue —— 答案四段渲染（第 9 阶段 T9／F2）
//
// 按 `交付物/03-代码\问答\prompt.py` 的 `SECTION_HEADERS` 四个**固定段头**切分 `answer_text`：
//   【回答】／【证据来源】／【知识图谱路径】／【数据截至与判定区间】
// 切分是纯文本定位，不改写内容、不臆造缺失段。
//
// 版式→原型屏②的四段 `.aSec`：① 回答正文（[证据N] 引用可点，跳到证据卡并高亮）；
// ② 证据来源（evidence 插槽 ← EvidenceList）；③ 知识图谱路径（path 插槽 ← GraphPathPanel
// ＋ 路径统计 metaGrid）；④ 数据截至与判定区间（metaGrid ＋ 段体叙述）。
//
// **缺段要显式提示缺哪一段**：某段头在正文里找不到时，该段显式渲染「未找到【XX】段」，
// 而不是静默丢弃。「模型分析（非公开事实）」字样出现时同屏醒目提示。

import { computed } from 'vue'

const props = defineProps({
  answerText: { type: String, default: '' },
  /** 判定区间（`time_interpretation`），仅作附加信息展示，不参与四段切分。 */
  timeInterpretation: { type: String, default: '' },
  /** 是否使用图谱扩展（1／0），驱动第 3 段的开关与未使用文案。 */
  isGraphExtended: { type: [Number, String], default: 0 },
  /** 第 3 段路径内容是否展开显示（用户可关）。 */
  graphOn: { type: Boolean, default: true },
  /** 证据条数（第 2 段头说明用）。 */
  evidenceCount: { type: Number, default: 0 },
  /** 第 3 段统计：{ count, depth, nodesEdges, triples }。 */
  pathMeta: { type: Object, default: () => ({}) },
  /**
   * 第 3 段说明文字里的深度读数（2026-10-17）：由父视图按落库载荷现算后传入，
   * 与「路径深度上限」卡片同源；取不到时父视图传「未给出」。**本组件不再写死任何深度。**
   */
  pathDepthText: { type: String, default: '未给出' },
  /** 第 4 段 metaGrid 单元：`[{label, value}]`。 */
  windowCells: { type: Array, default: () => [] },
})

const emits = defineEmits(['toggle-graph', 'jump'])

// 与后端 `交付物/03-代码\问答\prompt.py` 的 SECTION_HEADERS 逐字对齐（顺序即渲染顺序）
const HEADERS = ['【回答】', '【证据来源】', '【知识图谱路径】', '【数据截至与判定区间】']

const MODEL_ANALYSIS_MARKER = '模型分析（非公开事实）'

const hasModelAnalysis = computed(() => (props.answerText || '').includes(MODEL_ANALYSIS_MARKER))
const extended = computed(() => Number(props.isGraphExtended) === 1)

const sections = computed(() => {
  const text = props.answerText || ''
  const indexes = HEADERS.map((h) => text.indexOf(h))
  const out = []
  for (let i = 0; i < HEADERS.length; i++) {
    const header = HEADERS[i]
    const start = indexes[i]
    if (start < 0) { out.push({ header, body: '', present: false }); continue }
    let end = text.length
    for (let j = 0; j < HEADERS.length; j++) {
      const pos = indexes[j]
      if (pos > start && pos < end) end = pos
    }
    out.push({ header, body: text.slice(start + header.length, end).trim(), present: true })
  }
  return out
})

const missingHeaders = computed(() => sections.value.filter((s) => !s.present).map((s) => s.header))

// 事件三元组条数：从第 3 段正文里逐行数（后端渲染成「  EVT-xxxx / 类型 / 时间」），
// 数不出就显示「—」，不猜数字。
const tripleCount = computed(() => {
  const s = sections.value[2]
  if (!s || !s.present) return null
  return s.body.split('\n').filter((l) => /^\s*EVT-\S/.test(l)).length
})

// 正文转安全 HTML：先转义，再把 [证据N] 换成可点引用（data-ev=evN），保留换行。
// 注意：这里的 esc() 只转义 & < >，刻意不转义引号。它的唯一出口是下面 refHTML()
// 生成的 HTML，经 v-html 插入 <p> 的**文本节点**；引用正则只允许数字，且不会有
// 任何不可信值进入属性上下文。若将来把这个结果移进属性或其它拼接上下文，
// 必须换成同时转义 " 与 ' 的完整转义（或改用 DOM API）。
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
function refHTML(s) {
  return esc(s).replace(/\[证据(\d+)\]/g, '<a class="ref" href="#" data-ev="ev$1">[证据$1]</a>')
}

function onBodyClick(e) {
  const a = e.target && e.target.closest ? e.target.closest('.ref') : null
  if (!a) return
  e.preventDefault()
  emits('jump', a.getAttribute('data-ev'))
}
</script>

<template>
  <div>
    <p v-if="hasModelAnalysis" class="small" style="margin-bottom:16px">
      <strong>{{ MODEL_ANALYSIS_MARKER }}</strong>：本答案含大模型的分析性表述，属模型推断、
      不是公开披露事实，请与带 [证据n] 引用的事实部分区别看待。
    </p>
    <p v-if="missingHeaders.length" class="small" style="margin-bottom:16px;color:var(--accent-ink)">
      注意：答案缺少以下固定段落 —— {{ missingHeaders.join('、') }}（后端返回的正文不完整或段头被改动，
      已如实标注，内容未作任何补写）。
    </p>

    <!-- 段一：回答 -->
    <div class="aSec">
      <div class="aSec__head">
        <h2 class="aSec__h">{{ HEADERS[0] }}</h2>
        <span class="label">单轮一次生成 · 非流式</span>
      </div>
      <p v-if="sections[0].present" class="answerText" style="white-space:pre-wrap" @click="onBodyClick" v-html="refHTML(sections[0].body)"></p>
      <p v-else class="small" style="color:var(--accent-ink)">未找到 {{ HEADERS[0] }} 段（该段在答案正文中不存在）。</p>
    </div>

    <!-- 段二：证据来源 -->
    <div class="aSec">
      <div class="aSec__head">
        <h2 class="aSec__h">{{ HEADERS[1] }}</h2>
        <span class="label">共 {{ evidenceCount }} 条 · 引用编号 [证据1]～[证据{{ evidenceCount }}] 与 rank 一一对应 · 点卡片看原文上下文</span>
      </div>
      <slot name="evidence">
        <p v-if="sections[1].present" class="small" style="white-space:pre-wrap">{{ sections[1].body }}</p>
      </slot>
      <p v-if="!sections[1].present" class="small" style="color:var(--accent-ink)">
        未找到 {{ HEADERS[1] }} 段（该段在答案正文中不存在）。
      </p>
      <!-- 2026-10-17 修（缺陷 2）：本组件原来**只在未传 evidence 插槽时**才渲染 sections[1].body，
           而 AnswerView 恒传该插槽，于是后端写在 answer_text 里的【证据来源】逐行清单
           （[证据N] chunk_id=… doc_id=… 来源类型=… 发布时间=… 标题：…）在答案页一个字都看不到。
           现加一段**默认折叠**的 details：有无插槽都可展开，内容原样取自 sections[1].body，
           pre-wrap 不截断、不摘要、不改写；空体（载荷未给正文）如实显示文本占位，不留空壳。 -->
      <details class="rawBox">
        <summary>查看后端原文清单（【证据来源】段原样返回，未截断、未摘要）</summary>
        <p v-if="sections[1].present && sections[1].body" class="small" style="white-space:pre-wrap">{{ sections[1].body }}</p>
        <p v-else class="small">该段在 answer_text 中未给出正文（逐条清单为空）。</p>
      </details>
    </div>

    <!-- 段三：知识图谱路径 -->
    <div class="aSec">
      <div class="aSec__head">
        <h2 class="aSec__h">{{ HEADERS[2] }}</h2>
        <button v-if="extended" class="btn btn--ghost btn--sm" type="button"
                :aria-pressed="graphOn ? 'true' : 'false'" @click="emits('toggle-graph')">
          图谱扩展：{{ graphOn ? '开' : '关' }}
        </button>
        <span v-else class="label">本次回答未启用图谱扩展——<b>不是功能关闭</b>：提问台的图谱扩展开关已开启，是本次检索未产生<b>可用的图谱证据路径</b>（问题实体在图谱中暂无关系边、或语料覆盖不足）。系统在此如实降级、不编造路径；要看图谱的当前状态，可到「知识图谱」页检索该实体。</span>
      </div>

      <template v-if="extended && !graphOn">
        <div class="graphOff">
          已隐藏图谱扩展路径（本次回答<b>实际使用了</b>图谱扩展，点上方按钮可再次展开；此处不是「未使用」）。
        </div>
      </template>
      <template v-else>
        <!-- 2026-10-17 修（缺陷 2）：原来这里只有 `<slot name="path">` 且**没有缺段分支**（原第 132～134 行）：
             传了插槽时 sections[2].body 不显示（depth=… 行、事件三元组行、预算口径「备注：路径列表与事件
             三元组计入 Context Token Budget，不计入 K」全部被吞掉），缺段时不提示。现在插槽照旧，另补
             「未找到…段」提示（与段一／段二一致）＋ 默认折叠的后端原样路径说明。 -->
        <slot name="path">
          <p v-if="sections[2].present" class="small" style="white-space:pre-wrap">{{ sections[2].body }}</p>
        </slot>
        <p v-if="!sections[2].present" class="small" style="color:var(--accent-ink)">
          未找到 {{ HEADERS[2] }} 段（该段在答案正文中不存在）。
        </p>
        <details class="rawBox">
          <summary>查看后端原样路径说明（【知识图谱路径】段原样返回，含 depth 行、事件三元组与预算口径备注）</summary>
          <p v-if="sections[2].present && sections[2].body" class="small" style="white-space:pre-wrap">{{ sections[2].body }}</p>
          <p v-else class="small">该段在 answer_text 中未给出正文（路径说明为空）。</p>
        </details>
      </template>

      <div v-if="extended" class="metaGrid" style="margin-top:20px">
        <div class="metaCell"><span class="label">路径条数</span><b>{{ pathMeta.count != null ? pathMeta.count : '—' }}</b></div>
        <div class="metaCell"><span class="label">路径深度上限</span><b>{{ pathMeta.depth != null ? pathMeta.depth + ' 跳' : '—' }}</b></div>
        <div class="metaCell"><span class="label">本页节点 · 边</span><b>{{ pathMeta.nodesEdges || '—' }}</b></div>
        <div class="metaCell"><span class="label">事件三元组</span><b>{{ tripleCount != null ? tripleCount + ' 条' : '—' }}</b></div>
      </div>
      <p v-if="extended" class="small" style="margin-top:14px;max-width:96ch">
        路径逐条取自接口原样返回的 `answer.graph_path`（本回答记录中路径深度上限 {{ pathDepthText }}；
        与上方「路径深度上限」卡片同源，均按落库载荷现算），属性行照抄不做补写；
        缺失字段一律「—（空）」。整张子图的节点／边可视化落在<b>屏③「事件知识图谱」</b>。
      </p>
    </div>

    <!-- 段四：数据截至与判定区间 -->
    <div class="aSec">
      <div class="aSec__head">
        <h2 class="aSec__h">{{ HEADERS[3] }}</h2>
        <span class="label">只读 · 随回答一并落库</span>
      </div>
      <div v-if="windowCells.length" class="metaGrid">
        <div v-for="(c, i) in windowCells" :key="i" class="metaCell">
          <span class="label">{{ c.label }}</span><b>{{ c.value }}</b>
        </div>
      </div>
      <p v-if="sections[3].present" class="small" style="margin-top:14px;white-space:pre-wrap;max-width:96ch">{{ sections[3].body }}</p>
      <p v-else class="small" style="margin-top:14px;color:var(--accent-ink)">未找到 {{ HEADERS[3] }} 段（该段在答案正文中不存在）。</p>
      <p v-if="timeInterpretation" class="small" style="margin-top:10px;max-width:96ch">
       判定区间（time_interpretation）：{{ timeInterpretation }}
      </p>
    </div>
  </div>
</template>

<style scoped>
/* 后端原文折叠块（2026-10-17）：只用现有主题变量，与 `.graphOff` 同一套观感；
   默认折叠，展开后是原样正文（pre-wrap 由内联样式给出，不截断、不摘要）。 */
.rawBox { margin-top: 12px; }
.rawBox > summary { cursor: pointer; font-size: 13px; line-height: 1.6; color: var(--muted); }
.rawBox > summary:hover { color: var(--fg); }
.rawBox[open] > summary { color: var(--fg); margin-bottom: 8px; }
.rawBox p { max-width: 96ch; color: var(--faint); }
</style>

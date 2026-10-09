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

// 正文转安全 HTML：先转义，再把 [证据N] 换成可点引用（data-ev=evN），保留换行
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
        <p v-else class="small" style="color:var(--accent-ink)">未找到 {{ HEADERS[1] }} 段（该段在答案正文中不存在）。</p>
      </slot>
    </div>

    <!-- 段三：知识图谱路径 -->
    <div class="aSec">
      <div class="aSec__head">
        <h2 class="aSec__h">{{ HEADERS[2] }}</h2>
        <button v-if="extended" class="btn btn--ghost btn--sm" type="button"
                :aria-pressed="graphOn ? 'true' : 'false'" @click="emits('toggle-graph')">
          图谱扩展：{{ graphOn ? '开' : '关' }}
        </button>
        <span v-else class="label">本次回答未启用图谱扩展</span>
      </div>

      <div v-if="extended && !graphOn" class="graphOff">
        已隐藏图谱扩展路径（本次回答<b>实际使用了</b>图谱扩展，点上方按钮可再次展开；此处不是「未使用」）。
      </div>
      <slot v-else name="path">
        <p v-if="sections[2].present" class="small" style="white-space:pre-wrap">{{ sections[2].body }}</p>
      </slot>

      <div v-if="extended" class="metaGrid" style="margin-top:20px">
        <div class="metaCell"><span class="label">路径条数</span><b>{{ pathMeta.count != null ? pathMeta.count : '—' }}</b></div>
        <div class="metaCell"><span class="label">路径深度上限</span><b>{{ pathMeta.depth != null ? pathMeta.depth + ' 跳' : '—' }}</b></div>
        <div class="metaCell"><span class="label">本页节点 · 边</span><b>{{ pathMeta.nodesEdges || '—' }}</b></div>
        <div class="metaCell"><span class="label">事件三元组</span><b>{{ tripleCount != null ? tripleCount + ' 条' : '—' }}</b></div>
      </div>
      <p v-if="extended" class="small" style="margin-top:14px;max-width:96ch">
        路径逐条取自接口原样返回的 `answer.graph_path`（记录里的深度为 1～2 跳），属性行照抄不做补写；
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

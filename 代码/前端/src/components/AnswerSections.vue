<script setup>
// 代码\前端\src\components\AnswerSections.vue —— 答案四段渲染（第 9 阶段 T9／F2）
//
// 按 `代码\问答\prompt.py` 的 `SECTION_HEADERS` 四个**固定段头**切分 `answer_text`：
//   【回答】／【证据来源】／【知识图谱路径】／【数据截至与判定区间】
// 切分是纯文本定位，不改写内容、不臆造缺失段。
//
// **缺段要显式提示缺哪一段**（任务要求 3）：某段头在正文里找不到时，该段显式渲染
// 「未找到【XX】段」，而不是静默丢弃。
//
// 「模型分析（非公开事实）」提示：答案正文里出现该固定字样时同屏醒目提示
// （《24》第2.3节 硬约束 8：公开事实与模型分析必须区分）。

import { computed } from 'vue'

const props = defineProps({
  answerText: { type: String, default: '' },
  /** 判定区间（`time_interpretation`），仅作附加信息展示，不参与四段切分。 */
  timeInterpretation: { type: String, default: '' },
})

// 与后端 `代码\问答\prompt.py` 的 SECTION_HEADERS 逐字对齐（顺序即渲染顺序）
const HEADERS = ['【回答】', '【证据来源】', '【知识图谱路径】', '【数据截至与判定区间】']

const MODEL_ANALYSIS_MARKER = '模型分析（非公开事实）'

const hasModelAnalysis = computed(() =>
  (props.answerText || '').includes(MODEL_ANALYSIS_MARKER))

const sections = computed(() => {
  const text = props.answerText || ''
  const indexes = HEADERS.map((h) => text.indexOf(h))
  const out = []
  for (let i = 0; i < HEADERS.length; i++) {
    const header = HEADERS[i]
    const start = indexes[i]
    if (start < 0) {
      // 缺段：显式登记，不静默丢弃
      out.push({ header, body: '', present: false })
      continue
    }
    // 段体 = 本段头之后、到「下一个出现的段头」之前的文本
    let end = text.length
    for (let j = 0; j < HEADERS.length; j++) {
      const pos = indexes[j]
      if (pos > start && pos < end) end = pos
    }
    const body = text.slice(start + header.length, end).trim()
    out.push({ header, body, present: true })
  }
  return out
})

const missingHeaders = computed(() => sections.value.filter((s) => !s.present).map((s) => s.header))
</script>

<template>
  <div class="sections">
    <div v-if="hasModelAnalysis" class="warnbox model-analysis">
      <strong>模型分析（非公开事实）</strong>：本答案含大模型的分析性表述，属模型推断、
      不是公开披露事实，请与带 [证据n] 引用的事实部分区别看待。
    </div>

    <p v-if="missingHeaders.length" class="warnbox">
      注意：答案缺少以下固定段落 —— {{ missingHeaders.join('、') }}（后端返回的正文不完整或段头被改动，
      已如实标注，内容未作任何补写）。
    </p>

    <section v-for="s in sections" :key="s.header" class="section" :class="{ missing: !s.present }">
      <h3 class="section-head">{{ s.header }}</h3>
      <pre v-if="s.present" class="section-body">{{ s.body }}</pre>
      <p v-else class="section-absent">未找到 {{ s.header }} 段（该段在答案正文中不存在）。</p>
    </section>

    <section v-if="timeInterpretation" class="section">
      <h3 class="section-head">判定区间（time_interpretation）</h3>
      <pre class="section-body">{{ timeInterpretation }}</pre>
    </section>
  </div>
</template>

<style scoped>
.sections { display: flex; flex-direction: column; gap: 14px; }
.model-analysis { margin-bottom: 2px; }
.section { border-left: 3px solid var(--accent); padding: 2px 0 2px 12px; }
.section.missing { border-left-color: var(--warn-line); }
.section-head { margin: 0 0 6px; font-size: 14px; color: var(--accent); }
.section.missing .section-head { color: #a07800; }
.section-body {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; font-size: 14px; line-height: 1.75;
}
.section-absent { margin: 0; color: #a07800; font-size: 13px; }
</style>

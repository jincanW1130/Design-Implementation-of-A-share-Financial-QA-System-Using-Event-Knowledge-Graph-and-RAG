<script setup>
// 代码\前端\src\views\AnswerView.vue —— 答案与证据页（第 9 阶段 T9／F2～F5）
//
// 取数（三个后端接口，各司其职）：
//   * `GET /api/qa/answers/{answer_id}`          → answer_text／graph_path／is_graph_extended／元信息
//   * `GET /api/evidence/{answer_id}`            → 四类分组计数 groups ＋ 证据明细 items
//   * （数据截至取自 `/api/config/meta`，由 App.vue 拉取后 provide 到本页）
//
// 固定显示「数据截至：YYYY-MM-DD」（取 data_cutoff_time 的日期部分，硬约束 12／F3）。

import { computed, inject, ref, watch } from 'vue'
import { getAnswer, getEvidence, getGraphPath } from '../api.js'
import AnswerSections from '../components/AnswerSections.vue'
import EvidenceList from '../components/EvidenceList.vue'
import GraphPathPanel from '../components/GraphPathPanel.vue'

const props = defineProps({ answerId: { type: [String, Number], required: true } })
const appMeta = inject('appMeta', null)

const loading = ref(false)
const error = ref(null)
const answer = ref(null)
const evidence = ref({ groups: {}, items: [] })
const graphPath = ref({ is_graph_extended: 0, paths: null, display_mode: 'not_used' })

const cutoffDate = computed(() => {
  const iso = appMeta && appMeta.dataCutoffTime ? appMeta.dataCutoffTime : ''
  return iso ? iso.slice(0, 10) : '—'
})

async function load() {
  loading.value = true
  error.value = null
  answer.value = null
  evidence.value = { groups: {}, items: [] }
  graphPath.value = { is_graph_extended: 0, paths: null, display_mode: 'not_used' }
  try {
    // 回答详情、证据分组、图谱路径：三个接口并行取
    const [ans, ev, gp] = await Promise.all([
      getAnswer(props.answerId),
      getEvidence(props.answerId),
      getGraphPath(props.answerId),
    ])
    answer.value = ans
    evidence.value = { groups: (ev && ev.groups) || {}, items: (ev && ev.items) || [] }
    graphPath.value = gp || graphPath.value
  } catch (e) {
    error.value = { code: e.code, message: e.message }
  } finally {
    loading.value = false
  }
}

watch(() => props.answerId, load, { immediate: true })

function fmtTime(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 19) : '—' }
</script>

<template>
  <div>
    <div class="card cutoff-bar">
      <strong>数据截至：{{ cutoffDate }}</strong>
      <span class="muted">（dataset_version={{ appMeta ? appMeta.datasetVersion || '—' : '—' }}）</span>
      <span class="tag right">answer_id = {{ props.answerId }}</span>
    </div>

    <div v-if="loading" class="card muted">正在读取答案与证据…</div>

    <div v-else-if="error" class="card err">
      <strong>读取失败</strong>
      <span class="code-tag">code = {{ error.code }}</span>
      <p class="err-msg">{{ error.message }}</p>
      <p v-if="error.code === 2001" class="muted">该 answer_id 在库中不存在，请回提问页重新提问。</p>
    </div>

    <template v-else-if="answer">
      <div class="card">
        <h2>问题</h2>
        <p class="q-text">{{ answer.question_text }}</p>
        <p class="muted meta">
          answer_id={{ answer.answer_id }}｜question_id={{ answer.question_id }}｜
          模型 {{ answer.model_name }}｜Prompt {{ answer.prompt_version }}｜
          生成时间 {{ fmtTime(answer.create_time) }}
        </p>
      </div>

      <div class="card">
        <h2>答案（按四个固定段头渲染）</h2>
        <AnswerSections :answer-text="answer.answer_text" />
      </div>

      <div class="card">
        <h2>知识图谱路径</h2>
        <GraphPathPanel :is-graph-extended="graphPath.is_graph_extended"
                        :graph-path="graphPath.paths" />
      </div>

      <div class="card">
        <h2>证据（按四类分组）</h2>
        <EvidenceList :items="evidence.items" :groups="evidence.groups" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.cutoff-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.right { margin-left: auto; }
.code-tag { margin-left: 8px; font-family: Consolas, monospace; font-size: 12px; color: #7d2016; }
.err-msg { margin: 6px 0 0; }
.q-text { margin: 0 0 8px; font-weight: 600; }
.meta { margin: 0; font-size: 12px; }
</style>

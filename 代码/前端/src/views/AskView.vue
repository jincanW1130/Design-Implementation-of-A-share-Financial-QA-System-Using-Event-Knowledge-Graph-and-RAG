<script setup>
// 代码\前端\src\views\AskView.vue —— 提问页（第 9 阶段 T9）
//
// 交互：多行问题输入 ＋ 提交按钮；提交中显示加载态（真实链路约 10～30 s）；
// 成功后跳转 `/answer/:answerId`；失败时把后端的 `code` 与 `message` **都**显示出来
// （不是笼统的「请求失败」）。
//
// 固定 C 组：请求体只含 `question` 与 `session_id`（后者由 api.js 自动带上），
// 前端**不提供**任何 A～E 组／开关入口（硬约束 9）。

import { inject, ref } from 'vue'
import { useRouter } from 'vue-router'
import { askQuestion } from '../api.js'

const router = useRouter()
const appMeta = inject('appMeta', null)

const question = ref('')
const loading = ref(false)
const error = ref(null)
const elapsed = ref(0)

let timer = null

function startTimer() {
  elapsed.value = 0
  timer = window.setInterval(() => { elapsed.value += 1 }, 1000)
}
function stopTimer() {
  if (timer) { window.clearInterval(timer); timer = null }
}

async function submit() {
  const text = question.value.trim()
  error.value = null
  if (!text) {
    error.value = { code: '', message: '请输入问题后再提交。' }
    return
  }
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

const examples = [
  '长城汽车《2023年股票期权激励计划》首次授予股票期权第二个行权期的行权期有效期是什么时间段？',
  '最近30天内美的集团依据《关于上市公司实施员工持股计划试点的指导意见》办理的持股计划事件是什么？',
]
function useExample(t) { question.value = t }
</script>

<template>
  <div>
    <div class="card">
      <h2>提问</h2>
      <p class="muted intro">
        提问将走「检索 → 装配与生成 → 落库」的真实链路，约需 10～30 秒；答案固定 C 组（Method）。
        第一版不启用登录，会话由浏览器本地生成。
      </p>
      <textarea v-model="question" rows="4" :disabled="loading"
                placeholder="请输入关于 A 股信息披露的问题（支持多行）…"></textarea>
      <div class="actions">
        <button class="btn primary" :disabled="loading" @click="submit">
          {{ loading ? '提交中…' : '提交提问' }}
        </button>
        <span v-if="loading" class="loading">
          <span class="spinner"></span> 正在生成答案，已等待 {{ elapsed }} 秒（请勿关闭页面）
        </span>
        <span v-if="appMeta" class="muted cutoff">
          数据截至：{{ (appMeta.dataCutoffTime || '—').slice(0, 10) }}
        </span>
      </div>

      <div class="examples">
        <span class="muted">示例：</span>
        <button v-for="(t, i) in examples" :key="i" class="linklike" :disabled="loading"
                @click="useExample(t)">{{ t }}</button>
      </div>
    </div>

    <div v-if="error" class="card err">
      <strong>提交失败</strong>
      <span v-if="error.code !== '' && error.code !== undefined && error.code !== null"
            class="code-tag">code = {{ error.code }}</span>
      <p class="err-msg">{{ error.message }}</p>
    </div>
  </div>
</template>

<style scoped>
.intro { margin: 0 0 10px; font-size: 13px; }
textarea { resize: vertical; min-height: 88px; }
.actions { display: flex; align-items: center; gap: 14px; margin-top: 10px; flex-wrap: wrap; }
.loading { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); font-size: 13px; }
.cutoff { margin-left: auto; font-size: 12px; }
.spinner {
  width: 12px; height: 12px; border: 2px solid var(--accent-soft); border-top-color: var(--accent);
  border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.examples { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.linklike {
  background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; text-align: left;
  font: inherit; font-size: 13px;
}
.linklike:hover { text-decoration: underline; }
.code-tag {
  margin-left: 8px; font-family: Consolas, monospace; font-size: 12px; color: #7d2016;
}
.err-msg { margin: 6px 0 0; font-family: inherit; }
</style>

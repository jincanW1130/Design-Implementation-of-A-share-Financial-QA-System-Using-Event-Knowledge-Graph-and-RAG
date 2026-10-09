<script setup>
// 交付物/03-代码\前端\src\components\EvidenceList.vue —— 证据按四类分组展示（第 9 阶段 T9／F5）
//
// 四类固定顺序与后端 `qa_service.EVIDENCE_TYPES` 一致：
//   回答来源／新闻来源／公告来源／相关事件（F5 逐字机检 TYPES 数组）。
// 每条＝原型屏②的证据卡：证据N／标题／来源网站·发布日期·文档号·块序号／来源站（＋域名）／
// 「查看原文 ↗」（接口返回 url 直达，新窗口；未给出 url 时显示「记录未给出」，不猜链接）／
// 「查看原文上下文（该块＋相邻块）」→ 展开该块正文与相邻块（GET /api/documents/{doc_id}/chunks/{chunk_id}）。
// 字段缺失一律如实标注，不补写、不编造。

import { computed, reactive, ref } from 'vue'
import { getChunk } from '../api.js'
import { DOMAIN, EXT } from '../lib/graph.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** 后端返回的四类计数（`groups`）；缺省时按 items 现算。 */
  groups: { type: Object, default: () => ({}) },
  /** 需要高亮的证据卡 id（形如 `ev6`），由正文里的 [证据N] 引用触发。 */
  flashId: { type: String, default: '' },
})

// 与后端 EVIDENCE_TYPES 逐字对齐、顺序一致（F5 机检此数组）
const TYPES = ['回答来源', '新闻来源', '公告来源', '相关事件']

const grouped = computed(() => {
  const out = {}
  for (const t of TYPES) out[t] = props.items.filter((it) => it.evidence_type === t)
  return out
})

function countOf(t) {
  const n = props.groups ? props.groups[t] : undefined
  return typeof n === 'number' ? n : grouped.value[t].length
}

function evId(it) { return 'ev' + it.rank }
function domainOf(it) { return DOMAIN[it.source] || '' }
function urlOf(it) { return it.url || '' }
function fmtDate(t) { return typeof t === 'string' ? t.replace('T', ' ').slice(0, 10) : '' }

const openKey = ref('')                 // 当前展开上下文的那一条（同一时刻一条）
const chunks = reactive({})             // 缓存：key → {loading, error, data}
function keyOf(it) { return `${it.doc_id}-${it.chunk_id}` }

async function toggleCtx(it) {
  const key = keyOf(it)
  if (openKey.value === key) { openKey.value = ''; return }
  openKey.value = key
  if (chunks[key] && !chunks[key].error) return   // 已缓存成功结果，不重复请求
  chunks[key] = { loading: true, error: '', data: null }
  try {
    const data = await getChunk(it.doc_id, it.chunk_id)
    chunks[key] = { loading: false, error: '', data }
  } catch (e) {
    chunks[key] = { loading: false, error: `${e.code ? '[' + e.code + '] ' : ''}${e.message}`, data: null }
  }
}
</script>

<template>
  <div class="evgrid">
    <div v-if="!items.length" class="evgrp--empty">
      <p>本次回答未返回任何证据条目。</p>
      <p>证据清单按回答来源／新闻来源／公告来源／相关事件四类归集；本条回答四类均未命中。</p>
    </div>

    <div v-for="t in TYPES" :key="t" class="evgroup">
      <div class="evgroup__head">
        <span class="label">{{ t }}</span>
        <span class="evgroup__n">{{ countOf(t) }} 条</span>
      </div>

      <div v-if="!grouped[t].length" class="evgrp--empty">
        <p>本次回答未命中该来源类别。</p>
        <p>证据清单按回答来源／新闻来源／公告来源／相关事件四类归集，本条回答该类未命中。</p>
      </div>

      <div v-else class="evgroup__cards">
        <article v-for="it in grouped[t]" :key="keyOf(it)" :id="evId(it)" class="ev"
                 :class="{ flash: flashId === evId(it) }">
          <span class="ev__no">证据{{ it.rank }}</span>
          <h4 class="ev__t">{{ it.title || '该条字段值未在记录中给出' }}</h4>

          <div class="ev__meta">
            <div class="ev__row"><span>来源网站</span>
              <template v-if="it.source">{{ it.source }}</template>
              <i v-else>记录未给出</i></div>
            <div class="ev__row"><span>发布日期</span>
              <template v-if="fmtDate(it.publish_time)">{{ fmtDate(it.publish_time) }}</template>
              <i v-else>记录未给出</i></div>
            <div class="ev__row"><span>文档号</span><i>doc_id={{ it.doc_id }}</i></div>
            <div class="ev__row"><span>块序号</span><i>chunk_id={{ it.chunk_id }}</i></div>
          </div>

          <div class="ev__src">
            <span>来源站</span>
            <div v-if="it.source"><b>{{ it.source }}</b><em v-if="domainOf(it)"> · {{ domainOf(it) }}</em></div>
            <div v-else><em>记录未给出</em></div>
          </div>

          <div class="ev__acts">
            <a v-if="urlOf(it)" class="ev__link" :href="urlOf(it)" target="_blank" rel="noopener"
               :aria-label="'查看原文：' + (it.title || '') + '（新窗口打开）'"><span v-html="EXT"></span>查看原文 ↗</a>
            <span v-else class="ev__nolink">记录未给出</span>
            <span class="small">{{ urlOf(it) ? '原文按接口返回的 url 直达，新窗口打开' : '本条未返回 url，不猜链接' }}</span>
          </div>

          <div class="ev__ctx">
            <button class="ev__ctxbtn" type="button" :aria-expanded="openKey === keyOf(it) ? 'true' : 'false'"
                    @click="toggleCtx(it)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
                   stroke-linejoin="round" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5"/></svg>
              查看原文上下文（该块＋相邻块）
            </button>
            <div v-show="openKey === keyOf(it)" class="ev__ctxbox">
              <div class="ev__ctxrow"><span>该块</span><i>doc_id {{ it.doc_id }} / chunk_id {{ it.chunk_id }}</i></div>
              <p v-if="chunks[keyOf(it)] && chunks[keyOf(it)].loading" class="ev__ctxnote">加载中…</p>
              <p v-else-if="chunks[keyOf(it)] && chunks[keyOf(it)].error" class="ev__ctxnote" style="color:var(--accent-ink)">
                {{ chunks[keyOf(it)].error }}
              </p>
              <template v-else-if="chunks[keyOf(it)] && chunks[keyOf(it)].data">
                <div class="ev__ctxrow"><span>相邻块</span><i>{{ (chunks[keyOf(it)].data.neighbor_chunks || []).length
                  ? (chunks[keyOf(it)].data.neighbor_chunks || []).map((n) => 'chunk_id ' + n.chunk_id).join('、')
                  : '未收录' }}</i></div>
                <div class="evctx__block">
                  <div class="ev__ctxnote">正文（chunk_id {{ chunks[keyOf(it)].data.chunk_id }} · 原文照抄，不截断／不摘要）</div>
                  <pre class="evctx__text">{{ chunks[keyOf(it)].data.chunk_content }}</pre>
                </div>
                <div v-for="nb in (chunks[keyOf(it)].data.neighbor_chunks || [])" :key="nb.chunk_id" class="evctx__block">
                  <div class="ev__ctxnote">相邻块 chunk_id {{ nb.chunk_id }}（index={{ nb.chunk_index }}）</div>
                  <pre class="evctx__text">{{ nb.chunk_content }}</pre>
                </div>
              </template>
              <p class="ev__ctxnote">原文上下文按「该块＋相邻块」定位还原（真实接口 GET /api/documents/{doc_id}/chunks/{chunk_id} 的 chunk_content 与 neighbor_chunks）。</p>
            </div>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 仅补 theme.css 未覆盖的「原文正文」文本块样式；其余一律沿用全局主题类 */
.evctx__block { display: flex; flex-direction: column; gap: 5px; }
.evctx__text {
  margin: 0; white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow: auto;
  font-family: var(--f-mono); font-size: 11.5px; line-height: 1.7; color: rgba(255, 255, 255, .72);
  background: rgba(255, 255, 255, .022); border: 1px solid var(--border-soft); border-radius: 7px; padding: 9px 10px;
}
.small { color: var(--faint); }
</style>

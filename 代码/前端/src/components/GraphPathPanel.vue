<script setup>
// 代码\前端\src\components\GraphPathPanel.vue —— 图谱路径可读化（第 9 阶段 T9／F4）
//
// 两种情形（《24》硬约束 11、格式决策 5／7）：
//   * `is_graph_extended = 1`：把 `answer.graph_path` 的 JSON **渲染成可读链路**
//     「节点 —关系（role, confidence, source_doc_id, source_chunk_id）→ 节点」；
//   * `is_graph_extended = 0`：显示**固定文案**「本次回答未使用图谱扩展」——**不留空、不编造**。
//
// 数据来源是后端解析 `answer.graph_path` 落库原文后的结构化结果（`/api/evidence/{id}/graph-path`
// 或 `/api/qa/answers/{id}` 的 `graph_path` 字段），本组件**只做展示，不重建路径**。

import { computed } from 'vue'

const NO_GRAPH_MARKER = '本次回答未使用图谱扩展'

const props = defineProps({
  isGraphExtended: { type: [Number, String], default: 0 },
  /** 解析后的路径数组；也容忍后端偶发传回的 JSON 字符串（会就地解析）。 */
  graphPath: { type: [Array, String, Object], default: null },
})

const extended = computed(() => Number(props.isGraphExtended) === 1)

const paths = computed(() => {
  let raw = props.graphPath
  if (typeof raw === 'string') {
    try { raw = JSON.parse(raw) } catch (e) { return [] }
  }
  return Array.isArray(raw) ? raw : []
})

/** 单个节点的展示名：兼容「字符串 id」与「对象 {node_id, name, label}」两种形态。 */
function nodeLabel(node) {
  if (node === null || node === undefined) return '—'
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  const id = node.node_id ?? node.id ?? ''
  const name = node.name ?? ''
  return name ? `${name}（${id}）` : String(id || '—')
}

/** 关系边的四项证据属性（role／confidence／source_doc_id／source_chunk_id）。 */
function relAttrs(rel) {
  const ev = rel.evidence || {}
  const confidence = ev.confidence ?? rel.confidence
  const sourceDoc = ev.source_doc_id ?? rel.source_doc_id
  const sourceChunk = ev.source_chunk_id ?? rel.source_chunk_id
  const parts = []
  if (rel.role) parts.push(`role=${rel.role}`)
  if (confidence !== undefined && confidence !== null && confidence !== '') parts.push(`confidence=${confidence}`)
  if (sourceDoc !== undefined && sourceDoc !== null && sourceDoc !== '') parts.push(`source_doc_id=${sourceDoc}`)
  if (sourceChunk !== undefined && sourceChunk !== null && sourceChunk !== '') parts.push(`source_chunk_id=${sourceChunk}`)
  if (rel.evidence_doc_id) parts.push(`evidence_doc_id=${rel.evidence_doc_id}`)
  return parts.join(', ')
}

/** 把一条路径的 nodes 与 relations 交叉成可读链路的片段数组。 */
function chainOf(path) {
  const nodes = Array.isArray(path.nodes) ? path.nodes : []
  const rels = Array.isArray(path.relations) ? path.relations
    : (Array.isArray(path.edges) ? path.edges : [])
  const segs = []
  for (let i = 0; i < nodes.length; i++) {
    segs.push({ kind: 'node', text: nodeLabel(nodes[i]) })
    if (i < nodes.length - 1) {
      const rel = rels[i] || {}
      segs.push({
        kind: 'rel',
        relation: rel.relation || '—',
        direction: rel.direction || 'out',
        attrs: relAttrs(rel),
      })
    }
  }
  return segs
}
</script>

<template>
  <div class="graph-panel">
    <!-- 未使用图谱扩展：固定文案，不留空、不编造 -->
    <div v-if="!extended" class="not-used">
      <strong>{{ NO_GRAPH_MARKER }}</strong>
      <span class="muted">（本次回答未启用图谱扩展，`graph_path` 为空）</span>
    </div>

    <template v-else>
      <p v-if="!paths.length" class="warnbox">
        标记为使用了图谱扩展（is_graph_extended=1），但 `graph_path` 未返回任何路径。
      </p>
      <p v-else class="muted hit-count">共 {{ paths.length }} 条图谱路径。</p>

      <ol v-if="paths.length" class="path-list">
        <li v-for="(p, i) in paths" :key="i" class="path-item">
          <div class="path-meta muted">
            路径 {{ i + 1 }}
            <span v-if="p.depth !== undefined">｜ depth={{ p.depth }}</span>
            <span v-if="p.start">｜ {{ p.start }} → {{ p.end }}</span>
          </div>
          <div class="chain">
            <template v-for="(seg, j) in chainOf(p)" :key="j">
              <span v-if="seg.kind === 'node'" class="node">{{ seg.text }}</span>
              <span v-else class="rel">
                <span class="arrow">{{ seg.direction === 'in' ? '←' : '—' }}</span>
                <span class="rel-name">{{ seg.relation }}</span>
                <span v-if="seg.attrs" class="rel-attrs">（{{ seg.attrs }}）</span>
                <span class="arrow">{{ seg.direction === 'in' ? '—' : '→' }}</span>
              </span>
            </template>
          </div>
        </li>
      </ol>
    </template>
  </div>
</template>

<style scoped>
.not-used {
  display: flex; flex-direction: column; gap: 2px;
  background: #f2f4f7; border: 1px dashed var(--line); border-radius: 6px; padding: 12px 14px;
}
.not-used strong { color: var(--ink); }
.hit-count { margin: 0 0 8px; font-size: 13px; }
.path-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.path-item { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; }
.path-meta { font-size: 12px; margin-bottom: 4px; }
.chain { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: 13px; line-height: 2; }
.node {
  background: var(--accent-soft); border: 1px solid #c7d7f8; border-radius: 4px;
  padding: 1px 8px; font-weight: 600;
}
.rel { display: inline-flex; align-items: center; gap: 3px; color: var(--ink-soft); }
.rel-name { font-weight: 600; color: #7a5b00; }
.rel-attrs { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
.arrow { color: var(--accent); font-weight: 700; }
</style>

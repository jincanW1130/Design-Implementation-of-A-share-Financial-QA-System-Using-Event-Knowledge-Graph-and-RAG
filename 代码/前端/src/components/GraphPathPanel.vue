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
// 落库形态：每条路径 `{start, end, relations[{relation, role, evidence{confidence,
// source_doc_id, source_chunk_id}}]}`；也容忍 `nodes/edges` 与字符串两种历史形态。

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
  else parts.push('role=（空）')
  if (confidence !== undefined && confidence !== null && confidence !== '') parts.push(`confidence=${confidence}`)
  else parts.push('confidence=—（空）')
  if (sourceDoc !== undefined && sourceDoc !== null && sourceDoc !== '') parts.push(`source_doc_id=${sourceDoc}`)
  else parts.push('source_doc_id=—（空）')
  if (sourceChunk !== undefined && sourceChunk !== null && sourceChunk !== '') parts.push(`source_chunk_id=${sourceChunk}`)
  else parts.push('source_chunk_id=—（空）')
  if (rel.evidence_doc_id) parts.push(`evidence_doc_id=${rel.evidence_doc_id}`)
  return parts.join(' · ')
}

/** 把一条路径渲染成「节点／关系」片段数组；兼容 {nodes,relations} 与 {start,end,relations}。 */
function chainOf(path) {
  const nodes = Array.isArray(path.nodes) ? path.nodes : null
  const rels = Array.isArray(path.relations) ? path.relations
    : (Array.isArray(path.edges) ? path.edges : [])
  const segs = []
  if (nodes && nodes.length) {
    for (let i = 0; i < nodes.length; i++) {
      segs.push({ kind: 'node', text: nodeLabel(nodes[i]) })
      if (i < nodes.length - 1) {
        const rel = rels[i] || {}
        segs.push({ kind: 'rel', relation: rel.relation || '—', direction: rel.direction || 'out', attrs: relAttrs(rel) })
      }
    }
    return segs
  }
  // 落库形态：{start, end, relations[]}
  segs.push({ kind: 'node', text: path.start ?? '—' })
  for (const rel of rels) segs.push({ kind: 'rel', relation: rel.relation || '—', direction: 'out', attrs: relAttrs(rel) })
  segs.push({ kind: 'node', text: path.end ?? '—' })
  return segs
}

function pathMeta(p, i) {
  const bits = ['路径 ' + (i + 1)]
  if (p.depth !== undefined && p.depth !== null) bits.push('｜ depth=' + p.depth)
  if (p.start || p.end) bits.push('｜ ' + (p.start ?? '—') + ' → ' + (p.end ?? '—'))
  return bits.join(' ')
}
</script>

<template>
  <div>
    <!-- 未使用图谱扩展：固定文案，不留空、不编造 -->
    <div v-if="!extended" class="graphOff">{{ NO_GRAPH_MARKER }}</div>

    <template v-else>
      <p v-if="!paths.length" class="small" style="margin-bottom:12px">
        标记为使用了图谱扩展（is_graph_extended=1），但 `graph_path` 未返回任何路径。
      </p>
      <p v-else class="small" style="margin-bottom:12px">共 {{ paths.length }} 条图谱路径。</p>

      <div v-if="paths.length" class="paths">
        <div v-for="(p, i) in paths" :key="i" class="path">
          <template v-for="(seg, j) in chainOf(p)" :key="j">
            <span v-if="seg.kind === 'node'" class="path__node">{{ seg.text }}</span>
            <span v-else class="path__rel">
              {{ seg.direction === 'in' ? '←' : '—' }}[{{ seg.relation }}]{{ seg.direction === 'in' ? '—' : '→' }}
              <em v-if="seg.attrs" style="color:var(--faint)">（{{ seg.attrs }}）</em>
            </span>
          </template>
          <span class="path__attrs">{{ pathMeta(p, i) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

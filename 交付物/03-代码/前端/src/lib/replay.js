// 交付物/03-代码\前端\src\lib\replay.js —— 落库路径载荷（answer.graph_path）的回看还原
//
// 背景（2026-10-14 用户反馈「图谱都是编码」）：
//   * 检索层落库的 `graph_path_payload`（graph_query.py）里 nodes 只存**节点编号字符串**、
//     relations 存关系与证据三项——这是冻结的落库契约（拓扑可回放），后端不改；
//   * 画布标签 `label/lbl` 由 graph.js 的 buildDataset 在构造时**按当时的 n.name 算死**；
//     HistoryView 旧实现先 buildDataset（name 兜底成编号）再异步改 n.name，标签不会重算，
//     故补名不生效——本模块把顺序反过来：**先批量补名，再 buildDataset**；
//   * 补名只调单实体详情接口（GET /api/graph/entities/{id}，真实属性，不编造），
//     **3 并发**（与 GraphView.prefetchEvents 同一防限流纪律：后端 60 次/60 秒）；
//     单个补名失败该节点保持编号，不阻断画布。
//
// 口径：回看/展示只按**当时记录的路径载荷**渲染，不重新查询图谱拓扑（与历史回看抽屉一致）。

import { getEntity } from '../api.js'
import { buildDataset } from './graph.js'

/** 节点编号 → 画布类型（载荷只存编号，按编号前缀判别；判不出的一律按「文档」处理，不猜）。 */
export function typeOfId(id) {
  const s = String(id)
  if (/^PER-/.test(s)) return 'person'
  if (/^EVT-/.test(s)) return 'event'
  if (/^INST-|^ORG-/.test(s)) return 'org'
  if (/^POL-/.test(s)) return 'policy'
  if (/^IND-/.test(s)) return 'industry'
  if (/^\d{6}$/.test(s)) return 'company'
  return 'doc'
}

/**
 * 批量补名：编号 → 实体名（单实体详情接口；3 并发防限流）。
 * 返回 Map<id, name>；单个失败保持编号（不进 Map），不抛异常、不阻断。
 */
export async function enrichNames(ids) {
  const map = new Map()
  const list = [...new Set((ids || []).map(String))]
  const CONC = 3
  for (let i = 0; i < list.length; i += CONC) {
    await Promise.all(list.slice(i, i + CONC).map(async (id) => {
      try {
        const d = await getEntity(id)
        const name = d && d.node && d.node.name
        if (name) map.set(id, String(name))
      } catch (e) { /* 补名失败（限流／瞬时错误）：该节点保持编号，不阻断画布 */ }
    }))
  }
  return map
}

/**
 * 由 `answer.graph_path` 载荷收集全部节点编号（保序去重）。
 * 兼容两种落库形态：{nodes:[编号…], relations:[…]} 与 {start,end,relations:[…]}。
 */
export function collectPathNodes(payload) {
  const out = []
  const seen = new Set()
  const push = (x) => {
    if (x === undefined || x === null) return
    const id = String(x)
    if (!id || seen.has(id)) return
    seen.add(id); out.push(id)
  }
  for (const p of ((payload && payload.paths) || [])) {
    const nodes = Array.isArray(p.nodes) ? p.nodes : null
    if (nodes && nodes.length) nodes.forEach(push)
    else { push(p.start) }
    for (const rel of (p.relations || [])) push(rel && rel.neighbor)
    if (!(nodes && nodes.length)) push(p.end)
  }
  return out
}

/** 载荷里第一个公司节点（六位数字编号）——「在知识图谱页查看」的锚点；取不到回退首条路径起点。 */
export function firstCompanyOf(payload) {
  for (const p of ((payload && payload.paths) || [])) {
    for (const n of (Array.isArray(p.nodes) ? p.nodes : [])) {
      if (/^\d{6}$/.test(String(n))) return String(n)
    }
  }
  const p0 = payload && payload.paths && payload.paths[0]
  return p0 && p0.start !== undefined && p0.start !== null ? String(p0.start) : null
}

/**
 * 由落库载荷构造回看数据集（**先补名、后 buildDataset**——这是 2026-10-14 修正的关键顺序）。
 * 边构造与 HistoryView 旧 replayDs 完全同形（in/out 方向、证据三项、noev 标记）。
 * 返回 buildDataset 的结果（含 label/lbl/布局）；无路径返回 null。
 */
export async function buildReplayDataset(payload) {
  const paths = (payload && payload.paths) || []
  if (!Array.isArray(paths) || !paths.length) return null
  const nodeSet = new Set()
  const edges = []
  for (const p of paths) {
    const nodes = Array.isArray(p.nodes) ? p.nodes : []
    ;(p.relations || []).forEach((rel, i) => {
      const a = nodes.length ? nodes[i] : p.start
      const b = rel.neighbor
      if (a === undefined || a === null || b === undefined || b === null) return
      nodeSet.add(String(a)); nodeSet.add(String(b))
      const inEdge = rel.direction === 'in'
      const ev = rel.evidence || {}
      const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))
      edges.push({
        f: String(inEdge ? b : a),
        t: String(inEdge ? a : b),
        rel: rel.relation,
        role: rel.role || '',
        conf: num(ev.confidence),
        sdoc: ev.source_doc_id !== undefined ? ev.source_doc_id : null,
        schunk: ev.source_chunk_id !== undefined ? ev.source_chunk_id : null,
        noev: rel.relation === 'EVIDENCED_BY' ? 1 : 0,
        src: 'answer.graph_path',
      })
    })
    if (!nodes.length) {
      if (p.start !== undefined && p.start !== null) nodeSet.add(String(p.start))
      if (p.end !== undefined && p.end !== null) nodeSet.add(String(p.end))
    }
  }
  if (!nodeSet.size) return null
  const nameMap = await enrichNames([...nodeSet])
  const nodes = [...nodeSet].map((id) => ({
    id, eid: id, type: typeOfId(id),
    name: nameMap.get(id) || id,          // 补名成功＝实体名；失败保持编号（如实降级，不编造）
    code: '', sub: '', time: null,
  }))
  return buildDataset('replay', nodes, edges)
}

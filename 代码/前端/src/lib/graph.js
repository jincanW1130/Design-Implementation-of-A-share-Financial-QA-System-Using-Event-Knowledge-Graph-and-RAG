// 代码\前端\src\lib\graph.js —— 知识图谱渲染器（移植自 阶段09 前端设计原型 index.html 的脚本第 5 节）
//
// 设计语言唯一真源是原型；本文件把原型的**布局 / 去遮挡 / 标签规划 / 几何自检 /
// 命中测试 / 缩放平移拖拽 / 选中态状态机**逐字移植，唯一改动是**数据来源**：
//   原型里内置的演示数据（EAPI / GNODES / GEDGES / EVALL / GDOCS …）全部删除，
//   改为由调用方通过 `opt` 注入——真实后端接口（GET /api/graph/entities/{id}、
//   /evidence、/neighbors、/paths、/events/{id}）在视图层拉取后传进来。
//
// 三条纪律（与原型一致）：
//   · 记录未给出的字段一律显示「—（空）」/「—（该关系类型不带证据属性）」，绝不补写；
//   · 选中是幂等的（再点同节点不清空），取消只有三个明确出口（点空白 / 面板按钮 / Esc）；
//   · 任何浮层（图例、工具条、属性面板）都不压在绘图区上，画布留 ≥9% 安全边距。

export const REL = {
  HAS_EXECUTIVE: '任职', PARTICIPATES_IN: '参与', ISSUED_BY: '发布', BELONGS_TO: '属于',
  RELATED_TO: '相关', CUSTOMER_OF: '客户关系', COMPETES_WITH: '同业竞争', EVIDENCED_BY: '证据指向',
}
export const EMPTY = '—（空）'
export const NOEV = '—（该关系类型不带证据属性）'
export const RELNAME = (r) => REL[r] || r

export const TYPE = {
  company: { n: '公司', c: '#E63946', s: 'circle' },
  person: { n: '人物', c: '#6C7BE0', s: 'hex' },
  org: { n: '机构', c: '#3E93B8', s: 'rect' },
  event: { n: '事件', c: '#A06CD5', s: 'diamond' },
  policy: { n: '政策', c: '#8792A8', s: 'pentagon' },
  industry: { n: '行业', c: '#C3CBD8', s: 'triangle' },
  doc: { n: '文档', c: '#C89B5A', s: 'page' },
}
export const TKEYS = ['company', 'person', 'org', 'event', 'policy', 'industry', 'doc']

// 后端标签（6 类）→ 画布类型（7 类；Document 单列一类）的映射
export const LABEL2TYPE = {
  Company: 'company', Person: 'person', Institution: 'org', Event: 'event',
  Policy: 'policy', Industry: 'industry', Document: 'doc',
}
export function typeOfLabel(label) { return LABEL2TYPE[label] || 'doc' }

export const DOMAIN = {
  巨潮资讯网: 'static.cninfo.com.cn', 证券日报网: 'www.zqrb.cn', 中国政府网: 'www.gov.cn',
  中证网: 'www.cs.com.cn', 东方财富: 'data.eastmoney.com',
}

// 站内所有「原文 ↗」图标共用同一段 SVG（与原型第 7 行的 EXT 逐字一致）
export const EXT = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M4.2 2.4H2.6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V7.8"/>' +
  '<path d="M7 1.6h3.4V5"/><path d="M10.4 1.6 5.6 6.4"/></svg>'

// 实体档案的键名中文注释（只用于面板辅助显示，不改变原键名）＋ 长文本键
export const EAPI_LABEL = {
  company_name: '公司全称', short_name: '证券简称', aliases: '别名', exchange: '交易所',
  event_type: '事件类型', event_time: '事件时间', event_id: '事件编号',
  event_name: '事件名称', confidence: '置信度', description: '事件描述',
  title: '文档标题', source: '来源', publish_time: '发布时间', category: '分类',
  doc_id: '文档编号', url: '原文链接',
  industry_name: '行业名称', industry_code: '行业代码',
  person_id: '人物编号', person_name: '姓名',
  institution_id: '机构编号', institution_name: '机构名称',
  policy_id: '政策编号', policy_name: '政策名称',
}
const EAPI_HOT = {
  company: ['company_name', 'exchange', 'aliases'],
  event: ['event_type', 'event_time', 'confidence', 'description'],
}
const EAPI_LONG = { description: 1, title: 1, event_name: 1, url: 1, aliases: 1 }

// 半径按度数分级但钳位；画布安全边距；并行边曲率分距
const R_MIN = 14, R_MAX = 30, R_STEP = 2.6
const RULE_R = '半径 ＝ 14 + 度×2.6（公司 +2），上下限 14～30 px'
const SAFE = 0.09, RING_GAP = 34, COMP_GAP = 76

export function radiusOf(deg, type) {
  const r = R_MIN + deg * R_STEP + (type === 'company' ? 2 : 0)
  return Math.max(R_MIN, Math.min(R_MAX, Math.round(r)))
}

// —— 纯几何工具（逐字移植） ——
const LBL_MAX = 14
function trunclbl(s) { return s.length > LBL_MAX ? s.slice(0, LBL_MAX) + '…' : s }
function textW(s, size) {
  size = size || 11.5; let w = 0
  for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); w += (c > 0x2E80 ? size : size * 0.56) }
  return Math.round(w * 10) / 10
}
function rectHit(a, b) { return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y) }
function lrect(n, x, y) { const w = Math.max(n.lw, 10); return { x: x - w / 2, y: y + n.r + 3, w, h: 15 } }
function confTo(node, center, ds) {
  let best = -1
  ds.edges.forEach((e) => {
    if ((e.f === node.id && e.t === center.id) || (e.t === node.id && e.f === center.id))
      best = Math.max(best, e.conf === null ? -0.5 : e.conf)
  })
  return best
}
function ngon(r, n, rot) {
  const p = []
  for (let i = 0; i < n; i++) { const a = (rot + i * 360 / n) * Math.PI / 180; p.push((Math.cos(a) * r).toFixed(2) + ',' + (Math.sin(a) * r).toFixed(2)) }
  return p.join(' ')
}
export function shapeSVG(type, r, op) {
  const t = TYPE[type] || TYPE.doc
  const st = 'class="shape" fill="' + t.c + '" fill-opacity="' + (op === undefined ? 0.2 : op) + '" stroke="' + t.c + '" stroke-width="1.6"'
  if (t.s === 'circle') return '<circle r="' + r + '" ' + st + '/>'
  if (t.s === 'hex') return '<polygon points="' + ngon(r, 6, -90) + '" ' + st + '/>'
  if (t.s === 'rect') return '<rect x="' + (-r) + '" y="' + (-r * 0.86).toFixed(2) + '" width="' + (r * 2) + '" height="' + (r * 1.72).toFixed(2) + '" rx="' + (r * 0.3).toFixed(2) + '" ' + st + '/>'
  if (t.s === 'diamond') return '<polygon points="0,' + (-r) + ' ' + r + ',0 0,' + r + ' ' + (-r) + ',0" ' + st + '/>'
  if (t.s === 'pentagon') return '<polygon points="' + ngon(r, 5, -90) + '" ' + st + '/>'
  if (t.s === 'page') {
    const w = r * 1.8, h = r * 1.2, f = r * 0.46
    return '<path d="M' + (-w / 2) + ',' + (-h / 2) + ' H' + (w / 2 - f) + ' L' + (w / 2) + ',' + (-h / 2 + f) + ' V' + (h / 2) + ' H' + (-w / 2) + ' Z" ' + st + '/>' +
      '<path d="M' + (w / 2 - f) + ',' + (-h / 2) + ' V' + (-h / 2 + f) + ' H' + (w / 2) + '" fill="none" stroke="' + t.c + '" stroke-width="1.2" stroke-opacity=".85"/>'
  }
  return '<polygon points="' + ngon(r * 1.12, 3, 90) + '" ' + st + '/>'
}

// —— 确定性分层环形布局（逐字移植） ——
function ringPositions(ring, R, rot) {
  const n = ring.length, out = []
  for (let i = 0; i < n; i++) { const a = rot + i * 2 * Math.PI / n; out.push({ n: ring[i], x: Math.cos(a) * R, y: Math.sin(a) * R }) }
  return out
}
function ringClear(pos, placed) {
  for (let i = 0; i < pos.length; i++) {
    const a = pos[i]
    for (let j = 0; j < pos.length; j++) {
      if (i === j) continue
      const b = pos[j]
      if (Math.hypot(a.x - b.x, a.y - b.y) < a.n.r + b.n.r + 2) return false
      if (rectHit(lrect(a.n, a.x, a.y), lrect(b.n, b.x, b.y))) return false
    }
    for (let j = 0; j < placed.length; j++) {
      const b = placed[j]
      if (Math.hypot(a.x - b.x, a.y - b.y) < a.n.r + b.n.r + 2) return false
      if (rectHit(lrect(a.n, a.x, a.y), lrect(b.n, b.x, b.y))) return false
    }
  }
  return true
}
function layout(ds) {
  const groups = ds.comps.slice().sort((a, b) => (b.length - a.length) || (a[0] < b[0] ? -1 : 1))
  const iso = ds.nodes.filter((n) => n.deg === 0)
  const blocks = []
  groups.forEach((acc) => {
    const center = ds.idx[acc.slice().sort((a, b) => (ds.idx[b].deg - ds.idx[a].deg) || (a < b ? -1 : 1))[0]]
    const rings = {}
    acc.forEach((id) => { const d = ds.idx[id].dist; (rings[d] = rings[d] || []).push(ds.idx[id]) })
    const ks = Object.keys(rings).map(Number).sort((a, b) => a - b), R = { 0: 0 }, placed = []
    let hw = 0, hh = 0
    ks.forEach((k) => { if (k === 0) return; rings[k].sort((a, b) => (confTo(b, center, ds) - confTo(a, center, ds)) || (b.deg - a.deg) || (a.id < b.id ? -1 : 1)) })
    center.x = 0; center.y = 0; placed.push({ n: center, x: 0, y: 0 })
    for (let s = 1; s < ks.length; s++) {
      const kk = ks[s], ring = rings[kk], n = ring.length, pd = ks[s - 1]
      let prevMax = 0, maxR = 0
      rings[pd].forEach((x) => { prevMax = Math.max(prevMax, x.r) })
      ring.forEach((x) => { maxR = Math.max(maxR, x.r) })
      let Rk = Math.max(R[pd] + prevMax + maxR + RING_GAP, 96), pos = null
      let need = 0
      for (let j = 0; j < n; j++) {
        const a = ring[j], b = ring[(j + 1) % n]
        need = Math.max(need, a.r + b.r + 16, (a.lw + b.lw) / 2 + 14)
      }
      const rmin = (n > 1) ? need / (2 * Math.sin(Math.PI / n)) : 0
      Rk = Math.max(Rk, rmin)
      for (let it = 0; it < 40; it++) {
        pos = ringPositions(ring, Rk, -Math.PI / 2 + kk * 0.42)
        if (ringClear(pos, placed) && Rk >= R[pd] + prevMax + maxR + RING_GAP - 0.01) break
        Rk = Math.max(Rk * 1.08, rmin, R[pd] + prevMax + maxR + maxR + RING_GAP)
      }
      R[kk] = Rk
      pos.forEach((p) => { p.n.x = p.x; p.n.y = p.y; placed.push(p) })
      hw = Math.max(hw, Rk + maxR + 26); hh = Math.max(hh, Rk + maxR + 34)
    }
    if (ks.length === 1) hw = hh = Math.max(center.r + 34, 60)
    blocks.push({ center, hw, hh })
  })
  let x = 0, maxH = 60
  blocks.forEach((b) => { b.ox = x + b.hw; x += b.hw * 2 + COMP_GAP; maxH = Math.max(maxH, b.hh) })
  blocks.forEach((b) => { ds.nodes.forEach((n) => { if (n.centerId === b.center.id) n.x += b.ox }) })
  if (iso.length) {
    const iy = maxH + 66
    let cx = -((iso.reduce((s2, n) => s2 + n.lw + 34, 0)) / 2)
    iso.forEach((n) => { cx += n.lw / 2 + 17; n.x = cx; n.y = iy; cx += n.lw / 2 + 17 })
  }
  let bb = null
  ds.nodes.forEach((n) => {
    n.x = Math.round(n.x * 100) / 100; n.y = Math.round(n.y * 100) / 100
    const r = lrect(n, n.x, n.y)
    const x0 = Math.min(n.x - n.r, r.x), x1 = Math.max(n.x + n.r, r.x + r.w)
    const y0 = Math.min(n.y - n.r, r.y), y1 = Math.max(n.y + n.r, r.y + r.h)
    if (!bb) bb = { x0, y0, x1, y1 }
    else { bb.x0 = Math.min(bb.x0, x0); bb.y0 = Math.min(bb.y0, y0); bb.x1 = Math.max(bb.x1, x1); bb.y1 = Math.max(bb.y1, y1) }
  })
  ds.bb = { x: bb.x0, y: bb.y0, w: bb.x1 - bb.x0, h: bb.y1 - bb.y0 }
  return ds
}

// —— 标签优先级规划 ＋ 几何遮挡自检（逐字移植） ——
function planLabels(DS, S) {
  const live = DS.nodes.filter((n) => n.on)
  const neigh = {}
  let focus = null
  if (S.sel) {
    focus = S.sel.id
    DS.edges.forEach((e) => { if (e.f === S.sel.id) neigh[e.t] = 1; if (e.t === S.sel.id) neigh[e.f] = 1 })
  } else if (S.edge !== null && S.edge !== undefined && DS.edges[S.edge]) {
    const ee = DS.edges[S.edge]; neigh[ee.f] = 1; neigh[ee.t] = 1
  }
  live.forEach((n) => {
    n.pri = focus ? (n.id === focus ? 3 : (neigh[n.id] ? 2 : 0)) : (neigh[n.id] ? 2 : 1)
    n.rect = lrect(n, n.x, n.y)
    n.lblOn = false; n.lblHidden = false
  })
  const list = live.filter((n) => n.pri > 0).sort((a, b) => (b.pri - a.pri) || (b.deg - a.deg) || (a.id < b.id ? -1 : 1))
  const accepted = [], cap = S.sel ? 13 : 10
  list.forEach((n) => {
    if (accepted.length >= cap && n.pri < 2) { n.lblHidden = true; return }
    for (let i = 0; i < accepted.length; i++) if (rectHit(n.rect, accepted[i].rect)) { n.lblHidden = true; return }
    accepted.push(n); n.lblOn = true
  })
  live.forEach((n) => { if (n.pri === 0) n.lblHidden = true })
  DS.nodes.forEach((n) => { if (!n.lel) return; n.lel.classList.toggle('on', !!(n.on && n.lblOn)) })
  return { shown: accepted.length, hidden: live.length - accepted.length }
}
function selfCheck(DS) {
  const vis = DS.nodes.filter((n) => n.on)
  let no = 0, lo = 0
  for (let i = 0; i < vis.length; i++) for (let j = i + 1; j < vis.length; j++) {
    const a = vis[i], b = vis[j]
    if (Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)) < a.r + b.r - 0.5) no++
  }
  const lb = vis.filter((n) => n.lblOn)
  for (let i = 0; i < lb.length; i++) for (let j = i + 1; j < lb.length; j++) if (rectHit(lb[i].rect, lb[j].rect)) lo++
  return { node: no, label: lo, shown: lb.length, total: vis.length, hidden: vis.filter((n) => n.lblHidden).length }
}

function pathsOf(ds) {
  const a = []
  ds.edges.forEach((e) => { a.push({ d: 1, e: [e.i] }) })
  ds.edges.forEach((e) => { ds.edges.forEach((e2) => { if (e2.f === e.t) a.push({ d: 2, e: [e.i, e2.i] }) }) })
  for (let i = 0; i < a.length; i++) { a[i].f = ds.edges[a[i].e[0]].f; a[i].t = ds.edges[a[i].e[a[i].e.length - 1]].t }
  return a
}

// ------------------------------------------------------------------
// 数据集：由视图层给的**真实**节点/边数组构造（对应原型 makeDS，但不再内置演示数据）
//   nodes: {id,type,name,code,eid,sub,time}
//   edges: {f,t,rel,role,conf,sdoc,schunk,noev,src}
// ------------------------------------------------------------------
export function buildDataset(mode, nodeArr, edgeArr) {
  const nodes = nodeArr.map((n) => Object.assign({}, n))
  let edges = edgeArr.map((e) => Object.assign({}, e))
  const idx = {}, deg = {}, adj = {}
  nodes.forEach((n) => { idx[n.id] = n; deg[n.id] = 0; adj[n.id] = [] })
  edges.forEach((e, i) => {
    e.i = i
    if (deg[e.f] === undefined || deg[e.t] === undefined) return  // 边端点必须都在节点集里
    deg[e.f]++; deg[e.t]++; adj[e.f].push(e.t); adj[e.t].push(e.f)
  })
  edges = edges.filter((e) => idx[e.f] && idx[e.t])
  edges.forEach((e, i) => { e.i = i })
  nodes.forEach((n) => {
    n.deg = deg[n.id] || 0; n.r = radiusOf(n.deg, n.type)
    n.label = n.code ? (n.name + ' ' + n.code) : n.name
    n.lbl = trunclbl(n.label); n.lw = textW(n.lbl)
    n.lblOn = false; n.lblHidden = false; n.on = true; n.el = null; n.lel = null; n.pri = 0
    n.time = (n.time && n.time !== EMPTY && n.time !== null) ? n.time : null
  })
  const seen = {}, comps = []
  nodes.forEach((n) => {
    if (seen[n.id] || !adj[n.id].length) return
    const q = [n.id], acc = []; seen[n.id] = 1
    while (q.length) { const c = q.shift(); acc.push(c); adj[c].forEach((x) => { if (!seen[x]) { seen[x] = 1; q.push(x) } }) }
    comps.push(acc)
  })
  comps.forEach((acc) => {
    const center = acc.slice().sort((a, b) => (idx[b].deg - idx[a].deg) || (a < b ? -1 : 1))[0]
    const d = {}; d[center] = 0; const q = [center]
    while (q.length) { const c = q.shift(); adj[c].forEach((x) => { if (d[x] === undefined) { d[x] = d[c] + 1; q.push(x) } }) }
    acc.forEach((id) => { idx[id].dist = d[id]; idx[id].centerId = center })
  })
  nodes.forEach((n) => { if (n.dist === undefined) { n.dist = 99; n.centerId = null } n.isCenter = (n.centerId === n.id) })
  let hops = 0
  nodes.forEach((n) => { if (n.dist < 99 && n.dist > hops) hops = n.dist })
  const ds = { mode, nodes, edges, idx, adj, comps, hops }
  layout(ds)
  ds.paths = pathsOf(ds)
  return ds
}

// ------------------------------------------------------------------
// 可复用图谱渲染器（移植自原型 mountGraph）
// opt:
//   ds        主数据集（buildDataset 的结构）
//   modes     [{key,label,ds,note}] 可选；多于 1 个时显示「数据集」分段控件
//   tag       准确性声明里的数据来源标签
//   select    数据集自带锚点（画布节点 id）
//   provider  {entity(id)->Promise, evidence(id,depth)->Promise, event(id)->Promise}
//   months    ["YYYY-MM", …] 可选；给定时启用时间轴联动（否则恒为全域）
//   onReset / onDataset 可选回调
// ------------------------------------------------------------------
export function mountGraph(host, opt) {
  if (!host) return null
  opt = opt || {}
  const uid = 'gm' + (mountGraph._n = (mountGraph._n || 0) + 1), mk = 'mk' + uid
  const provider = opt.provider || {}
  let MODES = (opt.modes && opt.modes.length) ? opt.modes.slice() : null

  function cloneDS(src) {
    const nodes = src.nodes.map((n) => {
      const c = {}; for (const k in n) c[k] = n[k]
      c.el = null; c.lel = null; c.on = true; c.lblOn = false; c.lblHidden = false; return c
    })
    const idx = {}; nodes.forEach((n) => { idx[n.id] = n })
    const edges = src.edges.map((e) => { const c = {}; for (const k in e) c[k] = e[k]; c.el = null; return c })
    const paths = src.paths.map((p) => ({ d: p.d, e: p.e.slice(), f: p.f, t: p.t }))
    return { mode: src.mode, nodes, edges, idx, adj: src.adj, comps: src.comps, hops: src.hops, bb: src.bb, paths }
  }

  let DS = cloneDS(opt.ds)
  const S = { sel: null, edge: null, path: null, hidden: {}, depth: opt.depth || 2, i0: 0, i1: (opt.months ? opt.months.length - 1 : 0), userCleared: false }
  const PREF = opt.select || null
  const MONTHS = opt.months || null
  const view = { k: 1, tx: 0, ty: 0, fit: 1, bb: null }
  let groot = null
  const VB = { w: 900, h: 620 }, H_MIN = 420, H_MAX = 680, K_MIN = 0.25, K_MAX = 14
  let paintedW = 0
  // 异步数据缓存（真实接口）
  const CACHE = { ent: {}, evi: {}, evt: {} }
  const PEND = { ent: {}, evi: {}, evt: {} }

  host.innerHTML =
    (MODES ?
      '<div class="gtop gtop--mode">' +
        '<div class="gbar" role="group" aria-label="数据集">' +
          '<span class="label">数据集</span><div class="seg" data-g="modes"></div>' +
          '<span class="label" data-g="modenote"></span>' +
        '</div>' +
      '</div>' : '') +
    '<div class="gtop">' +
      '<div class="gbar" data-g="filters" role="group" aria-label="按实体类型筛选节点"></div>' +
      '<div class="gbar">' +
        '<div class="seg" data-g="depth" role="group" aria-label="图谱深度"></div>' +
        '<button class="gchip gchip--icon" type="button" data-g="zout" aria-label="缩小">−</button>' +
        '<button class="gchip gchip--icon" type="button" data-g="zin" aria-label="放大">+</button>' +
        '<button class="chip" type="button" data-g="fit">适应窗口</button>' +
        '<button class="chip" type="button" data-g="reset">重置</button>' +
        '<span class="label" data-g="hint">点击节点或边查看属性</span>' +
      '</div>' +
    '</div>' +
    '<div class="glegendBar" data-g="legend"></div>' +
    '<div class="gwrap">' +
      '<div class="gcanvasWrap">' +
        '<svg data-g="svg" viewBox="0 0 ' + VB.w + ' ' + VB.h + '" preserveAspectRatio="none" role="img" aria-label="事件知识图谱：节点与有向关系边"></svg>' +
        '<div class="gstatus">' +
          '<span class="gstatus__i gstatus__i--key" data-g="check">遮挡自检：—</span>' +
          '<span class="gstatus__i" data-g="zoominfo">缩放 ×1.000</span>' +
          '<span class="gstatus__i" data-g="vbinfo">内容包围盒 —</span>' +
          '<span class="gstatus__i">拖节点微调布局 · 拖空白平移 · 滚轮以光标为锚点缩放</span>' +
        '</div>' +
      '</div>' +
      '<aside class="gpanel" aria-live="polite">' +
        '<div class="gpanel__head"><span class="label">属性面板</span><span class="label" data-g="ptype">未选中</span></div>' +
        '<div class="gpanel__body" data-g="pbody"></div>' +
      '</aside>' +
    '</div>' +
    '<section class="gev" data-g="ev"></section>' +
    '<div class="gwrap gwrap--lists">' +
      '<section class="card" style="padding:18px 18px 14px">' +
        '<div class="evgroup__head" style="margin-bottom:12px"><span class="label">路径列表 · 起 → 关系 → 终</span>' +
          '<span class="evgroup__n" data-g="pcount"></span></div>' +
        '<div class="gpaths" data-g="paths"></div>' +
      '</section>' +
      '<section class="card" style="padding:18px 18px 14px">' +
        '<div class="evgroup__head" style="margin-bottom:12px"><span class="label">孤立节点</span>' +
          '<span class="evgroup__n" data-g="icount"></span></div>' +
        '<div class="giso" data-g="iso"></div>' +
      '</section>' +
    '</div>' +
    '<div data-g="acc"></div>' +
    '<p class="gnote gnote--wide" data-g="note"></p>'

  const q = (k) => host.querySelector('[data-g="' + k + '"]')
  const $$ = (s, r) => Array.prototype.slice.call((r || host).querySelectorAll(s))
  const svg = q('svg'), legend = q('legend'), filters = q('filters'), depthBox = q('depth'),
    pbody = q('pbody'), ptype = q('ptype'), pathsBox = q('paths'), pcount = q('pcount'),
    isoBox = q('iso'), icount = q('icount'), hint = q('hint'), zoominfo = q('zoominfo'),
    checkEl = q('check'), evBox = q('ev'), accBox = q('acc'), noteBox = q('note'),
    modesBox = q('modes'), vbinfo = q('vbinfo'), cwrap = svg ? svg.parentNode : null

  // —— 并行边分叉（措施④） ——
  function buildEdgeOffsets() {
    const g = {}
    DS.edges.forEach((e) => {
      const k = (e.f < e.t ? e.f + '|' + e.t : e.t + '|' + e.f)
      ;(g[k] = g[k] || []).push(e)
    })
    Object.keys(g).forEach((k) => {
      const arr = g[k], total = arr.length, canon = k.split('|')[0]
      arr.sort((a, b) => {
        const ka = String(a.schunk || ''), kb = String(b.schunk || '')
        return (ka < kb ? -1 : (ka > kb ? 1 : 0)) || (a.f < b.f ? -1 : (a.f > b.f ? 1 : 0)) || (a.i - b.i)
      })
      arr.forEach((e, idx) => { e.canonFrom = canon; e.clat = (idx - (total - 1) / 2) * 24 })
    })
  }

  function edgeGeom(e) {
    const a = DS.idx[e.f], b = DS.idx[e.t]
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / d, uy = dy / d
    const x1 = a.x + ux * (a.r + 3), y1 = a.y + uy * (a.r + 3)
    const x2 = b.x - ux * (b.r + 10), y2 = b.y - uy * (b.r + 10)
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
    const off = (e.clat || 0) * (e.f === e.canonFrom ? 1 : -1)
    const cx = mx - uy * off * 2, cy = my + ux * off * 2
    const lx = mx - uy * off, ly = my + ux * off
    return { x1, y1, x2, y2, lx, ly, d: 'M' + x1.toFixed(1) + ',' + y1.toFixed(1) + ' Q' + cx.toFixed(1) + ',' + cy.toFixed(1) + ' ' + x2.toFixed(1) + ',' + y2.toFixed(1) }
  }

  function paintLegend() {
    if (!legend) return
    legend.innerHTML = '<span class="label glegendBar__t">图例 · 7 类节点</span>' +
      '<div class="glg glg--row">' +
      TKEYS.map((k) => {
        const n = DS.nodes.filter((x) => x.type === k).length
        return '<span class="glg__i" data-zero="' + (n ? 0 : 1) + '">' +
          '<svg viewBox="-11 -11 22 22" aria-hidden="true">' + shapeSVG(k, 7, 0.35) + '</svg>' +
          '<b>' + TYPE[k].n + '</b><em>' + (n ? n + ' 个' : '0 · 本次无') + '</em></span>'
      }).join('') + '</div>' +
      '<button class="chip chip--mini" type="button" data-g="ruletog" aria-expanded="false">编码规则</button>' +
      '<div class="glg__rule" data-g="rule" hidden>' +
        '<b>形状＋颜色</b> ＝ 实体类型；<b>' + RULE_R + '</b>；<br>' +
        '<b>箭头</b> ＝ 关系方向；<b>边上的文字只在悬停／选中该边时出现</b>，内容为「中文关系名 ＋ 置信度」；<br>' +
        '<b>线宽</b> ＝ 1.0 + confidence×1.6，<b>不透明度</b> ＝ .55 + confidence×.45；' +
        '<b>虚线</b> ＝ confidence 为空（属性面板显示「' + EMPTY + '」）；<br>' +
        '<b>曲率</b> ＝ 同一对节点间存在多条关系时按贝塞尔偏移分叉；<b>压暗</b> ＝ 被类型筛选／深度／时间区间排除在外，数据未删。' +
      '</div>'
  }

  function paintModes() {
    if (!modesBox) return
    modesBox.innerHTML = MODES.map((m) => {
      return '<button class="seg__b" type="button" data-mode="' + m.key + '" aria-pressed="' + (DS.mode === m.key ? 'true' : 'false') + '">' +
        m.label + ' <em>' + m.ds.nodes.length + ' · ' + m.ds.edges.length + '</em></button>'
    }).join('')
    const mn = q('modenote')
    if (mn) { const cur = MODES.filter((m) => m.key === DS.mode)[0]; mn.textContent = cur ? cur.note : '' }
  }

  function paintFilters() {
    if (!filters) return
    filters.innerHTML = TKEYS.map((k) => {
      const n = DS.nodes.filter((x) => x.type === k).length
      return '<button class="chip chip--f" type="button" role="checkbox" aria-checked="true" data-ftype="' + k + '"' +
        (n ? '' : ' disabled') + ' title="' + TYPE[k].n + '（本数据集 ' + n + ' 个节点）">' +
        '<span class="bx" aria-hidden="true"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M1.6 5.2 3.9 7.5 8.4 2.6"/></svg></span>' +
        '<svg width="13" height="13" viewBox="-11 -11 22 22" aria-hidden="true">' + shapeSVG(k, 7, 0.3) + '</svg>' +
        TYPE[k].n + '<em class="chip__n">' + n + '</em></button>'
    }).join('')
    $$('[data-ftype]', filters).forEach((b) => { b.setAttribute('aria-checked', S.hidden[b.getAttribute('data-ftype')] ? 'false' : 'true') })
  }

  function paintDepth() {
    if (!depthBox) return
    depthBox.innerHTML = [2, 1].map((d) => {
      return '<button class="seg__b" type="button" data-depth="' + d + '" aria-pressed="' + (d === S.depth ? 'true' : 'false') + '">' +
        d + ' 跳' + (d === 2 ? ' · 默认' : ' · 近邻') + '</button>'
    }).join('')
  }

  function liveBB() {
    const on = DS.nodes.filter((n) => n.on)
    if (!on.length) return null
    let bb = null
    on.forEach((n) => {
      const r = lrect(n, n.x, n.y)
      const x0 = Math.min(n.x - n.r, r.x), x1 = Math.max(n.x + n.r, r.x + r.w)
      const y0 = Math.min(n.y - n.r, r.y), y1 = Math.max(n.y + n.r, r.y + r.h)
      if (!bb) bb = { x0, y0, x1, y1 }
      else { bb.x0 = Math.min(bb.x0, x0); bb.y0 = Math.min(bb.y0, y0); bb.x1 = Math.max(bb.x1, x1); bb.y1 = Math.max(bb.y1, y1) }
    })
    return { x: bb.x0, y: bb.y0, w: bb.x1 - bb.x0, h: bb.y1 - bb.y0 }
  }
  function measureCanvas(bb) {
    const W = (cwrap && cwrap.clientWidth) || 0
    if (!W) { VB.w = 900; VB.h = 620 }
    else {
      VB.w = W
      const nat = bb ? W * (bb.h / bb.w) : 0
      VB.h = Math.round(Math.max(H_MIN, Math.min(H_MAX, nat || H_MIN)))
    }
    svg.setAttribute('viewBox', '0 0 ' + VB.w + ' ' + VB.h)
    svg.setAttribute('preserveAspectRatio', 'none')
    svg.style.height = VB.h + 'px'
    paintedW = VB.w
  }
  function applyView() {
    if (groot) groot.setAttribute('transform', 'translate(' + view.tx.toFixed(1) + ',' + view.ty.toFixed(1) + ') scale(' + view.k.toFixed(3) + ')')
    if (zoominfo) zoominfo.textContent = '缩放 ×' + view.k.toFixed(3)
    if (vbinfo) {
      const b = view.bb
      vbinfo.innerHTML = b
        ? '内容包围盒 <b>' + b.w.toFixed(1) + ' × ' + b.h.toFixed(1) + '</b> · 适配比 <b>' + view.fit.toFixed(3) + '</b> · 实际 <b>' + Math.round(view.k / view.fit * 100) + '%</b> · 画布 <b>' + VB.w + ' × ' + VB.h + '</b>'
        : '内容包围盒 <b>—</b> · 画布 <b>' + VB.w + ' × ' + VB.h + '</b>'
    }
  }
  function fitView() {
    const bb = liveBB()
    measureCanvas(bb)
    if (!bb || !bb.w) { view.k = 1; view.tx = 0; view.ty = 0; view.fit = 1; view.bb = null; applyView(); return }
    let s = Math.min(VB.w * (1 - 2 * SAFE) / bb.w, VB.h * (1 - 2 * SAFE) / bb.h)
    s = Math.max(K_MIN, Math.min(K_MAX, s))
    view.k = s; view.fit = s; view.bb = bb
    view.tx = VB.w / 2 - (bb.x + bb.w / 2) * s
    view.ty = VB.h / 2 - (bb.y + bb.h / 2) * s
    applyView()
  }
  function onCanvasResize() {
    const W = (cwrap && cwrap.clientWidth) || 0
    if (!W) return
    if (Math.abs(W - paintedW) < 0.5) return
    fitView()
  }
  if (cwrap) {
    if (window.ResizeObserver) { try { new ResizeObserver(onCanvasResize).observe(cwrap) } catch (e) { /* noop */ } }
    else window.addEventListener('resize', onCanvasResize)
  }
  function refit() { refresh(); fitView() }

  function paint() {
    let out = '<defs>' +
      '<marker id="' + mk + 'a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.4" markerHeight="5.4" orient="auto-start-reverse"><path d="M0,1.3 L9,5 L0,8.7 Z" fill="rgba(255,255,255,.46)"/></marker>' +
      '<marker id="' + mk + 'h" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.4" markerHeight="5.4" orient="auto-start-reverse"><path d="M0,1.3 L9,5 L0,8.7 Z" fill="#E63946"/></marker>' +
      '</defs><g class="groot">'
    DS.edges.forEach((e) => {
      const a = DS.idx[e.f], b = DS.idx[e.t], g = edgeGeom(e)
      const sw = (e.conf === null || e.conf === undefined) ? 1 : (1 + e.conf * 1.6)
      const op = (e.conf === null || e.conf === undefined) ? 0.55 : (0.55 + e.conf * 0.45)
      const dash = (e.conf === null || e.conf === undefined) ? ' stroke-dasharray="4 3"' : ''
      const confTxt = (e.conf === null || e.conf === undefined) ? EMPTY : e.conf
      out += '<g class="geline" data-edge="' + e.i + '" tabindex="0" role="button" aria-label="' +
        a.label + ' 到 ' + b.label + '，关系' + RELNAME(e.rel) + '（' + e.rel + '）">' +
        '<path class="gehit" d="' + g.d + '"/>' +
        '<path class="gedge" d="' + g.d + '" stroke="rgba(255,255,255,.55)" stroke-width="' + sw.toFixed(2) +
        '" stroke-opacity="' + op.toFixed(2) + '"' + dash + ' marker-end="url(#' + mk + 'a)"/>' +
        '<text class="gelabel" x="' + g.lx.toFixed(1) + '" y="' + g.ly.toFixed(1) + '" text-anchor="middle">' +
        RELNAME(e.rel) + ' · ' + confTxt + '</text>' +
        '</g>'
    })
    DS.nodes.forEach((n) => {
      if (n.deg === 0) return  // 孤立节点只在下方列表渲染（避免「看得见点不到」的幽灵元素）
      out += '<g class="gnode" data-node="' + n.id + '" tabindex="0" role="button" transform="translate(' +
        n.x.toFixed(1) + ',' + n.y.toFixed(1) + ')" ' +
        'aria-label="' + TYPE[n.type].n + '节点 ' + n.label + '，连接数 ' + n.deg + '">' +
        '<title>' + n.label + ' · ' + TYPE[n.type].n + ' · 连接数 ' + n.deg + '</title>' +
        '<circle class="ghit" r="' + (n.r + 12) + '"/>' +
        '<circle class="halo" r="' + (n.r + 7) + '"/>' + shapeSVG(n.type, n.r) +
        '<text class="glabel" y="' + (n.r + 16) + '" data-lbl="' + n.id + '">' + n.lbl + '</text>' +
        (n.sub ? '<text class="code" y="' + (n.r + 28) + '">' + n.sub + '</text>' : '') +
        '</g>'
    })
    svg.innerHTML = out + '</g>'
    groot = svg.querySelector('.groot')
    DS.nodes.forEach((n) => {
      if (n.deg === 0) { n.el = null; n.lel = null; return }
      n.el = svg.querySelector('[data-node="' + n.id + '"]')
      n.lel = svg.querySelector('[data-lbl="' + n.id + '"]')
    })
    DS.edges.forEach((e) => { e.el = svg.querySelector('[data-edge="' + e.i + '"]') })
    applyView()
  }

  function pathLabel(p) {
    const s = []
    for (let k = 0; k < p.e.length; k++) {
      const e = DS.edges[p.e[k]]
      if (k === 0) s.push(DS.idx[e.f].label)
      s.push(RELNAME(e.rel)); s.push(DS.idx[e.t].label)
    }
    return s.join(' → ')
  }

  function inTimeRange(n) {
    if (!MONTHS) return true
    return n.ti === null || n.ti === undefined || (n.ti >= S.i0 && n.ti <= S.i1)
  }

  function refresh() {
    const adj = {}, hotE = {}
    if (S.sel) DS.edges.forEach((e) => { if (e.f === S.sel.id || e.t === S.sel.id) { adj[e.f] = 1; adj[e.t] = 1; hotE[e.i] = 1 } })
    if (S.edge !== null && DS.edges[S.edge]) { const se = DS.edges[S.edge]; adj[se.f] = 1; adj[se.t] = 1; hotE[se.i] = 1 }
    if (S.path) S.path.e.forEach((i2) => { hotE[i2] = 1; adj[DS.edges[i2].f] = 1; adj[DS.edges[i2].t] = 1 })
    const hasHot = !!(S.sel || S.path || (S.edge !== null))
    DS.nodes.forEach((n) => {
      const on = (!S.hidden[n.type]) && (n.dist <= S.depth) && inTimeRange(n)
      n.on = on
      if (!n.el) return
      n.el.classList.toggle('sel', !!(S.sel && S.sel.id === n.id))
      if (n.deg === 0) {
        n.el.classList.remove('dim'); n.el.classList.remove('out')
        n.el.style.pointerEvents = ''; n.el.setAttribute('aria-hidden', 'false')
        return
      }
      n.el.classList.toggle('dim', on && hasHot && adj[n.id] !== 1)
      n.el.classList.toggle('out', !on)
      n.el.style.pointerEvents = on ? '' : 'none'
      n.el.setAttribute('aria-hidden', on ? 'false' : 'true')
    })
    DS.edges.forEach((e) => {
      const on = DS.idx[e.f].on && DS.idx[e.t].on, hot = on && hotE[e.i] === 1
      e.on = on
      if (!e.el) return
      const ln = e.el.querySelector('.gedge')
      ln.classList.toggle('hot', !!hot)
      ln.setAttribute('marker-end', 'url(#' + (hot ? mk + 'h' : mk + 'a') + ')')
      e.el.classList.toggle('sel', S.edge === e.i)
      e.el.classList.toggle('dim', on && hasHot && !hot)
      e.el.classList.toggle('out', !on)
      e.el.querySelector('.gelabel').classList.toggle('on', !!hot || S.edge === e.i)
      e.el.style.pointerEvents = on ? '' : 'none'
    })
    const lp = planLabels(DS, S), sc = selfCheck(DS)
    if (checkEl) checkEl.innerHTML = '遮挡自检：节点重叠 <b>' + sc.node + '</b> ／ 标签重叠 <b>' + sc.label +
      '</b> · 可见标签 <b>' + sc.shown + '</b>/' + sc.total +
      (lp.hidden > 0 ? ' · 已隐藏 <b>' + lp.hidden + '</b> 个标签（悬停查看）' : '')
    if (hint) hint.textContent = S.sel ? ('已选中 ' + S.sel.label)
      : (S.path ? ('已选中路径 ' + pathLabel(S.path)) : '点击节点或边查看属性')
    renderPaths(); renderIso(); panel(); renderEvidence()
  }

  function renderPaths() {
    if (!pathsBox) return
    const PL = DS.paths
    const shown = PL.filter((p) => p.d <= S.depth)
    const live = shown.filter((p) => p.e.every((i) => DS.edges[i] && DS.edges[i].on && DS.idx[DS.edges[i].f].on && DS.idx[DS.edges[i].t].on))
    if (pcount) pcount.textContent = '显示 ' + live.length + ' / 可枚举 ' + PL.length + ' 条'
    let out = live.map((p) => {
      const e0 = DS.edges[p.e[0]]
      return '<button class="gpath' + (S.path === p ? ' on' : '') + '" type="button" data-pi="' + PL.indexOf(p) + '" ' +
        'aria-pressed="' + (S.path === p ? 'true' : 'false') + '">' +
        '<span class="gpath__l">' + p.e.map((i, k) => {
          const e = DS.edges[i]
          return (k === 0 ? '<i style="background:' + TYPE[DS.idx[e.f].type].c + '"></i>' + DS.idx[e.f].label : '') +
            '<span class="gpath__rel">—[' + RELNAME(e.rel) + ']→</span>' +
            '<i style="background:' + TYPE[DS.idx[e.t].type].c + '"></i>' + DS.idx[e.t].label
        }).join('') + '</span>' +
        '<span class="gpath__d">' + p.d + ' 跳</span>' +
        '<span class="gpath__a">首条关系 ' + e0.rel + ' · role=' + (e0.role || NOEV) + ' · confidence=' + (e0.conf === null || e0.conf === undefined ? EMPTY : e0.conf) +
        ' · source_doc_id=' + (e0.sdoc || NOEV) + ' · source_chunk_id=' + (e0.schunk || NOEV) + '</span></button>'
    }).join('')
    if (shown.length - live.length) out += '<p class="gpath__flt">另有 ' + (shown.length - live.length) + ' 条路径因类型筛选、深度或时间区间被过滤，暂不显示（未被删除，重置后回来）。</p>'
    if (!live.length) out = '<p class="gpath__flt">当前筛选条件下没有可用路径。放宽类型、深度或时间区间即可恢复。</p>' + out
    pathsBox.innerHTML = out
  }

  function renderIso() {
    if (!isoBox) return
    const iso = DS.nodes.filter((n) => n.deg === 0)
    if (icount) icount.textContent = iso.length + ' 个 · 连接数 0'
    isoBox.innerHTML = iso.length ? iso.map((n) => {
      const sel = !!(S.sel && S.sel.id === n.id)
      return '<button class="giso__i' + (sel ? ' is-sel' : '') + '" type="button" ' +
        'data-iso="' + n.id + '" aria-pressed="' + (sel ? 'true' : 'false') + '" ' +
        'aria-label="孤立节点 ' + n.label + ' · ' + TYPE[n.type].n + '，点选查看属性">' +
        '<svg class="giso__g" viewBox="-11 -11 22 22" aria-hidden="true">' +
          '<g class="gnode" data-node="' + n.id + '">' +
            '<circle class="ghit" r="10"/><circle class="halo" r="8.6"/>' + shapeSVG(n.type, 7, 0.3) +
          '</g>' +
        '</svg>' +
        '<span><span class="giso__n">' + n.label + (n.sub ? ' · ' + n.sub : '') + ' · ' + TYPE[n.type].n + '</span>' +
        '<span class="giso__d">该节点在本次返回的图谱路径中未出现邻接边。事件时间 ' + (n.time ? n.time : EMPTY) + '。</span></span></button>'
    }).join('') : '<div class="giso__d">本数据集里没有孤立节点。</div>'
    iso.forEach((n) => { n.el = isoBox.querySelector('.gnode[data-node="' + n.id + '"]'); n.lel = null })
  }

  // —— 异步真实接口加载 ——
  function apiOf(n) { return CACHE.ent[n.eid || n.id] || null }
  function ensureEntity(n) {
    const id = n.eid || n.id
    if (CACHE.ent[id] || PEND.ent[id] || !provider.entity) return
    PEND.ent[id] = true
    provider.entity(id).then((d) => { CACHE.ent[id] = d || { __empty: true } })
      .catch((e) => { CACHE.ent[id] = { __error: e && e.message || String(e) } })
      .then(() => { PEND.ent[id] = false; if (S.sel && (S.sel.eid || S.sel.id) === id) panel() })
  }
  function ensureEvidence(n) {
    const id = n.eid || n.id, key = id + '#' + S.depth
    if (CACHE.evi[key] || PEND.evi[key] || !provider.evidence) return
    PEND.evi[key] = true
    provider.evidence(id, S.depth).then((d) => { CACHE.evi[key] = d || { __empty: true } })
      .catch((e) => { CACHE.evi[key] = { __error: e && e.message || String(e) } })
      .then(() => { PEND.evi[key] = false; if (S.sel && (S.sel.eid || S.sel.id) === id) renderEvidence() })
  }
  function ensureEvent(n) {
    const id = n.eid || n.id
    if (CACHE.evt[id] || PEND.evt[id] || !provider.event) return
    PEND.evt[id] = true
    provider.event(id).then((d) => { CACHE.evt[id] = d || { __empty: true } })
      .catch((e) => { CACHE.evt[id] = { __error: e && e.message || String(e) } })
      .then(() => { PEND.evt[id] = false; if (S.sel && (S.sel.eid || S.sel.id) === id) renderEvidence() })
  }

  function propOrder(n, e) {
    const hot = EAPI_HOT[n.type] || [], seen = {}, out = []
    const keys = e.property_keys || Object.keys(e.properties || {})
    for (let i = 0; i < hot.length; i++) if (e.properties && e.properties[hot[i]] !== undefined) { out.push([hot[i], e.properties[hot[i]]]); seen[hot[i]] = 1 }
    keys.forEach((k) => { if (!seen[k]) out.push([k, (e.properties || {})[k]]) })
    return out
  }
  function propVal(k, v) {
    if (v === null || v === undefined || v === '' || v === EMPTY)
      return '<span class="gvp gvp--empty">' + EMPTY + '</span>' +
        '<span class="gsrc" style="display:block;margin-top:3px">本节点该属性在本次记录中为空</span>'
    const c = EAPI_LONG[k] ? (k === 'url' ? 'gvp gvp--url' : 'gvp gvp--long') : 'gvp'
    const txt = String(v)
    const html = (k === 'url' || /^https?:\/\//.test(txt))
      ? '<a class="gvp gvp--url" href="' + txt + '" target="_blank" rel="noopener">' + txt + '</a>'
      : '<span class="' + c + '">' + txt + '</span>'
    return html
  }

  function panelNode(n) {
    ptype.textContent = TYPE[n.type].n
    const EID = n.eid || n.id
    const nb = []
    let out = 0, inc = 0
    DS.edges.forEach((e) => {
      if (e.f === n.id) { nb.push({ dir: '出', rel: e.rel, to: DS.idx[e.t] }); out++ }
      else if (e.t === n.id) { nb.push({ dir: '入', rel: e.rel, to: DS.idx[e.f] }); inc++ }
    })
    const e = apiOf(n)
    const loaded = e && !e.__empty && !e.__error
    const rows = loaded ? propOrder(n, e) : []
    const cnts = loaded ? e.counts : null
    const cnt = (k, v) => {
      const empty = (v === null || v === undefined)
      return '<div><dt>' + k + '</dt><dd' + (empty ? ' class="is-empty"' : '') + '>' + (empty ? EMPTY : v) + '</dd></div>'
    }
    let entBlock
    if (!e) {
      entBlock = provider.entity
        ? '<p class="gvp--none">正在请求实体详情接口 <b>GET /api/graph/entities/' + EID + '</b> …</p>'
        : '<p class="gvp--none">回看还原模式：本图按<b>当时记录的路径载荷</b>绘制，<b>不重新查询图谱</b>，故此处不提供实体档案。如需实体详情与证据，请到屏③「事件知识图谱」按节点查询。</p>'
    } else if (e.__empty) {
      entBlock = '<p class="gvp--none">实体详情接口未返回内容（该实体在后端不存在或为空）。</p>'
    } else if (e.__error) {
      entBlock = '<p class="gvp--none">实体详情接口请求失败：' + e.__error + '</p>'
    } else {
      entBlock = (rows.length
        ? '<dl class="gkv">' + rows.map((r) => '<div class="kv"><dt>' + r[0] + (EAPI_LABEL[r[0]] ? '<span>' + EAPI_LABEL[r[0]] + '</span>' : '') + '</dt><dd>' + propVal(r[0], r[1]) + '</dd></div>').join('') + '</dl>'
        : '<p class="gvp--none">' + TYPE[n.type].n + ' 类实体的属性键名以实体详情接口实返为准；本次接口未返回可显示的属性键，本原型不推测键名。下方「本视图关系」不受影响。</p>') +
        '<p class="gsrc" style="margin-top:10px">属性来源：实体详情接口 <b>GET /api/graph/entities/' + EID + '</b> 的实测返回。属性值原样取自图谱，未派生；键序＝该实体的 property_keys。</p>' +
        ((n.type === 'person' || n.type === 'org' || n.type === 'policy') && rows.length
          ? '<p class="gsrc" style="margin-top:4px">本类实体在图谱中仅存 <b>' + rows.length + ' 个自有属性</b>；其' + TYPE[n.type].n + '信息主要体现在<b>关系与证据</b>中（见下方「本视图关系」与「实体证据」区）。</p>'
          : '') +
        '<div class="gblkH" style="margin:14px 0 0;padding-top:13px;border-top:1px solid var(--border)"><span class="label">接口 degree · 全图度数</span><span class="gsrc">GET /api/graph/entities/' + EID + '</span></div>' +
        '<dl class="gkv"><div class="kv"><dt>入 / 出 / 度<span>接口按全图统计</span></dt><dd class="mono">' + e.degree.in_ + ' / ' + e.degree.out + ' / ' + e.degree.total + '</dd></div></dl>' +
        '<p class="gsrc" style="margin-top:9px">这是该实体在<b>全图</b>里的度数；下方「本视图关系」的度是<b>当前数据集画布局部</b>的度数。两块口径不同，各自标注、不相互换算。</p>' +
        '<div class="gblkH" style="margin:14px 0 0;padding-top:13px;border-top:1px solid var(--border)"><span class="label">实体证据计数</span></div>' +
        '<dl class="gcount">' + cnt('邻居', cnts ? cnts.neighbors : null) + cnt('关系', cnts ? cnts.relations : null) + cnt('涉及文档', cnts ? cnts.documents : null) + cnt('不同文本块', cnts ? cnts.chunks : null) + '</dl>' +
        '<p class="gsrc" style="margin-top:9px">计数来源：实体详情接口 <b>GET /api/graph/entities/' + EID + '</b>（与下方「实体证据」区 ① 同源）。</p>'
    }
    pbody.innerHTML =
      '<div class="gsel"><i style="background:' + TYPE[n.type].c + '"></i>' +
        '<b>已选中 · ' + n.label + '</b><em>' + TYPE[n.type].n + ' · ' + EID + '</em>' +
        '<button class="gchip" type="button" data-g="unselect" title="取消选中（也可以按 Esc，或点画布空白处）">取消选中</button>' +
      '</div>' +
      '<section class="gblk gblk--first">' +
        '<div class="gblkH"><span class="label">实体档案 · Entity profile</span></div>' + entBlock +
      '</section>' +
      '<section class="gblk">' +
        '<div class="gblkH"><span class="label">本视图关系 · In this view</span><span class="gsrc">画布局部 · 当前数据集</span></div>' +
        '<dl class="gkv">' +
          '<div class="kv"><dt>度<span>本数据集</span></dt><dd class="mono">' + n.deg + '（出 ' + out + ' / 入 ' + inc + '）</dd></div>' +
          '<div class="kv"><dt>距中心<span>到分量中心</span></dt><dd class="mono">' +
            (n.dist > 90 ? EMPTY + '（在本次边集里不可达）' : n.dist + ' 跳' + (n.isCenter ? '（所在分量的中心实体）' : '') + (n.dist > S.depth ? ' · 超出当前 ' + S.depth + ' 跳视图，已压暗' : '')) +
          '</dd></div>' +
        '</dl>' +
        '<div class="gblkH" style="margin:13px 0 0"><span class="label">邻接关系 · ' + nb.length + ' 条</span></div>' +
        '<div class="grel">' + (nb.length ? nb.map((x) => '<div class="grel__i"><i style="background:' + TYPE[x.to.type].c + '"></i>' +
          '<span class="gpath__rel">' + x.dir + ' · ' + RELNAME(x.rel) + '</span> ' + x.to.label + '<em>' + TYPE[x.to.type].n + '</em></div>').join('')
          : '<div class="grel--none">该节点在本次返回的图谱路径中未出现邻接边。</div>') + '</div>' +
      '</section>'
    ensureEntity(n)
  }

  function panelEdge(e) {
    ptype.textContent = '关系边'
    const noev = !!e.noev
    const val = (v) => (v === null || v === undefined || v === EMPTY)
      ? '<span style="color:rgba(255,255,255,.62)">' + (noev ? NOEV : EMPTY) + '</span>' : v
    pbody.innerHTML =
      '<div class="gsel"><i style="background:' + TYPE[DS.idx[e.f].type].c + '"></i>' +
        '<b>已选中 · ' + DS.idx[e.f].label + ' → ' + DS.idx[e.t].label + '</b><em>边 #' + e.i + '</em>' +
        '<button class="gchip" type="button" data-g="unselect" title="取消选中（也可以按 Esc，或点画布空白处）">取消选中</button>' +
      '</div>' +
      '<div><span class="label">关系</span><div class="h4" style="margin-top:6px">' + e.rel + ' · ' + RELNAME(e.rel) + '</div>' +
        '<span class="tag" style="margin-top:9px">' + (e.src || '') + '</span>' +
        (e.clat ? '<span class="tag tag--muted" style="margin-top:9px;margin-left:6px">并行边 · 曲率分叉</span>' : '') + '</div>' +
      '<dl style="display:flex;flex-direction:column;gap:12px;margin:0">' +
        '<div class="kv"><dt>起点</dt><dd>' + DS.idx[e.f].label + '</dd></div>' +
        '<div class="kv"><dt>终点</dt><dd>' + DS.idx[e.t].label + '</dd></div>' +
        '<div class="kv"><dt>role</dt><dd class="mono">' + val(e.role) + '</dd></div>' +
        '<div class="kv"><dt>confidence</dt><dd class="mono">' + val(e.conf) + '</dd></div>' +
        '<div class="kv"><dt>source_doc_id</dt><dd class="mono">' + val(e.sdoc) + '</dd></div>' +
        '<div class="kv"><dt>source_chunk_id</dt><dd class="mono">' + val(e.schunk) + '</dd></div>' +
      '</dl>' +
      '<p class="gnote" style="font-size:11px">' + (noev
        ? '该关系类型（<i>' + e.rel + '</i>）不带证据属性，四项证据字段按作者口径一律显示「' + NOEV + '」。'
        : '线宽与不透明度由 confidence 编码：' + (e.conf === null || e.conf === undefined
          ? '本次为空 → 虚线、线宽 1.0、不透明度 .55。'
          : 'confidence ' + e.conf + ' → 线宽 ' + (1 + e.conf * 1.6).toFixed(2) + '、不透明度 ' + (0.55 + e.conf * 0.45).toFixed(2) + '。')) +
      '</p>' +
      '<div style="margin-top:auto;padding-top:14px;border-top:1px solid var(--border)">' +
        '<button class="btn btn--quiet btn--sm" type="button" data-g="jump" ' + (e.schunk ? '' : 'disabled') + '>' +
          (e.schunk ? '跳到对应证据' : '该边不带 source_chunk_id') + '</button>' +
        '<p class="gnote" style="font-size:10.5px;margin-top:9px">按 source_chunk_id ' + (e.schunk || '（无）') + ' 在证据清单里定位并高亮那一条。</p>' +
      '</div>'
  }

  function panel() {
    if (!pbody) return
    if (S.edge !== null) { panelEdge(DS.edges[S.edge]); return }
    if (S.sel) { panelNode(S.sel); return }
    const vis = DS.nodes.filter((n) => n.on).length
    ptype.textContent = '未选中'
    pbody.innerHTML = '<div class="gempty"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#bull"></use></svg>' +
      '<p>未选中任何实体<br>点节点或边查看属性；当前视图共 <b>' + vis + '</b> 个节点</p>' +
      '<p class="gsrc" style="max-width:24ch">单击已选中的节点<b>不会</b>取消选中；取消请按 Esc、点画布空白，或用面板上的「取消选中」。</p>' +
      (DS.nodes.length ? '' : '<p class="gsrc" style="max-width:24ch">本数据集暂无可选节点。</p>') +
      '</div>'
  }

  // —— 实体证据区（四块，全部取自真实 /evidence 接口） ——
  function docMap(ev) {
    const m = {}
    ;(ev && ev.documents || []).forEach((d) => { m[String(d.doc_id)] = d })
    return m
  }
  function relRow(rel, peerLabel, docId, chunkId, conf, role, docUrl, docTitle) {
    const noev = rel === 'EVIDENCED_BY'
    const td = (v) => noev ? '' : '<td class="mono">' + ((v === null || v === undefined || v === '') ? '<span class="gev__gap">' + EMPTY + '</span>' : v) + '</td>'
    const link = docUrl
      ? '<a class="ev__link ev__link--sm" href="' + docUrl + '" target="_blank" rel="noopener" aria-label="查看原文：' + (docTitle || '') + '（新窗口打开）">' + EXT + '查看原文 ↗</a>'
      : '<span class="ev__nolink ev__nolink--sm">记录未给出</span>'
    return '<tr>' +
      '<td class="k"><b>' + RELNAME(rel) + '</b><em>' + rel + '</em></td>' +
      '<td><i class="gdot" style="background:' + '#8792A8' + '"></i>' + peerLabel + '</td>' +
      (noev ? '<td colspan="4" class="gev__gap">' + NOEV + '</td>'
        : td(role) + td(conf) + td(docId) + td(chunkId)) +
      '<td class="gev__acts">' + (noev ? '<span class="gev__gap">—</span>'
        : link + ' <button class="gchip" type="button" data-ctx="' + docId + ':' + chunkId + '" aria-expanded="false">查看上下文</button>') +
      '</td></tr>'
  }
  function renderEvidence() {
    if (!evBox) return
    if (!S.sel) {
      evBox.innerHTML = '<div class="gev__head"><div><span class="label">实体证据 · Entity evidence</span>' +
        '<h3 class="h3">未选中实体</h3></div></div>' +
        '<p class="gnote">选中画布上任一节点，这里给出该实体的完整证据：① 计数概览 ② 关系证据表 ③ 文档聚合 ④ 事件实体额外四项。三块均取自真实接口 <i>GET /api/graph/entities/{id}/evidence</i>。</p>'
      return
    }
    const n = S.sel, EID = n.eid || n.id
    ensureEvidence(n)
    if (n.type === 'event') ensureEvent(n)
    const key = EID + '#' + S.depth, ev = CACHE.evi[key]
    const stat = (k, v) => '<div class="gstat"><span class="label">' + k + '</span><b>' +
      (v === null || v === undefined ? '<em class="gev__gap">—</em>' : v) + '</b></div>'
    let h = '<div class="gev__head"><div><span class="label">实体证据 · Entity evidence</span>' +
        '<h3 class="h3">' + n.label + ' <em class="gev__kind">' + TYPE[n.type].n + '</em></h3></div>' +
        '<span class="label">深度 ' + S.depth + ' 跳 · GET /api/graph/entities/' + EID + '/evidence?depth=' + S.depth + '</span></div>' +
      '<div class="gev__grid">'

    const c = (ev && !ev.__empty && !ev.__error) ? ev.counts : null
    h += '<section class="gev__blk"><div class="gev__blkH"><span class="label">① 计数概览</span>' +
      '<span class="label">' + (c ? '实体证据接口实测' : '未返回') + '</span></div>' +
      '<div class="gstat4">' + stat('邻居', c ? c.neighbors : null) + stat('关系', c ? c.relations : null) + stat('涉及文档', c ? c.documents : null) + stat('不同文本块', c ? c.chunks : null) + '</div>' +
      '<p class="gnote">' + (c ? '以上四项为实体证据接口对该实体的实测值，原样照抄。本页画布只展开本次返回中逐条给出的关系，二者口径不同，不相互换算。' : '该实体未随本次请求返回计数，如实留「—」，不推算、不填充。') + '</p></section>'

    // ② 关系证据表
    let rows = ''
    let rcount = 0
    if (ev && !ev.__empty && !ev.__error && ev.documents) {
      const dm = docMap(ev)
      ev.documents.forEach((d) => {
        ;(d.chunks || []).forEach((ck) => {
          ;(ck.relations || []).forEach((r) => {
            rcount++
            const peer = (DS.idx[r.neighbor] && DS.idx[r.neighbor].label) || r.neighbor
            rows += relRow(r.relation, peer, d.doc_id, ck.chunk_id, r.confidence, r.role, d.url, d.title)
          })
        })
      })
      ;(ev.relations_without_evidence || []).forEach((r) => {
        rcount++
        const peer = (DS.idx[r.neighbor] && DS.idx[r.neighbor].label) || r.neighbor
        rows += relRow(r.relation, peer, null, null, null, null)
      })
    }
    h += '<section class="gev__blk gev__blk--wide"><div class="gev__blkH"><span class="label">② 关系证据表</span><span class="label">' + rcount + ' 条</span></div>' +
      '<div class="gev__tblWrap"><table class="gev__tbl"><thead><tr>' +
        '<th>中文关系名</th><th>对端实体</th><th>role</th><th>confidence</th><th>source_doc_id</th><th>source_chunk_id</th><th>操作</th></tr></thead><tbody>' +
      (rows || '<tr><td colspan="7" class="gev__gap">' + (ev ? (ev.__error ? '实体证据接口请求失败：' + ev.__error : '该实体在本次返回里没有邻接关系。') : (provider.evidence ? '正在请求实体证据接口 …' : '回看还原模式不重新查询图谱：本载荷不含逐条实体证据。')) + '</td></tr>') +
      '</tbody></table></div>' +
      '<p class="gnote">「查看原文 ↗」按该文档接口返回的 url 直达外部原文（新窗口打开，记录未给出 url 时显示「记录未给出」，不猜链接）；「查看上下文」＝展开该块的正文片段（真实接口 <i>GET /api/documents/{doc_id}/chunks/{chunk_id}</i> 的 <i>chunk_content</i> 与 <i>neighbor_chunks</i>）。不带证据属性的关系类型（如 <i>EVIDENCED_BY</i>）整行显示「' + NOEV + '」。</p></section>'

    // ③ 文档聚合
    const docs = (ev && ev.documents) || []
    h += '<section class="gev__blk gev__blk--wide"><div class="gev__blkH"><span class="label">③ 文档聚合 · 按文档看证据</span><span class="label">' + (ev && ev.documents_total != null ? ev.documents_total + ' 篇' : '—') + '</span></div>' +
      '<div class="gev__tblWrap"><table class="gev__tbl"><thead><tr><th>标题</th><th>来源站</th><th>发布日期</th><th>支撑的关系数</th><th>原文</th></tr></thead><tbody>' +
      (docs.length ? docs.map((d) => {
        const url = d.url ? '<a class="ev__link ev__link--sm" href="' + d.url + '" target="_blank" rel="noopener" aria-label="查看原文：' + (d.title || '') + '（新窗口打开）">' + EXT + '查看原文 ↗</a>' : '<span class="ev__nolink ev__nolink--sm">记录未给出 url</span>'
        return '<tr><td class="k"><b>' + (d.title || '—（本次记录未给出标题）') + '</b><em>doc_id ' + d.doc_id + '</em></td>' +
          '<td>' + (d.source ? ('<b>' + d.source + '</b>' + (DOMAIN[d.source] ? '<em class="ev__dom">' + DOMAIN[d.source] + '</em>' : '')) : '<span class="gev__gap">—（未给出）</span>') + '</td>' +
          '<td class="mono">' + (d.publish_time ? String(d.publish_time).slice(0, 10) : '<span class="gev__gap">—（未给出）</span>') + '</td>' +
          '<td class="mono">' + (d.support_relations != null ? d.support_relations + ' 条' : '<span class="gev__gap">—</span>') + '</td>' +
          '<td>' + url + '</td></tr>'
      }).join('') : '<tr><td colspan="5" class="gev__gap">本次返回里没有与该实体关联的文档。</td></tr>') +
      '</tbody></table></div>' +
      '<p class="gnote">文档编号按文档去重列出，同一文档的多个文本块只计一行。</p></section>'

    // ④ 事件实体额外四项（仅 Event 节点；取自 GET /api/graph/events/{event_id}）
    if (n.type === 'event') {
      const evd = CACHE.evt[EID]
      let body
      if (!evd) body = '<p class="gnote">正在请求事件详情接口 <i>GET /api/graph/events/' + EID + '</i> …</p>'
      else if (evd.__error) body = '<p class="gnote">事件详情接口请求失败：' + evd.__error + '</p>'
      else if (evd.__empty) body = '<p class="gnote">事件详情接口未返回内容。</p>'
      else {
        const parts = evd.participants || [], issuer = evd.issuer, policies = evd.policies || [], evs = evd.evidences || []
        const sorted = evs.slice().sort((a, b) => (String(a.publish_time || '') < String(b.publish_time || '') ? -1 : (String(a.publish_time || '') > String(b.publish_time || '') ? 1 : 0)))
        const seenDoc = {}, uniq = []
        sorted.forEach((s) => { if (!seenDoc[s.doc_id]) { seenDoc[s.doc_id] = 1; uniq.push(s) } })
        body = '<div class="gev__kv4">' +
          '<div><span class="label">参与者（含 role）</span><p>' + (parts.length ? parts.map((p) => '<b>' + (p.name || p.node_id) + '</b><em class="gev__role">role=' + (p.role || EMPTY) + '</em>').join('、') : '—') + '</p></div>' +
          '<div><span class="label">发布机构</span><p>' + (issuer ? '<b>' + (issuer.name || issuer.node_id) + '</b>' : '<span class="gev__gap">—（空）</span>') + '</p></div>' +
          '<div><span class="label">相关政策</span><p>' + (policies.length ? policies.map((x) => '<b>' + (x.name || x.node_id) + '</b>').join('、') : '<span class="gev__gap">—（空）</span>') + '</p></div>' +
          '<div><span class="label">多来源证据 · 按发布时间升序</span><p>原始 ' + evs.length + ' 条 · 去重后 ' + uniq.length + ' 个来源</p></div>' +
        '</div>' +
        '<div class="gev__tblWrap"><table class="gev__tbl"><thead><tr><th>来源</th><th>文档</th><th>文本块</th><th>来源站</th><th>发布日期</th><th>原文</th></tr></thead><tbody>' +
        uniq.map((s, i) => {
          const url = s.url ? '<a class="ev__link ev__link--sm" href="' + s.url + '" target="_blank" rel="noopener">' + EXT + '查看原文 ↗</a>' : '<span class="ev__nolink ev__nolink--sm">记录未给出</span>'
          return '<tr><td class="k">' + (i === 0 ? '<b class="gev__main">主要来源</b>' : '<em>同源（同文档，已去重）</em>') + '</td>' +
            '<td class="k"><b>' + (s.title || '—（未给出标题）') + '</b><em>doc_id ' + s.doc_id + '</em></td>' +
            '<td class="mono"><span class="gev__gap">' + s.chunk_id + '</span></td>' +
            '<td>' + (s.source || '<span class="gev__gap">—（未给出）</span>') + '</td>' +
            '<td class="mono">' + (s.publish_time ? String(s.publish_time).slice(0, 10) : '<span class="gev__gap">—（未给出）</span>') + '</td>' +
            '<td>' + url + '</td></tr>'
        }).join('') + '</tbody></table></div>' +
        '<p class="gnote">多来源证据按发布日期升序排列，最早一份标为「主要来源」，合并为一行不重复计算。</p>'
      }
      h += '<section class="gev__blk gev__blk--wide"><div class="gev__blkH"><span class="label">④ 事件实体额外四项</span><span class="label">GET /api/graph/events/' + EID + '</span></div>' + body + '</section>'
    }

    h += '</div>' +
      '<p class="gnote gnote--wide"><b>⑤ 缺口说明</b>：① 的计数与 ②③ 逐条列出的关系口径不同（① 是实体级实测总量，② 只列本次返回里逐条给出的关系），两处不做换算；' +
      '不带证据属性的关系类型（如 <i>EVIDENCED_BY</i>）在 ② 里整行显示「' + NOEV + '」；文档标题／来源站／发布日期缺失时显示「—（未给出）」而不猜。</p>'
    evBox.innerHTML = h
  }

  function paintAcc() {
    const n = DS.nodes.length, e = DS.edges.length
    const p1 = DS.paths.filter((p) => p.d === 1).length, p2 = DS.paths.filter((p) => p.d === 2).length
    if (accBox) accBox.innerHTML = '<div class="gacc">' +
      '<span class="label">准确性声明</span>' +
      '<span class="small">' + (opt.modeName || '当前数据集') + '：<b>' + n + '</b> 节点 / <b>' + e + '</b> 边，全部来自真实返回</span>' +
      '<span class="tag tag--red">图谱深度上限 ' + DS.hops + ' 跳</span>' +
      '<span class="tag tag--muted">' + (opt.tag || '真实接口返回') + '</span>' +
    '</div>'
    if (noteBox) noteBox.innerHTML = '数据集由真实接口返回构造：画布绘制全部 <i>' + n + '</i> 个节点与 <i>' + e + '</i> 条边；' +
      '据此可枚举 1 跳路径 <i>' + p1 + '</i> 条、2 跳路径 <i>' + p2 + '</i> 条。跳数从各连通分量的中心实体（度最高者）起算。' +
      '压暗只影响可见性，不删除数据 —— 属性面板照常可查、路径列表只是暂不显示，重置即回来。属性值未做任何补写。'
  }

  // —— 交互（逐字移植） ——
  function pick(t) {
    if (t.classList.contains('gnode')) {
      const id = t.getAttribute('data-node'), n = DS.idx[id]
      if (!n) return
      S.edge = null; S.path = null; S.sel = n; S.userCleared = false
    } else {
      const i = parseInt(t.getAttribute('data-edge'), 10)
      if (!(i >= 0) || !DS.edges[i]) return
      S.sel = null; S.path = null; S.edge = i; S.userCleared = false
    }
    refresh()
  }
  function clearSel() {
    S.userCleared = true
    if (!S.sel && S.edge === null && !S.path) return
    S.sel = null; S.edge = null; S.path = null; refresh()
  }
  function anchorOf(ds, prevId, pref) {
    if (prevId && ds.idx[prevId]) return ds.idx[prevId]
    if (pref) { const p = ds.idx[pref]; if (p) return p }
    let best = null
    for (let i = 0; i < ds.nodes.length; i++) {
      const n = ds.nodes[i]
      if (!best || n.deg > best.deg || (n.deg === best.deg && n.id < best.id)) best = n
    }
    return best
  }
  function autoAnchor(pref, prevId) {
    S.userCleared = false
    const a = anchorOf(DS, prevId, pref)
    S.sel = a || null; S.edge = null; S.path = null
    return a
  }
  function reenter() {
    S.userCleared = false
    if (!S.sel && S.edge === null) autoAnchor(PREF, null)
    refresh()
  }
  function onKey(e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return
    if (document.body.getAttribute('data-drawer') === 'on') return
    clearSel()
  }
  document.addEventListener('keydown', onKey)
  let moved = false, downTarget = null
  svg.addEventListener('click', function (e) {
    // pointerdown 时对 svg 调用了 setPointerCapture，浏览器会把后续 click 的 target 重定到 svg，
    // 从而丢掉「点的是哪个节点/边」。故这里回退到 pointerdown 时记下的真实命中元素。
    const t0 = downTarget; downTarget = null
    if (moved) { moved = false; return }
    const t = (e.target.closest ? e.target.closest('.gnode,.geline') : null) || t0
    if (!t) { clearSel(); return }
    pick(t)
  })
  svg.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return
    const t = e.target.closest ? e.target.closest('.gnode,.geline') : null
    if (!t) return
    e.preventDefault(); pick(t)
  })
  if (pathsBox) pathsBox.addEventListener('click', function (e) {
    const b = e.target.closest ? e.target.closest('[data-pi]') : null
    if (!b) return
    const p = DS.paths[parseInt(b.getAttribute('data-pi'), 10)]
    S.path = (S.path === p) ? null : p; S.sel = null; S.edge = null; refresh()
  })
  if (filters) filters.addEventListener('click', function (e) {
    const b = e.target.closest ? e.target.closest('[data-ftype]') : null
    if (!b || b.disabled) return
    const k = b.getAttribute('data-ftype')
    S.hidden[k] = !S.hidden[k]
    b.setAttribute('aria-checked', S.hidden[k] ? 'false' : 'true')
    refit()
  })
  if (depthBox) depthBox.addEventListener('click', function (e) {
    const b = e.target.closest ? e.target.closest('[data-depth]') : null
    if (!b) return
    S.depth = parseInt(b.getAttribute('data-depth'), 10)
    $$('[data-depth]', depthBox).forEach((x) => { x.setAttribute('aria-pressed', parseInt(x.getAttribute('data-depth'), 10) === S.depth ? 'true' : 'false') })
    refit()
  })
  if (modesBox) modesBox.addEventListener('click', function (e) {
    const b = e.target.closest ? e.target.closest('[data-mode]') : null
    if (!b) return
    const m = b.getAttribute('data-mode')
    if (m === DS.mode) return
    const md = MODES.filter((x) => x.key === m)[0]
    if (!md) return
    opt.modeName = md.label
    setDataset(cloneDS(md.ds), md.select || null)
  })
  if (isoBox) isoBox.addEventListener('click', function (e) {
    if (!e.target.closest) return
    const g = e.target.closest('.gnode')
    if (g && g.getAttribute('data-node')) { pick(g); return }
    const b = e.target.closest('[data-iso]')
    if (!b) return
    const n = DS.idx[b.getAttribute('data-iso')]
    if (!n) return
    S.edge = null; S.path = null; S.sel = n; S.userCleared = false; refresh()
  })
  if (pbody) pbody.addEventListener('click', function (e) {
    const u = e.target.closest ? e.target.closest('[data-g="unselect"]') : null
    if (u) { clearSel(); return }
    const b = e.target.closest ? e.target.closest('[data-g="jump"]') : null
    if (!b || b.disabled) return
    if (S.edge === null) return
    if (opt.jumpEvidence) opt.jumpEvidence(DS.edges[S.edge].schunk)
  })
  host.addEventListener('click', function (e) {
    if (!e.target.closest) return
    const r = e.target.closest('[data-g="ruletog"]')
    if (r) {
      const rl = q('rule'); const open = r.getAttribute('aria-expanded') === 'true'
      r.setAttribute('aria-expanded', open ? 'false' : 'true'); if (rl) rl.hidden = open; return
    }
    const c = e.target.closest('[data-ctx]')
    if (c) {
      const keyv = c.getAttribute('data-ctx')
      const row = host.querySelector('[data-ctxfor="' + keyv + '"]')
      const open2 = c.getAttribute('aria-expanded') === 'true'
      c.setAttribute('aria-expanded', open2 ? 'false' : 'true')
      if (row) row.hidden = open2
      else loadCtx(c, keyv)
    }
  })
  function loadCtx(btn, keyv) {
    const parts = keyv.split(':'), docId = parts[0], chunkId = parts[1]
    if (!opt.fetchChunk) return
    btn.setAttribute('aria-expanded', 'true')
    const wrap = document.createElement('tr')
    wrap.className = 'gev__ctxrowWrap'; wrap.setAttribute('data-ctxfor', keyv)
    wrap.innerHTML = '<td colspan="7"><div class="gev__ctx"><span class="label">查看上下文</span>' +
      '<div class="gev__ctxrow"><span>接口</span><i>GET /api/documents/' + docId + '/chunks/' + chunkId + '</i></div>' +
      '<p class="gev__gap" style="margin:8px 0 0">正在请求 …</p></div></td>'
    const tr = btn.closest('tr')
    if (tr && tr.parentNode) tr.parentNode.insertBefore(wrap, tr.nextSibling)
    opt.fetchChunk(docId, chunkId).then((d) => {
      const content = (d && d.chunk_content) || '（接口未返回正文）'
      const nb = (d && d.neighbor_chunks) || []
      wrap.querySelector('div.gev__ctx').innerHTML =
        '<span class="label">查看上下文</span>' +
        '<div class="gev__ctxrow"><span>接口</span><i>GET /api/documents/' + docId + '/chunks/' + chunkId + '</i></div>' +
        '<div class="gev__ctxrow"><span>chunk_id</span><i>' + chunkId + '</i></div>' +
        '<div class="gev__ctxrow"><span>chunk_content</span><i>' + content + '</i></div>' +
        '<div class="gev__ctxrow"><span>neighbor_chunks</span><i>' + (nb.length ? nb.map((x) => 'chunk_id ' + x.chunk_id).join('、') : '本次返回里没有相邻块') + '</i></div>'
    }).catch((e) => {
      wrap.querySelector('div.gev__ctx').innerHTML =
        '<span class="label">查看上下文</span><p class="gev__gap">正文接口请求失败：' + (e && e.message || e) + '</p>'
    })
  }
  function setDataset(ds, pref) {
    const prevId = (S.sel && S.sel.id) || null
    DS = ds
    S.hidden = {}; S.depth = opt.depth || 2
    autoAnchor(pref !== undefined ? pref : PREF, prevId)
    buildEdgeOffsets(); paintLegend(); paintModes(); paintFilters(); paintDepth(); paintAcc()
    fitView(); paint(); refresh()
    if (opt.onDataset) opt.onDataset(DS)
  }
  const resetBtn = q('reset')
  if (resetBtn) resetBtn.addEventListener('click', function () {
    S.sel = null; S.edge = null; S.path = null; S.hidden = {}; S.depth = opt.depth || 2
    $$('[data-ftype]', filters).forEach((b) => b.setAttribute('aria-checked', 'true'))
    $$('[data-depth]', depthBox).forEach((x) => x.setAttribute('aria-pressed', x.getAttribute('data-depth') === '2' ? 'true' : 'false'))
    layout(DS); fitView(); paint(); refresh()
    if (opt.onReset) opt.onReset()
  })
  const fitBtn = q('fit')
  if (fitBtn) fitBtn.addEventListener('click', fitView)

  function zoomAt(cx, cy, f) {
    const r = svg.getBoundingClientRect(); if (!r.width) return
    const mx = (cx - r.left) / r.width * VB.w, my = (cy - r.top) / r.height * VB.h
    const nk = Math.max(Math.max(K_MIN, view.fit * 0.35), Math.min(Math.min(K_MAX, view.fit * 8), view.k * f))
    view.tx = mx - (mx - view.tx) * (nk / view.k)
    view.ty = my - (my - view.ty) * (nk / view.k)
    view.k = nk; applyView()
  }
  svg.addEventListener('wheel', function (e) {
    e.preventDefault(); zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.12 : 1 / 1.12)
  }, { passive: false })
  const zin = q('zin'), zout = q('zout')
  if (zin) zin.addEventListener('click', function () { const r = svg.getBoundingClientRect(); zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1.2) })
  if (zout) zout.addEventListener('click', function () { const r = svg.getBoundingClientRect(); zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1 / 1.2) })

  function toLocal(cx, cy) {
    const r = svg.getBoundingClientRect(); if (!r.width) return null
    const vx = (cx - r.left) / r.width * VB.w, vy = (cy - r.top) / r.height * VB.h
    return { x: (vx - view.tx) / view.k, y: (vy - view.ty) / view.k }
  }
  function moveNode(n) {
    if (n.el) n.el.setAttribute('transform', 'translate(' + n.x.toFixed(1) + ',' + n.y.toFixed(1) + ')')
    DS.edges.forEach((e) => {
      if (e.f !== n.id && e.t !== n.id) return
      const g = edgeGeom(e)
      const p = e.el && e.el.querySelector('.gedge'), hit = e.el && e.el.querySelector('.gehit'), lab = e.el && e.el.querySelector('.gelabel')
      if (p) p.setAttribute('d', g.d)
      if (hit) hit.setAttribute('d', g.d)
      if (lab) { lab.setAttribute('x', g.lx.toFixed(1)); lab.setAttribute('y', g.ly.toFixed(1)) }
    })
  }
  let drag = null, dn = null
  svg.addEventListener('pointerdown', function (e) {
    downTarget = e.target.closest ? e.target.closest('.gnode,.geline') : null
    const g = e.target.closest ? e.target.closest('.gnode') : null
    const p = toLocal(e.clientX, e.clientY); if (!p) return
    if (g) {
      const n = DS.idx[g.getAttribute('data-node')]
      if (!n || !n.on) return
      dn = { n, dx: n.x - p.x, dy: n.y - p.y }; moved = false
      g.classList.add('dragging')
    } else {
      drag = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty }
      svg.classList.add('panning')
    }
    if (svg.setPointerCapture) svg.setPointerCapture(e.pointerId)
  })
  svg.addEventListener('pointermove', function (e) {
    if (!drag && !dn) return
    const p = toLocal(e.clientX, e.clientY); if (!p) return
    if (dn) {
      if (Math.abs(p.x - (dn.n.x - dn.dx)) + Math.abs(p.y - (dn.n.y - dn.dy)) > 3) moved = true
      dn.n.x = p.x + dn.dx; dn.n.y = p.y + dn.dy; moveNode(dn.n)
      return
    }
    const r = svg.getBoundingClientRect(); if (!r.width) return
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 4) moved = true
    view.tx = drag.tx + dx / r.width * VB.w
    view.ty = drag.ty + dy / r.height * VB.h
    applyView()
  })
  function endPan(e) {
    if (dn && dn.n.el) dn.n.el.classList.remove('dragging')
    if (dn) refresh()
    drag = null; dn = null; svg.classList.remove('panning')
    if (svg.releasePointerCapture && e && e.pointerId !== undefined && svg.hasPointerCapture && svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId)
  }
  svg.addEventListener('pointerup', endPan)
  svg.addEventListener('pointercancel', endPan)

  buildEdgeOffsets(); paintLegend(); paintModes(); paintFilters(); paintDepth(); paintAcc()
  fitView(); paint()
  autoAnchor(PREF, null)
  refresh()
  return {
    host,
    ds: () => DS,
    setTimeRange: function (a, b) { S.i0 = a; S.i1 = b; refit() },
    setDataset,
    reenter,
    reset: function () { if (resetBtn) resetBtn.click() },
    scale: function () { fitView() },
    // 卸载时移除挂到 document 上的 Esc 监听，避免离开本页后仍响应 Esc（模板销毁后不应再触发选中清理）
    destroy: function () { document.removeEventListener('keydown', onKey) },
  }
}

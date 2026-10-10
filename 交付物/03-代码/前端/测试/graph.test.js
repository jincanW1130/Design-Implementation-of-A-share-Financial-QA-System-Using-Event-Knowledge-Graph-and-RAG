// 交付物/03-代码\前端\测试\graph.test.js —— G 组：`src/lib/graph.js` 的纯函数单测
//
// `graph.js` 是知识图谱渲染器，**大部分**函数都绑在 DOM／SVG 上（mountGraph 那一段），
// 但那不是本文件的目标——本文件只测它**导出且无副作用**的那部分：
//
//   * 常量表：`REL` / `TYPE` / `TKEYS` / `LABEL2TYPE` / `DOMAIN` / `EMPTY` / `NOEV` / `EXT`；
//   * `RELNAME` / `typeOfLabel` / `radiusOf` / `shapeSVG` —— 纯映射与纯几何；
//   * `buildDataset` —— 数据集构造（节点度数、连通分量、中心、跳数、路径枚举），
//     这是**唯一**能离线验证渲染器"数据理解"是否正确的入口。
//
// 与 Python 侧一致的三条纪律：不联网、不留状态、关键断言配负向标定。
// 本文件**不**挂载 DOM（mountGraph 归属"需要起服务／真实浏览器"的覆盖面，如实留给阶段门禁）。

import { describe, it, expect } from 'vitest'
import {
  REL, EMPTY, NOEV, RELNAME, TYPE, TKEYS, LABEL2TYPE, typeOfLabel, DOMAIN, EXT,
  radiusOf, shapeSVG, buildDataset,
} from '../src/lib/graph.js'

// ==========================================================================
// G8 组 · 常量表（设计语言的"唯一真源"）
// ==========================================================================
describe('常量表', () => {
  it('REL 是 8 条核心关系的中文名映射（键为英文枚举）', () => {
    expect(Object.keys(REL)).toHaveLength(8)
    expect(REL.HAS_EXECUTIVE).toBe('任职')
    expect(REL.PARTICIPATES_IN).toBe('参与')
    expect(REL.ISSUED_BY).toBe('发布')
    expect(REL.EVIDENCED_BY).toBe('证据指向')
    for (const v of Object.values(REL)) expect(typeof v).toBe('string')
  })

  it('EMPTY / NOEV 是两条固定标注（"未给出"与"该关系类型不带证据属性"）', () => {
    expect(EMPTY).toBe('—（空）')
    expect(NOEV).toBe('—（该关系类型不带证据属性）')
  })

  it('RELNAME 命中时取中文名，未命中时原样返回（不猜、不补写）', () => {
    expect(RELNAME('HAS_EXECUTIVE')).toBe('任职')
    expect(RELNAME('SOME_NEW_REL')).toBe('SOME_NEW_REL')
    expect(RELNAME('')).toBe('')
  })

  it('TYPE 覆盖 7 类节点，每类都有名称/颜色/形状', () => {
    expect(TKEYS).toEqual(['company', 'person', 'org', 'event', 'policy', 'industry', 'doc'])
    for (const k of TKEYS) {
      expect(TYPE[k]).toBeTruthy()
      expect(typeof TYPE[k].n).toBe('string')
      expect(TYPE[k].c).toMatch(/^#[0-9A-Fa-f]{6}$/)
      expect(['circle', 'hex', 'rect', 'diamond', 'pentagon', 'page', 'triangle']).toContain(TYPE[k].s)
    }
  })

  it('LABEL2TYPE 覆盖后端 7 类标签（含 Document，各映射到画布类型）', () => {
    expect(Object.keys(LABEL2TYPE)).toHaveLength(7)
    expect(LABEL2TYPE.Company).toBe('company')
    expect(LABEL2TYPE.Person).toBe('person')
    expect(LABEL2TYPE.Institution).toBe('org')
    expect(LABEL2TYPE.Event).toBe('event')
    expect(LABEL2TYPE.Policy).toBe('policy')
    expect(LABEL2TYPE.Industry).toBe('industry')
    expect(LABEL2TYPE.Document).toBe('doc')
  })

  it('typeOfLabel：已知标签映射；未知标签兜底为 doc（不抛错、不返回 undefined）', () => {
    expect(typeOfLabel('Company')).toBe('company')
    expect(typeOfLabel('Document')).toBe('doc')
    expect(typeOfLabel('Nope')).toBe('doc')
    expect(typeOfLabel(undefined)).toBe('doc')
  })

  it('DOMAIN 覆盖 5 个来源站点的域名', () => {
    expect(DOMAIN['巨潮资讯网']).toBe('static.cninfo.com.cn')
    expect(DOMAIN['中国政府网']).toBe('www.gov.cn')
    expect(Object.keys(DOMAIN)).toHaveLength(5)
  })

  it('EXT 是「原文 ↗」图标共用的那段 SVG（站内唯一）', () => {
    expect(EXT.startsWith('<svg')).toBe(true)
    expect(EXT).toContain('aria-hidden="true"')
    expect(EXT).toContain('stroke="currentColor"')
  })
})

// ==========================================================================
// G9 组 · 半径分级与形状 SVG（纯几何）
// ==========================================================================
describe('radiusOf()', () => {
  it('度数越大半径越大，并钳位到 [14, 30]', () => {
    expect(radiusOf(0, 'person')).toBe(14)
    expect(radiusOf(1000, 'person')).toBe(30)
    expect(radiusOf(3, 'person')).toBeLessThan(radiusOf(5, 'person'))
  })

  it('公司类型在同等度数下额外 +2（再钳位）', () => {
    expect(radiusOf(2, 'company')).toBe(radiusOf(2, 'person') + 2)
    expect(radiusOf(0, 'company')).toBe(16)
    expect(radiusOf(100, 'company')).toBe(30)   // 钳位仍生效
  })
})

describe('shapeSVG()', () => {
  it('circle 类型出 <circle>', () => {
    const svg = shapeSVG('company', 10)
    expect(svg).toContain('<circle')
    expect(svg).toContain('r="10"')
    expect(svg).toContain(TYPE.company.c)
  })

  it('hex/pentagon/triangle 出 <polygon>；event 出菱形 polygon', () => {
    for (const t of ['person', 'policy', 'industry', 'event']) {
      expect(shapeSVG(t, 10)).toContain('<polygon')
    }
  })

  it('org 出 <rect>；doc 出双路径 <path>', () => {
    expect(shapeSVG('org', 10)).toContain('<rect')
    expect(shapeSVG('doc', 10)).toContain('<path')
  })

  it('未指定 op 时默认 fill-opacity=0.2；显式 op 时用之', () => {
    expect(shapeSVG('company', 10)).toContain('fill-opacity="0.2"')
    expect(shapeSVG('company', 10, 0.35)).toContain('fill-opacity="0.35"')
  })

  it('未知类型兜底为 doc 的 page 形状（不抛错、不返回 undefined）', () => {
    const svg = shapeSVG('no_such_type', 10)
    expect(typeof svg).toBe('string')
    expect(svg).toContain('<path')            // TYPE.doc 的 page 形状
    expect(svg).toContain(TYPE.doc.c)
  })
})

// ==========================================================================
// G10 组 · buildDataset（数据理解的唯一离线入口）
// ==========================================================================
/** 造一个最小可测图：中心公司 + 两条边 + 一个孤立节点。 */
function sampleNodesEdges() {
  const nodes = [
    { id: 'C1', type: 'company', name: '甲公司', code: '000001' },
    { id: 'E1', type: 'event', name: '业绩事件', eid: 'EVT-0001' },
    { id: 'P1', type: 'person', name: '张三' },
    { id: 'ISO', type: 'industry', name: '孤立行业' },
  ]
  const edges = [
    { f: 'C1', t: 'E1', rel: 'PARTICIPATES_IN', conf: 0.9 },
    { f: 'P1', t: 'C1', rel: 'HAS_EXECUTIVE', conf: 0.8 },
  ]
  return { nodes, edges }
}

describe('buildDataset()', () => {
  it('计算每个节点的度数；孤立节点度为 0', () => {
    const { nodes, edges } = sampleNodesEdges()
    const ds = buildDataset('m', nodes, edges)
    expect(ds.idx.C1.deg).toBe(2)
    expect(ds.idx.E1.deg).toBe(1)
    expect(ds.idx.P1.deg).toBe(1)
    expect(ds.idx.ISO.deg).toBe(0)
    expect(ds.mode).toBe('m')
  })

  it('label 把证券代码拼在名称后；无 code 时只用名称；并算出截断标签与标签宽度', () => {
    const { nodes, edges } = sampleNodesEdges()
    const ds = buildDataset('m', nodes, edges)
    expect(ds.idx.C1.label).toBe('甲公司 000001')
    expect(ds.idx.E1.label).toBe('业绩事件')
    expect(typeof ds.idx.C1.lbl).toBe('string')
    expect(ds.idx.C1.lw).toBeGreaterThan(0)
  })

  it('长名称被截断到 14 字并加省略号（trunclbl）', () => {
    const long = '甲'.repeat(30)
    const ds = buildDataset('m', [{ id: 'X', type: 'company', name: long }], [])
    expect(ds.idx.X.lbl.endsWith('…')).toBe(true)
    expect(ds.idx.X.lbl.length).toBe(15)          // 14 字 + 省略号
  })

  it('连通分量：两个分量被分别识别，孤立节点不算分量', () => {
    const nodes = [
      { id: 'A', type: 'company', name: 'A' },
      { id: 'B', type: 'company', name: 'B' },
      { id: 'C', type: 'company', name: 'C' },
      { id: 'D', type: 'company', name: 'D' },
    ]
    const edges = [
      { f: 'A', t: 'B', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'C', t: 'D', rel: 'RELATED_TO', conf: 0.5 },
    ]
    const ds = buildDataset('m', nodes, edges)
    expect(ds.comps).toHaveLength(2)
    for (const c of ds.comps) expect(c).toHaveLength(2)
  })

  it('分量中心是度最高的节点；跳数从中心起算，孤立节点 dist=99 且无中心', () => {
    const { nodes, edges } = sampleNodesEdges()
    const ds = buildDataset('m', nodes, edges)
    // C1 度 2 最高 → 中心；E1/P1 距中心 1 跳
    expect(ds.idx.C1.isCenter).toBe(true)
    expect(ds.idx.C1.dist).toBe(0)
    expect(ds.idx.E1.dist).toBe(1)
    expect(ds.idx.P1.dist).toBe(1)
    expect(ds.idx.ISO.dist).toBe(99)
    expect(ds.idx.ISO.centerId).toBeNull()
    expect(ds.hops).toBe(1)
  })

  it('跳数上限 = 各分量中心到最远可达节点的最大距离（从中心起算）', () => {
    const nodes = ['A', 'B', 'C', 'D'].map((id) => ({ id, type: 'company', name: id }))
    const edges = [
      { f: 'A', t: 'B', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'B', t: 'C', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'C', t: 'D', rel: 'RELATED_TO', conf: 0.5 },
    ]
    const ds = buildDataset('m', nodes, edges)
    // B 在链中间、度最高（2）→ 中心；A/C 距 1 跳、D 距 2 跳
    expect(ds.idx.B.isCenter).toBe(true)
    expect(ds.idx.D.dist).toBe(2)
    expect(ds.hops).toBe(2)
  })

  it('丢弃端点不在节点集里的边（悬挂边不得进入数据集）', () => {
    const nodes = [{ id: 'A', type: 'company', name: 'A' }]
    const edges = [
      { f: 'A', t: 'GHOST', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'A', t: 'A', rel: 'RELATED_TO', conf: 0.5 },
    ]
    const ds = buildDataset('m', nodes, edges)
    expect(ds.edges).toHaveLength(1)
    expect(ds.edges[0].f).toBe('A')
    expect(ds.edges[0].t).toBe('A')
  })

  it('边的 i 被重编为去掉悬挂边后的连续下标', () => {
    const nodes = ['A', 'B', 'C'].map((id) => ({ id, type: 'company', name: id }))
    const edges = [
      { f: 'A', t: 'GHOST', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'A', t: 'B', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'B', t: 'C', rel: 'RELATED_TO', conf: 0.5 },
    ]
    const ds = buildDataset('m', nodes, edges)
    expect(ds.edges.map((e) => e.i)).toEqual([0, 1])
  })

  it('路径枚举：1 跳路径数 = 边数；2 跳路径按"首尾相接"展开', () => {
    const nodes = ['A', 'B', 'C'].map((id) => ({ id, type: 'company', name: id }))
    const edges = [
      { f: 'A', t: 'B', rel: 'RELATED_TO', conf: 0.5 },
      { f: 'B', t: 'C', rel: 'RELATED_TO', conf: 0.5 },
    ]
    const ds = buildDataset('m', nodes, edges)
    const p1 = ds.paths.filter((p) => p.d === 1)
    const p2 = ds.paths.filter((p) => p.d === 2)
    expect(p1).toHaveLength(2)                 // 两条边各算 1 跳
    expect(p2).toHaveLength(1)                 // A→B→C 一条 2 跳路径
    expect(p2[0].f).toBe('A')
    expect(p2[0].t).toBe('C')
  })

  it('time 为空值/标注/None 时统一置 null（不把「—（空）」当成时间）', () => {
    const nodes = [
      { id: 'A', type: 'event', name: 'A', time: '2026-03-01' },
      { id: 'B', type: 'event', name: 'B', time: EMPTY },
      { id: 'C', type: 'event', name: 'C', time: null },
      { id: 'D', type: 'event', name: 'D', time: '' },
    ]
    const edges = [{ f: 'A', t: 'B', rel: 'RELATED_TO', conf: 0.5 }, { f: 'C', t: 'D', rel: 'RELATED_TO', conf: 0.5 }]
    const ds = buildDataset('m', nodes, edges)
    expect(ds.idx.A.time).toBe('2026-03-01')
    expect(ds.idx.B.time).toBeNull()
    expect(ds.idx.C.time).toBeNull()
    expect(ds.idx.D.time).toBeNull()
  })

  it('确定性：同一输入两次构造，节点坐标与包围盒逐值一致', () => {
    const { nodes, edges } = sampleNodesEdges()
    const a = buildDataset('m', nodes, edges)
    const b = buildDataset('m', nodes, edges)
    expect(a.nodes.map((n) => [n.id, n.x, n.y])).toEqual(b.nodes.map((n) => [n.id, n.x, n.y]))
    expect(a.bb).toEqual(b.bb)
  })

  it('输入数组与对象不被就地改写（buildDataset 复制节点/边）', () => {
    const nodes = [{ id: 'A', type: 'company', name: 'A' }]
    const edges = []
    const nodesCopy = JSON.parse(JSON.stringify(nodes))
    buildDataset('m', nodes, edges)
    expect(nodes).toEqual(nodesCopy)
    expect(nodes[0].deg).toBeUndefined()       // 度数写在副本上，不污染入参
  })

  it('包围盒覆盖全部节点（w/h 为正；顶点落在 bb 内）', () => {
    const { nodes, edges } = sampleNodesEdges()
    const ds = buildDataset('m', nodes, edges)
    expect(ds.bb.w).toBeGreaterThan(0)
    expect(ds.bb.h).toBeGreaterThan(0)
    for (const n of ds.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(ds.bb.x - 1)
      expect(n.x).toBeLessThanOrEqual(ds.bb.x + ds.bb.w + 1)
    }
  })

  it('每个节点初始 on=true、lblOn=false（渲染前不做可见性裁剪）', () => {
    const { nodes, edges } = sampleNodesEdges()
    const ds = buildDataset('m', nodes, edges)
    for (const n of ds.nodes) {
      expect(n.on).toBe(true)
      expect(n.lblOn).toBe(false)
      expect(n.pri).toBe(0)
    }
  })
})

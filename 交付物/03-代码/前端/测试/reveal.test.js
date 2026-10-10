// 交付物/03-代码\前端\测试\reveal.test.js —— G 组：`src/lib/reveal.js` 的单元测试
//
// `reveal.js` 用**显式几何检查**（不是 IntersectionObserver）做滚动入场，
// 理由是 IO 在「视图 display 切换」与「后台标签页节流」下不可靠。本文件用 jsdom
// 把这条判据钉住：命中视口才加 `.in`，隐藏视图内的项跳过，错位入场序号写进 `--d`。
//
// jsdom 不做真实布局：`getBoundingClientRect()` 与 `offsetParent` 都返回默认值，
// 因此本文件一律用 `vi.spyOn(...).mockReturnValue(...)` 给出**可控几何**——
// 这样测的是「判据逻辑」而不是浏览器排版（后者属端到端覆盖面）。

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { kickReveal } from '../src/lib/reveal.js'

/** 造一个带 rect 的元素，并把它挂进 document。 */
function makeReveal(top, bottom, { hidden = false, host = null } = {}) {
  const el = document.createElement('div')
  el.className = 'reveal'
  if (host) host.appendChild(el)
  else document.body.appendChild(el)
  // 隐藏视图：offsetParent === null
  Object.defineProperty(el, 'offsetParent', {
    configurable: true,
    get: () => (hidden ? null : document.body),
  })
  el.getBoundingClientRect = () => ({ top, bottom, left: 0, right: 0, width: 0, height: 0 })
  return el
}

beforeEach(() => {
  document.body.innerHTML = ''
  window.innerHeight = 800
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('kickReveal() 的视口判据', () => {
  it('命中视口（top < 0.94H 且 bottom > -60）→ 加 .in', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const el = makeReveal(100, 200)          // 0.94*800 = 752；100 < 752 且 200 > -60
    kickReveal()
    expect(el.classList.contains('in')).toBe(true)
  })

  it('在视口下方（top ≥ 0.94H）→ 不加 .in', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const el = makeReveal(760, 900)          // 760 ≥ 752
    kickReveal()
    expect(el.classList.contains('in')).toBe(false)
  })

  it('在视口上方过远（bottom ≤ -60）→ 不加 .in', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const el = makeReveal(-200, -61)
    kickReveal()
    expect(el.classList.contains('in')).toBe(false)
  })

  it('负向标定：边界附近的取值按严格不等号判定', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    // 恰在边界上：top=752 时 752<752 为假 → 不入场
    const onEdge = makeReveal(752, 800)
    kickReveal()
    expect(onEdge.classList.contains('in')).toBe(false)
    // bottom=-60 时 -60>-60 为假 → 不入场
    const onBottomEdge = makeReveal(-100, -60)
    kickReveal()
    expect(onBottomEdge.classList.contains('in')).toBe(false)
  })

  it('隐藏视图（offsetParent === null）内的项被跳过', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const el = makeReveal(100, 200, { hidden: true })
    kickReveal()
    expect(el.classList.contains('in')).toBe(false)
  })

  it('已带 .in 的项不再重复处理（幂等）', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const el = makeReveal(100, 200)
    el.classList.add('in')
    el.style.setProperty('--d', '999ms')
    kickReveal()
    expect(el.style.getPropertyValue('--d')).toBe('999ms')   // 未被重写
  })

  it('错位入场：按同类兄弟序号写 --d（每级 55ms，上限索引 9）', () => {
    vi.stubGlobal('requestAnimationFrame', (cb) => { cb(); return 1 })
    const host = document.createElement('div')
    host.className = 'view'
    document.body.appendChild(host)
    const a = makeReveal(100, 200, { host })
    const b = makeReveal(100, 200, { host })
    kickReveal()
    expect(a.style.getPropertyValue('--d')).toBe('0ms')
    expect(b.style.getPropertyValue('--d')).toBe('55ms')
  })

  it('同一帧内重复调用只排一次（ticking 去抖）', () => {
    // 关键：回调**不能**同步执行，否则 ticking 会立刻被 check() 复位；
    // 这里只记录排期、不立刻跑，才能观察到"第二次被挡"。
    const queued = []
    const raf = vi.fn((cb) => { queued.push(cb); return queued.length })
    vi.stubGlobal('requestAnimationFrame', raf)
    makeReveal(100, 200)
    kickReveal()
    kickReveal()          // 第二次应被 ticking 挡住
    expect(raf).toHaveBeenCalledTimes(1)
    expect(queued).toHaveLength(1)
    queued[0]()           // 跑掉这一帧
    kickReveal()          // 复位之后可以再排
    expect(raf).toHaveBeenCalledTimes(2)
  })
})

describe('initReveal()', () => {
  it('首次调用绑定监听并立即排一次入场检查；重复调用被 bound 守卫挡住', async () => {
    // 用 vi.resetModules + 动态 import 拿一份**全新**的 reveal 模块，
    // 才能稳定观察到"首次初始化"这条路径（不受前面用例影响）。
    vi.resetModules()
    const queued = []
    vi.stubGlobal('requestAnimationFrame', (cb) => { queued.push(cb); return queued.length })
    const addSpy = vi.spyOn(window, 'addEventListener')
    const fresh = await import('../src/lib/reveal.js')
    const el = makeReveal(50, 100)

    fresh.initReveal()                       // 首次
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true })
    expect(addSpy).toHaveBeenCalledWith('resize', expect.any(Function))
    expect(queued.length).toBe(1)
    queued[0]()
    expect(el.classList.contains('in')).toBe(true)

    // 再次调用：bound 已置真 → 不新增监听、不排新帧
    const before = addSpy.mock.calls.length
    fresh.initReveal()
    fresh.initReveal()
    expect(addSpy.mock.calls.length).toBe(before)
    expect(queued.length).toBe(1)
  })
})

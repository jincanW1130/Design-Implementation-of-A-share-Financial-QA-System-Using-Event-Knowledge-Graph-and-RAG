// 交付物/03-代码\前端\src\lib\reveal.js —— 滚动进入（逐字移植原型脚本第 8 节的 reveal）
//
// 关键点：原型用的是**显式几何检查**（不是 IntersectionObserver）——
// IO 在「视图 display 切换」与「后台标签页节流」下不可靠，会漏触。
// 这里同样：遍历所有尚未 .in 且可见的元素，命中视口（top<0.94H 且 bottom>−60）就加 .in，
// 并按同类兄弟的序号写 --d 做错位入场。切换路由后调 kick() 重播。

let ticking = false
let bound = false

function check() {
  ticking = false
  const els = Array.prototype.slice.call(document.querySelectorAll('.reveal'))
  for (let i = 0; i < els.length; i++) {
    const e = els[i]
    if (e.classList.contains('in') || e.offsetParent === null) continue  // 跳过隐藏视图内的项
    const r = e.getBoundingClientRect()
    if (r.top < window.innerHeight * 0.94 && r.bottom > -60) {
      const host = e.closest('.view')
      const sibs = host ? Array.prototype.slice.call(host.querySelectorAll('.reveal')) : els
      e.style.setProperty('--d', Math.min(sibs.indexOf(e), 9) * 55 + 'ms')
      e.classList.add('in')
    }
  }
}

export function kickReveal() {
  if (!ticking) { ticking = true; requestAnimationFrame(check) }
}

export function initReveal() {
  if (bound) return
  bound = true
  window.addEventListener('scroll', kickReveal, { passive: true })
  window.addEventListener('resize', kickReveal)
  kickReveal()
}

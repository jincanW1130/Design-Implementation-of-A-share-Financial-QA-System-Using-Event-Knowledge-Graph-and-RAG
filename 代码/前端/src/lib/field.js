// 代码\前端\src\lib\field.js —— 全站背景：动态、持续波动、整体上升的股票曲线
//
// 逐字移植自 阶段09 前端设计原型 index.html 脚本第 1 节（field 流场）——
// 参数（点间距 1.6px、约 96px/s 水平推进、每点漂移 −0.22px、波动 ±2.6、
// 动量 0.42、相机死区 [0.28H,0.72H]）完全一致，未改一个数。
//
// 两处启用条件与原型一致：
//   · 仅「精确指针 + 可 hover」设备启用（触屏不画，省电、也不乱动）；
//   · prefers-reduced-motion 时改为**静态绘制一条上升曲线**，不启动动画。

export function mountField() {
  const cv = document.getElementById('field')
  const veil = document.getElementById('veil')
  if (!cv || !cv.getContext) return { start() {}, stop() {} }

  const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)')
  const fineMQ = matchMedia('(hover:hover) and (pointer:fine)')
  // 点击热区遮罩：与原型同一处切换（#veil.on）
  if (veil) veil.classList.add('on')
  if (!fineMQ.matches) return { start() {}, stop() {} }

  cv.classList.add('on')
  const ctx = cv.getContext('2d')
  const SPACING = 1.6, SPEED = 1.6, DRIFT = -0.22, VOL = 2.6, VOLR = 3.4, DEM = 0.42
  let W = 0, H = 0, buf = [], y = 0, cam = 0, meanY = 0, scroll = 0, acc = 0, last = 0, raf = 0, running = false

  function newPoint() {
    let mom = newPoint._m || 0
    mom = mom * DEM + (Math.random() - 0.5) * VOLR
    newPoint._m = mom
    y += DRIFT + mom + (Math.random() - 0.5) * VOL * 2
    return y
  }
  function seed() {
    buf = []; y = H * 0.52; newPoint._m = 0; cam = 0; scroll = 0
    const n = Math.ceil(W / SPACING) + 2
    for (let i = 0; i < n; i++) buf.push(newPoint())
  }
  function fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    W = window.innerWidth; H = window.innerHeight
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr)
    cv.style.width = W + 'px'; cv.style.height = H + 'px'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    seed()
    if (reduceMQ.matches) paint()
  }
  function grid() {
    ctx.strokeStyle = 'rgba(255,255,255,.035)'; ctx.lineWidth = 1; ctx.beginPath()
    for (let x = 0; x <= W; x += 48) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H) }
    for (let yy = 0; yy <= H; yy += 48) { ctx.moveTo(0, yy + 0.5); ctx.lineTo(W, yy + 0.5) }
    ctx.stroke()
  }
  function axes() {
    const n = buf.length, pts = []
    for (let i = 0; i < n; i++) pts.push({ x: i * SPACING - scroll, y: buf[i] - cam })
    return pts
  }
  function paint() {
    ctx.clearRect(0, 0, W, H)
    grid()
    const pts = axes(), n = pts.length
    const ma = [], win = 24; let sum = 0
    for (let i = 0; i < n; i++) { sum += buf[i]; if (i >= win) sum -= buf[i - win]; ma.push(i >= win - 1 ? sum / win : null) }
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y)
    for (let i = 1; i < n; i++) ctx.lineTo(pts[i].x, pts[i].y)
    const g = ctx.createLinearGradient(0, meanY - 140, 0, H)
    g.addColorStop(0, 'rgba(230,57,70,.12)'); g.addColorStop(1, 'rgba(230,57,70,0)')
    ctx.lineTo(W, H); ctx.lineTo(pts[0].x, H); ctx.closePath()
    ctx.fillStyle = g; ctx.fill()
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y)
    for (let i = 1; i < n; i++) ctx.lineTo(pts[i].x, pts[i].y)
    ctx.strokeStyle = '#E63946'; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round'
    ctx.shadowColor = 'rgba(230,57,70,.9)'; ctx.shadowBlur = 12; ctx.stroke(); ctx.shadowBlur = 0
    ctx.beginPath(); let s = 0
    for (let i = 0; i < n; i++) {
      if (ma[i] === null) continue
      const py = ma[i] - cam
      if (!s) { ctx.moveTo(pts[i].x, py); s = 1 } else ctx.lineTo(pts[i].x, py)
    }
    ctx.strokeStyle = 'rgba(230,57,70,.28)'; ctx.lineWidth = 1.4; ctx.stroke()
  }
  function frame(ts) {
    if (!running) return
    const dt = last ? Math.min(ts - last, 64) : 16.67; last = ts
    let f = dt / 16.67; if (f <= 0) f = 1
    scroll += SPEED * f; acc += f
    while (acc >= 1) { acc -= 1; buf.push(newPoint()); buf.shift() }
    while (scroll >= SPACING) scroll -= SPACING
    let sum = 0
    for (let i = 0; i < buf.length; i++) sum += buf[i]
    meanY = sum / buf.length - cam
    const hi = H * 0.28, lo = H * 0.72; let target = cam
    if (meanY < hi) target = sum / buf.length - hi
    else if (meanY > lo) target = sum / buf.length - lo
    cam += (target - cam) * (1 - Math.pow(1 - 0.05, f))
    paint()
    raf = requestAnimationFrame(frame)
  }
  function start() { if (running || document.hidden || reduceMQ.matches) return; running = true; last = 0; raf = requestAnimationFrame(frame) }
  function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0 }

  fit(); start()
  let rt = 0
  const onResize = () => { clearTimeout(rt); rt = setTimeout(() => { stop(); fit(); start() }, 180) }
  const onVis = () => { if (document.hidden) stop(); else start() }
  const onReduce = () => { if (reduceMQ.matches) { stop(); seed(); paint() } else start() }
  window.addEventListener('resize', onResize)
  document.addEventListener('visibilitychange', onVis)
  if (reduceMQ.addEventListener) reduceMQ.addEventListener('change', onReduce)

  return {
    start,
    stop,
    destroy() {
      stop()
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVis)
      if (reduceMQ.removeEventListener) reduceMQ.removeEventListener('change', onReduce)
    },
  }
}

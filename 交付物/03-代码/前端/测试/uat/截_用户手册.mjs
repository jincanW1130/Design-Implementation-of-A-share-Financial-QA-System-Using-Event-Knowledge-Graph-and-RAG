/**
 * 用户手册截图（2026-10-18 第 8 轮）。
 * 用法：node 测试/uat/截_用户手册.mjs [http://127.0.0.1:5173] [输出目录]
 *
 * 口径：
 *   · 视口 1440×900、deviceScaleFactor=1，PNG，逐页截**视口**（不是整页长图）；
 *   · 只读：不写业务数据。为让 /history 与 /ask 的「当前会话」有真实内容，
 *     仅在本浏览器上下文里把 localStorage 会话号设为既有基线会话 S-001（不删改服务端记录）；
 *   · 答案页 id 动态取自 `/api/history?session_id=S-001`，不写死；
 *   · 截图前不打开任何后台管理页面，页面不含令牌、连接串或绝对路径。
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:5173';
// 从 `交付物/03-代码/前端` 运行：上两级即 `交付物/`，再进 `10-部署/截图`
const OUT = process.argv[3] || path.resolve('..', '..', '10-部署', '截图');

async function firstAnswerId() {
  const resp = await fetch(`${BASE}/api/history?session_id=S-001&page=1&page_size=1`);
  const payload = await resp.json();
  const item = payload && payload.data && Array.isArray(payload.data.items) && payload.data.items[0];
  if (!item || item.answer_id == null) throw new Error('未能从 /api/history 取到真实 answer_id');
  return item.answer_id;
}

fs.mkdirSync(OUT, { recursive: true });
const answerId = await firstAnswerId();
console.log(`answer_id = ${answerId}`);

const browser = await chromium.launch();
const ctx = await browser.newContext({
  locale: 'zh-CN',
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
// 仅本上下文：使用既有基线会话，让历史页／最近问答有真实只读内容
await ctx.addInitScript(() => {
  try { window.localStorage.setItem('qa-console-session-id', 'S-001') } catch (e) { /* 不影响截图 */ }
});
const page = await ctx.newPage();

async function shot(route, file, selector, { scrollTo = null, settle = 600 } = {}) {
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector(selector, { timeout: 30000 });
  if (scrollTo) {
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (el) window.scrollTo({ top: window.pageYOffset + el.getBoundingClientRect().top - 84, behavior: 'instant' });
    }, scrollTo);
  }
  await page.waitForTimeout(settle);
  const target = path.join(OUT, file);
  await page.screenshot({ path: target, type: 'png' });
  console.log(`已截图 ${file} ← ${route}`);
}

// ① 提问台：滚到提问区，包含输入框、运行状态与「当前会话最近 3 条」
await shot('/ask', '01-提问台.png', '#q', { scrollTo: '.ask', settle: 900 });
// ② 答案与证据：动态真实 answer_id
await shot(`/answer/${answerId}`, '02-答案与证据.png', 'text=【回答】', { settle: 1400 });
// ③ 知识图谱：滚到画布本体（标题在上一屏，画布从视口中部开始）
await shot('/graph', '03-知识图谱.png', '.gnode', { scrollTo: '.gcanvasWrap', settle: 1400 });
// ④ 历史记录（S-001 既有真实记录）
await shot('/history', '04-历史记录.png', '[data-testid="history-list"], [data-testid="history-empty"]', { settle: 800 });

await browser.close();
console.log(`输出目录：${OUT}`);

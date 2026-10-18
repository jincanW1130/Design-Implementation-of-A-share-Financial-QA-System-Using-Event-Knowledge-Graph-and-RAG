/**
 * 工具\测_无障碍对比度.mjs —— 用真实 Chromium 取计算样式，实测 WCAG AA 文本对比度。
 *
 * 口径：
 *   · 普通文本 ≥ 4.5:1；大字号（≥24px，或 ≥18.66px 且粗体 ≥700）≥ 3.0:1；
 *   · 前景色与背景色都取 `getComputedStyle` 的真实值，半透明颜色按 alpha 逐层
 *     合成到最近的不透明祖先背景上（没有不透明背景时以白色为底）；
 *   · 背景含渐变／图片时**不猜**：标记为「人工复核」，不纳入自动达标结论。
 *
 * 只读：只访问页面与 /api/history，不改任何业务文件与数据。
 * 用法（仓库根目录）：node 工具\测_无障碍对比度.mjs [http://127.0.0.1:5173]
 *
 * 退出码：0 = 无自动判定不达标项；1 = 存在不达标项（明细仍会完整打印）。
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const UAT_PKG = path.join(ROOT, '交付物/03-代码/前端/测试/uat/package.json');
const requireFromUat = createRequire(UAT_PKG);
const { chromium } = requireFromUat('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5173';
const OUT = path.join(ROOT, '交付物/05-系统实现/前后端系统集成/_工作底稿/无障碍对比度_第四轮.json');

async function resolveAnswerPath() {
  try {
    const resp = await fetch(`${BASE}/api/history?session_id=S-001&page=1&page_size=1`);
    const payload = await resp.json();
    const item = payload?.data?.items?.[0];
    if (item?.answer_id != null) return `/answer/${item.answer_id}`;
  } catch { /* 下面如实跳过 */ }
  return '';
}

const answerPath = await resolveAnswerPath();
const PAGES = [
  { path: '/ask', name: '提问台' },
  ...(answerPath ? [{ path: answerPath, name: '答案与证据' }] : []),
  { path: '/graph', name: '知识图谱' },
  { path: '/history', name: '历史记录' },
];

const browser = await chromium.launch();
const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1440, height: 900 } });

const rows = [];
const notes = [];
if (!answerPath) notes.push('未能从 /api/history?session_id=S-001 取到真实 answer_id，答案页未测。');

for (const page of PAGES) {
  const tab = await context.newPage();
  await tab.goto(BASE + page.path, { waitUntil: 'networkidle', timeout: 30000 });
  await tab.waitForTimeout(400);
  const pageRows = await tab.evaluate((pageName) => {
    const parseColor = (value) => {
      const m = String(value || '').match(/rgba?\(([^)]+)\)/i);
      if (!m) return [0, 0, 0, 0];
      const parts = m[1].split(/[,/\s]+/).filter(Boolean).map(Number);
      return [parts[0] || 0, parts[1] || 0, parts[2] || 0,
              parts.length >= 4 ? parts[3] : 1];
    };
    const over = (fg, bg) => {
      const a = Math.max(0, Math.min(1, fg[3]));
      return [fg[0] * a + bg[0] * (1 - a),
              fg[1] * a + bg[1] * (1 - a),
              fg[2] * a + bg[2] * (1 - a),
              1];
    };
    const luminance = (rgb) => {
      const f = (c) => {
        c /= 255;
        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
    };
    const contrast = (a, b) => {
      const la = luminance(a), lb = luminance(b);
      const hi = Math.max(la, lb), lo = Math.min(la, lb);
      return (hi + 0.05) / (lo + 0.05);
    };
    const toHex = (rgb) => '#' + rgb.slice(0, 3)
      .map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');

    const effectiveBackground = (el) => {
      const layers = [];
      let hasImage = false;
      for (let node = el; node; node = node.parentElement) {
        const cs = getComputedStyle(node);
        const bg = parseColor(cs.backgroundColor);
        if (bg[3] > 0) layers.push(bg);
        // 只统计元素与「最近的不透明底」之间的背景图／渐变：更上层的不透明底已经
        // 把它遮住，不会影响这块文本的可读性。
        if (cs.backgroundImage && cs.backgroundImage !== 'none') hasImage = true;
        if (bg[3] >= 0.999) break;
      }
      let bg = [255, 255, 255, 1];
      for (let i = layers.length - 1; i >= 0; i -= 1) bg = over(layers[i], bg);
      return { rgb: bg, hasImage };
    };

    const selectorOf = (el) => {
      const tag = el.tagName.toLowerCase();
      if (el.id) return `${tag}#${el.id}`;
      const classes = Array.from(el.classList || []).slice(0, 3).join('.');
      return classes ? `${tag}.${classes}` : tag;
    };

    const out = [];
    const seen = new Set();
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;
      const text = Array.from(el.childNodes)
        .filter((n) => n.nodeType === 3)
        .map((n) => n.textContent)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (!text) continue;

      const isSvgText = ['text', 'tspan'].includes(el.tagName.toLowerCase());
      const fgColor = parseColor(isSvgText ? cs.fill : cs.color);
      const { rgb: bgColor, hasImage } = effectiveBackground(el);
      const fg = over(fgColor, bgColor);
      const ratio = contrast(fg, bgColor);
      const fontSize = parseFloat(cs.fontSize) || 16;
      const weight = parseInt(cs.fontWeight, 10) || 400;
      const large = fontSize >= 24 || (fontSize >= 18.66 && weight >= 700);
      const threshold = large ? 3.0 : 4.5;
      const key = [selectorOf(el), text, toHex(fg), toHex(bgColor), fontSize, weight].join('|');
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        page: pageName,
        element: selectorOf(el),
        text: text.length > 48 ? text.slice(0, 48) + '…' : text,
        foreground: toHex(fg),
        background: toHex(bgColor),
        font_size_px: Number(fontSize.toFixed(1)),
        font_weight: weight,
        large_text: large,
        threshold,
        contrast: Number(ratio.toFixed(2)),
        pass: hasImage ? null : ratio + 0.005 >= threshold,
        manual_review: hasImage,
        note: hasImage ? '背景含渐变／图片，自动测量仅作参考' : '',
      });
    }
    return out;
  }, page.name);
  rows.push(...pageRows);
  await tab.close();
}

await browser.close();

const autoRows = rows.filter((r) => r.pass !== null);
const failures = autoRows.filter((r) => !r.pass);
const manual = rows.filter((r) => r.manual_review);
const summary = {
  generated_at: new Date().toISOString(),
  base_url: BASE,
  wcag: { normal_text: 4.5, large_text: 3.0 },
  pages: PAGES.map((p) => ({ name: p.name, path: p.path })),
  measured_elements: rows.length,
  auto_judged: autoRows.length,
  passed: autoRows.length - failures.length,
  failed: failures.length,
  manual_review: manual.length,
  notes,
};
const payload = { summary, failures, manual_review: manual, rows };
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n', 'utf8');

console.log(`实测页面 ${PAGES.length} 个；元素 ${rows.length} 个（自动判定 ${autoRows.length}，人工复核 ${manual.length}）`);
console.log(`WCAG AA：普通文本 4.5:1，大字号 3.0:1 —— 通过 ${summary.passed}，不达标 ${summary.failed}`);
if (failures.length) {
  console.log('\n不达标明细（元素 → 对比度 → 是否达标）：');
  for (const r of failures) {
    console.log(`  [${r.page}] ${r.element} 「${r.text}」 ${r.foreground} on ${r.background} `
      + `${r.contrast}:1（阈值 ${r.threshold}:1，${r.font_size_px}px/${r.font_weight}）→ 不达标`);
  }
} else {
  console.log('所有可自动判定的文本均达到 WCAG AA。');
}
for (const note of notes) console.log(`注意：${note}`);
console.log(`\n完整明细：${OUT}`);
process.exitCode = failures.length ? 1 : 0;

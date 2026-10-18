/**
 * 维度 6 探针：前端质量（控制台错误、请求失败、无障碍基线、键盘可达性）。
 * 用法：node 测_无障碍与控制台.mjs [http://127.0.0.1:5173]
 * 只读：不修改任何业务文件，结论打印到 stdout。
 */
import { chromium } from 'playwright';

const BASE = process.argv[2] || 'http://127.0.0.1:5173';
const PAGES = [
  { path: '/ask', name: '提问台', sel: '#q' },
  { path: '/answer', name: '答案与证据', sel: 'text=【回答】' },
  { path: '/graph', name: '知识图谱', sel: '.gnode' },
  { path: '/history', name: '历史记录', sel: '.hrow, table tbody tr' },
];

const consoleErrors = [];
const failedReqs = [];
const issues = [];

const browser = await chromium.launch();
const ctx = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(`${page.url()} :: ${m.text().slice(0, 160)}`); });
page.on('pageerror', (e) => consoleErrors.push(`PAGEERROR ${e.message.slice(0, 160)}`));
page.on('requestfailed', (r) => failedReqs.push(`${r.url().slice(0, 80)} :: ${r.failure()?.errorText}`));

for (const p of PAGES) {
  const t0 = Date.now();
  await page.goto(BASE + p.path, { waitUntil: 'networkidle', timeout: 30000 });
  try { await page.waitForSelector(p.sel, { timeout: 20000 }); } catch { issues.push(`${p.name}：关键元素 ${p.sel} 未出现`); }
  const ms = Date.now() - t0;

  const meta = await page.evaluate(() => {
    const unlabeled = (sel) => Array.from(document.querySelectorAll(sel)).filter((el) => {
      const t = (el.innerText || '').trim();
      const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';
      const labelled = el.getAttribute('aria-labelledby');
      return !t && !aria && !labelled;
    }).length;
    const imgs = Array.from(document.images);
    return {
      lang: document.documentElement.lang || '',
      title: (document.title || '').slice(0, 40),
      h1: document.querySelectorAll('h1').length,
      buttons: document.querySelectorAll('button').length,
      unlabeledButtons: unlabeled('button'),
      inputs: document.querySelectorAll('input,textarea,select').length,
      unlabeledInputs: unlabeled('input,textarea,select') + Array.from(document.querySelectorAll('input,textarea,select')).filter((el) => !(el.labels?.length || el.getAttribute('aria-label') || el.placeholder)).length,
      imgs: imgs.length,
      imgsNoAlt: imgs.filter((i) => !i.hasAttribute('alt')).length,
      landmarks: document.querySelectorAll('main,nav,header,footer,[role=main],[role=navigation]').length,
      skipLink: !!document.querySelector('a[href^="#"]'),
    };
  });
  issues.push(`${p.name}：${ms}ms lang=${meta.lang || '(空)'} title=${meta.title} h1=${meta.h1} 无语义按钮=${meta.unlabeledButtons} 无标签表单=${meta.unlabeledInputs} img无alt=${meta.imgsNoAlt}/${meta.imgs} 地标=${meta.landmarks}`);
  if (!meta.lang) issues.push(`${p.name}：<html> 缺 lang`);
  if (!meta.title) issues.push(`${p.name}：缺 title`);
  if (meta.h1 !== 1) issues.push(`${p.name}：h1 数量 ${meta.h1}（期望 1）`);
  if (meta.imgsNoAlt) issues.push(`${p.name}：${meta.imgsNoAlt} 张图缺 alt`);
  if (meta.unlabeledButtons) issues.push(`${p.name}：${meta.unlabeledButtons} 个按钮无可访问名`);
}

// 键盘可达性：Tab 前 8 次，检查焦点是否可见
await page.goto(BASE + '/ask', { waitUntil: 'networkidle' });
const focusTrace = [];
for (let i = 0; i < 8; i++) {
  await page.keyboard.press('Tab');
  const info = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      name: (el.innerText || el.getAttribute('aria-label') || el.placeholder || el.id || '').trim().slice(0, 24),
      outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0,
      shadow: cs.boxShadow !== 'none',
      ring: !!(cs.getPropertyValue('--focus-ring')),
    };
  });
  if (info) focusTrace.push(info);
}
const noVisible = focusTrace.filter((f) => !f.outline && !f.shadow && !f.ring);
if (noVisible.length) issues.push(`键盘焦点不可见：${noVisible.map((f) => f.tag + '/' + f.name).join(', ')}`);

console.log('=== 页面基线 ===');
issues.filter((i) => !i.startsWith('键盘')).forEach((i) => console.log('  ' + i));
console.log('\n=== 控制台错误 ===');
console.log(consoleErrors.length ? consoleErrors.map((e) => '  ' + e).join('\n') : '  无');
console.log('\n=== 失败请求 ===');
console.log(failedReqs.length ? failedReqs.map((e) => '  ' + e).join('\n') : '  无');
console.log('\n=== 键盘焦点轨迹（前 8 次 Tab）===');
console.log('  ' + focusTrace.map((f) => `${f.tag}${f.outline || f.shadow ? '✓' : '✗'}`).join(' '));
const hard = issues.filter((i) => /缺 lang|缺 title|h1 数量|缺 alt|无可访问名|未出现|焦点不可见/.test(i));
console.log('\n=== 结论 ===');
console.log(`  硬问题 ${hard.length} 项；控制台错误 ${consoleErrors.length} 条；失败请求 ${failedReqs.length} 条`);
if (hard.length) console.log(hard.map((h) => '  !! ' + h).join('\n'));

await browser.close();

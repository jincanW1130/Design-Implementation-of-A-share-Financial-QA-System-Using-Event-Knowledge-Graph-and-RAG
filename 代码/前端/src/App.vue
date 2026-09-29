<script setup>
// 代码\前端\src\App.vue —— 应用外壳：顶栏（系统名／数据截至／四个导航项）＋ 路由出口
//
// 顶栏的「数据截至」取自 `GET /api/config/meta` 的 `data_cutoff_time`，取日期部分，
// 固定显示为「数据截至：YYYY-MM-DD」（《24》硬约束 12／F3）。
// 该元信息通过 provide 下发给四个页面，避免每页各拉一次。
//
// 第一版**不启用登录**：顶栏没有任何登录／用户入口（非目标 3、格式决策 6）。

import { onMounted, provide, reactive } from 'vue'
import { getConfigMeta, getHealth } from './api.js'

const appMeta = reactive({
  datasetVersion: '',
  dataCutoffTime: '',   // 原始 ISO 字符串（带 +08:00 偏移）
  backendOk: null,      // 后端健康状态：true／false／null（未知）
  error: '',
})
provide('appMeta', appMeta)

/** 取 ISO 时间的日期部分（`2026-09-25T23:59:59+08:00` → `2026-09-25`）。 */
function datePart(iso) {
  return typeof iso === 'string' && iso.length >= 10 ? iso.slice(0, 10) : '—'
}

const nav = [
  { to: '/ask', label: '提问' },
  { to: '/graph', label: '图谱查看' },
  { to: '/history', label: '历史记录' },
]

onMounted(async () => {
  try {
    const { data } = await getConfigMeta()
    appMeta.datasetVersion = data.dataset_version || ''
    appMeta.dataCutoffTime = data.data_cutoff_time || ''
  } catch (e) {
    appMeta.error = `读取配置元信息失败：${e.message}`
  }
  try {
    const health = await getHealth()
    appMeta.backendOk = !!(health && health.status === 'ok')
  } catch (e) {
    appMeta.backendOk = false
  }
})
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-name">A股信息披露问答系统</span>
        <span class="brand-sub" v-if="appMeta.datasetVersion">数据集 {{ appMeta.datasetVersion }}</span>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-link">
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="cutoff">
        <span class="cutoff-label">数据截至：{{ datePart(appMeta.dataCutoffTime) }}</span>
        <span class="dot" :class="{ ok: appMeta.backendOk === true, bad: appMeta.backendOk === false }"></span>
      </div>
    </div>
    <p v-if="appMeta.error" class="topbar-warn">{{ appMeta.error }}</p>
  </header>

  <main class="page">
    <RouterView />
  </main>
</template>

<!-- 全局基础样式（非 scoped）：原生 CSS，不引入任何 UI 组件库 -->
<style>
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #1f2328;
  --ink-soft: #57606a;
  --line: #d8dee4;
  --accent: #1a56db;
  --accent-soft: #e8effd;
  --warn-bg: #fff8e6;
  --warn-line: #d4a72c;
  --err-bg: #fdeeee;
  --err-line: #c0392b;
  --ok: #1a7f37;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.6 "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, sans-serif;
}
a { color: var(--accent); }
code, .mono { font-family: Consolas, "Courier New", monospace; }
.page { max-width: 1080px; margin: 0 auto; padding: 20px 16px 64px; }
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 16px 18px; margin-bottom: 16px;
}
.card > h2 { margin: 0 0 12px; font-size: 15px; }
.btn {
  display: inline-block; border: 1px solid var(--line); background: #fff; color: var(--ink);
  border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer;
}
.btn:hover { background: #f0f2f5; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: #1546b0; }
.btn.primary:disabled { background: #9db4e6; border-color: #9db4e6; cursor: not-allowed; }
input[type="text"], textarea, select {
  border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font: inherit;
  background: #fff; color: var(--ink); width: 100%;
}
.muted { color: var(--ink-soft); }
.tag {
  display: inline-block; border: 1px solid var(--line); border-radius: 999px;
  padding: 1px 8px; font-size: 12px; color: var(--ink-soft); background: #fafbfc;
}
.err {
  background: var(--err-bg); border: 1px solid var(--err-line); border-radius: 6px;
  padding: 10px 12px; color: #7d2016;
}
.empty {
  background: #f2f4f7; border: 1px dashed var(--line); border-radius: 6px;
  padding: 14px; color: var(--ink-soft); text-align: center;
}
.warnbox {
  background: var(--warn-bg); border: 1px solid var(--warn-line); border-radius: 6px;
  padding: 10px 12px; color: #7a5b00;
}
table.grid { width: 100%; border-collapse: collapse; }
table.grid th, table.grid td {
  border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top;
}
table.grid th { color: var(--ink-soft); font-weight: 600; font-size: 12px; }
</style>

<style scoped>
.topbar { background: #fff; border-bottom: 1px solid var(--line); }
.topbar-inner {
  max-width: 1080px; margin: 0 auto; padding: 10px 16px;
  display: flex; align-items: center; gap: 20px;
}
.brand { display: flex; flex-direction: column; line-height: 1.25; }
.brand-name { font-weight: 700; font-size: 16px; }
.brand-sub { font-size: 12px; color: var(--ink-soft); }
.nav { display: flex; gap: 4px; margin-left: auto; }
.nav-link {
  text-decoration: none; color: var(--ink-soft); padding: 6px 12px; border-radius: 6px;
  font-size: 14px;
}
.nav-link:hover { background: #f0f2f5; color: var(--ink); }
.nav-link.router-link-active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.cutoff { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.cutoff-label { font-size: 13px; color: var(--ink-soft); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #c9ced6; }
.dot.ok { background: var(--ok); }
.dot.bad { background: var(--err-line); }
.topbar-warn { max-width: 1080px; margin: 0 auto; padding: 0 16px 8px; color: #7d2016; font-size: 12px; }
</style>

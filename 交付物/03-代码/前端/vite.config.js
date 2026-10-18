// 交付物/03-代码\前端\vite.config.js —— Vite 开发服务器配置（第 9 阶段 T9）
//
// 两项固定口径（《24-第9阶段任务书》第4.3节 与 第六节 格式决策）：
//   * dev server 端口固定 **5173**（《24》第2.4节 必固化 3）；
//   * `proxy`：`/api` → `http://127.0.0.1:8000`（后端 uvicorn 默认端口），
//     前端**只调 `/api/*`**，不直连模型与数据库（硬约束 2／14）。
//
// 本文件**不含任何密钥、模型端点或数据库连接串**：代理目标是本机回环地址与端口，
// 属可公开的部署信息，不构成凭据（硬约束 2 只约束密钥与会话凭据）。

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：默认回环 8000；如需改端口用环境变量 VITE_BACKEND_ORIGIN 覆盖（不写字面量到源码里）
const BACKEND_ORIGIN = process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // 2026-10-18 修复：dev server 会监听**整个前端目录**，而 `测试/uat/` 下有 node_modules、
    // 证据截图与编辑器原子写产生的 `.xxx.tmpdir/`。实测过一次真崩溃：编辑器在
    // `测试/uat/` 下写临时文件时，chokidar 触发 `EBUSY: resource busy or locked` → FSWatcher
    // 抛错 → **整个 vite 进程退出（exit 1）**，5173 直接不可用（答辩现场若发生等同演示中断）。
    // 故显式排除测试资产与构建产物：它们不被产品代码 import，无需热更新。
    watch: {
      ignored: [
        '**/测试/**',
        '**/dist/**',
        '**/.git/**',
        '**/*.tmpdir/**',
      ],
    },
    proxy: {
      '/api': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        // 问答链路 10～30 s，代理超时放宽到 120 s，避免长请求被 dev server 掐断
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
  build: {
    outDir: 'dist',
    // 构建产物不进仓库（.gitignore 已覆盖 交付物/03-代码/前端/dist/，硬约束 23）
    sourcemap: false,
    // 2026-10-11（复评「兼容性」整改）：显式声明构建目标，取代 Vite 默认的
    // 'modules'（其基线随 Vite 版本漂移、无文档口径）。es2020 ＝ Chrome 80+／
    // Edge 80+／Firefox 75+／Safari 13.1+（2020 年起的 evergreen 浏览器基线），
    // 与本项目的语法面（可选链／空值合并等 ES2020 特性）匹配；**不支持 IE**。
    // 口径与浏览器矩阵的完整登记见同目录 `兼容性口径与矩阵.md`。
    target: 'es2020',
  },
})

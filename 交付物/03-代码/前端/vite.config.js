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
  },
})

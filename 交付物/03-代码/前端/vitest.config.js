// 交付物/03-代码\前端\vitest.config.js —— 前端单元测试配置（P1-12 补测 · G 组）
//
// 为什么单开一份而不是并进 vite.config.js：
//   * `vite.config.js` 的职责是**开发服务器与构建**（端口 5173、/api 代理、产物目录），
//     它被 `npm run dev` / `npm run build` 直接使用，改它等于动交付路径；
//   * 测试只用到 `environment: jsdom`，不需要 dev server、不需要代理。
//   `mergeConfig` 让测试复用同一份 `@vitejs/plugin-vue`（`.vue` 组件在测试里也能被编译），
//   同时**不启动**任何服务器、**不发起**任何真实网络请求。
//
// 环境决策：`environment: 'jsdom'` —— `api.js` 用到 `window.localStorage`／`window.crypto`／
// `fetch`，这三样在 jsdom 里都有；测试里一律用 `vi.stubGlobal('fetch', …)` 装**替身**，
// 因此本套测试**离线**（与 Python 侧 `conftest.forbid_network` 的纪律一致）。

import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    include: ['测试/**/*.test.js'],
    // 不写到 `前端/` 之外；产物目录不进版本库（.gitignore 已覆盖 前端/dist/）
    reporters: ['default'],
    globals: false,
  },
}))

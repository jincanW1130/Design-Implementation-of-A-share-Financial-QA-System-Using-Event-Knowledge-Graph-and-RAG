# 交付物/03-代码/前端/测试/ —— 前端单元测试（vitest，离线）

> **一句话**：本目录是前端（Vue 3 ＋ Vite）**唯一的单元测试**入口，测的是 `src/` 下
> **可离线验证的纯函数与纯逻辑**（API 层错误分支、图谱数据构造与几何、滚动入场判据）。
> 与 `交付物/03-代码\测试\`（Python pytest，测后端／检索／问答／数据准备／抽取与图谱）
> **并列而不重叠**：一个管 Python 侧的系统行为，一个管前端侧的纯逻辑。

对应外部评审 **B-06**（"建议为前端补 vitest 用例（`api.js` 的 `ApiError` 分支）"）；
Python 侧的原登记见 `交付物/03-代码\测试\README.md` 第五节「没覆盖什么」。

---

## 一、怎么跑

```powershell
# 推荐：一键入口（已设好 Node 路径、汇总退出码）
powershell -File 交付物/03-代码/前端/运行前端测试.ps1

# 或直接：
cd 交付物/03-代码/前端
npm test              # = vitest run（跑一次即退）
npm run test:watch    # 监听模式（开发时用）
```

* 依赖：`vitest@3.2.7` ＋ `jsdom`（已登记进 `前端/package.json` 的 `devDependencies`）。
* 首次需 `npm install`（`node_modules` 已在工作区，但换机后要重装）。
* **完全离线**：`fetch` 一律用 `vi.stubGlobal` 装替身，绝不发真实网络请求
  （与 Python 侧 `conftest.forbid_network` 的同一条纪律）。
* 配置在 `前端/vitest.config.js`：`environment: 'jsdom'`，`include: ['测试/**/*.test.js']`。
  它用 `mergeConfig` 复用 `vite.config.js` 的 `@vitejs/plugin-vue`，但**不启动**任何 dev server。

### 本机实测读数（2026-10-10 实跑）

| 测试文件 | 用例数 | 结果 |
| --- | --- | --- |
| `测试/api.test.js` | 29 | 通过 |
| `测试/graph.test.js` | 29 | 通过 |
| `测试/reveal.test.js` | 9 | 通过 |
| **合计** | **67** | **67 passed（失败 0）** |

---

## 二、文件

| 文件 | 作用 |
| --- | --- |
| `api.test.js` | G1–G7 组：`src/api.js` —— `ApiError` 三条失败分支、信封解析、query 拼装、会话标识、23 个接口路径 |
| `graph.test.js` | G8–G10 组：`src/lib/graph.js` —— 常量表、半径分级、形状 SVG、`buildDataset`（度数／分量／中心／跳数／路径） |
| `reveal.test.js` | G 组：`src/lib/reveal.js` —— 视口入场判据、隐藏视图跳过、错位入场序号、去抖、`bound` 守卫 |

---

## 三、覆盖了什么

### G1–G2 · `ApiError` 与 `request()` 的三条失败路径（评审 B-06 点名的分支）

* `fetch` 抛异常（后端未起／断网）→ `ApiError(code=0)`，message 含方法与 URL；
* 响应体非 JSON（代理 502 页面）→ `ApiError(code=0)`，原文摘要进 message，带 HTTP 状态；
* HTTP 非 2xx 且响应体带 `code` → 取**后端 code 优先于 HTTP 状态**，并带 httpStatus；
* HTTP 200 但响应体带 `code` → 仍判为错误（后端错误信封一律 `{code,message}`）；
* 无 message 时兜底「请求失败（HTTP xxx）」，code 取 HTTP 状态；
* **负向标定**：HTTP 200 且无 code → 正常返回 `data`，不得误判为错误。

### G3–G5 · 成功路径 / `requestMeta` / `getHealth`

* 成功信封取 `data`；空响应体返回 `null`；
* GET 不带 body／Content-Type；带 body 时自动加 `Content-Type` 与 JSON 序列化；
* query 拼装：跳过 `undefined`/`null`、保留空串、**URL 编码**（空格 → `%20`）；
* `withSession=true` 自动带 `session_id`；URL 前缀**恒为 `/api`**（不写后端主机名）；
* `requestMeta` 返回 `{data, meta}`；`getHealth` 返回**原始对象**（非信封）。

### G6 · 会话标识

* 首次生成 36 字符 UUID 并落 `localStorage`，复用同一值；
* `crypto.randomUUID` 不可用时走兜底，仍是 UUID v4 形态（版本位 4、变体位 ∈ {8,9,a,b}）；
* `localStorage` 被禁用时退化为内存态（不抛错）。

### G7 · 接口清单路径（与后端表 4-13 一一对应）

23 个导出接口逐一断言 URL 形态与必需参数（含问答三接口、证据与原文、历史、图谱、
实时数据区四接口）。

### G8–G10 · `graph.js` 常量与 `buildDataset`

* `REL`（8 条关系中文名）、`TYPE`（7 类节点）、`LABEL2TYPE`（7 类标签）、`DOMAIN`、`EXT`；
* `RELNAME` 未命中时原样返回（不猜）；`typeOfLabel` 未知标签兜底 `doc`；
* `radiusOf` 分级＋钳位（公司 +2）；`shapeSVG` 七种形状、默认 opacity、未知类型兜底；
* `buildDataset`：度数、**连通分量**、**分量中心（度最高者）**、**跳数（从中心起算）**、
  孤立节点 `dist=99`、悬挂边丢弃、边下标重编、路径枚举（1 跳 = 边数、2 跳按首尾相接）、
  时间空值归一、**确定性**（两次构造逐值一致）、**不改写入参**。

### G（reveal）· 滚动入场判据

* 命中视口（`top < 0.94H` 且 `bottom > -60`）加 `.in`；边界按**严格不等号**（负向标定）；
* 隐藏视图（`offsetParent === null`）内的项跳过；已 `.in` 的不重复处理；
* 错位入场 `--d` 按兄弟序号 × 55ms；同一帧去抖只排一次；
* `initReveal` 首次绑定监听并立即排帧；`bound` 守卫防止重复绑定。

---

## 四、没覆盖什么（如实登记）

| 没覆盖的部分 | 为什么没覆盖 |
| --- | --- |
| **`.vue` 组件的渲染与交互**（`App.vue`、四个 `views/*.vue`、三个 `components/*.vue`） | 需要 `@vue/test-utils` ＋ 组件挂载；本次目标是评审 B-06 点名的**纯逻辑**。组件级测试属"需要起服务／真实浏览器"的覆盖面 |
| **`mountGraph` 的 DOM 渲染与指针交互** | 需真实 SVG 布局与 pointer 事件序列；本次只测它的**纯函数**（`buildDataset` 等）。**如实登记为待办** |
| **`mountField`（背景股票曲线）** | 依赖 `<canvas>` ＋ `requestAnimationFrame` 渲染循环；纯视觉动画，无业务判据 |
| **真实后端联调**（25 个接口端到端、限流、CORS） | 要起后端进程，属第 9 阶段门禁（`工具\验收第9阶段.py`）的覆盖面 |
| **`vite build` 产物正确性** | 属构建门禁；本目录只保证源码层纯逻辑 |
| 端到端"文档—产物一致性" | 那是 `工具\` 下验收脚本的职责，两者**分工不重叠**、都要跑 |

---

## 五、给论文 6.4「功能测试」的用法

* 一张表：**用例组 → 被测文件 → 覆盖的契约 → 用例数 → 结果**（本文件第三节的分组可直接引用）；
* 前端侧可写进正文的**取证方式**：
  1. **错误分支可区分**：`ApiError` 的三条失败路径（网络层／非 JSON／后端 code）各有独立
     断言与可展示 message，说明"失败也有明确语义"；
  2. **契约可区分**：`request()` 的"成功信封取 data"与"错误信封抛 ApiError"由负向标定分开，
     不是恒真断言；
  3. **确定性**：`buildDataset` 两次构造逐值一致；`reveal` 的入场判据按严格不等号可复现。

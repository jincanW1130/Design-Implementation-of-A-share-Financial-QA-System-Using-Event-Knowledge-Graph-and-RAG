# 交付物/03-代码\前端 —— A股信息披露问答系统前端（Vue 3 ＋ Vite）

第 9 阶段（前后端系统集成）T9／T10 的前端产物。四类页面：**提问**／**答案与证据**／**图谱查看**／**历史记录**。

## 一、技术栈与版本（锁定，见 `package.json`）

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| `vue` | 3.5.13 | 视图层（Composition API ＋ `<script setup>`） |
| `vue-router` | 4.5.0 | 四条路由（history 模式） |
| `vite` | 6.0.11 | 开发服务器（5173）与构建 |
| `@vitejs/plugin-vue` | 5.2.1 | 单文件组件编译 |

**不引入**任何被《02》第8.4节 排除的技术：无 UI 组件库套件、无大型可视化框架（图谱可视化用**轻量自绘 SVG**，见 `views/GraphView.vue`）；样式用原生 CSS。
`package-lock.json` 随仓库提交（硬约束 23）；`node_modules\` 与 `dist\` 不入库（已在 `.gitignore`）。

## 二、启动方式

```bat
cd 交付物/03-代码\前端
npm install
npm run dev      :: 开发服务器，默认 http://127.0.0.1:5173
npm run build    :: 产出 dist\（静态托管用）
npm run preview  :: 预览构建产物
```

**前置条件**：后端在 `http://127.0.0.1:8000` 运行（`python 交付物/03-代码\后端\run.py`）。

### 与后端的连通方式

`vite.config.js` 里配置了开发代理：**`/api` → `http://127.0.0.1:8000`**。
因此前端**只请求同源的 `/api/*`**，不直连大模型、不直连数据库，也不在源码／构建产物里出现任何密钥、模型端点或数据库连接串（硬约束 2／14）。
后端地址可用环境变量 `VITE_BACKEND_ORIGIN` 覆盖（默认回环 8000）。

## 三、页面清单与取数接口

| 路由 | 视图 | 取数接口 |
| --- | --- | --- |
| `/ask` | `views/AskView.vue` 提问页 | `POST /api/qa/ask`（体：`question`／`session_id`，固定 C 组） |
| `/answer/:answerId` | `views/AnswerView.vue` 答案与证据页 | `GET /api/qa/answers/{id}`、`GET /api/evidence/{id}`、`GET /api/evidence/{id}/graph-path` |
| `/graph` | `views/GraphView.vue` 图谱查看页 | `GET /api/graph/entities`、`/entities/{id}/neighbors`、`/paths`、`/events`、`/events/{id}` |
| `/history` | `views/HistoryView.vue` 历史记录页 | `GET /api/history`、`GET /api/history/{question_id}` |
| 全局顶栏 | `App.vue` | `GET /api/config/meta`（数据截至）、`GET /api/health`（后端状态） |

复用组件（`src/components/`）：

| 组件 | 职责 |
| --- | --- |
| `AnswerSections.vue` | 答案四段渲染：按 `【回答】`／`【证据来源】`／`【知识图谱路径】`／`【数据截至与判定区间】` **固定段头**切分；**缺段显式提示**；出现「模型分析（非公开事实）」时同屏提示 |
| `EvidenceList.vue` | 证据按四类分组（回答来源／新闻来源／公告来源／相关事件）；每条提供「查看原文上下文」→ `GET /api/documents/{doc_id}/chunks/{chunk_id}` |
| `GraphPathPanel.vue` | 图谱路径可读化：「节点 —关系（role/confidence/source_doc_id/source_chunk_id）→ 节点」；未使用图谱扩展时显示**固定字样**「本次回答未使用图谱扩展」 |

## 四、与后端的接口约定

1. **响应信封**：成功 `{ "data": …, "meta": { "dataset_version": …, "data_cutoff_time": … } }`；错误 `{ "code": …, "message": … }`。
2. **错误处理**：`src/api.js` 的 `request()` 把非 2xx 或含 `code` 的响应体抛成 `ApiError(code, message)`；`message` 来自后端、**可直接展示**（不显示裸的「请求失败」）。
3. **空结果不是错误**：`2002` 的语义是 **HTTP 200 的空结果**。图谱空查询、历史空列表按正常业务状态处理，页面给「未检索到匹配结果」提示，**不是**错误样式。
4. **会话**：首次访问用 `crypto.randomUUID()` 生成 `session_id` 存 `localStorage`，所有请求自动带上（格式决策 6）。**不显示登录入口**（第一版不启用登录）。
   * **历史记录按会话隔离**（FR-06）：新访客的会话是全新的 UUID，因此「历史记录」页**初始为空**（提示「未检索到匹配结果」），在本会话里提问后才会出现记录。库中既有的 30 条记录属于 `session_id = S-001`，不会串到浏览器会话里。
5. **数据截至**：所有涉及相对时间的区域固定显示「数据截至：YYYY-MM-DD」，取自 `data_cutoff_time` 的日期部分。
6. **问答固定 C 组**：`/api/qa/ask` 的请求体只含 `question` 与 `session_id`，前端**不提供**任何 A～E 组切换入口。

## 五、已知限制

* **无浏览器自动化**：本环境无 Playwright／Selenium，页面的可用性以「构建成功 ＋ dev server 200 ＋ 代理联通 ＋ 组件内对每个接口的调用点清单」为证据，**未做真实浏览器点击验证**（作者目视验收）。
* **SVG 可视化规模上限**：环形布局在约 40 个节点内可读性良好，超过 60 个节点标签会拥挤（`GraphView.vue` 会在节点数 > 60 时给出提示）。不引入力导向库是《24》格式决策 5 的要求。
* **图谱路径回看不重渲染**：历史回看按设计**只还原三表内容**，不重新渲染当时的图谱路径视图（`graph_path_available` 只做布尔提示）。
* **中文检索词的编码**：在 GBK 控制台下用命令行手工拼 URL 时，中文需 `--data-urlencode` 或 `encodeURIComponent`；页面内由 `fetch` 自动编码，无此问题。

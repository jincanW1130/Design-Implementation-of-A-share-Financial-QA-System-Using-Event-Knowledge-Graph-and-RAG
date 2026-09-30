# 前端设计原型（OpenDesign 产出）

> **性质**：这是第 9 阶段系统前端的**视觉设计原型**（浏览器可直接打开的单文件 HTML），不是 `代码\前端\` 的 Vue 实现本身。
> 它由 **OpenDesign**（本地守护进程）生成并交付，本目录是**固化副本**，以免 OpenDesign 工作区被清理后丢失。

| 版本 | 文件 | OpenDesign 项目 | 说明 |
| --- | --- | --- | --- |
| **v2（当前）** | `index.html`（124 287 字节） | `ashare-qa-redbull`「A股问答系统前端·红色牛市版（复刻 Jesper × DSH）」 | 作者 2026-09-30 指定方向：**复刻 `jesperlandberg.com` × `deepseek.com/harness`，红色为主，股票与牛元素，背景为动态上升的股票曲线** |
| v1（留痕） | `_v1_赛博霓虹\index.html`（122 709 字节） | `ashare-qa-cyber-frontend`「A股问答系统前端·赛博红牛版」 | 第一版「赛博霓虹」方向，**作者明确表示不满意**，仅作过程留痕，不作为交付 |

当前版交付文档 SHA-256：`6989b02738d8addda72b88cb2cbb563dd05f53d2f232525345f6504a1af6a32d`
（与 OpenDesign 工作区原件**逐字节一致**）

---

## 一、需求（作者 2026-09-30）

> 复刻 `http://jesperlandberg.com/` 和 `https://www.deepseek.com/harness/`，二者结合，以红色为主，
> 添加股票元素、牛元素。背景要动态不断波动上升的股票曲线。

## 二、被复刻的两个参考站（我从两站真实源码里抠出的设计 DNA，写进了设计任务书）

**A. `jesperlandberg.com`** —— 复刻**版式与动效语言**：
`@font-face` 里的 **ABCDiatype 可变 grotesk**（一个 `font-weight: 200 1000` 覆盖全字重）、
源码实值 `.label{font-size:1rem;font-weight:500;text-transform:uppercase}` 的**全大写微标签**、
超大 display 标题（`clamp()`）＋ 紧字距紧行高、细线分隔的**大行列表**、
以及滚动进入动效／marquee／自定义光标；近单色底 ＋ **只允许一个强调色**。

**B. `deepseek.com/harness/`** —— 复刻**产品落地页骨架与设计令牌**：
吸顶 header（品牌／导航／实心主按钮）、hero（「预览版」徽章 ＋ 超大主张句）、
产品窗口 mockup（侧栏「新会话／插件／自动化任务／工作区」＋ 对话转录）、能力卡片分区、页脚；
令牌实值 `--ds-color-bg-dark:#1a1615`、`--ds-color-bg-page:#f9f8f8`、
`--ds-color-brand:#4d6bfe`（**本版替换为红 `#E63946`**）、`--ds-btn-primary-bg:#1a1615`；
以及那个**只在 `@media (hover:hover) and (pointer:fine)` 才显示的 canvas 流场背景**——
本版由**股票曲线 canvas** 承担同一角色。

## 三、核验结论（决策者独立复核，**不采信生成方自报**）

复核脚本：`阶段09-前后端系统集成\_工作底稿\决策者核验\核验_前端设计原型v2.py`（**43 项全部通过、退出码 0**）：

- **基本形态**：完整 HTML；**零外部依赖**（唯一 URL 是 SVG namespace）；无 CDN；无外部图片；单 `<script>`；
- **复刻 A**：全大写微标签、`clamp()` 超大标题、负字距、紧行高、marquee 关键帧、IntersectionObserver、自定义光标、`#E63946` 出现 **20 处**（强调色收敛）；
- **复刻 B**：吸顶 header、「预览版」徽章、「开箱即用」主张句、`#1a1615` 令牌、产品窗口侧栏项、55 处 grid、字体栈保留 `Host Grotesk／DM Sans／Montserrat`；
- **背景曲线**：`<canvas>` ＋ `requestAnimationFrame` ＋ 页面隐藏暂停 ＋ `devicePixelRatio` ＋ `prefers-reduced-motion` 静态回退 ＋ **上升漂移**与**动量项**参数 ＋ 红色辉光与线下渐变 ＋ 画布透明度受限；
- **色彩**：红的三档分工（`#E63946` 面积／`#FF3B30` 小字／`#C8102E` 承载白字的实心面）；**全文件扫描六位色值后，绿色有且只有 `#22C55E`**（阴线与跌幅专用）；
- **股票与牛**：跑马灯／600519／成交量／换手率／市盈率／MA5／阳线／阴线 ≥5 类；牛头为 `<symbol id="bull">` ＋ `<use>` 复用；
- **系统口径**：四个固定段头**逐字**、「本次回答未使用图谱扩展」逐字、数据截至 `2026-09-25`、证据四类齐备、含 `deepseek-flash`、历史回看「不重新渲染」提示、提问框占位文案逐字；
- **布局与可访问性**：`minmax(0,1fr)` 栅格、**不使用 `100vw`**、**无 >1400px 固定宽**、`min-width:0` 4 处、marquee 轨道裁剪、`overflow-x:auto` 只出现在窄屏 nav、5 处媒体查询、`role="tabpanel"` / `aria-selected`。

## 四、背景曲线的实现（生成方给的参数，已逐项核验存在）

`<canvas>` 覆盖视口（`position:fixed;inset:0;z-index:0`），内容层 `z-index:1`，画布整体不透明度 0.5。
**环形缓冲区 ＋ 相机偏移**：每帧右端追加新点、左端丢点；点间距 1.6px，水平速度约 96px/s，
**上升漂移 −0.22px/点**（900 点跨度累计约 +198px，即趋势向上），随机波动 ±2.6px/点再叠**动量项**（权重 0.42、±1.7）。
分层绘制：48px 网格 → 24 点 SMA 均线 → 线下渐变填充 → 红色主线（`lineWidth 2`、`shadowBlur 12`）。
相机用**死区钳制**（基线只在均值越出 `[0.28H, 0.72H]` 时以 0.05 系数缓回），
避免恒定系数回归把「整体上升」抹平成水平线；步进按 `dt/16.67` 归一，高刷屏观感一致。

## 五、已知限制（如实登记）

1. **未做真实浏览器渲染验证**：本机无浏览器自动化，OpenDesign 的截图导出只在桌面运行时可用
   （两版生成方都实测到 `screenshot export is only available in the desktop runtime`）。
   因此「1440px 无横向滚动」是**结构证据**（无 `100vw`、无超宽固定宽、有 `min-width:0` 与裁剪容器）
   而非目视结论——**请作者在浏览器里过一眼**。
2. **原型是设计稿，不是 `代码\前端\` 的 Vue 实现**：落到工程需要一次「设计 → 组件」的移植
   （拆 `views\`／`components\`、把色板与字体栈落成 CSS 变量、把内联 SVG 提成组件、把 canvas 曲线做成组件）。
   **本次未做移植**，属延后项。
3. **文案与数字是演示样例**：行情、证据、图谱节点均为贴近课题的构造样例，**不得作为任何读数引用**。
4. v1 与 v2 均为单文件（122KB／124KB），超出「单文件约 1000 行」的常规约束（为满足自包含要求而保持不拆）。

## 六、怎么打开

- **OpenDesign 预览**（需守护进程在跑）：`http://127.0.0.1:7456/api/projects/ashare-qa-redbull/raw/index.html`
- **本地直接打开**：双击本目录的 `index.html`（零外部依赖，无需服务器）。
- 本地文件：`阶段09-前后端系统集成\前端设计原型\index.html`

# -*- coding: utf-8 -*-
"""把《29-第11阶段产出文档（毕业论文）.md》导出为 Word 成稿《王锦灿_20234225193_题目.docx》。

用途
----
《29》是本课题论文的 Markdown 全文草稿。学校论文模板（仓库根 `刘元_…docx`，同门已提交的
学位论文，格式即校方要求）已下发，本脚本按模板实测规格产出**提交件**。脚本**只做格式转换**：
不改写、不增补、不删除论文正文一个字；被剔除的只有三类工作留痕——文首元数据块
（题目下的引用块＋`| 项 | 取值 |` 元数据表）与两处「修订记录」区块（第七章内的
`## 修订记录`、文末的 `# 修订记录`）。题目本身不丢，它被排到封面上。
**新增页面（声明页）与封面字段值不属于「论文正文」**：前者是模板要求的固定表格件，
后者是论文题目页；二者都由本脚本的常量产出，详见下面「模板下发后改哪里」。

纪律（重要）
------------
1. 产物 `交付物/01-论文/提交件/王锦灿_20234225193_基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现.docx`
   （`OUT_REL`）**由本脚本生成，不得手改**；`--out` 仍可覆盖产出路径。
   要改内容请改《29》（或它上游的 `交付物/01-论文/_分章源文件/`），然后**重跑本脚本**。
   直接在 Word 里改产物，下一次重跑即被覆盖。
2. **确定性**：同一份《29》两次运行，产物**逐字节一致**（sha256 相同）。做法有三条：
   ① `core_properties` 的 created／modified／last_modified_by／revision 全部写固定哨兵值，
   不用 `datetime.now()`；② 正文里不写任何生成时间戳；③ python-docx 保存时会把**当前
   时间**写进 OOXML 包（zip）的条目时间，故保存后由 `_repack_deterministic()` 把整包的
   条目时间统一重写为 1980-01-01 并固定压缩方式与外部属性。少了第 ③ 条，两次运行的
   sha256 必然不同。
3. 编码 UTF-8 无 BOM、换行 LF（脚本本身与它读写的文本文件）。
4. 图片**解析不到就非零退出**，绝不静默跳过。

本次修复记录（2026-10-10，五处；旧行为／新行为／为什么）
--------------------------------------------------------
1. **一级标题全丢**（最严重，旧自检没抓到）。旧行为：`split_sections()` 把 `#` 一级块摘出去
   只当区段名用，区段块列表里只剩二三级块，`render_blocks()` 因而一个 Heading 1 也没写——
   源侧 13 个 `#`，成稿 Heading1=0。旧自检之所以没抓到：它比对的 `stats["h1"]` 也是从块列表
   数出来的，两边一起漏。新行为：一级块留在自己区段块列表的首位，照常渲染；题目段整段仍被
   剔除（题目文字排在封面）。为什么：一级块是论文正文的一部分，不是区段标签。
2. **修订记录只剔了一处**。旧行为：只按「一级标题文本 == 修订记录」剔了文末那一处，第七章里的
   `## 修订记录` 连同它的整张修订表被当正文渲染进了成稿（实测「修订记录」出现 9 次，其中 4 次
   来自该残留表与残留标题）。新行为：**任何层级**标题文本恰为「修订记录」的标题块，以及它之后
   直到下一个标题块之前的全部块，一律剔除（两处表随之剔除），实测 0 个整段命中、交叉引用 5 次
   原样保留。为什么：两处都是工作留痕，且「修订记录」标题在论文里不该出现。
3. **残留字面 `**` × 2 与反引号 × 6**。定位：`**` 全部来自三级标题里的行内加粗
   （`### …（**与正式集方向相反**）`）；反引号有 4 处来自表题里的行内等宽
   （`表 6-11 … 即 `gold_hop_depth ≥ 1``），另 2 处来自行内**嵌套**——
   `**主 judge 的 `kimi-k3` 端点…**` 这种「加粗里套等宽」被 `INLINE_RE` 整段当成一个
   `**…**` 记号，剥掉外层 `**` 后把内层反引号原样吐了出来。旧行为：标题与表题走
   `doc.add_paragraph(text)` 裸文本路径（不过行内解析）。新行为：标题、表题、图题一律走
   `add_inline()`，且 `add_inline()` 对内层文字**递归**再解析（内层仍可能含反引号／斜体）。
   为什么：行内标记不是正文，任何进入成稿的文字都要过同一套行内解析。
4. **归一化等价性判据本身不成立**（它从来、也不可能通过）。旧判据把源文件原文（含 `#`、`>`、
   `|`、`**`、反引号、`![]()` 目标、`<p align>` 外壳、围栏、`---`）去空白后直接当期望文字，
   而成稿里这些标记本就不存在。新行为：新增 `strip_md_lines()`，按**行**把源侧 Markdown 标记
   剥成「渲染后会落进成稿的纯文字」（行内部分与 `_inline_plain()` 同源），再与成稿读回文字比对。
   为什么这不算放松判据：期望文字仍然**逐字来自源文件**（不是来自解析后的块，所以「丢正文」
   与「凭空造正文」都仍会被抓住），被剔的两类工作留痕按**行号**排除，题目行由封面文字承接；
   被剥掉的只是标记本身——`#`／`>` 是块首标记（文字不丢）、`|` 是分隔符（单元格文字不丢）、
   `| --- |` 是表头分隔行（无文字）、`![alt](path)` 的 path 与 `<p align>` 里的 PNG 路径是资产
   落点（图题由 alt 承担）、围栏与 `---` 是版式记号、行内标记由 `add_inline()` 转成字形。
   失败时打印差集：逐处给出「源侧多出（疑似丢正文）」与「成稿多出（疑似凭空造字）」，并回指
   源文件行号。
5. **自检补强**（旧自检漏掉了上面这一类）。见 `verify()`：标题数与源侧对应数、结构基线逐级比对；
   内嵌插图数 == 9 且 `word/media/` 条目数 == 9；表格数按两个口径断言（甲=连续 `|` 行成块数，
   乙=带表题的表块数）；字面标记零命中（`**`／反引号／`<p align=`／`| --- |`／`](`／`](http`）；
   「修订记录」无整段命中且交叉引用次数不变；文首元数据特征串零命中（**「文档编号」除外**——
   它是正文六张 `document` 表的字段名，命中几十次属正常，只打印不做失败判据）；插图解析规则
   必须全为规则①；TOC 域、PAGE 域、zip 条目时间固定值一并断言。
6. **模板规格断言**（第二批新增）。见 `verify()`：页边距四边 == 3.00 cm；章标题样式 16pt 且
   eastAsia == 黑体；参考文献条目样式 12pt；图题／表题样式仍 10.5pt；`摘  要`／`目  录` 带两个
   全角空格（**实测是半角，见第三批改动 3**）；声明页标题与 `本人郑重声明` 正文存在；节数 == 3 且第 2 节 `w:start="1"`；
   第 1 节页脚无 PAGE 域而全篇页脚里至少有一个 PAGE 域。全部写进同一条「自检不过不写盘」。

模板下发后改哪里
----------------
只改下面「格式参数」一节的常量（字体、字号、行距、页边距、首行缩进字符数、图宽上限、
参考文献悬挂缩进、页脚字号、封面字段值、声明页文字、`RENDER_TEXT_MAP` 渲染文本映射）。
版式逻辑不必动：全部排版都挂在**样式对象**上，换模板时改这些常量即可。

本次修改记录（2026-10-10 第二批，模板对齐；旧行为／新行为／为什么）
------------------------------------------------------------------
1. **页边距**。旧行为：上下 2.54／左 3.17／右 2.54 cm（python-docx 默认值微调）。
   新行为：四边一律 `MARGIN_* = Cm(3.00)`。为什么：模板实测 `w:pgMar` 四边同为 1701
   twips ＝ 3.00 cm，学校装订要求左右留白一致。`TEXT_WIDTH` 由三个常量推导，自动跟随。
2. **章标题字号**。旧行为：`SIZE_H1 = Pt(15)`（小三）。新行为：`Pt(16)`（三号）。
   为什么：模板章标题 `w:sz` ＝ 32 半磅 ＝ 16pt、eastAsia 黑体。**只改常量**，`setup_styles()`
   的排版逻辑一行没动（字号始终由「格式参数」常量注入样式）。
3. **参考文献条目字号**。旧行为：复用 `SIZE_CAPTION`（10.5pt 五号）。新行为：新增常量
   `SIZE_REF = Pt(12)` 并让「参考文献条目」样式改用它。为什么：模板参考文献条目是 12pt 小四，
   与图名／表名（五号）不同号；旧实现把它和图题共用一个常量，导致「改一处、动两处」。
   拆成独立常量后，图名／表名仍走 `SIZE_CAPTION`，二者互不牵连。
4. **前置部分标题写法**。旧行为：`# 摘要` 原样渲染成「摘要」、目录标题写死「目录」。
   新行为：新增 `RENDER_TEXT_MAP`「渲染文本映射」常量，渲染时把「摘要」换成「摘  要」、
   「目录」换成「目  录」（两个字之间两个全角空格 U+3000——**这一句是错的，实测为两个半角
   空格 U+0020 ×2，见第三批改动 3；原记录保留不改**）。为什么：模板的前置标题是
   字距拉开的写法；**《29》源文件里的标题文字不能改**（那是 Markdown 交付物，门禁脚本按它
   断言，改了会红），所以映射只发生在渲染侧。`_inline_plain()`／`strip_md_lines()` 走同一个
   映射，期望文字一侧同步，归一化等价性自检不受影响（映射是确定性字符串替换，不含空白，
   `_norm()` 去空白后两侧仍然逐字相等）。「参考文献」「致谢」按模板体例保持原写法。
5. **声明页**。旧行为：无。新行为：封面之后、摘要之前新增一页 `声  明`，含模板体例的
   声明正文与两行留空落款（`签  名：____`／`日  期：____`）。为什么：模板封面之后确有这一页，
   是学位论文的固定表格件。**落款一律留空**：模板里是别人已签的姓名与日期，抄进来等于伪造，
   故只保留下划线待作者本人签署。声明页文字是模板固定件（不是论文正文），故由 `STATEMENT_*`
   常量产出并计入「期望文字」，不违反「不改写正文」。
6. **封面填真实信息**。旧行为：六个字段全是 `__________` 占位。新行为：填入作者提供的真实值
   （学院／学号／姓名／指导教师／完成日期），**专业一栏作者未提供，保持下划线待填**（不推测）。
   为什么：模板阶段封面必须落真名真号才能交。`COVER_FIELDS` 仍是唯一改动点。
7. **产出路径改为提交件**。旧行为：`交付物/01-论文/30-毕业论文（成稿·Word）.docx`。
   新行为：`交付物/01-论文/提交件/王锦灿_20234225193_题目.docx`（校方文件名体例
   `姓名_学号_题目.docx`），并**删除旧落点**，不留两份互相竞争的成稿。为什么：学校按文件名
   体例收件；两份同名不同路径的成稿迟早会被交错修改。`--out` 仍可覆盖路径。
8. **分节编页**。旧行为：全篇 1 节、1 个页脚，页码从头连续编到尾。新行为：3 节——封面／声明／
   摘要／Abstract／目录为第 1 节（**不显示页码**，`footer` 显式清空），目录之后插分节符，
   正文第一章起为第 2 节，页脚 PAGE 域且 `w:pgNumType w:start="1"` **重新从 1 编号**。
   为什么：模板实测 14 节／3 个页脚，前置部分与正文分别编页、正文首页 `w:start="1"`。
   模板前置部分是罗马数字（`w:fmt="upperRoman"`），但任务只取到「前置与正文分别编页」这一
   层信息，故按更保守的「前置不显示页码」处理——宁缺勿造。实现方式见 `_add_restart_pgnum()`
   与 `_add_sections()`；这不是「写个 Word 认不出的域充样子」，`w:pgNumType` 是 Word 原生
   分节页码属性，域仍是标准 PAGE 域。

本次修改记录（2026-10-10 第三批，模板逐字对齐；旧行为／新行为／为什么）
--------------------------------------------------------------------
1. **声明正文改回模板逐字原文**（本批最重要）。旧行为：`STATEMENT_BODY` 是第一轮的**改写稿**
   （140 字，另起一套措辞，还多一句「本人完全意识到本声明的法律结果由本人承担。」）。新行为：
   整段换成仓库根模板 `刘元_…docx` 里那一段的**逐字原文**（124 字，两个半角空格之外的每一个
   标点都照抄），并把它的 sha256 固化成常量 `STATEMENT_BODY_SHA256`、在 `verify()` 里现场断言。
   为什么：声明是**法定表格件**，措辞由校方给定，改写＝换了一份声明；第一轮注释写「按任务书
   文字执行，故保留现状」是判断错误——任务书要的是「照模板」，不是「另写一版」。
2. **封面「专业」填真值**。旧行为：`专　　业：__________`（第一轮派单时作者未提供，占位待填）。
   新行为：`专　　业：软件工程`。为什么：模板阶段封面必须落真值才能交件，六字段不得留占位。
3. **修正一处说谎的注释**（字符串本身不动）。旧行为：`RENDER_TEXT_MAP` 的注释写「两个全角空格」，
   实测是**两个半角空格 U+0020 ×2**——模板 `摘  要` ＝ `[0x6458,0x20,0x20,0x8981]`，本产物逐码点
   相同。新行为：注释与打印标签一律改为「两个半角空格（U+0020 ×2），与模板逐字一致」。
   为什么：半角才是与模板逐字一致的那一版，错的是注释；同类误述（`声  明`／`目  录` 的注释与
   断言消息）一并改正，**常量里的字符一个都没动**。
4. **一级标题分页：确认已有 + 立「分页来源唯一」不变式**。旧行为：`Heading 1` 样式**已经**带
   `pageBreakBefore`（第二批就做了），所以「章不另起页」这个判断不成立——实测成稿
   `word/document.xml` 里 `w:br w:type="page"` 共 **0** 个，Word 渲染后「第一章 绪论」在正文
   首页、「第二章 相关技术」另起一页。新行为：把该属性提成显式常量 `H1_PAGE_BREAK_BEFORE`
   （值仍为 True），并给每个「另起一页的段落」立下**恰好一个分页来源**的不变式。为什么：
   显式分页符与样式级分页同时作用于同一个一级标题会多出一页空白；本轮新增的两个分节符
   （分节符本身就是分页）落在哪个一级标题前面，哪个标题的样式级分页就用段落级
   `w:pageBreakBefore w:val="0"` 关掉（见 `_suppress_page_break()`）——即「让样式只作用于
   该作用的地方」。`verify()` 会逐个数出每个一级标题前面的分页来源个数并断言 == 1。
5. **页眉**。旧行为：全篇无页眉。新行为：新增常量 `HEADER_TEXT`（`姓名：题目`，姓名与封面／
   元数据同源，见 `AUTHOR_NAME`）与「页眉」样式（宋体五号居中，`SIZE_HEADER`），挂在第 2 节
   （摘要＋Abstract＋目录）；第 3 节（正文）沿用模板节 8～14 的「继承上一节」写法，故正文各页
   同样有页眉。**封面与声明不显示页眉**：第 1 节不带任何 `w:headerReference`，且它是首节、
   无处可继承。为什么：模板实测页眉 `刘元：基于Spring Boot…` 挂在节 4，封面与声明所在的前三节
   都没有页眉。注：模板页眉的字体字号本轮未取到，按宋体五号居中做（**推定值**）；其 header
   样式实测为 9pt（小五）居中且带下边框，若要严格对齐改 `SIZE_HEADER` 一处即可。
   （**本条的推定值已在第四批改动 3 落实**：`SIZE_HEADER` 改 `Pt(9)`，并给「页眉」样式加了
   模板同款的 `w:pBdr/w:bottom`；原记录保留不改。）
6. **页码体例改成模板样式（2 节 → 真 3 节）**。旧行为：2 节——第 1 节（封面…目录）页脚显式
   清空，第 2 节（正文）页码 `w:start="1"` 从 1 起，页脚只有一个裸 PAGE 域。（第二批记录第 8 条
   写的是「3 节」，实际实现只有 2 节，本条把它落实。）新行为：3 节——
   ① 封面＋声明：无页眉、无页码（页脚显式清空）；
   ② 摘要＋Abstract＋目录：有页眉，`w:pgNumType w:fmt="upperRoman" w:start="1"`（大写罗马数字，从 I 起）；
   ③ 正文第一章…致谢：有页眉，`w:pgNumType w:start="1"`（省略 `w:fmt` ＝十进制，与模板节 7 同款），
      页码重新从 1 起。
   **页脚文字体例一律 `- N -`**（短横线＋空格＋PAGE 域＋空格＋短横线，见 `FOOTER_LEAD`／
   `FOOTER_TAIL`）；罗马数字与阿拉伯数字都由 `w:fmt` 交给 Word 渲染，脚本**不把页码算成文字**。
   （**本条的两个空格已在第四批改动 4 去掉**：模板 footer1.xml 的 runs 是 `['-','45','-']`，
   即 `-N-` 体例；原记录保留不改。）
   为什么：模板实测节 1～6 `w:fmt="upperRoman"`、节 7 起 `w:start="1"`（十进制），页脚文字
   `['-','45','-']`，即短横线夹 PAGE 域。
7. **GBK 控制台崩溃**。旧行为：脚本打印 `✓`／`✗`，在默认 GBK 的 Windows 控制台直接
   UnicodeEncodeError 崩掉，必须调用方先设 `PYTHONIOENCODING=utf-8` 才能跑。新行为：脚本开头
   按本项目既有做法（见 `工具/验收第11阶段.py`）把 `sys.stdout`／`sys.stderr` 重设为 UTF-8。
   为什么：脚本不该要求调用方记得设环境变量；`reconfigure` 不可用时（老解释器）不致命，故
   try/except 包住，静默跳过。

本次修改记录（2026-10-10 第四批，超页插图切块＋四处模板对齐＋写盘健壮性；旧行为／新行为／为什么）
------------------------------------------------------------------------------------------
1. **超页插图切成多块面板跨页排**（本轮主缺陷）。旧行为：插图一律只按**宽度**上限缩放到
   `IMG_MAX_WIDTH`（14.6cm），**不看高度**；三张 `flowchart TB` 长竖向流程图的源 PNG
   纵横比分别低到 0.163／0.514／0.242，折成 14.6cm 宽后高度达 **89.69／28.42／60.23 cm**，
   是版心高（`TEXT_HEIGHT` ＝ 29.7 − 3.0 − 3.0 ＝ 23.70cm）的 3.8／1.2／2.5 倍：Word 渲染后
   整页只有图、图题被挤到下一页、图的下半截跑到页外，打印必被截断。
   新行为：导出时**在内存里**用 Pillow 把超页图按「墨迹极小值行」切成 K 块面板，逐块嵌入；
   源 PNG 一个字节都不改、不落盘、不改图号；第 1 块用原图题，第 k≥2 块图题为
   `原图题（续 k/K）`。为什么切在墨迹最小行：流程图的行墨迹剖面在**节点之间的连接线**处
   最细，取墨迹最小的行下刀就不会把节点框拦腰切开（算法见 `plan_panels()`）。
2. **写盘被 Word／WPS 占用时给可操作提示**（健壮性）。旧行为：产物正被 Word／WPS 打开时
   `open(out_path, "wb")` 抛裸 `PermissionError: [Errno 13]` traceback，用户只看到栈回溯。
   新行为：`write_product()` 分「打开阶段／写入阶段」捕获 `OSError`，打印可操作提示
   （关闭 Word／WPS 后重跑；打开阶段失败时明说「一个字节都没写、产物未被改动」），退出码 3。
   为什么：这是 Windows 上最常见的失败，脚本必须自解释而不是扔栈回溯；**不吞异常**，
   报完就返回，不继续往下走。
3. **页眉字号与下边框**。旧行为：`SIZE_HEADER = Pt(10.5)`（五号）、无边框。
   新行为：`Pt(9)`（小五），并给「页眉」样式加模板同款 `w:pBdr/w:bottom`
   （`w:val="single" w:color="auto" w:sz="6" w:space="1"`）。为什么：模板页眉样式
   （styleId 9，`w:name="header"`）实测 `<w:sz w:val="18"/>` ＝ 9pt、
   `<w:jc w:val="center"/>`、`<w:pBdr><w:bottom w:val="single" w:color="auto" w:sz="6"
   w:space="1"/></w:pBdr>`。
4. **页脚字号与字面空格**。旧行为：`SIZE_FOOTER = Pt(10.5)`、页脚文字 `- 1 -`
   （`FOOTER_LEAD = "- "`／`FOOTER_TAIL = " -"`）。新行为：`Pt(12)`（小四）、
   `FOOTER_LEAD = "-"`／`FOOTER_TAIL = "-"`，页脚三个 run 的文字形如 `['-','1','-']`。
   为什么：模板 `word/footer1.xml` 的 run 级 rPr 实测 `w:sz="24"`（12pt）且 ascii／hAnsi／cs
   三个字体属性全是 Times New Roman，文字 runs 为 `['-','45','-']`——短横线与页码之间
   **没有**字面空格。注：模板 footer **样式**（styleId 8）自带的是 9pt，12pt 来自 run 级 rPr；
   本产物把 12pt 同时写进「页脚页码」样式与 run，两个口径一致、读回自验。
5. **正文行距改固定值 20 磅**。旧行为：正文段落继承 `Normal` 的 1.5 倍行距。
   新行为：新增常量 `LINE_SPACING_BODY = Pt(20)`，**只**给「正文段落」样式设
   `line_spacing = Pt(20)`（python-docx 写成 `w:line="400" w:lineRule="exact"`）。
   为什么：模板正文样式「0毕设正文」实测 `<w:spacing w:line="400" w:lineRule="exact"/>`
   ＝ 固定值 20 磅（400 二十分之一磅）。标题／图题／表题／代码块／引文／参考文献条目／
   页眉页脚的行距**一处都没动**。
6. **自检跟着改**：插图那一条从「内嵌 9 == media 9 == 基线 9」改成三层——① 源侧插图数
   （9 张源图）**单独断言**；② 各图面板数由切图结果**现场推导**，断言
   `内嵌图片数 == word/media 条目数 == 面板总数`；③ 图题段数：**有文字**的「图题」段
   == 面板总数（「图题」样式段总数 == 2×面板总数：每块面板另有一个承载图片的段）。
   另新增读回断言：逐张内嵌图高度 ≤ 版心高 23.70cm、续图标记图题计数、页眉字号 9pt 与
   下边框 `w:pBdr/w:bottom`、页脚字号 12pt、正文段落 `w:line="400" w:lineRule="exact"`。
7. **期望文字同步切块图题**。新行为：`strip_md_lines()` 与 `expected_norm()` 多收一个
   `fig_text_by_line`（源行号 → 该行图题的期望文字），把切块后**每块一份**的图题
   （第 k≥2 块带「（续 k/K）」）按渲染顺序拼好补进期望文字。
   为什么：成稿里每块面板都有一个图题段，归一化等价性自检若不按同一口径补，会把重复出现的
   图题当成「成稿凭空造字」而误报失败（实测第一次跑就是这么红的）。

用法
----
    python 工具\\导出论文docx.py                       # 生成提交件，打印统计与 sha256
    python 工具\\导出论文docx.py --out 试跑.docx        # 覆盖产出路径（试跑／确定性核对用）
    python 工具\\导出论文docx.py --check                # 只核对磁盘产物是否与现场生成逐字节一致
    python 工具\\导出论文docx.py --keep-code-backticks  # 代码块保留 PowerShell 续行反引号（默认并句去掉）

注意 `--keep-code-backticks` 是排查用的开关：它保留的反引号会命中「成稿 0 反引号」这条断言，
脚本会非零退出且不写盘。这是刻意设计——产物不允许残留 Markdown 标记。

退出码：0 成功；1 自检或 --check 不一致；2 源文件／图片等输入缺失；3 写盘失败（产物被
Word／WPS 占用等）。

关于 PDF 阅读副本
-----------------
本脚本只产 docx。若本机装有 Word，可用下面这条命令另出一份 PDF（不进版本库、不改 docx）：

    $w = New-Object -ComObject Word.Application; $w.Visible = $false
    $d = $w.Documents.Open("<docx 绝对路径>", $false, $true)      # 第三参 = 只读
    $d.ExportAsFixedFormat("<pdf 绝对路径>", 17)                   # 17 = wdExportFormatPDF
    $d.Close(0); $w.Quit()
"""

import argparse
import collections
import datetime
import hashlib
import io
import math
import os
import re
import sys
import zipfile

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.image import Image as DocxImage
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

# 切图用的图像库（第四批改动 1）：numpy 算逐行墨迹剖面、Pillow 读图与在内存里裁块。
# 二者都是**硬依赖**：缺了就非零退出（`build()` 抛 RuntimeError，`main()` 转成退出码 2），
# 绝不静默跳过切图——跳过会让「内嵌图高度 ≤ 版心高」这条自检直接失败，反而更难定位。
try:
    import numpy as _np
    from PIL import Image as _PILImage
    _IMAGING_ERROR = None
except ImportError as _exc:                      # pragma: no cover
    _np = None
    _PILImage = None
    _IMAGING_ERROR = _exc

# 控制台编码（第三批改动 7）：Windows 默认 GBK 控制台打印 `✓`／`✗` 会 UnicodeEncodeError
# 直接崩，本脚本原先要求调用方先设 `PYTHONIOENCODING=utf-8` 才能跑。按本项目既有做法
# （见 `工具/验收第11阶段.py`）在进程内把 stdout／stderr 切到 UTF-8，脚本自己负责自己的编码。
# `reconfigure` 在极老的解释器上不存在，失败不致命，故 try/except 静默跳过。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_REL = "交付物/01-论文/29-第11阶段产出文档（毕业论文）.md"
# 提交件落点：校方文件名体例 `姓名_学号_题目.docx`
OUT_REL = ("交付物/01-论文/提交件/"
           "王锦灿_20234225193_基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现.docx")
# 被本落点取代的旧落点：脚本跑完自动删除，避免两份成稿互相竞争（见「本次修改记录 7」）
STALE_OUT_REL = ("交付物/01-论文/30-毕业论文（成稿·Word）.docx",)
SRC = os.path.join(ROOT, SRC_REL.replace("/", os.sep))
OUT = os.path.join(ROOT, OUT_REL.replace("/", os.sep))
STALE_OUTS = [os.path.join(ROOT, r.replace("/", os.sep)) for r in STALE_OUT_REL]

TITLE = "基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现"

# =============================================================================
# 格式参数（学校模板下发后改这里）
# =============================================================================
FONT_TITLE_CN = "黑体"           # 各级标题中文字体
FONT_BODY_CN = "宋体"            # 正文中文字体
FONT_LATIN = "Times New Roman"   # 西文与数字字体
FONT_MONO = "Consolas"           # 代码等宽字体（西文）
FONT_MONO_CN = "宋体"            # 代码里的中文字体

SIZE_H1 = Pt(16)                 # 一级标题（章标题）：三号 ← 模板实测 16pt 黑体
SIZE_H2 = Pt(14)                 # 二级标题（节标题）：四号 ← 模板已合
SIZE_H3 = Pt(12)                 # 三级标题（小节标题）：小四 ← 模板已合
SIZE_BODY = Pt(12)               # 正文：小四 ← 模板已合
SIZE_CAPTION = Pt(10.5)          # 图题／表题／引文／代码：五号 ← 模板已合
SIZE_TABLE = Pt(10.5)            # 表格内容：五号 ← 模板已合
SIZE_REF = Pt(12)                # 参考文献条目：小四 ← 模板实测 12pt（与图题不同号，独立常量）
SIZE_FOOTER = Pt(12)             # 页脚页码：小四 ← 模板 footer1.xml 的 run 级 w:sz=24（12pt）
SIZE_COVER_TITLE = Pt(22)        # 封面题目：二号
SIZE_COVER_LABEL = Pt(18)        # 封面文体标签：小二
SIZE_COVER_FIELD = Pt(14)        # 封面字段：四号

LINE_SPACING = 1.5               # 倍数行距：标题、引文、封面、目录说明、参考文献条目等
# 正文段落的行距**固定 20 磅**（第四批改动 5）：模板「0毕设正文」实测
# `<w:spacing w:line="400" w:lineRule="exact"/>`（400 二十分之一磅 ＝ 20pt，lineRule=exact）。
# python-docx 里给 `paragraph_format.line_spacing` 赋一个 Length（而不是数字）就会写成
# 「固定值」——赋 `Pt(20)` 即得上面的 XML。**只有「正文段落」样式用它**，别处仍走 LINE_SPACING。
LINE_SPACING_BODY = Pt(20)       # 正文段落：固定值 20 磅
LINE_SPACING_TIGHT = 1.0         # 表格、题注、代码行距
FIRST_LINE_CHARS = 200           # 正文首行缩进：2 字符（w:firstLineChars，不是固定磅值）
SPACE_BEFORE = Pt(0)             # 正文段前
SPACE_AFTER = Pt(0)              # 正文段后
H1_BEFORE, H1_AFTER = Pt(12), Pt(12)
H2_BEFORE, H2_AFTER = Pt(12), Pt(6)
H3_BEFORE, H3_AFTER = Pt(6), Pt(6)

PAGE_WIDTH = Cm(21.0)            # A4
PAGE_HEIGHT = Cm(29.7)
MARGIN_TOP = Cm(3.00)            # ← 模板实测 w:pgMar 四边均为 1701 twips ＝ 3.00 cm
MARGIN_BOTTOM = Cm(3.00)
MARGIN_LEFT = Cm(3.00)
MARGIN_RIGHT = Cm(3.00)
TEXT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT   # 15.00cm（随页边距常量自动跟随）
TEXT_HEIGHT = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM  # 23.70cm（版心高；插图高度的硬上限）
IMG_MAX_WIDTH = Cm(14.6)         # 插图宽度上限（不超过正文宽度）
IMG_MAX_WIDTH_CM = 14.6          # 同上，厘米浮点口径（切图算术用，与上一行同源）
TEXT_HEIGHT_CM = 23.70           # 同上，厘米浮点口径（断言内嵌图高度不许超过它）
REF_HANGING = Cm(0.74)           # 参考文献悬挂缩进
QUOTE_INDENT = Cm(0.74)          # 引文块左右缩进
CODE_INDENT = Cm(0.74)           # 代码块左缩进
LIST_INDENT = Cm(0.74)           # 列表项左缩进

# ---- 超页插图切块（第四批改动 1）----
# 版心高 23.70cm 里留 0.30cm 余量：一块面板按宽度上限渲染时高度不得超过 MAX_PANEL_H_CM。
# 留余量的原因：Word 计算行高时会算上段前段后与图片基线的行距，贴着版心高做会在个别
# 字号／字体替换（缺字体的机器）下溢出到页外；0.30cm 的余量对这类抖动足够。
MAX_PANEL_H = Cm(23.4)           # 单块面板高度上限（版心高 − 0.30cm 余量）
MAX_PANEL_H_CM = 23.4            # 同上，厘米浮点口径（切图算术用，与上一行同源）
INK_THRESHOLD = 200              # 灰度 < 200 记为该行「有墨迹」（阈值来自实测：流程图的
                                 # 连线与节点框都是深色，200 足以把它们与白底分开）
INK_WINDOW_RATIO = 0.12          # 切点搜索窗口：等分位置 h*k/K 的 ±12%
MIN_PANEL_PX = 32                # 相邻面板最小像素高（避免切出空块／退化块）
MAX_PANEL_K = 24                 # 自适应块数上限：防病态图把「K+1 直到装得下」拖成死循环
CONT_SUFFIX_FMT = "（续 %d/%d）"  # 续图标记，接在第 k(≥2) 块的原图题之后，k 与 K 都是 1 基

H1_ALIGN = WD_ALIGN_PARAGRAPH.CENTER   # 一级标题：居中（二三级左对齐，二者择一，见报告）
H2H3_ALIGN = WD_ALIGN_PARAGRAPH.LEFT

# ---- 渲染文本映射（模板写法 ↔ 源文件写法；只改显示文本，不动《29》一个字）----
# 为什么要有这张表：校方模板的前置部分标题写作「摘  要」「目  录」（两字之间**两个半角空格
# U+0020 ×2**），而《29》是 Markdown 交付物、其标题文字被门禁脚本按字面断言，**源文件不能改**。
# 因此把差异收敛到渲染侧：装配时按本表替换显示文本，读回自检的期望文字一侧走同一个映射
# （见 `_render_text()` 的三处调用），两侧同源，等价性判据毫发无损。
# 注意映射值是**确定性字符串替换**且不含空白字符，`_norm()` 去空白后两侧仍逐字相等。
# 「参考文献」「致谢」模板未单独取到样式，按模板体例保持原写法，故不入表。
RENDER_TEXT_MAP = {
    "摘要": "摘  要",      # 两个半角空格（U+0020 ×2），与模板逐字一致
    "目录": "目  录",      # 两个半角空格（U+0020 ×2），与模板逐字一致
    "Abstract": "Abstract",   # 模板即 Abstract，原样（列出仅为自文档化）
}

# ---- 声明页（模板封面之后的一页固定表格件，非论文正文）----
# 落款一律留空：模板里是他人已签的姓名与日期，抄进来等于伪造，故只保留下划线待作者签署。
STATEMENT_TITLE = "声  明"           # 两个字之间两个半角空格（U+0020 ×2），与模板逐字一致
# 【第三批改动 1】声明正文＝仓库根模板 `刘元_…docx` 里那一段的**逐字原文**（124 字）。
# 旧行为是第一轮的**改写稿**（140 字，另起一套措辞，还多一句「本人完全意识到本声明的法律
# 结果由本人承担。」）。为什么必须改：声明是**法定表格件**，措辞由校方给定；改写＝换了一份
# 声明，等于伪造授权文本。任务书说的「照模板」就是照抄，不是另写一版。
# 逐字核对口径：`STATEMENT_BODY_SHA256` 是模板里该段文字的 sha256（`verify()` 现场断言）；
# 下面常量与模板该段实测逐字符一致（124 字），**结尾不留多余空格**。
# 关于第一轮为什么会写错：旧注释把「任务书文字」理解成了「另写一版措辞」，于是拿同义改写
# 替掉了模板原句。声明是法定件，同义改写就是另一份声明，故本轮改为逐字照抄。
# 逐字比对的实测口径（本轮验收现场跑过）：模板该段文字与本常量同为 124 字，sha256 同为
# a9b20452…2deaf，逐字符相同；旧改写稿是 140 字／85898780…20e6——两者差异一眼可见，
# 那正是本项改动要消灭的东西。
# 【不要动字符串】半角空格、全角标点、句末不留空格，都是「与模板逐字一致」的一部分；
# 真要改措辞请先改模板原件——本脚本只做格式转换，不改写任何文本。
#
STATEMENT_BODY = (
    "本人郑重声明：所呈交的学位论文，是本人在导师指导下，独立进行研究工作所取得的成果。"
    "尽我所知，除文中已经注明引用的内容外，本学位论文的研究成果不包含任何他人享有"
    "著作权的内容。对本论文所涉及的研究工作做出贡献的其他个人和集体，均已在文中以"
    "明确方式标明。")
STATEMENT_BODY_SHA256 = "a9b2045263618e543c66d5ae343557eef733cc83bbc4abab176221f1be62deaf"
STATEMENT_SIGN_LINES = (
    "签　　名：__________________",
    "日　　期：__________________",
)

TOC_INSTR = ' TOC \\o "1-3" \\h \\z \\u '   # 目录域：显示 1~3 级标题、超链接、隐藏页码域、使用大纲级别
TOC_DIRTY = True                            # 让 Word 打开时自动标记该域待更新
TOC_NOTE = ("说明：本目录为 Word 域，页码在刷新后自动生成。在 Word 中按 Ctrl+A 后按 F9"
            "（或右键→更新域）即可刷新目录与页码。")
TOC_PLACEHOLDER = "（目录域：请在 Word 中按 Ctrl+A 后 F9 刷新，页码将自动生成）"

COVER_LABEL = "本科毕业设计（论文）"
# 作者姓名：封面姓名栏、页眉「姓名：题目」、core_properties 作者三处同源，不各写一遍
AUTHOR_NAME = "王锦灿"
# 封面六字段：**真值**（作者本人提供）。第三批改动 2 把「专业」由下划线占位改为真值
# （第一轮派单时作者未提供，故留 `__________`；现补 `软件工程`），六栏不得再有占位。
COVER_FIELDS = [
    "学　　院：人工智能学院",
    "专　　业：软件工程",
    "学　　号：20234225193",
    "姓　　名：" + AUTHOR_NAME,
    "指导教师：徐文莉",
    "完成日期：2026年5月",
]

# ---- 页眉（第三批改动 5；模板实测：`姓名：题目`，挂在摘要所属的那一节，封面与声明没有页眉）----
# 文字与封面「姓名」栏、core_properties 作者同源（`AUTHOR_NAME`），题目复用 `TITLE`。
HEADER_TEXT = AUTHOR_NAME + "：" + TITLE
# 页眉字号／下边框（第四批改动 3）：模板页眉样式（styleId 9，`w:name="header"`）实测
# `<w:sz w:val="18"/>` ＝ 9pt（小五）、`<w:jc w:val="center"/>`、且带下边框
# `<w:pBdr><w:bottom w:val="single" w:color="auto" w:sz="6" w:space="1"/></w:pBdr>`。
# 旧行为是五号(10.5pt)且无边框——第三批把它记成「推定值」，本轮按模板实测值落实。
SIZE_HEADER = Pt(9)                         # 页眉：宋体小五居中（模板实测 9pt）
HEADER_BORDER = {"val": "single", "color": "auto", "sz": "6", "space": "1"}  # 下边框（模板同款）

# ---- 分节编页（第三批改动 6：2 节 → 真 3 节，对齐模板实测体例）----
# 模板实测：节 1～6 `w:pgNumType w:fmt="upperRoman"`（前置部分大写罗马数字），节 7 起
# `w:pgNumType w:start="1"`（正文十进制从 1 起），页脚文字形如 `-N-`。本稿按同一体例分 3 节：
#   ① 封面＋声明：无页眉、无页码（页脚显式清空）
#   ② 摘要＋Abstract＋目录：有页眉；页码大写罗马数字，从 I 起
#   ③ 正文第一章…致谢：有页眉（继承第 2 节）；页码十进制，重新从 1 起
SECTION_COUNT = 3                           # 期望节数
FRONT_FOOTER_BLANK = True                   # 第 1 节（封面＋声明）页脚显式清空：无页码
FRONT_PAGE_FMT = "upperRoman"               # 第 2 节页码格式：大写罗马数字（由 Word 渲染，非文字）
FRONT_PAGE_START = 1                        # 第 2 节从 I 起
BODY_PAGE_START = 1                         # 第 3 节（正文）重新从 1 起；`w:fmt` 省略 ＝ 十进制
BODY_PAGE_FMT = None                        # 与模板节 7 同款：不写 `w:fmt`，即十进制
FOOTER_LEAD = "-"                           # 页脚体例 `-N-`：短横线（与页码之间无字面空格）
FOOTER_TAIL = "-"                           # …＋短横线（模板 footer1.xml 的 runs 为 ['-','45','-']）
H1_PAGE_BREAK_BEFORE = True                 # 一级标题另起新页（第三批改动 4；本就是 True，提成常量）

# core_properties 的固定哨兵值（确定性要求：不得使用 datetime.now()）
CORE_CREATED = datetime.datetime(2000, 1, 1, 0, 0, 0)
CORE_MODIFIED = datetime.datetime(2000, 1, 1, 0, 0, 0)
CORE_REVISION = 1
CORE_AUTHOR = AUTHOR_NAME                    # 封面已落真名，元数据同步（同源常量）
CORE_LAST_MODIFIED_BY = "工具/导出论文docx.py"
CORE_COMMENTS = "由 工具/导出论文docx.py 从《29-第11阶段产出文档（毕业论文）.md》导出；本文件不得手改，改源后重跑脚本。"
CORE_KEYWORDS = "事件知识图谱;RAG;A股财经信息;智能问答"
CORE_SUBJECT = "本科毕业设计（论文）提交件"
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)       # OOXML 包条目时间（zip 最早可表示时间）

# 自检用的禁用串（术语红线与"格式转换不引入原文以外的词"）
FORBIDDEN_TERMS = ("向量数据库",)           # 四字连写术语，全文 0 命中
# 产物正文里不得残留的字面 Markdown 标记（`](` 已含 `](http`，两条都列出来是为了报告时逐条可见）
MARKUP_RESIDUE = ("**", "`", "<p align=", "| --- |", "](", "](http")

# 文首元数据块的特征串，分两张名单：
#   ① DROPPED_META_KEYS：用于「被剔除区命中了哪些键」的报告，也参与成稿命中数的打印；
#   ② META_RESIDUE_KEYS：**成稿里必须 0 命中**的特征串。
# 「文档编号」只在 ① 里：它是正文六张 `document` 表的字段名（实测正文命中 39 次），
# 拿它当失败条件必然误报——这是上一版处理对的地方，本次保持不动。
DROPPED_META_KEYS = ("文档编号", "所属阶段", "文档版本", "载体形态",
                     "章节目录依据", "拼装顺序", "读数口径", "术语口径")
META_RESIDUE_KEYS = ("所属阶段", "文档版本", "载体形态",
                     "章节目录依据", "拼装顺序", "读数口径", "术语口径")

# 结构基线：本版《29》应有的成稿结构。源文件结构若**有意**变化（增删章节／图／表），
# 必须在这里显式改数并说明原因；不显式改数就说明是无意漂移，脚本会非零退出。
#   H1 11 ＝ 源侧 13 − 题目 1（排到封面）− 文末修订记录 1
#   H2 44 ＝ 源侧 45 − 章内修订记录 1
#   H3 20 ＝ 源侧 20 − 0
#   表 43 ＝ 源侧 46 块 − 文首元数据表 1 − 两处修订记录表 2
#     （任务书里写的「源侧 46 → 成稿 44」是按「只剔文末那一处修订表」算的；两处表都剔之后
#      正确口径是 43，脚本按「源侧数 − 实际剔除数」现场推导并断言，不写死中间那个 44）
#   表题 38 ＝ 源侧带 `**表 x-y …**` 表题行的表块数（两处修订记录表与元数据表都无表题）
STRUCT_BASELINE = {"h1": 11, "h2": 44, "h3": 20, "tables": 43, "table_caps": 38, "images": 9}

# 前置区（在目录之前渲染的区段）：摘要与 Abstract 依源顺序排在目录前面
FRONT_SECTIONS = ("摘要", "Abstract")

# =============================================================================
# 解析
# =============================================================================
H_RE = re.compile(r"^(#{1,3})[ \t]+(.*?)[ \t]*$")
IMG_RE = re.compile(r"^!\[(.*?)\]\((.*?)\)[ \t]*$")
CAP_PATH_RE = re.compile(r"`([^`]+)`")
TABLE_CAP_RE = re.compile(r"^\*\*[ \t]*(表[ \t]*\d+[ \t]*[-–—][ \t]*\d+.*?)\*\*[ \t]*$")
SEP_ROW_RE = re.compile(r"^\|[\s:\-|]+\|$")
LIST_RE = re.compile(r"^\s*([-*+]|\d+[.、)])\s+\S")
REF_RE = re.compile(r"^\[\d+\]")
INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|~~.+?~~|\*[^*\n]+?\*)")
HANZI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
WS_RE = re.compile(r"\s+")

REVISION_TITLE = "修订记录"


def _read_text(path):
    """读文本：去 BOM、换行统一 LF。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _hanzi(text):
    """汉字数（CJK 基本区＋扩展 A）。"""
    return len(HANZI_RE.findall(text))


def _render_text(text):
    """渲染文本映射：源文件写法 → 模板写法（见 `RENDER_TEXT_MAP` 的说明）。

    只做**整串**替换，不做子串替换：`RENDER_TEXT_MAP` 的键都是标题全文（「摘要」「目录」），
    子串替换会误伤正文里恰好出现这两个词的句子（例如「摘要」出现在正文描述里），
    那就成了改写正文——本脚本一个字都不许动正文，所以宁可不替换也不能误替换。
    调用点共三处，渲染侧与期望文字侧同源：`_inline_plain()`、`add_inline()`、
    `strip_md_lines()` 的标题分支。
    """
    return RENDER_TEXT_MAP.get(text, text)


def _norm(text):
    """归一化：去掉全部空白，用于「成稿文字 == 源文字 − 被剔除区 − Markdown 标记」的等价性自检。"""
    return WS_RE.sub("", text)


def _split_row(row):
    """`| a | b |` → ['a', 'b']。"""
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parse_blocks(lines, keep_code_backticks=False):
    """把 Markdown 行解析成块序列。每个块带 src_span=(起始行, 结束行)（0 基、闭区间）。"""
    out = []
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s == "---":                       # Markdown 分隔线：版式记号，不是内容
            i += 1
            continue
        if s.startswith("<p align"):          # 图注行的 HTML 外壳：图题由 ![]() 的 alt 承担
            i += 1
            continue
        if s.startswith("```"):               # 围栏代码块
            lang = s[3:].strip()
            start = i
            i += 1
            body = []
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1                            # 跳过收尾围栏
            body = _normalize_code(body, keep_code_backticks)
            out.append({"kind": "code", "lang": lang, "lines": body,
                        "src_span": (start, i - 1)})
            continue
        m = H_RE.match(raw)
        if m:
            out.append({"kind": "h%d" % len(m.group(1)), "text": m.group(2).strip(),
                        "src_span": (i, i)})
            i += 1
            continue
        m = IMG_RE.match(s)
        if m:
            alt, target = m.group(1).strip(), m.group(2).strip()
            # 图注行（若有）紧随其后，中间可能隔空行；其反引号里的仓库根相对路径是解析的权威依据
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            cap_rel, cap_line = None, None
            if j < n and lines[j].lstrip().startswith("<p align"):
                mm = CAP_PATH_RE.search(lines[j])
                if mm:
                    cap_rel = mm.group(1).strip()
                cap_line = j
            out.append({"kind": "img", "alt": alt, "target": target, "cap_rel": cap_rel,
                        "src_span": (i, i), "cap_span": (cap_line, cap_line) if cap_line is not None else None})
            i = (cap_line + 1) if cap_line is not None else i + 1
            continue
        if s.startswith("|"):                 # 表格
            start = i
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            body_rows = [_split_row(r) for r in rows if not SEP_ROW_RE.match(r)]
            cap, cap_span = None, None
            if out and out[-1]["kind"] == "p":
                mm = TABLE_CAP_RE.match(out[-1]["text"])
                if mm:
                    cap = mm.group(1).strip()
                    cap_span = out[-1]["src_span"]   # 表题行的行号：剔除该表时表题行要一并剔除
                    out.pop()                  # 表题从正文段落提升为表题段（表题在表上方）
            out.append({"kind": "table", "rows": body_rows, "caption": cap, "cap_span": cap_span,
                        "ragged": len({len(r) for r in body_rows}) > 1,
                        "src_span": (start, i - 1)})
            continue
        if s.startswith(">"):                 # 引用块
            out.append({"kind": "quote", "text": s[1:].strip(), "src_span": (i, i)})
            i += 1
            continue
        if REF_RE.match(s):                   # 参考文献条目（悬挂缩进）
            out.append({"kind": "ref", "text": s, "src_span": (i, i)})
            i += 1
            continue
        if LIST_RE.match(raw):                # 列表项：标记原样保留，只做版式缩进
            out.append({"kind": "list", "text": s, "src_span": (i, i)})
            i += 1
            continue
        out.append({"kind": "p", "text": s, "src_span": (i, i)})
        i += 1
    return out


def _normalize_code(body, keep_code_backticks):
    """代码块：默认把 PowerShell 续行反引号并句（去反引号、接成一行），使产物 0 反引号。

    代码块的等宽字体（代码块样式）与内容语义不变：并句只吃掉行尾的续行反引号，
    文字一个不丢（`strip_md_lines()` 用同一口径剥离源侧，见该函数注释）。
    """
    if keep_code_backticks:
        return list(body)
    out = []
    for line in body:
        stripped = line.rstrip()
        if stripped.endswith("`"):
            if not out:
                out.append(stripped[:-1])
            else:
                out[-1] = out[-1] + " " + stripped[:-1]
        else:
            out.append(line)
    joined = "\n".join(out)
    if "`" in joined:
        raise ValueError("代码块内存在非续行反引号，无法在「产物 0 反引号」前提下原样保留；"
                         "请用 --keep-code-backticks 或先修改源文件")
    return out


def split_sections(blocks):
    """按一级标题切段；返回 (头部块, [(一级标题文本, 块列表)], 全部一级标题列表)。

    一级块**留在它自己区段块列表的首位**（本次修复 ①：旧行为把它摘出去只当区段名，块列表里
    只剩二三级块，成稿因此一个 Heading 1 都没有——解析器读到了 13 个 `#`，渲染循环却从来
    见不到 h1）。区段名仍然由返回的元组首项给出，供装配阶段按名字编排顺序。
    """
    head = []
    sections = []
    cur = None
    for b in blocks:
        if b["kind"] == "h1":
            cur = (b["text"], [b])
            sections.append(cur)
        elif cur is None:
            head.append(b)
        else:
            cur[1].append(b)
    return head, sections


def compute_drops(head, sections):
    """算出要剔除的两类工作留痕：行号集合、块集合、以及供报告/断言用的分类计数。

    剔除范围（本次修复 ②：旧实现只处理了其中的一部分）：
      ① 头部散块（第一个 `#` 之前的块；本论文里为空）；
      ② 题目段整段——`# 题目` 一级块本身，以及它名下的引用块与 `| 项 | 取值 |` 元数据表。
         题目文字不丢：它排在封面上（封面题目用 TITLE 常量渲染，`build()` 另核对二者逐字一致）；
      ③ 两处「修订记录」——**任何层级**标题文本恰为「修订记录」的标题块，以及它之后直到下一个
         标题块之前的全部块（含各自的整张修订表）。旧实现按「一级标题文本 == 修订记录」只剔了
         文末那一处，第七章的 `## 修订记录` 与它的表被当正文渲染进了成稿。
    正文里作为**子串**出现的「修订记录」（对外部文档修订史的交叉引用，实测 5 次）不在此列。
    """
    drop_blocks = []                 # [(原因, 块)]
    for b in head:
        drop_blocks.append(("头部散块", b))
    for title, bs in sections:
        if title == TITLE:
            for b in bs:
                drop_blocks.append(("文首元数据块", b))
        elif title == REVISION_TITLE:
            for b in bs:
                drop_blocks.append(("文末修订记录区段", b))
        else:
            skipping = False
            for b in bs:
                if b["kind"] in ("h1", "h2", "h3") and b["text"].strip() == REVISION_TITLE:
                    skipping = True
                if skipping:
                    drop_blocks.append(("章内修订记录区块", b))

    drop_idx = set()
    dropped = {"lines": 0, "by_reason": {}, "h1": 0, "h2": 0, "h3": 0,
               "tables": 0, "table_caps": 0, "imgs": 0,
               "revision_spans": [], "meta_span": None}
    for reason, b in drop_blocks:
        a, z = b["src_span"]
        drop_idx.update(range(a, z + 1))
        if b.get("cap_span"):                    # 图注的 HTML 外壳行 / 表题行
            a2, z2 = b["cap_span"]
            drop_idx.update(range(a2, z2 + 1))
        dropped["by_reason"][reason] = dropped["by_reason"].get(reason, 0) + 1
        if b["kind"] in ("h1", "h2", "h3"):
            dropped[b["kind"]] += 1
        elif b["kind"] == "table":
            dropped["tables"] += 1
            if b.get("caption"):
                dropped["table_caps"] += 1
        elif b["kind"] == "img":
            dropped["imgs"] += 1
        if reason in ("文末修订记录区段", "章内修订记录区块"):
            dropped["revision_spans"].append((a, z))
        if reason == "文首元数据块":
            dropped["meta_span"] = (a, z) if dropped["meta_span"] is None else \
                (min(dropped["meta_span"][0], a), max(dropped["meta_span"][1], z))
    dropped["lines"] = len(drop_idx)
    dropped["revision_spans"].sort()
    return drop_idx, drop_blocks, dropped


# =============================================================================
# 图片解析：① 仓库根＋图注反引号路径；② ![]() 目标按《29》所在目录；③ 按仓库根
# =============================================================================
def resolve_image(block):
    """返回 (绝对路径, 规则编号 1/2/3)。都解析不到则抛 FileNotFoundError。"""
    cands = []
    if block.get("cap_rel"):
        cands.append((1, os.path.normpath(os.path.join(ROOT, block["cap_rel"].replace("/", os.sep)))))
    tgt = block["target"]
    if not re.match(r"^[a-zA-Z]+://", tgt):
        cands.append((2, os.path.normpath(os.path.join(os.path.dirname(SRC), tgt.replace("/", os.sep)))))
        cands.append((3, os.path.normpath(os.path.join(ROOT, tgt.replace("/", os.sep)))))
    for rule, path in cands:
        if os.path.isfile(path):
            return path, rule
    raise FileNotFoundError(
        "插图解析失败：alt=%r target=%r cap_rel=%r；已尝试：%s"
        % (block.get("alt"), tgt, block.get("cap_rel"),
           "; ".join("规则%d=%s" % (r, p) for r, p in cands)))


# =============================================================================
# 超页插图切块（第四批改动 1）：只读源 PNG，在内存里切，源文件一个字节都不改
# =============================================================================
# 面板：`top`／`bottom` 是源图像素行区间（左闭右开），`w_px`／`h_px` 是裁块后的像素尺寸，
# `w_emu`／`h_emu` 是嵌入尺寸（EMU），`cont` 是续图标记（第 1 块为空串）。
Panel = collections.namedtuple("Panel", "top bottom w_px h_px w_emu h_emu cont")


def _require_imaging():
    """切图依赖 numpy 与 Pillow；缺任一就报错退出，绝不静默跳过切图。"""
    if _IMAGING_ERROR is not None:
        raise RuntimeError("超页插图切块需要 numpy 与 Pillow，导入失败：%s" % _IMAGING_ERROR)


def _ink_rows(path):
    """读图 → 灰度 → 逐行墨迹计数。返回 (宽px, 高px, 每行墨迹像素数)。

    墨迹判据 `gray < INK_THRESHOLD(200)`：流程图的节点框与连线都是深色，白底是 255，
    200 这个阈值能把二者干净分开。数组口径与任务书一致（`np.asarray` 灰度）。
    """
    with _PILImage.open(path) as im:
        gray = im.convert("L")
        arr = _np.asarray(gray)
    h, w = arr.shape[:2]
    return w, h, (arr < INK_THRESHOLD).sum(axis=1)


def _cut_positions(ink, height, blocks):
    """给 `blocks` 块面板选切点：等分位置 h*k/K 的 ±12% 窗口内取墨迹最小的那一行。

    为什么取墨迹最小行：长竖向流程图的墨迹剖面在**节点之间的连接线**处最细（实测切点落在
    ink=0～10 的行上），而节点框内部动辄上千；在最小行下刀就不会把节点框拦腰切开。
    并列时取**离等分位置最近**的那一行（同分再取靠上的），保证结果确定。
    两道约束：切点严格递增、每个面板不小于 `MIN_PANEL_PX`——K 过大时窗口会被挤空，
    此时退回「等分位置本身」，仍由调用方的「装不下就 K+1」循环兜底。
    """
    cuts = []
    for k in range(1, blocks):
        nominal = height * k / blocks
        lo = max(0, int(math.floor(nominal * (1 - INK_WINDOW_RATIO))))
        hi = min(height - 1, int(math.ceil(nominal * (1 + INK_WINDOW_RATIO))))
        prev = cuts[-1] if cuts else -1
        lo = max(lo, prev + MIN_PANEL_PX)
        hi = min(hi, height - 1 - (blocks - k) * MIN_PANEL_PX)
        if lo > hi:                                  # 窗口被约束挤空：退回等分位置
            lo = hi = min(max(int(round(nominal)), prev + MIN_PANEL_PX), height - 1)
        seg = ink[lo:hi + 1]
        best = int(seg.min()) if len(seg) else 0
        cands = [lo + j for j, v in enumerate(seg) if int(v) == best]
        cuts.append(min(cands, key=lambda x: (abs(x - nominal), x)))
    return cuts


def plan_panels(path):
    """规划一张插图的嵌入面板：不超页就是 1 块（不切），超页就切到每块都装得下。

    算法（第四批改动 1，按任务书给定的口径实现）：
      ① 用源图纵横比算出「按宽度上限 14.6cm 渲染时的高度」`h_cm`；
      ② `h_cm <= MAX_PANEL_H_CM(23.4cm)` → **不切**，返回 1 块（维持现状，源文件直接用）；
      ③ 否则自适应块数：从 `K = ceil(h_cm / MAX_PANEL_H_CM)` 起步，**逐次 K+1 直到每一块
         都装得下**。等分后各块高度并不相等（切点可在窗口内漂移），只算一次必然漏掉
         「某一块仍超高」的情形——实测图4-2 在 K=4、K=5 时都还有块超过 23.4cm，K=6 才收敛。
      ④ 每块按**双重上限**嵌入：`scale = min(IMG_MAX_WIDTH / 宽px, MAX_PANEL_H / 高px)`
         （两个常量都是 EMU 口径，故 scale 是 EMU/像素），取较小者，故每块的渲染高度必然
         ≤ 23.4cm（版心高 23.70cm 以内）；宽度通常正好吃满 14.6cm。
    返回 `Panel` 列表（第 k≥2 块的 `cont` 为 `（续 k/K）`）；解析不到图／缺依赖照常报错。
    """
    _require_imaging()
    info = DocxImage.from_file(path)
    w_px, h_px = info.px_width, info.px_height
    h_cm = IMG_MAX_WIDTH_CM * h_px / w_px                     # 按宽度上限渲染时的高度
    if h_cm <= MAX_PANEL_H_CM:                                # ① / ② 不超页：原样嵌入
        width = info.width if info.width < IMG_MAX_WIDTH else IMG_MAX_WIDTH
        # 高度口径与 python-docx 的 `scaled_dimensions()` 完全一致（只给宽度时它按 info 的
        # EMU 宽高比反算），这样「不切」的图与历史产物逐 EMU 相同。
        height = int(round(info.height * float(width) / float(info.width)))
        return [Panel(0, h_px, w_px, h_px, int(width), height, "")]
    _w, _h, ink = _ink_rows(path)                             # ③ 逐行墨迹剖面
    blocks = max(1, int(math.ceil(h_cm / MAX_PANEL_H_CM)))
    while True:
        cuts = _cut_positions(ink, h_px, blocks)
        bounds = [0] + cuts + [h_px]
        heights = [bounds[i + 1] - bounds[i] for i in range(blocks)]
        if all(IMG_MAX_WIDTH_CM * hp / w_px <= MAX_PANEL_H_CM for hp in heights):
            break
        blocks += 1
        if blocks > MAX_PANEL_K:
            raise RuntimeError("插图 %s 切到 %d 块仍有面板超版心，已超 MAX_PANEL_K=%d"
                               % (path, blocks - 1, MAX_PANEL_K))
    panels = []
    for k in range(blocks):
        top, bottom = bounds[k], bounds[k + 1]
        hp = bottom - top
        # ④ 双重上限：宽度上限 14.6cm 与单块高度上限 23.4cm 取较小的那个缩放比。
        # 注意单位——`IMG_MAX_WIDTH`／`MAX_PANEL_H` 都是 EMU（Length），故这里的
        # `scale` 是 **EMU/像素**；写成厘米口径会把 14.6cm 算成 14.6EMU（实测踩过：
        # 面板宽高全变 0.00cm，Word 里等于没有图）。
        scale = min(float(IMG_MAX_WIDTH) / w_px, float(MAX_PANEL_H) / hp)
        panels.append(Panel(top, bottom, w_px, hp,
                            int(round(w_px * scale)), int(round(hp * scale)),
                            "" if k == 0 else CONT_SUFFIX_FMT % (k + 1, blocks)))
    return panels


def plan_image_panels(blocks):
    """给每个插图块挂上 `panels`（`plan_panels()` 的结果），返回 {源行号: 该行图题期望文字}。

    返回值供 `strip_md_lines()`／`expected_norm()` 的期望文字一侧使用：切块后**每一块面板
    都有一个图题段**，第 k≥2 块的图题比原图题多出「（续 k/K）」，故该行在成稿里出现的图题
    文字是「各块图题依次拼起来」。期望文字若不按这个口径补，归一化等价性自检会把它判成
    「成稿凭空造字」。**两侧同源**：渲染侧读 `b["panels"]`，期望侧读本函数返回的映射；
    不切块的图不进映射（期望文字仍是原来的 alt 一次）。
    """
    fig_text_by_line = {}
    for b in blocks:
        if b["kind"] != "img":
            continue
        path, _rule = resolve_image(b)
        panels = plan_panels(path)
        b["panels"] = panels
        if len(panels) > 1:
            fig_text_by_line[b["src_span"][0]] = "".join(
                _inline_plain(b["alt"] + p.cont) for p in panels)
    return fig_text_by_line


def _panel_blobs(path, panels):
    """把面板几何在**内存里**裁成 PNG 字节；K==1 时返回 [None]（直接用源文件，不做无谓重编码）。

    只解码一次源图、逐块 `crop()`，裁块不落盘（`$env:TEMP` 也不需要），仓库里不留任何中间面板。
    返回的字节直接喂给 `add_picture(BytesIO(...))`，python-docx 会按 PNG 头识别格式。
    """
    if len(panels) == 1:
        return [None]
    blobs = []
    with _PILImage.open(path) as im:
        for pn in panels:
            tile = im.crop((0, pn.top, pn.w_px, pn.bottom))
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            blobs.append(buf.getvalue())
    return blobs


# =============================================================================
# 样式
# =============================================================================
def _force_fonts(rfonts, latin, cn):
    """写 ascii/hAnsi/eastAsia/cs，并**删除主题字体属性**——主题属性优先级高于显式字体，
    留着它们会出现「设了字体却不生效」（python-docx 设中文必须走 w:eastAsia）。"""
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        if rfonts.get(qn("w:" + attr)) is not None:
            del rfonts.attrib[qn("w:" + attr)]
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:cs"), latin)


def _force_black(rpr):
    """把字体颜色钉成黑色（模板里标题常带主题色，主题色优先于 w:color 的 val）。"""
    color = rpr.find(qn("w:color"))
    if color is None:
        color = OxmlElement("w:color")
        rpr.append(color)
    for attr in ("themeColor", "themeTint", "themeShade"):
        if color.get(qn("w:" + attr)) is not None:
            del color.attrib[qn("w:" + attr)]
    color.set(qn("w:val"), "000000")


def _style_font(style, latin, cn, size, bold=None, black=True):
    style.font.size = size
    if bold is not None:
        style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    _force_fonts(rfonts, latin, cn)
    if black:
        _force_black(rpr)


def _style_par(style, align=None, line_spacing=None, before=None, after=None,
               first_line_chars=None, left=None, right=None, hanging=None,
               page_break_before=None, keep_next=None):
    pf = style.paragraph_format
    if align is not None:
        pf.alignment = align
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if before is not None:
        pf.space_before = before
    if after is not None:
        pf.space_after = after
    if left is not None:
        pf.left_indent = left
    if right is not None:
        pf.right_indent = right
    if hanging is not None:
        pf.first_line_indent = -hanging
    if page_break_before is not None:
        pf.page_break_before = page_break_before
    if keep_next is not None:
        pf.keep_with_next = keep_next
    ppr = style.element.get_or_add_pPr()
    ind = ppr.get_or_add_ind()
    if first_line_chars is not None:
        # 用 w:firstLineChars（字符口径）而不是固定磅值：换字号时缩进自动跟随
        if first_line_chars:
            ind.set(qn("w:firstLineChars"), str(first_line_chars))
            if ind.get(qn("w:firstLine")) is not None:
                del ind.attrib[qn("w:firstLine")]
        else:
            ind.set(qn("w:firstLineChars"), "0")
            ind.set(qn("w:firstLine"), "0")


def _new_style(doc, name, base="Normal"):
    st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    st.base_style = doc.styles[base]
    return st


# `w:pPr` 的子元素次序（OOXML schema 规定，第四批改动 3 用到其中的 `w:pBdr` 落位）。
# 只列到 `w:jc` 这一带——本项目用到的段落属性都在这个范围内；不在表里的元素按「排最后」处理。
_PPR_ORDER = ("w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr",
              "w:widowControl", "w:numPr", "w:suppressLineNumbers", "w:pBdr", "w:shd",
              "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
              "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
              "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
              "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
              "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
              "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr")


def _set_par_bottom_border(style, spec):
    """给段落**样式**加下边框（第四批改动 3：页眉样式要模板同款的下边框）。

    旧行为：「页眉」样式没有 `w:pBdr`，产物页眉下没有横线。
    新行为：按 `spec`（`HEADER_BORDER`）写 `<w:pBdr><w:bottom w:val="single" w:color="auto"
    w:sz="6" w:space="1"/></w:pBdr>`——值与模板页眉样式（styleId 9）逐属性一致。
    为什么必须自己管落位：`w:pPr` 的子元素次序由 schema 规定（`w:pBdr` 在 `w:widowControl`
    之后、`w:shd`／`w:tabs`／`w:spacing`／`w:ind`／`w:jc` 之前），盲目 `append()` 会把
    `w:pBdr` 排到 `w:jc` 之后，Word 能容错打开但那是非法次序（同一类坑见 `_suppress_page_break()`
    与 `_set_pgnum()` 的注释）。这里按 `_PPR_ORDER` 找第一个次序更大的兄弟节点，插在它前面。
    """
    ppr = style.element.get_or_add_pPr()
    old = ppr.find(qn("w:pBdr"))
    if old is not None:
        ppr.remove(old)
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key in ("val", "color", "sz", "space"):
        bottom.set(qn("w:" + key), spec[key])
    bdr.append(bottom)
    rank = {qn(t): i for i, t in enumerate(_PPR_ORDER)}
    mine = rank[qn("w:pBdr")]
    for child in ppr:
        if rank.get(child.tag, 99) > mine:
            child.addprevious(bdr)
            break
    else:
        ppr.append(bdr)
    return bdr


def _set_outline(style, level):
    ppr = style.element.get_or_add_pPr()
    ol = ppr.find(qn("w:outlineLvl"))
    if ol is None:
        ol = OxmlElement("w:outlineLvl")
        ppr.append(ol)
    ol.set(qn("w:val"), str(level))


def setup_styles(doc):
    """把全部排版挂到样式对象上（不逐段硬设），换模板时改样式即可。"""
    styles = doc.styles

    # Normal：只定字体字号行距与对齐，**不设缩进**，避免被各级样式继承出意外缩进
    normal = styles["Normal"]
    _style_font(normal, FONT_LATIN, FONT_BODY_CN, SIZE_BODY, black=False)
    _style_par(normal, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line_spacing=LINE_SPACING,
               before=SPACE_BEFORE, after=SPACE_AFTER)

    # 标题：黑体；一级居中，二三级左对齐；一级另起新页（`H1_PAGE_BREAK_BEFORE`，第三批改动 4）
    for lvl, size, before, after in ((1, SIZE_H1, H1_BEFORE, H1_AFTER),
                                     (2, SIZE_H2, H2_BEFORE, H2_AFTER),
                                     (3, SIZE_H3, H3_BEFORE, H3_AFTER)):
        st = styles["Heading %d" % lvl]
        st.base_style = normal
        _style_font(st, FONT_LATIN, FONT_TITLE_CN, size, bold=True)
        _style_par(st, align=(H1_ALIGN if lvl == 1 else H2H3_ALIGN),
                   line_spacing=LINE_SPACING, before=before, after=after,
                   first_line_chars=0, keep_next=True,
                   page_break_before=(H1_PAGE_BREAK_BEFORE if lvl == 1 else False))
        _set_outline(st, lvl - 1)

    # 正文段落：首行缩进 2 字符、段前段后 0、两端对齐（继承 Normal）；
    # 行距**固定 20 磅**（第四批改动 5，`LINE_SPACING_BODY = Pt(20)` → `w:line="400"
    # w:lineRule="exact"`，模板「0毕设正文」实测同款）。只改这一处，其余样式仍走倍数行距。
    body = _new_style(doc, "正文段落")
    _style_par(body, first_line_chars=FIRST_LINE_CHARS, line_spacing=LINE_SPACING_BODY)

    # 图题／表题：五号居中、不缩进
    fig = _new_style(doc, "图题")
    _style_font(fig, FONT_LATIN, FONT_BODY_CN, SIZE_CAPTION, black=False)
    _style_par(fig, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING_TIGHT,
               before=Pt(3), after=Pt(6), first_line_chars=0)
    tab = _new_style(doc, "表题")
    _style_font(tab, FONT_LATIN, FONT_BODY_CN, SIZE_CAPTION, bold=True, black=False)
    _style_par(tab, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING_TIGHT,
               before=Pt(6), after=Pt(3), first_line_chars=0, keep_next=True)

    # 表格文字：五号、不缩进、单倍行距
    cell = _new_style(doc, "表格文字")
    _style_font(cell, FONT_LATIN, FONT_BODY_CN, SIZE_TABLE, black=False)
    _style_par(cell, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=LINE_SPACING_TIGHT,
               before=Pt(1), after=Pt(1), first_line_chars=0)

    # 引文（> 块）：五号、左右缩进、不缩进首行
    quote = _new_style(doc, "引文")
    _style_font(quote, FONT_LATIN, FONT_BODY_CN, SIZE_CAPTION, black=False)
    _style_par(quote, line_spacing=LINE_SPACING, before=Pt(3), after=Pt(3),
               first_line_chars=0, left=QUOTE_INDENT, right=QUOTE_INDENT)

    # 列表项：标记原样保留，只做左缩进
    lst = _new_style(doc, "列表项")
    _style_par(lst, first_line_chars=0, left=LIST_INDENT, before=Pt(0), after=Pt(0))

    # 代码块：等宽、五号、单倍行距、不缩进首行（源文字逐字保留）
    code = _new_style(doc, "代码块")
    _style_font(code, FONT_MONO, FONT_MONO_CN, SIZE_CAPTION, black=False)
    _style_par(code, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=LINE_SPACING_TIGHT,
               before=Pt(0), after=Pt(0), first_line_chars=0, left=CODE_INDENT)

    # 参考文献条目：**小四**（模板实测 12pt，与图题不同号，见 SIZE_REF）、悬挂缩进 0.74cm
    # （w:left + w:hanging，且不复用首行缩进口径）
    ref = _new_style(doc, "参考文献条目")
    _style_font(ref, FONT_LATIN, FONT_BODY_CN, SIZE_REF, black=False)
    _style_par(ref, line_spacing=LINE_SPACING, before=Pt(0), after=Pt(0),
               left=REF_HANGING, hanging=REF_HANGING)
    ppr = ref.element.get_or_add_pPr()
    ind = ppr.get_or_add_ind()
    ind.set(qn("w:firstLineChars"), "0")
    if ind.get(qn("w:firstLine")) is not None:
        del ind.attrib[qn("w:firstLine")]

    # 页脚页码：Times New Roman **小四(12pt)** 居中（第四批改动 4：模板 footer1.xml 的 run 级
    # rPr 实测 `w:sz="24"` ＋ ascii/hAnsi/cs 全为 Times New Roman；旧行为是五号 10.5pt）。
    foot = _new_style(doc, "页脚页码")
    _style_font(foot, FONT_LATIN, FONT_BODY_CN, SIZE_FOOTER, black=False)
    _style_par(foot, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING_TIGHT,
               first_line_chars=0)

    # 页眉（第三批改动 5 新增；第四批改动 3 对齐模板实测值）：宋体**小五(9pt)** 居中、
    # 带**下边框**。模板页眉样式（styleId 9，`w:name="header"`）实测 `<w:sz w:val="18"/>`
    # ＝ 9pt、`<w:jc w:val="center"/>`、`<w:pBdr><w:bottom w:val="single" w:color="auto"
    # w:sz="6" w:space="1"/></w:pBdr>`；旧行为是五号(10.5pt)且无边框。
    head = _new_style(doc, "页眉")
    _style_font(head, FONT_LATIN, FONT_BODY_CN, SIZE_HEADER, black=False)
    _style_par(head, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING_TIGHT,
               before=Pt(0), after=Pt(0), first_line_chars=0)
    _set_par_bottom_border(head, HEADER_BORDER)

    # 封面
    cov_t = _new_style(doc, "封面题目")
    _style_font(cov_t, FONT_LATIN, FONT_TITLE_CN, SIZE_COVER_TITLE, bold=True)
    _style_par(cov_t, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING,
               before=Pt(0), after=Pt(0), first_line_chars=0)
    cov_l = _new_style(doc, "封面标签")
    _style_font(cov_l, FONT_LATIN, FONT_TITLE_CN, SIZE_COVER_LABEL, bold=True)
    _style_par(cov_l, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING,
               before=Pt(0), after=Pt(0), first_line_chars=0)
    cov_f = _new_style(doc, "封面字段")
    _style_font(cov_f, FONT_LATIN, FONT_BODY_CN, SIZE_COVER_FIELD, black=False)
    _style_par(cov_f, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING,
               before=Pt(0), after=Pt(0), first_line_chars=0)

    # 目录标题／目录说明
    toc_t = _new_style(doc, "目录标题")
    _style_font(toc_t, FONT_LATIN, FONT_TITLE_CN, SIZE_H1, bold=True)
    _style_par(toc_t, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING,
               before=Pt(0), after=H2_AFTER, first_line_chars=0, page_break_before=True)
    toc_n = _new_style(doc, "目录说明")
    _style_font(toc_n, FONT_LATIN, FONT_BODY_CN, SIZE_CAPTION, black=False)
    _style_par(toc_n, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing=LINE_SPACING,
               before=Pt(0), after=Pt(6), first_line_chars=0)

    # 声明页标题：与章标题同款（黑体三号居中），但 `page_break_before` 由装配阶段决定
    # （封面后、摘要前各一处分页的落点见 `_add_statement()`）；声明正文与落款复用「正文段落」
    # 与「封面字段」样式，不另造字形——模板里声明页的正文与封面字段同为宋体小四／四号。
    stat_t = _new_style(doc, "声明标题")
    _style_font(stat_t, FONT_LATIN, FONT_TITLE_CN, SIZE_H1, bold=True)
    _style_par(stat_t, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing=LINE_SPACING,
               before=Pt(0), after=H2_AFTER, first_line_chars=0, page_break_before=True)
    return styles


# =============================================================================
# 行内标记与各类块的渲染
# =============================================================================
def _run(par, text, latin=FONT_LATIN, cn=FONT_BODY_CN, size=None,
         bold=None, italic=None, strike=None):
    r = par.add_run(text)
    rpr = r._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    _force_fonts(rfonts, latin, cn)
    if size is not None:
        r.font.size = size
    if bold is not None:
        r.bold = bold
    if italic is not None:
        r.italic = italic
    if strike is not None:
        r.font.strike = strike
    return r


def _inline_plain(text):
    """行内标记剥离：返回 `add_inline()` 渲染后**会落进成稿的纯文字**。

    与 `add_inline()` 同源同规则（同一支 `INLINE_RE`、同一套分支与递归），供源侧期望文字使用。
    本次修复 ③ 的另一半：`**…**` 内层仍可能含反引号／斜体（实测
    `**主 judge 的 `kimi-k3` 端点…**`），剥外层时**必须递归**再解析内层，
    否则内层的反引号会被原样吐进成稿。

    第二批改动：开头的 `_render_text()` 是「渲染文本映射」的期望文字侧——标题呈现模板写法
    （「摘  要」「目  录」）时，期望文字也必须同步，否则等价性自检会当成「成稿凭空造字」。
    """
    out = []
    for tok in INLINE_RE.split(_render_text(text)):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) >= 4:
            out.append(_inline_plain(tok[2:-2]))
        elif tok.startswith("~~") and tok.endswith("~~") and len(tok) >= 4:
            out.append(_inline_plain(tok[2:-2]))
        elif tok.startswith("`") and tok.endswith("`") and len(tok) >= 2:
            out.append(tok[1:-1])          # 等宽 run：内容是字面量，不再递归
        elif tok.startswith("*") and tok.endswith("*") and len(tok) >= 2:
            out.append(_inline_plain(tok[1:-1]))
        else:
            out.append(tok)
    return "".join(out)


def add_inline(par, text, size=None, bold=None, cn=FONT_BODY_CN, latin=FONT_LATIN,
               italic=None, strike=None):
    """渲染行内标记：**加粗** → 加粗 run；`代码` → 等宽 run；*斜体*、~~删除线~~。

    剥出的内层文字**递归**交给本函数（本次修复 ③）：内层可能还嵌着反引号或斜体，
    不递归就会把字面标记漏进成稿。字形标记（bold／italic／strike）作为参数往下传，
    保证内层每一段 run 都带上外层的字形。

    第二批改动：开头的 `_render_text()` 做「渲染文本映射」（标题呈现模板写法）。
    只对**整串**命中生效；递归进内层时内层已经不是标题全文，映射自然不再触发。
    """
    for tok in INLINE_RE.split(_render_text(text)):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) >= 4:
            add_inline(par, tok[2:-2], size=size, bold=True, cn=cn, latin=latin,
                       italic=italic, strike=strike)
        elif tok.startswith("~~") and tok.endswith("~~") and len(tok) >= 4:
            add_inline(par, tok[2:-2], size=size, bold=bold, cn=cn, latin=latin,
                       italic=italic, strike=True)
        elif tok.startswith("`") and tok.endswith("`") and len(tok) >= 2:
            _run(par, tok[1:-1], latin=FONT_MONO, cn=FONT_MONO_CN, size=size,
                 bold=bold, italic=italic, strike=strike)
        elif tok.startswith("*") and tok.endswith("*") and len(tok) >= 2:
            add_inline(par, tok[1:-1], size=size, bold=bold, cn=cn, latin=latin,
                       italic=True, strike=strike)
        else:
            _run(par, tok, latin=latin, cn=cn, size=size, bold=bold,
                 italic=italic, strike=strike)


def add_table(doc, rows):
    """Markdown 表 → 真正的 Word 表：加边框、首行加粗且跨页重复、内容五号、整表居中、列宽自适应。"""
    ncols = max(len(r) for r in rows)
    header = rows[0] if len(rows) > 1 else None      # 解析时已剔除 `| --- |` 分隔行
    data = rows[1:] if header else rows
    table = doc.add_table(rows=len(data) + (1 if header else 0), cols=ncols)
    table.style = doc.styles["Table Grid"]
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "autofit")
    tbl_pr.append(layout)
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:w"), "5000")
    tbl_w.set(qn("w:type"), "pct")
    tbl_pr.append(tbl_w)

    r0 = 0
    if header:
        _fill_row(table.rows[0], header, ncols, bold=True)
        tr_pr = table.rows[0]._tr.get_or_add_trPr()
        rep = OxmlElement("w:tblHeader")             # 跨页重复标题行
        rep.set(qn("w:val"), "true")
        tr_pr.append(rep)
        r0 = 1
    for k, row in enumerate(data):
        _fill_row(table.rows[r0 + k], row, ncols, bold=False)
    return table


def _fill_row(trow, cells, ncols, bold):
    for c in range(ncols):
        txt = cells[c] if c < len(cells) else ""
        cell = trow.cells[c]
        par = cell.paragraphs[0]
        par.style = trow._tr.getparent().getparent().getparent().part.document.styles["表格文字"] \
            if False else None
        add_inline(par, txt, bold=True if bold else None)


def add_page_field(par):
    """页脚页码：`-N-` 体例——短横线 ＋ PAGE 域 ＋ 短横线（第四批改动 4 去掉了两处字面空格）。

    模板 `word/footer1.xml` 实测的可见文字 runs 是 `['-','45','-']`：短横线与页码之间**没有**
    字面空格；旧行为按第三批的「任务给定体例」写成 `- N -`（`FOOTER_LEAD = "- "`）。
    字号同样对齐模板：run 级 `w:sz="24"` ＝ 12pt、字体 Times New Roman（`SIZE_FOOTER`）。
    域仍是标准 PAGE 域：页码由 Word 渲染，**脚本不把页码算成文字**（罗马数字同理，
    交给 `w:pgNumType/@w:fmt`）。
    """
    if FOOTER_LEAD:
        _run(par, FOOTER_LEAD, latin=FONT_LATIN, cn=FONT_BODY_CN, size=SIZE_FOOTER)
    r = par.add_run()
    rpr = r._element.get_or_add_rPr()
    _force_fonts(rpr.get_or_add_rFonts(), FONT_LATIN, FONT_BODY_CN)
    r.font.size = SIZE_FOOTER
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, txt, end):
        r._r.append(el)
    if FOOTER_TAIL:
        _run(par, FOOTER_TAIL, latin=FONT_LATIN, cn=FONT_BODY_CN, size=SIZE_FOOTER)


def _suppress_page_break(par):
    """关掉**这一个段落**继承来的「段前分页」（`w:pageBreakBefore w:val="0"`）。

    第三批改动 4 的配套：分节符本身就是一次分页，落在分节符后面的第一个一级标题如果再带上
    `Heading 1` 样式的段前分页，就出现「两个分页来源指向同一处」——多出来的那一个在 Word 里
    就是一张空白页。段落级直接格式优先于样式，故在这里逐段关掉，使**每个一级标题前面恰好只有
    一个分页来源**（`verify()` 逐个数出来断言）。

    落位必须走 python-docx 的 API：`w:pPr` 的子元素有 schema 规定次序
    （`w:pStyle` → `w:keepNext` → `w:keepLines` → `w:pageBreakBefore` → …），
    直接 `insert(0, …)` 会把 `w:pageBreakBefore` 放到 `w:pStyle` **前面**——Word 能容错打开，
    但那是非法次序（同一类坑见 `_set_pgnum()` 的注释）。`CT_PPr` 自带次序表，交给它落位。
    """
    par.paragraph_format.page_break_before = False


# =============================================================================
# 分节编页（模板：前置部分与正文分别编页，正文首页 w:start="1"）
# =============================================================================
_PGNUM_ORDER = ("w:headerReference", "w:footerReference", "w:footnotePr", "w:endnotePr",
                "w:type", "w:pgSz", "w:pgMar", "w:paperSrc", "w:pgBorders", "w:lnNumType",
                "w:pgNumType", "w:cols", "w:formProt", "w:vAlign", "w:noEndnote",
                "w:titlePg", "w:textDirection", "w:bidi", "w:rtlGutter", "w:docGrid",
                "w:printerSettings")


def _set_pgnum(section, start=None, fmt=None):
    """把 `w:pgNumType` 写进 sectPr（Word 原生的分节页码属性）。

    这不是「自造一个 Word 认不出的域来充样子」：`w:pgNumType/@w:start`（本节重新起编）与
    `@w:fmt`（编号格式）都是 OOXML 分节页码的标准属性，模板实测节 1～6 带
    `<w:pgNumType w:fmt="upperRoman"/>`、节 7 带 `<w:pgNumType w:start="1"/>`。页脚里的域
    仍是标准 PAGE 域，页码文字由 Word 渲染。
    `fmt=None` 表示**不写** `w:fmt`：按模板节 7 的写法，省略即十进制（不是脚本自己算页码）。
    子元素必须落在 schema 规定的次序上（pgNumType 在 pgMar 之后、cols 之前），否则 Word 会
    判定文档损坏；因此按 `_PGNUM_ORDER` 定位插入点，而不是盲目 append。
    """
    sect_pr = section._sectPr
    old = sect_pr.find(qn("w:pgNumType"))
    if old is not None:
        sect_pr.remove(old)
    el = OxmlElement("w:pgNumType")
    if fmt is not None:
        el.set(qn("w:fmt"), fmt)
    if start is not None:
        el.set(qn("w:start"), str(start))
    rank = {qn(t): i for i, t in enumerate(_PGNUM_ORDER)}
    mine = rank[qn("w:pgNumType")]
    for child in sect_pr:
        if rank.get(child.tag, 99) > mine:
            child.addprevious(el)
            break
    else:
        sect_pr.append(el)


def _blank_footer(section, styles):
    """把某一节的页脚显式清空（无页码）。

    刻意**不清空段落对象本身**：Word 要求页脚 part 至少含一个块级元素，留空段即可。
    自检按「该节页脚没有 PAGE 域」断言，而不是按「页脚段落数 == 0」。
    """
    foot = section.footer
    foot.is_linked_to_previous = False
    for par in list(foot.paragraphs):          # 清空段落**文字**，不留空 run
        for run in list(par.runs):
            run._element.getparent().remove(run._element)
    if not foot.paragraphs:                    # 段落数为 0 时补一个空段，避免页脚 part 非法
        foot.add_paragraph()
    foot.paragraphs[0].style = styles["页脚页码"]


def _setup_header(section, styles):
    """给某一节挂页眉（`HEADER_TEXT`，宋体五号居中）。

    `is_linked_to_previous = False` 会让 python-docx 新建一个 header part 并把
    `w:headerReference` 写进该节 sectPr——这正是「封面与声明不显示页眉」的实现方式：
    第 1 节**不带**任何 `w:headerReference`，且它是首节、无处可继承。
    """
    hdr = section.header
    hdr.is_linked_to_previous = False
    par = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()
    for run in list(par.runs):                 # 新建的 header part 自带一个空段，复用并清空
        run._element.getparent().remove(run._element)
    par.style = styles["页眉"]
    _run(par, HEADER_TEXT, latin=FONT_LATIN, cn=FONT_BODY_CN, size=SIZE_HEADER)


def _add_sections(doc, styles):
    """把文档切成 3 节并配好页眉／页脚／页码（第三批改动 5、6）。

    模板实测：节 1～6 `w:fmt="upperRoman"`（前置部分大写罗马数字）、节 7 起 `w:start="1"`
    （正文十进制从 1 起）、页眉 `姓名：题目` 只挂在摘要所属的那一节（封面与声明没有页眉）、
    页脚体例 `-N-`。本脚本按同一体例分 3 节（不照抄模板的 14 节——模板把每章各切一节，
    对本论文没有必要，且会在正文里插满「为分节而分节」的分页）：

      * 第 1 节（`doc.sections[0]`）封面＋声明：**无页眉、无页码**（页脚显式清空）。
      * 第 2 节（`doc.sections[1]`）摘要＋Abstract＋目录：有页眉；页脚 `-N-`；
        `w:pgNumType w:fmt="upperRoman" w:start="1"` → 大写罗马数字从 I 起。
      * 第 3 节（`doc.sections[2]`）正文第一章…致谢：页眉与页脚沿用模板节 8～14 的
        「不写引用 ＝ 继承上一节」写法（故正文各页同样有页眉与 `-N-` 页码）；
        `w:pgNumType w:start="1"`（省略 `w:fmt` ＝十进制）→ 页码重新从 1 起。

    两个分节符由 `build_document()` 在装配时插入（声明之后、目录之后）。
    返回 (节数, 第 3 节的 sectPr)，供自检核对。
    """
    cover, front, body = doc.sections[0], doc.sections[1], doc.sections[2]
    if FRONT_FOOTER_BLANK:
        _blank_footer(cover, styles)           # 封面＋声明：不显示页码
    _setup_header(front, styles)               # 摘要起才有页眉
    ff = front.footer
    ff.is_linked_to_previous = False
    fp = ff.paragraphs[0] if ff.paragraphs else ff.add_paragraph()
    fp.style = styles["页脚页码"]
    add_page_field(fp)                         # `-N-`
    _set_pgnum(front, start=FRONT_PAGE_START, fmt=FRONT_PAGE_FMT)
    # 第 3 节：页眉／页脚都不写引用 → 继承第 2 节（模板节 8～14 就是这么做的）。
    # 这里显式赋值 True 只为把「有意继承」写进代码：值为 True 时 python-docx 发现本来就没有
    # 定义，直接返回、不产生任何副作用（也不会凭空建出 header/footer part）。
    body.header.is_linked_to_previous = True
    body.footer.is_linked_to_previous = True
    _set_pgnum(body, start=BODY_PAGE_START, fmt=BODY_PAGE_FMT)
    return len(doc.sections), body


def _remove_stale(stale, out_path):
    """删除旧落点。删除纯属清理，**任何失败都不影响本次产出**：捕获 OSError 后原样返回，
    由调用方打印「待人工处理」提示（含一条现成的删除命令）。

    为什么不做「自动关掉占用它的 Word」：本机实测不可行——`GetActiveObject` 在这台机器上
    取到的 Word 实例 `Documents.Count == 0`，真正持有文档的那个可见实例根本不在 ROT 里；
    更糟的是，机器上没有现成实例时获取 COM 对象会**另外拉起**一个无窗口 Word 进程，它照样
    锁着文件、用户却看不见也关不掉（本次调试就踩到过，多出一个僵尸 WINWORD）。所以宁可
    如实报告让人来关，也不去动用户的 Word 会话。

    （第四批改动 2 复核：`os.remove` 的 `OSError` 捕获这里**本来就有**，故本轮不动逻辑；
    真正缺捕获的是下面 `write_product()` 的写盘路径。）
    """
    if os.path.abspath(stale) == os.path.abspath(out_path):
        return None                                     # --out 恰好指到旧落点：不动它
    if not os.path.isfile(stale):
        return None
    try:
        os.remove(stale)
    except OSError as exc:
        return exc
    return None


def write_product(out_path, data):
    """把产物写盘。成功返回 None；失败返回 (阶段, OSError)，由 `main()` 打印提示并以退出码 3 结束。

    第四批改动 2（旧行为／新行为／为什么）：旧行为是裸 `open(out_path, "wb")`，产物正被
    Word／WPS 打开时抛 `PermissionError: [Errno 13]` 的**裸 traceback**，用户只看到栈回溯，
    不知道该关什么、也不知道产物有没有被写坏。新行为按三个可能失败的阶段分别捕获 `OSError`：
      * `mkdir`：建产出目录失败（盘满／无权限）；
      * `open`：打开产物失败——**Windows 上文件被 Word／WPS 占用时失败就发生在这里，
        一个字节都还没写，故可以如实说「产物未被改动」**；
      * `write`：写入中途失败，产物可能不完整（如实提示，别谎称没动过）。
    为什么分三段而不是一把 try：三种情形给用户的话不一样，「产物未被改动」这句只在
    确实没写任何字节时才能说。**一律不吞异常继续往下走**：报完就返回非零退出码。
    """
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    except OSError as exc:
        return ("mkdir", exc)
    try:
        fh = open(out_path, "wb")
    except OSError as exc:
        return ("open", exc)
    try:
        with fh:
            fh.write(data)
    except OSError as exc:
        return ("write", exc)
    return None


def add_toc_field(par):
    """目录域：TOC \\o "1-3" \\h \\z \\u。"""
    r = par.add_run()
    rpr = r._element.get_or_add_rPr()
    _force_fonts(rpr.get_or_add_rFonts(), FONT_LATIN, FONT_BODY_CN)
    r.font.size = SIZE_CAPTION
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    if TOC_DIRTY:
        begin.set(qn("w:dirty"), "true")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = TOC_INSTR
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = TOC_PLACEHOLDER
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, txt, end):
        r._r.append(el)


# =============================================================================
# 成稿装配
# =============================================================================
def _cover_text():
    """封面文字（参与等价性自检）。空白占位段不产文字。"""
    return COVER_LABEL + TITLE + "".join(COVER_FIELDS)


def _statement_text():
    """声明页文字（模板固定表格件，非论文正文；参与等价性自检）。"""
    return STATEMENT_TITLE + STATEMENT_BODY + "".join(STATEMENT_SIGN_LINES)


def _toc_text():
    """目录页文字。标题走渲染文本映射（「目录」→「目  录」），与 `_add_toc()` 同源。"""
    return _render_text("目录") + TOC_NOTE + TOC_PLACEHOLDER


def _add_statement(doc):
    """声明页：标题 + 声明正文 + 两行留空落款（封面之后、摘要之前，单独一页）。

    「声明标题」样式自带 `page_break_before`，所以它自己起一页（声明页与封面同属第 1 节，
    该节无页眉、无页码）。紧接着的摘要不再靠 `page_break_before` 起页——它前面是分节符①
    （分节符本身就是分页），其段前分页已被 `_suppress_page_break()` 关掉，免得同一处两个
    分页来源多出一张空白页（第三批改动 4、6）。落款一律留空（见 `STATEMENT_*` 注释）。
    """
    doc.add_paragraph(STATEMENT_TITLE, style="声明标题")
    doc.add_paragraph(STATEMENT_BODY, style="正文段落")
    for line in STATEMENT_SIGN_LINES:
        doc.add_paragraph(line, style="封面字段")


def _add_toc(doc):
    """目录页：标题 + 域说明 + TOC 域（「目录标题」样式自带 page_break_before，另起一页）。"""
    doc.add_paragraph(RENDER_TEXT_MAP["目录"], style="目录标题")
    doc.add_paragraph(TOC_NOTE, style="目录说明")
    ptoc = doc.add_paragraph(style="目录说明")
    add_toc_field(ptoc)


def build_document(sections, stats):
    """sections 只含**保留**的区段（题目段与两处修订记录已在外层剔除），顺序即成稿顺序。

    装订顺序：封面 → 声明 → 分节符 → 前置区段（摘要／Abstract，源顺序）→ 目录 → 分节符 →
    正文（第一章…致谢）。源文件里没有目录与声明页，所以期望文字一侧（`expected_norm()`）
    也按这个位置插进去。两个分节符分别切出「摘要起有页眉与罗马页码」与「正文阿拉伯页码从 1 起」
    （见 `_add_sections()`）。

    分页来源唯一（第三批改动 4）：分节符本身就是一次分页，所以紧跟分节符的那个一级标题
    （摘要、第一章）要把 `Heading 1` 样式继承来的段前分页逐段关掉（`_suppress_page_break()`），
    否则同一处有两个分页来源，Word 里会多出一张空白页。`suppress_break` 就是给这两个位置用的。
    """
    from docx.enum.section import WD_SECTION
    doc = Document()
    styles = setup_styles(doc)

    sec = doc.sections[0]
    sec.page_width = PAGE_WIDTH
    sec.page_height = PAGE_HEIGHT
    sec.top_margin = MARGIN_TOP
    sec.bottom_margin = MARGIN_BOTTOM
    sec.left_margin = MARGIN_LEFT
    sec.right_margin = MARGIN_RIGHT
    sec.header_distance = Cm(1.5)      # 模板实测 w:pgMar/@w:header="850" twips ＝ 1.5cm
    sec.footer_distance = Cm(1.75)     # 模板实测 w:pgMar/@w:footer="992" twips ＝ 1.75cm

    # ---- 封面（单独一页；六字段均为作者提供的真值）----
    for _ in range(3):
        doc.add_paragraph("", style="封面字段")
    doc.add_paragraph(COVER_LABEL, style="封面标签")
    doc.add_paragraph(TITLE, style="封面题目")
    for _ in range(3):
        doc.add_paragraph("", style="封面字段")
    for f in COVER_FIELDS:
        doc.add_paragraph(f, style="封面字段")

    # ---- 声明页（封面之后、摘要之前，单独一页；仍在第 1 节内，故与封面一样没有页眉页码）----
    _add_statement(doc)

    # ---- 分节符①：第 2 节从摘要开始（有页眉；页码 upperRoman 从 I 起）----
    doc.add_section(WD_SECTION.NEW_PAGE)

    # ---- 前置区段（摘要／Abstract，源顺序）→ 目录 → 分节符② → 正文（第一章…致谢）----
    toc_at = next((k for k, (t, _) in enumerate(sections) if t not in FRONT_SECTIONS),
                  len(sections))
    suppress_break = True                          # 本节第一个一级标题紧跟分节符①：关掉重复分页
    for k, (title, blocks) in enumerate(sections):
        if k == toc_at:
            _add_toc(doc)
            doc.add_section(WD_SECTION.NEW_PAGE)   # 分节符②：第 3 节正文，页码重新从 1 起
            suppress_break = True                  # 第一章同样紧跟一个分节符
        render_blocks(doc, blocks, stats, suppress_break=suppress_break)
        suppress_break = False
    if toc_at == len(sections):                    # 源里没有正文区段时，目录收在最后
        _add_toc(doc)
        doc.add_section(WD_SECTION.NEW_PAGE)

    # ---- 3 节的页眉／页脚／页码（见 `_add_sections()`）----
    stats["sections"], _body = _add_sections(doc, styles)
    return doc


def render_blocks(doc, blocks, stats, suppress_break=False):
    """渲染一个区段的块。

    `suppress_break=True`：本区段第一个一级标题**不再**自带段前分页——它前面已经有一个分节符
    （分节符本身就是分页），两个来源叠在一起会多出一张空白页（第三批改动 4）。
    """
    for b in blocks:
        k = b["kind"]
        if k in ("h1", "h2", "h3"):
            lvl = int(k[1])
            p = doc.add_paragraph(style="Heading %d" % lvl)
            if lvl == 1 and suppress_break:
                _suppress_page_break(p)
            # 标题也必须走行内解析（本次修复 ③：裸文本会把标题里的 `**` 原样带进成稿）。
            # 字体取标题中文字体、字号交给样式：run 级只钉字体，不钉字号，免覆盖样式。
            add_inline(p, b["text"], cn=FONT_TITLE_CN)
            stats["h%d" % lvl] += 1
        elif k == "p":
            p = doc.add_paragraph(style="正文段落")
            add_inline(p, b["text"])
            stats["p"] += 1
        elif k == "list":
            p = doc.add_paragraph(style="列表项")
            add_inline(p, b["text"])
            stats["list"] += 1
        elif k == "quote":
            p = doc.add_paragraph(style="引文")
            add_inline(p, b["text"])
            stats["quote"] += 1
        elif k == "ref":
            p = doc.add_paragraph(style="参考文献条目")
            add_inline(p, b["text"])
            stats["ref"] += 1
        elif k == "code":
            for line in b["lines"]:
                p = doc.add_paragraph(style="代码块")
                _run(p, line if line else " ", latin=FONT_MONO, cn=FONT_MONO_CN,
                     size=SIZE_CAPTION)
            stats["code"] += 1
        elif k == "img":
            path, rule = resolve_image(b)
            stats["img_rules"].append((b["alt"], rule, path))
            # 面板由 `plan_image_panels()` 预先算好（build() 在装配前统一规划：渲染侧与期望
            # 文字侧必须看到同一份结果）。这里只兜底重算，保证单独调用 render_blocks 也能用。
            panels = b.get("panels") or plan_panels(path)
            blobs = _panel_blobs(path, panels)
            stats["panels"].append({"alt": b["alt"], "path": path, "panels": panels,
                                    "src_w": panels[0].w_px,
                                    "src_h": sum(pn.bottom - pn.top for pn in panels)})
            stats["panel_total"] += len(panels)
            for idx, pn in enumerate(panels):
                p = doc.add_paragraph(style="图题")
                p.paragraph_format.keep_with_next = True     # 面板与它的图题不拆页
                if blobs[idx] is None:                       # 不切：与历史产物一致，直接嵌源文件
                    p.add_run().add_picture(path, width=Emu(pn.w_emu))
                else:                                        # 切块：内存里的 PNG 字节，带双上限尺寸
                    p.add_run().add_picture(io.BytesIO(blobs[idx]),
                                            width=Emu(pn.w_emu), height=Emu(pn.h_emu))
                # 图题也走行内解析；第 k≥2 块在图题后加续图标记「（续 k/K）」
                add_inline(doc.add_paragraph(style="图题"), b["alt"] + pn.cont)
            stats["img"] += 1
        elif k == "table":
            if b["caption"]:
                add_inline(doc.add_paragraph(style="表题"), b["caption"])  # 表题走行内解析
                stats["table_cap"] += 1
            add_table(doc, b["rows"])
            stats["table"] += 1
        else:
            raise ValueError("未知块类型：%r" % k)


# =============================================================================
# 确定性打包与自检
# =============================================================================
def _repack_deterministic(data):
    """把 python-docx 产出的 OOXML 包重打成确定性的 zip。

    python-docx 保存时用 `ZipFile.writestr(name, blob)`，条目时间取**当前时间**，
    因此两次运行的字节必然不同。这里把条目时间、压缩方式、外部属性全部钉死。
    """
    src = zipfile.ZipFile(io.BytesIO(data), "r")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            zi = zipfile.ZipInfo(info.filename, date_time=ZIP_DATE_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.create_version = 20
            zi.extract_version = 20
            zi.internal_attr = 0
            zi.external_attr = 0o600 << 16
            zi.flag_bits = 0
            dst.writestr(zi, payload)
    src.close()
    return buf.getvalue()


def _set_core_properties(doc):
    cp = doc.core_properties
    cp.title = TITLE
    cp.subject = CORE_SUBJECT
    cp.author = CORE_AUTHOR
    cp.last_modified_by = CORE_LAST_MODIFIED_BY
    cp.revision = CORE_REVISION
    cp.created = CORE_CREATED
    cp.modified = CORE_MODIFIED
    cp.comments = CORE_COMMENTS
    cp.keywords = CORE_KEYWORDS
    cp.category = ""
    cp.language = "zh-CN"


def iter_block_text(doc):
    """按文档顺序产出每段文字（含表格单元格），用于读回自检。"""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc).text
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            for row in tbl.rows:
                for cell in row.cells:
                    for par in cell.paragraphs:
                        yield par.text


def strip_md_lines(lines, keep_code_backticks=False, fig_text_by_line=None):
    """把源 Markdown 逐行剥成「渲染后会落进成稿的纯文字」（期望文字一侧，与解析器同口径）。

    为什么剥掉的这些差异是「标记」而不是「内容」（本次修复 ④ 的判据说明）：
      * `#`／`##`／`###` 与 `>` 是块首标记，标题文字与引文文字一字不丢；
      * `|` 是单元格分隔符（单元格文字一字不丢），`| --- |` 是表头分隔行（本身无文字）；
      * `![alt](path)` 的 path、以及 `<p align="center">…</p>` 里的 PNG 路径，都是**资产落点**
        （工作留痕），图题文字由 `![]()` 的 alt 承担；`<p align>` 整行只是图注的 HTML 外壳；
      * ``` 围栏与 `---` 分隔线是版式记号；
      * 代码块行尾的 PowerShell 续行反引号默认并句去掉（`--keep-code-backticks` 时保留，与
        `_normalize_code()` 完全同口径），代码块文字本身一字不丢；
      * 行内 `**`／`` ` ``／`~~`／`*` 由 `add_inline()` 转成字形，文字一字不丢
        （这里用同源的 `_inline_plain()`）。

    第四批改动 7 新增 `fig_text_by_line`（{源行号: 该行图题的期望文字}）：**超页切块**的插图
    在成稿里每块面板都有一个图题段（第 k≥2 块是「原图题（续 k/K）」），故这一行会落进成稿的
    图题文字是「各块图题依次拼起来」，由 `plan_image_panels()` 现场算出。期望文字一侧若不同步，
    等价性自检会把重复出现的图题判成「成稿凭空造字」。**不切块的图不进映射**，走的还是老路径。

    返回与 lines 等长的字符串列表：被整行剥掉的位置是 ""。
    """
    fig_text = fig_text_by_line or {}
    out = []
    in_code = False
    for idx, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("```"):                      # 围栏本身（版式记号）
            in_code = not in_code
            out.append("")
            continue
        if in_code:
            out.append(s if keep_code_backticks else s.rstrip("`"))
            continue
        if not s or s == "---" or s.startswith("<p align"):
            out.append("")
            continue
        m = H_RE.match(s)
        if m:
            # 标题文字过「渲染文本映射」：成稿里的「摘  要」「目  录」在源文件里写作
            # 「摘要」「目录」，期望文字一侧必须同步，否则会被误判成「凭空造字」。
            out.append(_inline_plain(_render_text(m.group(2).strip())))
            continue
        m = IMG_RE.match(s)
        if m:
            # 图题文字 = alt（不切块）；超页切块的行由 `fig_text_by_line` 给「各块图题拼起来」
            out.append(fig_text.get(idx) or _inline_plain(m.group(1).strip()))
            continue
        if s.startswith("|"):
            if SEP_ROW_RE.match(s):
                out.append("")
            else:
                out.append("".join(_inline_plain(c) for c in _split_row(s)))
            continue
        if s.startswith(">"):
            out.append(_inline_plain(s[1:].strip()))
            continue
        out.append(_inline_plain(s))                 # 正文段／列表项（标记原样保留）／参考文献条目
    return out


def expected_norm(lines, drop_idx, keep_code_backticks=False, fig_text_by_line=None):
    """期望归一化文字 = 封面 + 声明页 + 前置区段 + 目录 + 正文（后两者按源侧剥标记后的行拼接）。

    目录位置与 `build_document()` 一致：插在最后一个前置区段（摘要／Abstract）之后、正文之前。
    声明页文字（`_statement_text()`）与目录文字一样**不是源文件内容**，是模板固定表格件／版式件，
    由 `build_document()` 生成，故在此按同一顺序、同一常量补进期望值——两侧同源，等价性判据
    仍然只看「论文正文一个字没多也没少」。期望文字**直接来自源文件行**（不是来自解析后的块），
    所以「丢正文」与「凭空造正文」都会被抓到；被剔除的两类工作留痕按行号排除，题目行由封面
    文字（TITLE 常量）承接。
    `fig_text_by_line`（第四批改动 7）＝超页切块行在成稿里重复出现的图题文字，
    按同一行号交给 `strip_md_lines()`。
    """
    stripped = strip_md_lines(lines, keep_code_backticks, fig_text_by_line)
    cut = len(lines)
    for i, l in enumerate(lines):
        m = H_RE.match(l.strip())
        if (m and len(m.group(1)) == 1 and i not in drop_idx
                and m.group(2).strip() not in FRONT_SECTIONS):
            cut = i
            break
    front = [stripped[i] for i in range(0, cut) if i not in drop_idx]
    body = [stripped[i] for i in range(cut, len(lines)) if i not in drop_idx]
    return (_norm(_cover_text()) + _norm(_statement_text()) + _norm("\n".join(front))
            + _norm(_toc_text()) + _norm("\n".join(body)))


def _diff_report(got, want, lines, limit=6, width=70):
    """差集诊断：逐处给出「源侧多出（疑似丢正文）」与「成稿多出（疑似凭空造字）」，并回指源行号。

    只在归一化等价性自检失败时调用。归一化文字已经去掉全部空白，所以差集就是实打实的字。
    """
    rows = []
    i = 0
    while len(rows) < limit:
        n = min(len(got), len(want))
        pre = 0
        while i + pre < n and got[i + pre] == want[i + pre]:
            pre += 1
        g, w = got[i + pre:i + pre + width], want[i + pre:i + pre + width]
        if not g and not w:
            break
        rows.append("  差异 %d（归一处 %d 字）：源侧多出 %r ／ 成稿多出 %r"
                    % (len(rows) + 1, i + pre, w, g))
        probe = (w or g)[:12]
        hits = [str(k) for k, l in enumerate(lines) if probe and probe in l][:3]
        rows.append("      片段在源文件的行号：%s" % ("、".join(hits) if hits else "未找到"))
        i = i + pre + 1
    if not rows:
        rows.append("  差集为空（成稿 %d 字 == 期望 %d 字）" % (len(got), len(want)))
    return rows


def verify(det_bytes, expect_norm, stats, meta):
    """读回产物做硬自检；返回 (结果字典, 失败清单)。任一失败都让 main() 非零退出且不写盘。"""
    doc = Document(io.BytesIO(det_bytes))
    paras = doc.paragraphs
    texts = list(iter_block_text(doc))
    joined = "\n".join(texts)
    ss, dz = meta["src_stats"], meta["dropped"]
    exp = {
        "h1": ss["h1"] - dz["h1"], "h2": ss["h2"] - dz["h2"], "h3": ss["h3"] - dz["h3"],
        "tables": ss["table"] - dz["tables"], "table_caps": ss["table_cap"] - dz["table_caps"],
        "images": ss["img"] - dz["imgs"],
    }
    with zipfile.ZipFile(io.BytesIO(det_bytes)) as zf:
        names = zf.namelist()
        dates = sorted({info.date_time for info in zf.infolist()})
        doc_xml = zf.read("word/document.xml").decode("utf-8")
        style_xml = zf.read("word/styles.xml").decode("utf-8")
        headers = [n for n in names if re.match(r"^word/header\d*\.xml$", n)]
        footers = [n for n in names if re.match(r"^word/footer\d*\.xml$", n)]
    # ---- 模板规格读回（字号／字体从 styles.xml 里按样式名取，不靠 python-docx 的继承结果）----
    def _style_xml(name):
        """某个段落样式的完整 `<w:style>…</w:style>` 片段（取不到返回 ""）。"""
        m = re.search(r'<w:style [^>]*w:styleId="%s".*?</w:style>' % re.escape(name),
                      style_xml, re.S)
        return m.group(0) if m else ""

    def _style_sz(name, default=0.0):
        s = re.search(r'<w:sz w:val="(\d+)"/>', _style_xml(name))
        return int(s.group(1)) / 2.0 if s else default

    def _style_ea(name):
        # 注意：`<w:rFonts … w:eastAsia="黑体" w:cs="…"/>` 里 eastAsia 不是最后一个属性，
        # 所以不能写成 `<w:eastAsia="([^"]+)"/>`（那会漏配，实测踩过一次）。
        # 注意：`w:eastAsia` 是 `<w:rFonts>` 的**属性**，不是独立元素，所以模式不能带前导 `<`
        # （写成 `<w:eastAsia="…"` 会永远配不上——实测踩过一次，报「eastAsia 为空」误判）。
        e = re.search(r'w:eastAsia="([^"]+)"', _style_xml(name))
        return e.group(1) if e else ""

    def _style_attr(name, tag, attr):
        """某样式里 `<tag …/>` 的某个属性值（取不到返回 None）。用于读回 `w:spacing`／`w:bottom`。"""
        seg = re.search(r"<%s\b[^>]*/>" % re.escape(tag), _style_xml(name))
        if not seg:
            return None
        a = re.search(r'w:%s="([^"]*)"' % re.escape(attr), seg.group(0))
        return a.group(1) if a else None

    font_sizes = {"Heading1": _style_sz("Heading1"), "Heading2": _style_sz("Heading2"),
                  "Heading3": _style_sz("Heading3"),
                  "参考文献条目": _style_sz("参考文献条目"),
                  "图题": _style_sz("图题", _style_sz("Normal")),
                  "表题": _style_sz("表题", _style_sz("Normal")),
                  "正文段落": _style_sz("正文段落", _style_sz("Normal")),
                  "声明标题": _style_sz("声明标题"),
                  "页脚页码": _style_sz("页脚页码", _style_sz("Normal")),
                  "页眉": _style_sz("页眉", _style_sz("Normal"))}
    # 第四批改动 3／4／5 的三个读回口径（都直接读 styles.xml，不看 python-docx 的继承结果）：
    #   ① 正文段落行距：`w:line="400" w:lineRule="exact"` ＝ 固定值 20 磅（模板「0毕设正文」同款）；
    #   ② 页眉下边框：`w:pBdr/w:bottom` 的四属性须与模板页眉样式逐属性一致；
    #   ③ 页眉／页脚字号：分别 9pt／12pt（见上面的 font_sizes）。
    body_line = (_style_attr("正文段落", "w:spacing", "line"),
                 _style_attr("正文段落", "w:spacing", "lineRule"))
    head_bdr = {"present": "<w:pBdr>" in _style_xml("页眉"),
                "val": _style_attr("页眉", "w:bottom", "val"),
                "color": _style_attr("页眉", "w:bottom", "color"),
                "sz": _style_attr("页眉", "w:bottom", "sz"),
                "space": _style_attr("页眉", "w:bottom", "space")}
    h1_ea = _style_ea("Heading1")
    # 标题文本清单：这些标题**不都是 Heading 样式**（目录／声明的标题用各自的独立样式，
    # 不能带大纲级别，否则会混进目录域），故按「全部段落文本」核，而不是只看 Heading 样式段。
    headings = [p.text for p in paras]
    # 节与页边距：EMU → cm（1 cm = 360000 EMU）
    secs = [{"w_cm": round(s.page_width.cm, 4), "h_cm": round(s.page_height.cm, 4),
             "top_cm": round(s.top_margin.cm, 4), "bottom_cm": round(s.bottom_margin.cm, 4),
             "left_cm": round(s.left_margin.cm, 4), "right_cm": round(s.right_margin.cm, 4)}
            for s in doc.sections]
    # ---- 分节页码／页眉／页脚：**直接读 sectPr 与部件 XML**，不靠 python-docx 的继承解析 ----
    # 为什么要自己解析继承：python-docx 的 `section.footer.part` 走 `_get_or_add_definition()`，
    # 该函数在「本节没有引用」时会**递归取上一节的定义、必要时现场新建一个**——拿它做只读自检
    # 既会误判（把继承来的当成自己的），又会在内存里改文档。这里按 OOXML 规则自己解析：
    # 本节没有 `w:footerReference`（default 型）就往上找最近一个有引用且有定义的节。
    with zipfile.ZipFile(io.BytesIO(det_bytes)) as zf3:
        rels_xml = zf3.read("word/_rels/document.xml.rels").decode("utf-8")
        rel_map = {m.group(1): m.group(2) for m in re.finditer(
            r'<Relationship [^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels_xml)}
        part_xml = {}
        for n in names:
            if re.match(r"^word/(header|footer)\d*\.xml$", n):
                part_xml[n.split("/")[-1]] = zf3.read(n).decode("utf-8")

    def _ref_ids(sect_pr, tag):
        """某一节的 `w:headerReference`／`w:footerReference`：{type: rId}。"""
        out = {}
        for el in sect_pr.findall(qn(tag)):
            out[el.get(qn("w:type")) or "default"] = el.get(qn("r:id"))
        return out

    def _part_text(xml):
        """部件里的可见文字（把 w:t 拼起来）：页脚三个 run `-`／PAGE 域／`-` → '-1-'。"""
        return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S))

    sec_refs = []                    # 每节的 {header:{type:rId}, footer:{...}, pgNumType:{fmt,start}}
    for s in doc.sections:
        sp = s._sectPr
        pg = sp.find(qn("w:pgNumType"))
        sec_refs.append({
            "header": _ref_ids(sp, "w:headerReference"),
            "footer": _ref_ids(sp, "w:footerReference"),
            "pgnum": None if pg is None else
                    {"fmt": pg.get(qn("w:fmt")), "start": pg.get(qn("w:start"))},
        })

    def _resolve(idx, kind):
        """按 OOXML 继承规则解析第 idx 节的页眉／页脚部件名（本节无引用则回溯上一节）。"""
        for k in range(idx, -1, -1):
            rid = sec_refs[k][kind].get("default")
            if rid:
                return rel_map.get(rid, "").split("/")[-1]
        return None

    sec_heads = [_resolve(i, "header") for i in range(len(sec_refs))]
    sec_feet = [_resolve(i, "footer") for i in range(len(sec_refs))]
    head_texts = [None if p is None else _part_text(part_xml.get(p, "")) for p in sec_heads]
    foot_texts = [None if p is None else _part_text(part_xml.get(p, "")) for p in sec_feet]
    # ---- 分页来源审计（第三批改动 4）：每个一级标题前面**恰好一个**分页来源 ----
    # 来源共三类：① 段落所属样式的 `w:pageBreakBefore`（Heading 1 样式带）；② 段落自己的
    # `w:pageBreakBefore`（本轮给紧跟分节符的两处写成 `w:val="0"`，即显式关掉）；③ 段前分节符
    # （上一段的 `w:pPr/w:sectPr`）。另有第四类「显式分页符」`w:br w:type="page"`——本稿必须为 0。
    body_els = list(doc.element.body.iterchildren())
    h1_style_pbb = bool(re.search(r'w:styleId="Heading1".*?<w:pageBreakBefore/>',
                                  style_xml, re.S))
    break_audit = []
    for i, el in enumerate(body_els):
        if el.tag != qn("w:p"):
            continue
        if el.find(qn("w:pPr")) is None or el.find(qn("w:pPr")).find(qn("w:pStyle")) is None:
            continue
        style = el.find(qn("w:pPr")).find(qn("w:pStyle")).get(qn("w:val"))
        if style != "Heading1":
            continue
        text = "".join(t.text or "" for t in el.iter(qn("w:t")))
        ppr = el.find(qn("w:pPr"))
        own = ppr.find(qn("w:pageBreakBefore"))
        raw = None if own is None else own.get(qn("w:val"))
        # `w:val` 的「关」有 0／false 两种合法写法，两种都要认（python-docx 写的是 "0"）
        own_off = own is not None and str(raw).lower() in ("0", "false", "off")
        own_on = own is not None and not own_off
        prev = body_els[i - 1] if i else None
        sect_before = bool(prev is not None and prev.tag == qn("w:p")
                           and prev.find(qn("w:pPr")) is not None
                           and prev.find(qn("w:pPr")).find(qn("w:sectPr")) is not None)
        sources = []
        if h1_style_pbb and not own_off:
            sources.append("样式级 pageBreakBefore")
        if own_on:
            sources.append("段落级 pageBreakBefore")
        if sect_before:
            sources.append("分节符")
        br_before = 0
        if prev is not None and prev.tag == qn("w:p"):
            br_before = sum(1 for b in prev.iter(qn("w:br"))
                            if b.get(qn("w:type")) == "page")
        break_audit.append({"text": text, "sources": sources, "br_in_prev": br_before,
                            "own_pbb": raw, "sect_before": sect_before})
    explicit_breaks = [i for i, el in enumerate(body_els)
                       if any(b.get(qn("w:type")) == "page" for b in el.iter(qn("w:br")))]
    res = {
        "h1": sum(1 for p in paras if p.style.name == "Heading 1"),
        "h2": sum(1 for p in paras if p.style.name == "Heading 2"),
        "h3": sum(1 for p in paras if p.style.name == "Heading 3"),
        "tables": len(doc.tables),
        "table_caps": sum(1 for p in paras if p.style.name == "表题"),
        "fig_caps": sum(1 for p in paras if p.style.name == "图题"),
        # 「图题」样式段分两种：承载图片的段（无文字）与图题段（有文字）。第四批改动 6 的判据
        # 用**有文字**的那一种数「一块面板一个图题」；总数仍断言 == 2×面板数。
        "fig_cap_texts": sum(1 for p in paras if p.style.name == "图题" and p.text.strip()),
        "cont_caps": sum(1 for p in paras
                         if p.style.name == "图题" and "（续 " in p.text),
        "images": len(doc.inline_shapes),
        "media": sum(1 for n in names if n.startswith("word/media/")),
        # 逐张内嵌图的实测宽×高（cm）：第四批改动 1 的关键验收——高度必须 ≤ 版心高 23.70cm
        "img_sizes": [(round(sh.width / 360000.0, 2), round(sh.height / 360000.0, 2))
                      for sh in doc.inline_shapes],
        "paras": len(paras),
        "chars": len(joined),
        "hanzi": _hanzi(joined),
        "norm_text": _norm(joined),
        "norm_equal": _norm(joined) == expect_norm,
        "occur": {t: joined.count(t) for t in
                  (FORBIDDEN_TERMS + MARKUP_RESIDUE + DROPPED_META_KEYS + (REVISION_TITLE,))},
        "rev_exact_any": sum(1 for t in texts if t.strip() == REVISION_TITLE),
        "rev_exact_head": sum(1 for p in paras if p.text.strip() == REVISION_TITLE
                              and p.style.name.startswith("Heading")),
        "rev_substr": joined.count(REVISION_TITLE),
        "rev_substr_want": meta["expect_rev_substr"],
        "rules": sorted({r for _, r, _ in stats["img_rules"]}),
        "toc_field": "TOC" in doc_xml,
        "page_field": any("PAGE" in part_xml.get(f.split("/")[-1], "") for f in footers),
        "zip_dates": dates,
        "front_ok": meta["front_ok"],
        "expected": exp,
        "dropped": dz,
        # ---- 第二批／第三批：模板规格 ----
        "secs": secs,
        "sections": len(doc.sections),
        "sec_refs": sec_refs,
        "sec_heads": sec_heads,
        "sec_feet": sec_feet,
        "head_texts": head_texts,
        "foot_texts": foot_texts,
        "font_sizes": font_sizes,
        "headers": headers,
        "footers": footers,
        "break_audit": break_audit,
        "explicit_breaks": explicit_breaks,
        "h1_style_pbb": h1_style_pbb,
        "stmt_sha256": hashlib.sha256(STATEMENT_BODY.encode("utf-8")).hexdigest(),
        "h1_ea": h1_ea,
        "headings": headings,
        "body_line": body_line,
        "head_bdr": head_bdr,
        "panel_total": meta["panel_total"],
    }
    fails = []

    # ① 标题数：源侧 − 剔除 == 读回 == 结构基线（逐级列出数字）
    for lvl, key in ((1, "h1"), (2, "h2"), (3, "h3")):
        if not (res[key] == exp[key] == STRUCT_BASELINE[key]):
            fails.append("Heading%d 数不符：源侧 %d − 剔除 %d = 期望 %d，读回 %d，结构基线 %d"
                         % (lvl, ss[key], dz[key], exp[key], res[key], STRUCT_BASELINE[key]))
    # ② 插图（第四批改动 6 改口径）。三层判据，别把「9 张源图」这一项丢了：
    #    ⑴ 源侧插图数单独断言 == 结构基线 9（源图张数，与切块无关）；
    #    ⑵ 面板总数由切图结果现场推导（`meta["panel_total"]`，来自各图 `panels` 的实际长度），
    #       断言 成稿内嵌图片数 == word/media 条目数 == 面板总数；
    #    ⑶ 图题：有文字的「图题」段 == 面板总数；「图题」样式段总数 == 2×面板总数
    #       （每块面板另有一个只装图片、不带文字的「图题」段）；
    #       续图标记图题数 == 面板总数 − 源图数（第 1 块用原图题，第 2..K 块才带「（续 k/K）」）。
    if exp["images"] != STRUCT_BASELINE["images"]:
        fails.append("源侧插图数不符：源 %d − 剔除 %d = %d，结构基线 %d 张源图"
                     % (ss["img"], dz["imgs"], exp["images"], STRUCT_BASELINE["images"]))
    if not (res["images"] == res["media"] == res["panel_total"]):
        fails.append("插图面板数不符：%d 张源图（剔除 %d）切出面板 %d 块，成稿内嵌图片 %d，"
                     "word/media 条目 %d（三者必须相等）"
                     % (exp["images"], dz["imgs"], res["panel_total"], res["images"], res["media"]))
    if res["rules"] != [1]:
        fails.append("插图解析规则不是全①：实际命中规则 %s（图注反引号路径写错，或图不在仓库根）"
                     % res["rules"])
    if res["fig_cap_texts"] != res["panel_total"]:
        fails.append("图题段（有文字的「图题」段）数 %d != 面板总数 %d（一块面板一个图题）"
                     % (res["fig_cap_texts"], res["panel_total"]))
    if res["fig_caps"] != 2 * res["panel_total"]:
        fails.append("「图题」样式段总数 %d != 2×面板总数 %d（每块面板 1 个嵌图段 + 1 个图题段）"
                     % (res["fig_caps"], 2 * res["panel_total"]))
    if res["cont_caps"] != res["panel_total"] - exp["images"]:
        fails.append("续图标记图题 %d 个 != 面板总数 %d − 源图数 %d（第 1 块用原图题）"
                     % (res["cont_caps"], res["panel_total"], exp["images"]))
    # ⑵b 本项最关键的验收：逐张内嵌图的**实测高度** ≤ 版心高 23.70cm（旧版三张图高达
    #     89.69／28.42／60.23cm，Word 渲染后图的下半截跑到页外）。切图规划的上限是 23.4cm，
    #     这里用版心高 23.70cm 做硬判据，容忍 0.01cm 的 EMU 取整误差。
    over = [(i + 1, w_cm, h_cm) for i, (w_cm, h_cm) in enumerate(res["img_sizes"])
            if h_cm > TEXT_HEIGHT_CM + 0.01]
    if over:
        fails.append("有 %d 张内嵌图超出**版心高** %.2fcm：%s"
                     % (len(over), TEXT_HEIGHT_CM,
                        "；".join("第%d张 %.2f×%.2fcm" % t for t in over)))
    # ③ 表格：口径甲＝表块数（连续 `|` 行成块），口径乙＝带 `**表 x-y …**` 表题行的表块数
    if not (res["tables"] == exp["tables"] == STRUCT_BASELINE["tables"]):
        fails.append("表格数不符（口径甲：连续 `|` 行成块）：源侧 %d − 剔除 %d = 期望 %d，"
                     "读回 %d，结构基线 %d"
                     % (ss["table"], dz["tables"], exp["tables"], res["tables"],
                        STRUCT_BASELINE["tables"]))
    if not (res["table_caps"] == exp["table_caps"] == STRUCT_BASELINE["table_caps"]):
        fails.append("表题数不符（口径乙：表格块上方紧邻表题行）：源侧 %d − 剔除 %d = 期望 %d，"
                     "读回 %d，结构基线 %d"
                     % (ss["table_cap"], dz["table_caps"], exp["table_caps"],
                        res["table_caps"], STRUCT_BASELINE["table_caps"]))
    # ④ 归一化文字等价性（成稿 == 源 − 被剔除区 − Markdown 标记）
    if not res["norm_equal"]:
        fails.append("归一化文字等价性自检失败：成稿文字 != 源文字 − 被剔除区 − Markdown 标记")
    # ⑤ 字面标记／术语零命中
    for t in FORBIDDEN_TERMS + MARKUP_RESIDUE:
        if res["occur"][t]:
            fails.append("产物残留禁用串 %r × %d" % (t, res["occur"][t]))
    # ⑥ 修订记录：不得有整段命中；正文里的子串交叉引用次数必须与源侧保留数一致
    if res["rev_exact_any"] or res["rev_exact_head"]:
        fails.append("产物仍存在文本恰为「修订记录」的段落 × %d（其中标题段 × %d）"
                     % (res["rev_exact_any"], res["rev_exact_head"]))
    if res["rev_substr"] != res["rev_substr_want"]:
        fails.append("「修订记录」子串出现 %d 次，源侧保留区为 %d 次（交叉引用被改动或多剔）"
                     % (res["rev_substr"], res["rev_substr_want"]))
    # ⑦ 文首元数据特征串零命中（「文档编号」不在此列：它是正文 document 表的字段名）
    for t in META_RESIDUE_KEYS:
        if res["occur"][t]:
            fails.append("产物残留文首元数据特征串 %r × %d" % (t, res["occur"][t]))
    # ⑧ 前置区段、TOC 域、PAGE 域、zip 条目时间
    if not res["front_ok"]:
        fails.append("源文件缺少前置区段：期望含 %s" % "／".join(FRONT_SECTIONS))
    if not res["toc_field"]:
        fails.append("word/document.xml 里找不到 TOC 域")
    if not res["page_field"]:
        fails.append("页脚里找不到 PAGE 域")
    if res["zip_dates"] != [ZIP_DATE_TIME]:
        fails.append("zip 条目时间不是固定值：%s（确定性会破）" % res["zip_dates"])
    # ⑨ 模板规格（第二批）：页边距／字号／字体／前置标题写法／声明页／分节编页
    for k, sv in enumerate(secs):
        for side, key in (("上", "top_cm"), ("下", "bottom_cm"),
                          ("左", "left_cm"), ("右", "right_cm")):
            if abs(sv[key] - 3.0) > 0.005:
                fails.append("第 %d 节页边距%s为 %.4f cm，模板要求 3.00 cm" % (k + 1, side, sv[key]))
        if abs(sv["w_cm"] - 21.0) > 0.005 or abs(sv["h_cm"] - 29.7) > 0.005:
            fails.append("第 %d 节纸张不是 A4 21.0×29.7 cm：实测 %.4f×%.4f"
                         % (k + 1, sv["w_cm"], sv["h_cm"]))
    for name, want in (("Heading1", 16.0), ("Heading2", 14.0), ("Heading3", 12.0),
                       ("参考文献条目", 12.0), ("图题", 10.5), ("表题", 10.5),
                       ("正文段落", 12.0), ("声明标题", 16.0),
                       ("页眉", 9.0), ("页脚页码", 12.0)):
        got = font_sizes.get(name, 0.0)
        if abs(got - want) > 0.01:
            fails.append("样式「%s」字号 %.1fpt，模板要求 %.1fpt" % (name, got, want))
    # ⑨b 第四批改动 3／5 的两条读回断言（都直接读 styles.xml）：
    #   * 正文段落行距必须是**固定值 20 磅**（w:line="400" w:lineRule="exact"，模板「0毕设正文」同款）
    #   * 页眉样式必须带 `w:pBdr/w:bottom`，四属性与模板页眉样式逐属性一致
    if res["body_line"] != ("400", "exact"):
        fails.append("正文段落行距为 line=%r lineRule=%r，模板要求 line=\"400\" lineRule=\"exact\""
                     "（固定值 20 磅）" % res["body_line"])
    hb = res["head_bdr"]
    if not hb["present"] or (hb["val"], hb["color"], hb["sz"], hb["space"]) != \
            (HEADER_BORDER["val"], HEADER_BORDER["color"],
             HEADER_BORDER["sz"], HEADER_BORDER["space"]):
        fails.append("页眉样式下边框不符：实测 present=%s val=%r color=%r sz=%r space=%r，"
                     "模板要求 %r" % (hb["present"], hb["val"], hb["color"], hb["sz"],
                                      hb["space"], HEADER_BORDER))
    if res["h1_ea"] != FONT_TITLE_CN:
        fails.append("章标题 eastAsia 字体为 %r，模板要求 %r" % (res["h1_ea"], FONT_TITLE_CN))
    if RENDER_TEXT_MAP["摘要"] not in headings:
        fails.append("成稿里找不到带两个半角空格的「%s」标题" % RENDER_TEXT_MAP["摘要"])
    if RENDER_TEXT_MAP["目录"] not in headings:
        fails.append("成稿里找不到带两个半角空格的「%s」标题" % RENDER_TEXT_MAP["目录"])
    if STATEMENT_TITLE not in res["headings"]:
        fails.append("成稿里找不到声明页标题「%s」" % STATEMENT_TITLE)
    if STATEMENT_BODY not in res["norm_text"]:
        fails.append("成稿里找不到声明页正文（模板固定表述）")
    # 声明正文必须与模板逐字一致：常量 sha256 就是模板该段的 sha256（第三批改动 1）
    if res["stmt_sha256"] != STATEMENT_BODY_SHA256:
        fails.append("声明正文 sha256 为 %s，模板原文应为 %s（法定声明不得改写）"
                     % (res["stmt_sha256"], STATEMENT_BODY_SHA256))
    # ⑩ 分节编页／页眉／页脚（第三批改动 5、6）：3 节、页眉只从摘要起、页脚 `-N-`
    if res["sections"] != SECTION_COUNT:
        fails.append("节数为 %d，期望 %d（① 封面＋声明 ② 摘要…目录 ③ 正文…致谢）"
                     % (res["sections"], SECTION_COUNT))
    else:
        want_pgnum = [None,
                      {"fmt": FRONT_PAGE_FMT, "start": str(FRONT_PAGE_START)},
                      {"fmt": BODY_PAGE_FMT, "start": str(BODY_PAGE_START)}]
        got_pgnum = [s["pgnum"] for s in res["sec_refs"]]
        if got_pgnum != want_pgnum:
            fails.append("分节页码不符：期望 %r，实测 %r" % (want_pgnum, got_pgnum))
        # 页眉：第 1 节没有页眉（封面与声明不显示页眉），第 2 节有且文字逐字等于 HEADER_TEXT，
        # 第 3 节继承第 2 节（模板节 8～14 的写法），故解析结果与第 2 节同部件
        if res["sec_heads"][0] is not None:
            fails.append("第 1 节（封面＋声明）竟然挂着页眉部件 %r，模板里封面与声明没有页眉"
                         % res["sec_heads"][0])
        for idx in (1, 2):
            if res["head_texts"][idx] != HEADER_TEXT:
                fails.append("第 %d 节页眉文字为 %r，期望 %r"
                             % (idx + 1, res["head_texts"][idx], HEADER_TEXT))
        if len(res["head_texts"]) < 3 or res["head_texts"][2] != res["head_texts"][1]:
            fails.append("第 3 节页眉没有继承第 2 节：%r vs %r"
                         % (res["head_texts"][1:2] or [None], res["head_texts"][2:3] or [None]))
        # 页脚：第 1 节无 PAGE 域；第 2、3 节页脚形如 `-N-`
        if "PAGE" in (res["foot_texts"][0] or ""):
            fails.append("第 1 节（封面＋声明）页脚里仍有 PAGE 域，该节应当不显示页码")
        for idx in (1, 2):
            ft = res["foot_texts"][idx]
            if ft is None or "PAGE" not in (part_xml.get(res["sec_feet"][idx] or "", "")):
                fails.append("第 %d 节页脚里没有 PAGE 域，页码不会显示" % (idx + 1))
            elif ft != FOOTER_LEAD + "1" + FOOTER_TAIL:
                fails.append("第 %d 节页脚文字为 %r，期望 `-N-` 体例 %r"
                             % (idx + 1, ft, FOOTER_LEAD + "1" + FOOTER_TAIL))
    # ⑪ 分页来源唯一（第三批改动 4）：显式分页符 0 个；每个一级标题前面恰好一个分页来源
    if res["explicit_breaks"]:
        fails.append("word/document.xml 里有 %d 处显式分页符 `w:br w:type=page`（段落序号 %s），"
                     "样式级分页已足够，显式分页符会与它叠成空白页"
                     % (len(res["explicit_breaks"]), res["explicit_breaks"]))
    bad = [(b["text"], b["sources"], b["br_in_prev"]) for b in res["break_audit"]
           if len(b["sources"]) != 1 or b["br_in_prev"]]
    if bad:
        for text, sources, br in bad:
            fails.append("一级标题「%s」前面的分页来源不是恰好一个：%s（紧邻上一段里的显式分页符 "
                         "%d 个）" % (text, "＋".join(sources) or "0 个", br))
    if not res["h1_style_pbb"]:
        fails.append("Heading 1 样式没有 `w:pageBreakBefore`，各章不会另起新页")
    return res, fails


# =============================================================================
# 主流程
# =============================================================================
def build(src_path=SRC, keep_code_backticks=False):
    """解析 → 装配 → 确定性打包。返回 (产物字节, 统计, 元数据, 期望归一化文字)。"""
    if not os.path.isfile(src_path):
        raise SystemExit("找不到源文件：%s" % src_path)
    text = _read_text(src_path)
    lines = text.split("\n")
    blocks = parse_blocks(lines, keep_code_backticks=keep_code_backticks)
    head, sections = split_sections(blocks)

    # 源侧统计（剔除前）
    src_stats = {
        "h1": sum(1 for b in blocks if b["kind"] == "h1"),
        "h2": sum(1 for b in blocks if b["kind"] == "h2"),
        "h3": sum(1 for b in blocks if b["kind"] == "h3"),
        "table": sum(1 for b in blocks if b["kind"] == "table"),
        "table_cap": sum(1 for b in blocks if b["kind"] == "table" and b["caption"]),
        "img": sum(1 for b in blocks if b["kind"] == "img"),
        "ref": sum(1 for b in blocks if b["kind"] == "ref"),
        "code": sum(1 for b in blocks if b["kind"] == "code"),
        "ragged": sum(1 for b in blocks if b["kind"] == "table" and b["ragged"]),
    }

    # 剔除：文首元数据块（题目段整段）＋ 两处修订记录区块（见 compute_drops 的说明）
    drop_idx, drop_blocks, dropped = compute_drops(head, sections)
    dropped["sections"] = [t for t, _ in sections if t == REVISION_TITLE]
    removed_lines = sorted(drop_idx)
    removed_text = "\n".join(lines[i] for i in removed_lines)
    kept_text = "\n".join(l for i, l in enumerate(lines) if i not in drop_idx)
    dropped["chars"] = len(removed_text)
    dropped["hanzi"] = _hanzi(removed_text)
    dropped["bytes"] = len(removed_text.encode("utf-8"))
    dropped["meta_keys"] = [k for k in DROPPED_META_KEYS if k in removed_text]

    # 封面题目必须与源文件题目**逐字一致**：题目行被剔除后由封面承接，不一致就等于改题
    title_blocks = [b for b in blocks if b["kind"] == "h1" and b["text"].strip() == TITLE]
    if len(title_blocks) != 1:
        raise ValueError("源文件里文本恰为脚本常量 TITLE 的一级标题有 %d 个（应为 1 个）：%r"
                         % (len(title_blocks), TITLE))
    # 保留区段 = 去掉「题目段」与「文末修订记录段」两个整段，再逐块滤掉段内被剔除的块
    # （第七章里的 `## 修订记录` 与它的整张表就在段内——旧实现漏的正是这一处）
    drop_ids = {id(b) for _, b in drop_blocks}
    kept_sections = [(t, [b for b in bs if id(b) not in drop_ids])
                     for t, bs in sections if t != TITLE and t != REVISION_TITLE]
    kept_blocks = [b for _, bs in kept_sections for b in bs]
    # 保留块必须按源顺序覆盖「未被剔除的行」，否则说明剔除逻辑与解析结果对不上
    covered = set()
    for b in kept_blocks:
        a, z = b["src_span"]
        covered.update(range(a, z + 1))
        if b.get("cap_span"):
            a2, z2 = b["cap_span"]
            covered.update(range(a2, z2 + 1))
    lost = sorted(set(range(len(lines))) - covered - drop_idx
                  - {i for i, l in enumerate(lines)
                     if not l.strip() or l.strip() == "---" or l.strip().startswith("```")
                     or l.strip().startswith("<p align")})
    if lost:
        raise ValueError("有 %d 行源文件既没被解析成块、也不在剔除区（解析器漏行）：%s"
                         % (len(lost), lost[:10]))

    stats = {"h1": 0, "h2": 0, "h3": 0, "p": 0, "list": 0, "quote": 0, "ref": 0,
             "code": 0, "img": 0, "table": 0, "table_cap": 0, "img_rules": [],
             "sections": 0, "panels": [], "panel_total": 0}
    # 超页插图切块规划（第四批改动 1／7）：**装配之前**统一算一次，渲染侧（`b["panels"]`）
    # 与期望文字侧（`fig_text_by_line` 的图题文字）用的是同一份结果。只读源 PNG，不改不落盘。
    fig_text_by_line = plan_image_panels(blocks)
    doc = build_document(kept_sections, stats)
    _set_core_properties(doc)
    buf = io.BytesIO()
    doc.save(buf)
    det = _repack_deterministic(buf.getvalue())

    # 期望归一化文字：封面 + 前置区段 + 目录 + 正文（源侧按行剥掉 Markdown 标记）
    # 切块图重复出现的图题文字（含续图标记）按同一源行号交给期望文字一侧，两侧同源。
    expect_norm = expected_norm(lines, drop_idx, keep_code_backticks, fig_text_by_line)
    # 「修订记录」在成稿里的出现次数应当 == 源侧保留区里的次数（正文里的子串交叉引用不许多不许少）
    stripped = strip_md_lines(lines, keep_code_backticks, fig_text_by_line)
    rev_want = _norm("\n".join(stripped[i] for i in range(len(lines))
                               if i not in drop_idx)).count(REVISION_TITLE)
    meta = {"src_stats": src_stats, "removed": dropped, "kept_chars": len(kept_text),
            "kept_hanzi": _hanzi(kept_text), "src_chars": len(text), "src_hanzi": _hanzi(text),
            "src_bytes": len(text.encode("utf-8")), "src_lines": len(lines),
            "dropped": dropped, "dropped_sections": dropped["sections"],
            "expect_rev_substr": rev_want, "lines": lines,
            # 面板总数：由**保留块**的切图结果现场推导（自检的核心期望值，不写死数字）
            "panel_total": sum(len(b["panels"]) for b in kept_blocks if b["kind"] == "img"),
            "fig_text_by_line": fig_text_by_line,
            "front_ok": all(t in [x for x, _ in kept_sections] for t in FRONT_SECTIONS)}
    return det, stats, meta, expect_norm, kept_blocks


def main(argv=None):
    ap = argparse.ArgumentParser(description="把《29》论文 Markdown 草稿导出为 Word 提交件（姓名_学号_题目.docx）")
    ap.add_argument("--out", default=None, help="覆盖产出路径（试跑与确定性核对用）")
    ap.add_argument("--src", default=None, help="覆盖源文件路径")
    ap.add_argument("--check", action="store_true",
                    help="只核对磁盘产物是否与现场生成逐字节一致，不写盘")
    ap.add_argument("--keep-code-backticks", action="store_true",
                    help="代码块保留 PowerShell 续行反引号（默认并句去掉，以保证产物 0 反引号）")
    args = ap.parse_args(argv)

    src_path = os.path.abspath(args.src) if args.src else SRC
    out_path = os.path.abspath(args.out) if args.out else OUT

    try:
        det, stats, meta, expect_norm, kept_blocks = build(src_path, args.keep_code_backticks)
    except FileNotFoundError as exc:
        print("输入缺失：%s" % exc)
        return 2
    except RuntimeError as exc:                     # 切图依赖缺失／切块不收敛（第四批改动 1）
        print("切图失败：%s" % exc)
        return 2
    except ValueError as exc:
        print("解析失败：%s" % exc)
        return 2

    ss = meta["src_stats"]
    rm = meta["removed"]
    print("=" * 78)
    print("源文件：%s" % os.path.relpath(src_path, ROOT).replace(os.sep, "/"))
    print("  字符 %d ／ 汉字 %d ／ 字节 %d ／ 行 %d"
          % (meta["src_chars"], meta["src_hanzi"], meta["src_bytes"], meta["src_lines"]))
    print("  源侧标记：H1=%d H2=%d H3=%d 表格块=%d（带表题 %d）插图=%d 参考文献条目=%d 代码块=%d"
          % (ss["h1"], ss["h2"], ss["h3"], ss["table"], ss["table_cap"], ss["img"],
             ss["ref"], ss["code"]))
    if ss["ragged"]:
        print("  注意：有 %d 个表格存在参差行（已按最长行补空单元格）" % ss["ragged"])
    print("剔除（工作留痕，非论文内容）：")
    print("  文首元数据块（题目段整段：题目行的引用块＋`| 项 | 取值 |` 表）与两处修订记录"
          "（章内 `## 修订记录`、文末 `# 修订记录`，含各自整张修订表）共 %d 行" % rm["lines"])
    print("  字符 %d ／ 汉字 %d ／ 字节 %d；命中的元数据键：%s"
          % (rm["chars"], rm["hanzi"], rm["bytes"], "、".join(rm["meta_keys"])))
    print("  被剔除的修订记录区段（源文件行号区间）：%s"
          % "；".join("%d-%d" % sp for sp in rm["revision_spans"]))
    print("  被剔除的块：%s" % "、".join("%s %d" % (k, v) for k, v in sorted(rm["by_reason"].items())))
    print("保留（论文内容）：字符 %d ／ 汉字 %d" % (meta["kept_chars"], meta["kept_hanzi"]))
    print("成稿标记：H1=%d H2=%d H3=%d 表格=%d（含表题 %d）插图=%d 参考文献条目=%d "
          "代码块=%d 正文段=%d 列表项=%d 引文=%d"
          % (stats["h1"], stats["h2"], stats["h3"], stats["table"], stats["table_cap"],
             stats["img"], stats["ref"], stats["code"], stats["p"], stats["list"],
             stats["quote"]))
    print("插图解析（规则①＝仓库根＋图注反引号路径；②＝按《29》所在目录；③＝按仓库根）：")
    for alt, rule, path in stats["img_rules"]:
        print("  [规则%d] %-46s → %s" % (rule, alt, path.replace(os.sep, "/")))
    print("插图切图摘要（第四批改动 1：只读源 PNG，源文件一字节未改；仅超页图切块）：")
    print("  版心 %.2f×%.2f cm；插图宽度上限 %.2f cm；单块高度上限 %.2f cm（版心高 − %.2f cm 余量）"
          % (TEXT_WIDTH / 360000.0, TEXT_HEIGHT_CM, IMG_MAX_WIDTH_CM, MAX_PANEL_H_CM,
             TEXT_HEIGHT_CM - MAX_PANEL_H_CM))
    for item in stats["panels"]:
        ps = item["panels"]
        full_cm = IMG_MAX_WIDTH_CM * item["src_h"] / item["src_w"]   # 不切时的高度（cm）
        if len(ps) == 1:
            print("  %-42s %d 块（不切：按 %.2fcm 宽渲染高 %.2f cm ≤ 上限 %.2f cm）"
                  % (item["alt"], 1, IMG_MAX_WIDTH_CM, full_cm, MAX_PANEL_H_CM))
        else:
            print("  %-42s %d 块（整图按 %.2fcm 宽渲染高 %.2f cm > 上限 %.2f cm，故切）"
                  % (item["alt"], len(ps), IMG_MAX_WIDTH_CM, full_cm, MAX_PANEL_H_CM))
            for k, pn in enumerate(ps, 1):
                print("      块 %d/%d：源图第 %d–%d 行（%d px 高）→ %.2f × %.2f cm%s"
                      % (k, len(ps), pn.top, pn.bottom - 1, pn.h_px,
                         pn.w_emu / 360000.0, pn.h_emu / 360000.0,
                         "　图题：" + item["alt"] + pn.cont if pn.cont else ""))
    print("  面板合计：%d 张源图 → %d 块面板（内嵌图片数与 word/media 条目数都应为 %d）"
          % (stats["img"], stats["panel_total"], stats["panel_total"]))
    print("-" * 78)

    res, fails = verify(det, expect_norm, stats, meta)
    exp = res["expected"]
    print("读回自检：Heading1=%d Heading2=%d Heading3=%d 表格=%d 内嵌图片=%d 段落=%d"
          % (res["h1"], res["h2"], res["h3"], res["tables"], res["images"], res["paras"]))
    print("标题数比对（源侧 ＝ 题目／剔除 ＋ 成稿）：")
    for lvl, key in ((1, "h1"), (2, "h2"), (3, "h3")):
        print("  Heading%d：源 %d ＝ 剔除 %d ＋ 成稿 %d ／期望 %d ／结构基线 %d  %s"
              % (lvl, ss[key], rm[key], res[key], exp[key], STRUCT_BASELINE[key],
                 "✓" if res[key] == exp[key] == STRUCT_BASELINE[key] else "✗"))
    print("表格口径（两个口径都断言）：")
    print("  口径甲（连续 `|` 行成块，含表头分隔行）：源 %d 块 − 剔除 %d（文首元数据表 1 ＋ "
          "两处修订记录表 2）＝ 成稿 Word 表 %d ／结构基线 %d"
          % (ss["table"], rm["tables"], res["tables"], STRUCT_BASELINE["tables"]))
    print("  口径乙（表格块上方紧邻 `**表 x-y …**` 表题行）：源 %d 块 − 剔除 %d ＝ 成稿「表题」"
          "段落 %d ／结构基线 %d"
          % (ss["table_cap"], rm["table_caps"], res["table_caps"],
             STRUCT_BASELINE["table_caps"]))
    print("插图：源 %d 张源图 − 剔除 %d ＝ %d（单独断言 ／结构基线 %d 张）；%d 张源图切出面板 %d 块；"
          "成稿内嵌 %d ＝ word/media 条目 %d ＝ 面板总数 %d；解析规则集合 %s"
          % (ss["img"], rm["imgs"], exp["images"], STRUCT_BASELINE["images"],
             exp["images"], res["panel_total"], res["images"], res["media"],
             res["panel_total"], res["rules"]))
    print("  图题：有文字的「图题」段 %d（＝面板总数）；「图题」样式段总数 %d（＝2×面板数）；"
          "续图标记图题 %d（＝面板总数 − 源图数）"
          % (res["fig_cap_texts"], res["fig_caps"], res["cont_caps"]))
    print("  内嵌图逐张实测宽×高（cm，硬判据：高 ≤ 版心高 %.2fcm）：" % TEXT_HEIGHT_CM)
    for i, (w_cm, h_cm) in enumerate(res["img_sizes"], 1):
        print("    第 %2d 张：%6.2f × %6.2f cm  %s"
              % (i, w_cm, h_cm, "✓" if h_cm <= TEXT_HEIGHT_CM + 0.01 else "✗ 超版心高"))
    if res["img_sizes"]:
        wmax = max(res["img_sizes"], key=lambda t: t[1])
        print("    最大高度 %.2f cm（第 %d 张）／版心高 %.2f cm；超版心的张数 %d"
              % (wmax[1], res["img_sizes"].index(wmax) + 1, TEXT_HEIGHT_CM,
                 sum(1 for _w, h in res["img_sizes"] if h > TEXT_HEIGHT_CM + 0.01)))
    print("  成稿文字：字符 %d ／ 汉字 %d" % (res["chars"], res["hanzi"]))
    print("  归一化等价性（成稿 == 源 − 剔除区 − Markdown 标记）：%s"
          % ("一致" if res["norm_equal"] else "不一致"))
    print("  差集：成稿 %d 字 %s 源侧期望 %d 字%s"
          % (len(res["norm_text"]), "==" if res["norm_equal"] else "!=", len(expect_norm),
             "（差集为空）" if res["norm_equal"] else ""))
    if not res["norm_equal"]:
        print("  差集诊断（逐处归类）：")
        for row in _diff_report(res["norm_text"], expect_norm, meta["lines"]):
            print(row)
    occ = res["occur"]
    print("  禁用串命中：" + "、".join("%s=%d" % (t, occ[t]) for t in
                                      (FORBIDDEN_TERMS + MARKUP_RESIDUE)))
    print("  「修订记录」：整段命中 %d（其中标题段 %d）；作为子串出现 %d 次（源侧保留区 %d 次，"
          "属对外部文档修订史的交叉引用，按「不改写正文」原样保留）"
          % (res["rev_exact_any"], res["rev_exact_head"], res["rev_substr"],
             res["rev_substr_want"]))
    print("  文首元数据特征串命中：" + "、".join("%s=%d" % (k, occ[k]) for k in META_RESIDUE_KEYS)
          + "（须全 0）")
    print("  「文档编号」命中 %d 次（六张 `document` 表的字段名，正文出现属正常，不作失败判据）"
          % occ["文档编号"])
    print("  包结构：TOC 域=%s；页脚 PAGE 域=%s；zip 条目时间集合=%s"
          % ("有" if res["toc_field"] else "无", "有" if res["page_field"] else "无",
             res["zip_dates"]))
    fs = res["font_sizes"]
    print("模板规格读回（学校模板实测值 ← 本产物实测值）：")
    m0 = res["secs"][0] if res["secs"] else {}
    print("  页边距：模板 上/下/左/右 = 3.00/3.00/3.00/3.00 cm ← 本产物 %s cm（%s）"
          % ("/".join("%.2f" % m0.get(k, 0.0) for k in
                      ("top_cm", "bottom_cm", "left_cm", "right_cm")),
             "全部 %d 节一致" % len(res["secs"]) if len({(s["top_cm"], s["bottom_cm"],
                                                          s["left_cm"], s["right_cm"])
                                                         for s in res["secs"]}) == 1 else "各节不一致"))
    print("  字号：章标题 16.0pt ← %.1fpt（eastAsia=%s）；参考文献条目 12.0pt ← %.1fpt；"
          "节/小节/正文 14/12/12pt ← %.1f/%.1f/%.1fpt；图名表名 10.5pt ← %.1f/%.1fpt；"
          "页眉 9.0pt ← %.1fpt；页脚 12.0pt ← %.1fpt"
          % (fs["Heading1"], res["h1_ea"], fs["参考文献条目"], fs["Heading2"], fs["Heading3"],
             fs["正文段落"], fs["图题"], fs["表题"], fs["页眉"], fs["页脚页码"]))
    # 第四批改动 3／5 的读回：页眉下边框与正文段落行距（都直接读 styles.xml 的样式片段）
    hb = res["head_bdr"]
    print("  页眉下边框（模板 `w:pBdr/w:bottom` 四属性同款）：present=%s val=%r color=%r sz=%r space=%r"
          % (hb["present"], hb["val"], hb["color"], hb["sz"], hb["space"]))
    print("  正文段落行距：模板 `w:line=\"400\" w:lineRule=\"exact\"`（固定值 20 磅）← "
          "本产物 line=%r lineRule=%r" % res["body_line"])
    print("  前置标题写法：模板「摘  要」／「目  录」（两字之间两个半角空格 U+0020 ×2）← "
          "成稿含「%s」=%s、「%s」=%s"
          % (RENDER_TEXT_MAP["摘要"], RENDER_TEXT_MAP["摘要"] in res["headings"],
             RENDER_TEXT_MAP["目录"], RENDER_TEXT_MAP["目录"] in res["headings"]))
    print("  声明页：标题「%s」=%s；声明正文与模板逐字一致=%s（sha256 %s…，%d 字）；"
          "落款两行留空待签名"
          % (STATEMENT_TITLE, STATEMENT_TITLE in res["headings"],
             res["stmt_sha256"] == STATEMENT_BODY_SHA256, res["stmt_sha256"][:12],
             len(STATEMENT_BODY)))
    print("  封面六字段：%s" % "；".join(COVER_FIELDS))
    print("  分节编页：节数 %d（① 封面＋声明 ② 摘要＋Abstract＋目录 ③ 正文…致谢）；"
          "w:pgNumType 逐节（第 1 节无）＝ %s；页脚体例 `-N-`（%r）"
          % (res["sections"],
             "／".join("fmt=%s,start=%s" % (p["pgnum"]["fmt"], p["pgnum"]["start"])
                       for p in res["sec_refs"][1:] if p["pgnum"]) or "无",
             FOOTER_LEAD + "N" + FOOTER_TAIL))
    print("  页眉：包内 %d 个（%s）；第 1 节页眉=%s（封面与声明不显示页眉）；"
          "第 2／3 节页眉文字＝%r（%s）"
          % (len(res["headers"]), "、".join(os.path.basename(n) for n in res["headers"]) or "无",
             res["sec_heads"][0] or "无",
             res["head_texts"][2] if len(res["head_texts"]) > 2 else None,
             "逐字等于 HEADER_TEXT" if res["head_texts"][1:3] == [HEADER_TEXT, HEADER_TEXT]
             else "不等于 HEADER_TEXT"))
    print("  页脚：包内 %d 个（%s）；各节页脚文字＝%s（第 1 节应为空＝无页码）"
          % (len(res["footers"]), "、".join(os.path.basename(n) for n in res["footers"]),
             "／".join(repr(t) for t in res["foot_texts"])))
    print("  分页来源审计：显式分页符 `w:br w:type=page` %d 个；一级标题 %d 个，"
          "每个前面的分页来源个数＝%s（须全为 1）；Heading 1 样式自带 pageBreakBefore=%s"
          % (len(res["explicit_breaks"]), len(res["break_audit"]),
             "、".join(str(len(b["sources"])) for b in res["break_audit"]),
             res["h1_style_pbb"]))

    sha = hashlib.sha256(det).hexdigest()
    print("-" * 78)
    if args.check:
        if not os.path.isfile(out_path):
            print("核对结果：FAIL —— 产物不存在：%s" % out_path)
            return 1
        with open(out_path, "rb") as fh:
            disk = fh.read()
        same = disk == det
        print("核对结果：%s —— 磁盘 %d 字节 sha256:%s ／ 现场 %d 字节 sha256:%s"
              % ("OK 逐字节一致" if same else "FAIL 不一致",
                 len(disk), hashlib.sha256(disk).hexdigest(), len(det), sha))
        return 0 if (same and not fails) else 1

    if fails:
        print("自检失败，未写盘：")
        for f in fails:
            print("  - %s" % f)
        return 1

    # 旧落点（被提交件取代）删除：不留两份互相竞争的成稿。放在自检通过之后，
    # 这样自检失败时旧产物仍在，不会出现「新旧都没有」。--out 试跑同样会清旧落点。
    # 若旧产物正被 Word／WPS 打开，Windows 会拒绝删除（WinError 32）：此时**不中断**，
    # 照常写出新产物，并把「删除失败 + 现成的一条删除命令」显式报到 stderr——
    # 绝不为删文件去杀用户的 Word 进程（可能带着未保存内容）。
    stale_blocked = []
    for stale in STALE_OUTS:
        before = os.path.isfile(stale)
        exc = _remove_stale(stale, out_path)
        if before and not os.path.isfile(stale):
            print("已删除被取代的旧落点：%s" % stale.replace(os.sep, "/"))
        elif exc is not None:
            stale_blocked.append((stale, exc))
            print("【待人工处理】旧落点删除失败（多半是被 Word／WPS 打开占用）：%s\n"
                  "              原因：%s\n"
                  "              请关闭该文档后执行：Remove-Item -LiteralPath '%s'"
                  % (stale.replace(os.sep, "/"), exc, stale), file=sys.stderr)

    # 写盘（第四批改动 2）：被 Word／WPS 占用时给出可操作提示并以退出码 3 结束，
    # 不再抛裸 traceback，也**不吞异常继续往下走**。分阶段提示的措辞见 `write_product()`。
    write_err = write_product(out_path, det)
    if write_err is not None:
        stage, exc = write_err
        print("=" * 78, file=sys.stderr)
        # 标题按阶段如实区分：打开阶段失败＝一个字节都没写；写入阶段失败＝可能只写了一部分
        print(("【写盘失败】产物未被写出：%s" if stage != "write"
               else "【写盘失败】产物写了一半，可能不完整：%s")
              % out_path.replace(os.sep, "/"), file=sys.stderr)
        print("  失败阶段：%s；错误：%s"
              % ({"mkdir": "建产出目录", "open": "打开产物文件", "write": "写入产物内容"}[stage],
                 exc), file=sys.stderr)
        if stage == "open":
            print("  原因多半是产物正被 Word／WPS 打开占用（Windows 拒绝以写方式打开）。",
                  file=sys.stderr)
            print("  请关闭该文档后重跑本脚本；本次一个字节都没写，**产物未被改动**。",
                  file=sys.stderr)
        else:
            print("  原因多半是产物被 Word／WPS 占用，或磁盘空间／写权限不足。", file=sys.stderr)
            print("  请关闭该文档后重跑本脚本；注意本次已开始写入，磁盘上的产物可能不完整"
                  "（重跑会整份覆盖，不会做增量拼接）。", file=sys.stderr)
        print("  重跑命令：python 工具\\导出论文docx.py", file=sys.stderr)
        return 3

    print("已写出：%s" % out_path.replace(os.sep, "/"))
    print("  字节数：%d" % len(det))
    print("  sha256：%s" % sha)
    print("  确定性：core_properties 时间/作者/修订号固定；zip 条目时间固定为 1980-01-01；"
          "正文无生成时间戳")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# tests_e2e —— UI 级 E2E（Playwright，审查报告 S8）

> 2026-10-11 新建。此前门禁 F 组只对 .vue 源码做正则静态扫描，用户核心路径
> 「提问→答案→证据点击→图谱→历史」无一行浏览器级断言；本目录补上（10 条用例，
> 见 `test_ui_e2e.py`）。

## 环境准备（一次性）

```powershell
pip install playwright
playwright install chromium        # 下载浏览器（约 150 MB，一次性）
```

## 运行（需后端 8000 ＋ 前端 5173 已在跑）

```powershell
python -m pytest 交付物/03-代码\tests_e2e -q                 # 全部 10 条
E2E_SKIP_CHAIN=1 python -m pytest 交付物/03-代码\tests_e2e -q   # 跳过真实链路用例（提问）
```

环境变量：`E2E_BACKEND`（默认 http://127.0.0.1:8000）、`E2E_FRONTEND`（默认 http://127.0.0.1:5173）。

## UNRUN 语义（与门禁一致，不误报）

| 状况 | 行为 |
|---|---|
| 未安装 playwright | 收集期整体 **skip**（主套件 283 例照常全绿，本目录不绑架主回归） |
| 后端不可达 | 全部用例 skip，原因注明启动命令 |
| 前端 dev server 不可达 | 全部用例 skip |
| 当前会话无历史记录 | 第 10 条（历史详情）单独 skip |

**闭环标准（报告 S8）**：全绿环境（MySQL＋Neo4j＋后端＋前端）**10/10 通过**。

## 用例 ↔ 报告清单对应

| # | 用例 | 报告 S8 清单项 | 依赖 |
|---|---|---|---|
| 1 | ask_navigates_to_answer | 提问跳转 | 真实链路（模型调用，标 chain） |
| 2 | answer_sections_order | 四段头顺序 | answer_id=1 |
| 3 | evidence_groups | 证据分组 | answer_id=1 |
| 4 | citation_out_of_range_not_clickable | 引用越界 | answer_id=1 |
| 5 | fixed_wording_data_cutoff | 固定字样 | config/meta |
| 6 | graph_path_panel | 图谱路径 | answer_id=1 |
| 7 | evidence_source_opens_new_tab | 溯源新开标签 | answer_id=1 |
| 8 | graph_search | 图谱检索 | **Neo4j 运行中** |
| 9 | history_list | 历史列表 | MySQL |
| 10 | history_detail_consistency | 历史详情一致性 | MySQL（顺带真实触发 M13 焦点管理断言） |

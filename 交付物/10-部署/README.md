# 部署说明（第 9 阶段：前后端系统集成）

> 规格来源：《24-第9阶段任务书（前后端系统集成）》第4.4节（部署与脚本）、第八节 H 组验收；
> 《02-项目执行总控文档》第8.4节（技术栈边界：**Docker 只用于统一运行环境，不引入容器编排系统**）。

本目录交付：`Dockerfile`（后端镜像）、`Dockerfile.frontend`＋`nginx.conf`（前端静态镜像与
`/api` 反代）、`docker-compose.yml`（第 4 轮 7.2 的单机 Compose 清单：后端＋MySQL＋Neo4j＋
前端静态服务）、`启动.ps1`（本机一键启动）、`.env.example`（Compose 口令模板）、本文件。
**仍然不含** K8s／多机编排清单——本机只有单节点 Docker Engine，Compose 只用于统一运行环境
与换机复现。

---

## 一、本机形态（**演示与验收走这一条**）

三个组件各就各位，互相之间用本机端口通信：

| 组件 | 形态 | 端口 | 启动方式 |
| --- | --- | --- | --- |
| MySQL | Windows 服务 `MySQL84`（8.4.9），库 `ashare_qa` | 3306 | 系统服务，随开机 |
| 图数据库 | **Neo4j 5.26.31 community，容器 `ashare-neo4j`，跑在 WSL2 的 Docker Engine 内** | bolt 7687／HTTP 7474 | `wsl -d Ubuntu -u root -- bash -lc "systemctl start docker; docker start ashare-neo4j"` |
| 后端 | FastAPI ＋ uvicorn（单体） | 8000 | `python 交付物/03-代码\后端\run.py` |
| 前端 | Vue 3 ＋ Vite | 5173 | `cd 交付物/03-代码\前端; npm run dev`（或 `npm run build` 后用静态服务器托管 `dist\`） |

一键启动（依次做 MySQL 检查 → Neo4j → 后端 → 前端 → 健康检查，每步打印实测结果）：

```powershell
powershell -ExecutionPolicy Bypass -File 交付物/10-部署\启动.ps1
# 只起后端（不起前端）：   ... -NoFrontend
# 停掉前后端进程：         ... -Stop
```

**入口**：后端 `http://127.0.0.1:8000/api/health`；前端 `http://127.0.0.1:5173/`；Neo4j Browser `http://127.0.0.1:7474/`。

### 配置文件（不入库）

`交付物/03-代码\后端\config.local.json` 是本机配置，**被 `.gitignore` 覆盖、不提交**；模板见
`交付物/03-代码\后端\config.local.json.example`。字段：MySQL 主机／端口／账号／口令／库名与字符集、
Neo4j URI／账号／口令、后端与前端端口。**口令只从它或环境变量读**，不写死、不回显、不进日志、
不进前端构建产物（硬约束 2／14）。

---

## 二、容器形态（Dockerfile，统一运行环境）

```bash
# 在 WSL2 的 Ubuntu 内执行（本机没有 Docker Desktop，见「已知限制」）
cd /mnt/c/Users/15129/Desktop/毕业设计
docker build -f 交付物/10-部署/Dockerfile -t ashare-qa-backend:local .
docker run --rm -d --name ashare-qa-api --network host \
    -v "$PWD/交付物/10-部署/config.docker.json:/app/交付物/03-代码/后端/config.local.json:ro" \
    -v /mnt/d/Cache/huggingface:/app/hf:ro \
    ashare-qa-backend:local
curl -s http://127.0.0.1:8000/api/health
```

（第 3 行 `-v ...:/app/hf:ro` 是 embedding 模型缓存挂载，见「已知限制」第 7 条；
在 Windows／Docker Desktop 主机上执行时改写成 `-v D:/Cache/huggingface:/app/hf:ro`。）

### Compose 形态（第 4 轮 7.2，**未在本机实际拉起**）

`docker-compose.yml` 编排四个服务：`mysql`（8.4，首次启动执行 `schema/六张表.sql` 建表）、
`neo4j`（5.26-community）、`backend`（本目录 `Dockerfile`）、`frontend`（`Dockerfile.frontend`
多阶段构建 + `nginx.conf` 静态托管并反代 `/api/`）。

```bash
cd 交付物/10-部署
cp .env.example .env          # 填 MYSQL_ROOT_PASSWORD / NEO4J_PASSWORD / HF_CACHE_DIR
# config.docker.json 不入库；首次使用从后端模板复制（容器主机名/口令随后由 ASHARE_* 覆盖）
cp ../03-代码/后端/config.local.json.example config.docker.json
docker compose up -d --build
docker compose exec -T backend python 交付物/03-代码/后端/tools/import_data.py   # 首次导入数据
curl -s http://127.0.0.1:8000/api/health
```

配置关系：Compose 把 `config.docker.json` 只读挂成容器内的 `config.local.json`，再用第 4 轮
新增的 `ASHARE_*` 环境变量覆盖主机名与口令（容器网络里 MySQL＝`mysql`、Neo4j＝`neo4j`）；
口令只来自 `.env`，不写进清单。**本机限制**：WSL2 的 `docker.io` 包不带 compose 插件，
故本清单只做了 YAML 语法与 `services`／`volumes` 结构校验（见
`交付物/10-部署/工程化与可观测性方案.md`）。

镜像内容：Python 3.12-slim ＋ **仓库根 `requirements.txt` 里锁定的全部依赖**（该文件是全项目
Python 依赖的单一来源，与 `交付物/10-部署\Dockerfile` 同源——Dockerfile 用 `pip install -r requirements.txt`
安装，另单独补 `uvicorn[standard]` 的 extras）；`交付物/03-代码\后端\`＋`交付物/03-代码\检索\`＋`交付物/03-代码\问答\`（后端 import
复用上游组件，必须一起进镜像）；数据集 v2.1 的索引与图谱导出物（后端运行期读取的只读输入）。
构建上下文排除 `node_modules\`／`dist\`／`_工作底稿\`／**`config.local.json`**（见仓库根的 `.dockerignore`）。

`--network host` 的用意：容器与 Neo4j 容器共用 WSL 的网络命名空间，于是容器内 `127.0.0.1:7687`
直连 Neo4j。`交付物/10-部署\config.docker.json` 是容器专用的本机配置模板（**同样不入库**）。

---

## 三、已知限制（**如实登记，不是代码缺陷**）

1. **未安装 Docker Desktop**：本机 Windows 账户**不是管理员**，Docker Desktop 需要提权安装，本阶段
   无法完成；Docker 只以 **WSL2 内的 Docker Engine**（apt 包 `docker.io`，实测 29.1.3）形态可用。
   因此「按《10》的部署形态完整落地」这一说法**不成立**，论文与《25》按此如实表述。
2. **容器连不到宿主 MySQL**：Windows 上的 MySQL 8.4 只监听 `127.0.0.1`（`my.ini` 的 `bind-address`），
   WSL 宿主命名空间与容器**都**连不到它的 3306（实测：WSL→`172.31.32.1:3306` FAIL、容器→网关 3306 FAIL、
   `nameserver:3306` FAIL），而改 `my.ini` 需要管理员权限。**后果**：容器形态下 `/api/health` 的
   `mysql` 探针为 false、依赖 MySQL 的接口不可用；依赖 Neo4j 的 `/api/graph/*` 与静态托管正常。
   两条补救路径（本阶段未执行、留给后续）：① 以管理员身份把 MySQL 的 `bind-address` 改为 `0.0.0.0`
   并重启服务；② 另起一个 `mysql:8.4` 容器并用 `交付物/03-代码\后端\tools\import_data.py` 导入同一份数据。
   **完整可用的形态是本机形态（第一节）。**
3. **Neo4j 未注册为 Windows 服务**：它跑在 WSL2 的容器里，**WSL2 发行版空闲会挂起**，挂起后
   bolt 7687 不可达（`/api/health` 会如实报 `neo4j: false`、状态 `degraded`）。**2026-10-04 实测把窗口
   量化了**：最后一次 `wsl` 调用结束后**约 10～15 秒** VM 即挂起，Windows 侧 `bolt 7687` 由可达转为
   连接被拒；容器随之被**优雅停止**再由 `unless-stopped` 拉起（`docker inspect` 显示 `RestartCount=0`
   且 `FinishedAt` 非空、日志为 `Neo4j Server shutdown initiated by request`）—— 所以「刚启动好好的、
   十几秒后 Neo4j 就没了」**不是崩溃，是空闲挂起**。恢复：
   `wsl -d Ubuntu -u root -- bash -lc "systemctl start docker; docker start ashare-neo4j"`；
   **长期运行必须让一个 WSL 会话常驻**，两种做法等效：① `启动.ps1 -KeepAlive`（脚本替你起一个
   `wsl -d Ubuntu -u root -- sleep 7200`，用 `-Stop` 停）；② 自己另开一个窗口跑
   `wsl -d Ubuntu -u root -- tail -f /dev/null`。保活后实测：连续 60 秒轮询 `bolt 7687` 与
   `/api/health` 的 `neo4j` 探针**全程为真**。（`启动.ps1` **默认不保活**，加 `-KeepAlive` 才起。）
4. **WSL 服务偶发 `Wsl/Service/E_UNEXPECTED`**：本阶段实测出现过一次（并发调用 WSL 时），
   `wsl --shutdown` 后重跑启动脚本即可恢复；`启动.ps1` 的所有 WSL 调用都加了超时与作业包装，
   避免裸调挂住脚本。
5. **限流**：单进程内滑动窗口（60 次／60 秒，`/api/health` 豁免），多进程／多实例不共享计数。
6. **不引入多机编排**：第 4 轮补了**单机** `docker-compose.yml`（7.2），仍**没有** K8s／
   swarm 清单；本机 WSL2 的 `docker.io` 包**不带 compose 插件**（实测
   `docker compose` → `unknown command`，也没有独立的 `docker-compose` 二进制），
   因此本清单只做了 YAML 语法与 `services`／`volumes` 结构校验，**未在本机实际拉起**。
7. **容器形态下 embedding 模型须用 `-v` 挂载 HF 缓存**：embedding 模型快照
   `BAAI/bge-small-zh-v1.5`（约 183 MB）**不打进镜像**（避免构建上下文携带大文件、便于换机替换），
   容器内以环境变量 `HF_HOME=/app/hf` 为缓存根。**必须**把本机 HF 缓存 bind mount 到 `/app/hf`，
   否则容器内无快照、向量检索不可用（后端以错误码 **3003** 报"向量索引不可用"，不静默降级）。
   本机实测缓存路径 `D:\Cache\huggingface`（其下 `hub\models--BAAI--bge-small-zh-v1.5\snapshots\
   7999e1d3359715c523056ef9478215996d62a620`），挂载命令：
   * WSL2 内执行：`-v /mnt/d/Cache/huggingface:/app/hf:ro`
   * Windows／Docker Desktop：`-v D:/Cache/huggingface:/app/hf:ro`
8. **日志默认只出 stderr、不落盘**（评审 P1-11 已给可选开关）：`errors.setup_logging()` **始终**
   挂 `StreamHandler(stderr)`（容器形态靠 stdout／stderr 采集），**只有当** `交付物/03-代码\后端\config.local.json`
   里给了非空的 `log_path` 时**才追加**一个 `logging.handlers.RotatingFileHandler`
   （单文件 10 MiB、保留 5 个历史文件、UTF-8；目录不存在会自动创建）。**没配就不落文件**，
   行为与本次改动前完全一致。**为什么要配**：错误码的 `detail` 按硬约束「只进日志、不进响应体」，
   日志丢了就没有任何排障依据（第 9 阶段排查 PE-03 时正踩在这条上）。容器形态建议把 `log_path`
   指到挂载出来的卷（`-v <宿主目录>:/app/logs` ＋ `"log_path": "/app/logs/backend.log"`），
   否则容器一删日志即丢。日志格式与日志内容**不含**任何凭据取值。

---

## 三之二、工程化与运维脚本（第 4 轮）

| 脚本 | 用途 | 产物／说明 |
| --- | --- | --- |
| `工具\一键构建.py` | 装依赖→后端测试→三道门禁→前端测试与构建→导出论文 | 论文落 `构建产物/`（gitignore）；失败非零退出；不跑 `验收第9阶段.py` |
| `工具\启动自检.py` | 启动前只读体检（配置／输入／索引／模型／MySQL／Neo4j／端口／日志） | 全 OK/WARN 退出 0，任一 FAIL 退出 1 |
| `工具\备份.ps1` | MySQL dump＋Neo4j 逻辑导出＋FAISS＋manifest，并做临时库导入回验 | 落 `备份/<时间戳>/`（gitignore）；支持 `-DryRun`、`-Keep N` |
| `工具\运维巡检.py` | 磁盘／内存／CPU／端口／健康指标／日志轮转体检 | `--strict` 异常退出 1；可配合任务计划程序 |
| `工具\告警检查.py` | 读 `/api/health` 的依赖与 metrics，按阈值判定 | 超阈值退出 1；默认 5%／2 s／累计限流 20 |
| `工具\校验compose.py` | 校验 Compose 的服务／卷／端口／依赖／口令来源 | 30 项结构检查；**不执行 docker** |

方案、取舍、实测读数与告警／恢复／轮转细节见
`交付物/10-部署/工程化与可观测性方案.md` 与
`交付物/05-系统实现/性能与架构优化方案.md` §11；版本与提交流程见
`交付物/10-部署/版本与分支约定.md`。

### 日志落盘与轮转

默认**只输出 stderr**（行为与引入该能力前一致）。需要落盘时，在
`交付物/03-代码/后端/config.local.json` 增加非空 `log_path`，或用环境变量：

```powershell
$env:ASHARE_LOG_PATH = "{仓库根}\交付物\10-部署\构建产物\backend.log"
python 交付物\03-代码\后端\run.py
```

启用后额外挂 `RotatingFileHandler`：**单文件 10 MiB、保留 5 个历史文件、UTF-8**；
目录不存在会自动创建。容器形态已把 `ASHARE_LOG_PATH` 指到 `/app/logs/backend.log`，
由 `backend-logs` 命名卷承载。验证（离线、只写临时目录）：

```powershell
python -m pytest 交付物\03-代码\测试\test_m_log_rotation.py -q   # 4 passed
```

覆盖「不设不写／设了会写／轮转生效／路径不可写时服务照常启动」四件事。

### 告警阈值检查

```powershell
python 工具\告警检查.py
python 工具\告警检查.py --error-rate 0.02 --p95-ms 1500 --rate-limit-hits 5
```

默认阈值：错误率 **5%**（最近 60 s）、非问答路由 P95 **2000 ms**、问答路由 P95
**320000 ms**（LLM 链路单列）、进程启动以来累计限流命中 **20**。四项依赖任一
`ok=false` 或 metrics 不可用同样判失败。**退出码 0 = 全部在阈值内，1 = 超阈值／后端不可达**。
配合任务计划程序每 5 分钟执行一次即可作为最小告警：

```bat
schtasks /Create /SC MINUTE /MO 5 /TN "AshareAlert" ^
  /TR "python {仓库根}\工具\告警检查.py"
```

### 备份与保留期

```powershell
python 工具\备份.py --dry-run          # 只检查并打印计划（含保留期计划）
python 工具\备份.py --keep 3           # 备份＋导入回验，只保留最近 3 份
powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -Keep 7
```

`--keep`（默认 3）**只在本次备份成功后**清理更旧的备份目录；只认「目录名
`YYYYMMDD_HHMMSS` 且含 `manifest.json`」的直接子目录，不跟随符号链接、失败不清理；
本次刚生成的备份目录永不删除（防系统时钟回拨误删）。
备份产物仍落在 `交付物/10-部署/备份/`（已被 `.gitignore` 覆盖），不会污染工作区。
每日 02:30 定时备份示例：

```bat
schtasks /Create /SC DAILY /ST 02:30 /TN "AshareBackup" ^
  /TR "powershell -ExecutionPolicy Bypass -File {仓库根}\工具\备份.ps1 -Keep 3"
```

### Compose 结构校验

```powershell
python 工具\校验compose.py
```

解析 `docker-compose.yml`（PyYAML）并检查：4 个服务、5 个必需命名卷及挂载点、
端口映射、依赖顺序、**口令只来自 `.env` 插值**（任何 `*PASSWORD*` 不得硬编码）、
`.env.example` 两个口令键、backend 指向服务名与日志卷。实测 **30/30 通过**。
**只读**：不执行 `docker compose up`，也不改任何容器／卷。

---

## 四、端口一览（改动即视为口径变更，须回《02》登记）

| 端口 | 用途 |
| --- | --- |
| 3306 | MySQL |
| 7474 / 7687 | Neo4j HTTP（Browser）／bolt |
| 8000 | 后端 API（uvicorn） |
| 5173 | 前端 Vite dev server |

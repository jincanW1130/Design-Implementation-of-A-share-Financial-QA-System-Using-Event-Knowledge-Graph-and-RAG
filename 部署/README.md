# 部署说明（第 9 阶段：前后端系统集成）

> 规格来源：《24-第9阶段任务书（前后端系统集成）》第4.4节（部署与脚本）、第八节 H 组验收；
> 《02-项目执行总控文档》第8.4节（技术栈边界：**Docker 只用于统一运行环境，不引入容器编排系统**）。

本目录交付三件：`Dockerfile`（后端镜像）、`启动.ps1`（一键启动）、本文件（部署说明）。
**不含** docker-compose／K8s 清单——那属于被排除的容器编排。

---

## 一、本机形态（**演示与验收走这一条**）

三个组件各就各位，互相之间用本机端口通信：

| 组件 | 形态 | 端口 | 启动方式 |
| --- | --- | --- | --- |
| MySQL | Windows 服务 `MySQL84`（8.4.9），库 `ashare_qa` | 3306 | 系统服务，随开机 |
| 图数据库 | **Neo4j 5.26.31 community，容器 `ashare-neo4j`，跑在 WSL2 的 Docker Engine 内** | bolt 7687／HTTP 7474 | `wsl -d Ubuntu -u root -- bash -lc "systemctl start docker; docker start ashare-neo4j"` |
| 后端 | FastAPI ＋ uvicorn（单体） | 8000 | `python 代码\后端\run.py` |
| 前端 | Vue 3 ＋ Vite | 5173 | `cd 代码\前端; npm run dev`（或 `npm run build` 后用静态服务器托管 `dist\`） |

一键启动（依次做 MySQL 检查 → Neo4j → 后端 → 前端 → 健康检查，每步打印实测结果）：

```powershell
powershell -ExecutionPolicy Bypass -File 部署\启动.ps1
# 只起后端（不起前端）：   ... -NoFrontend
# 停掉前后端进程：         ... -Stop
```

**入口**：后端 `http://127.0.0.1:8000/api/health`；前端 `http://127.0.0.1:5173/`；Neo4j Browser `http://127.0.0.1:7474/`。

### 配置文件（不入库）

`代码\后端\config.local.json` 是本机配置，**被 `.gitignore` 覆盖、不提交**；模板见
`代码\后端\config.local.json.example`。字段：MySQL 主机／端口／账号／口令／库名与字符集、
Neo4j URI／账号／口令、后端与前端端口。**口令只从它或环境变量读**，不写死、不回显、不进日志、
不进前端构建产物（硬约束 2／14）。

---

## 二、容器形态（Dockerfile，统一运行环境）

```bash
# 在 WSL2 的 Ubuntu 内执行（本机没有 Docker Desktop，见「已知限制」）
cd /mnt/c/Users/15129/Desktop/毕业设计
docker build -f 部署/Dockerfile -t ashare-qa-backend:local .
docker run --rm -d --name ashare-qa-api --network host \
    -v "$PWD/部署/config.docker.json:/app/代码/后端/config.local.json:ro" \
    -v /mnt/d/Cache/huggingface:/app/hf:ro \
    ashare-qa-backend:local
curl -s http://127.0.0.1:8000/api/health
```

（第 3 行 `-v ...:/app/hf:ro` 是 embedding 模型缓存挂载，见「已知限制」第 7 条；
在 Windows／Docker Desktop 主机上执行时改写成 `-v D:/Cache/huggingface:/app/hf:ro`。）

镜像内容：Python 3.12-slim ＋ **仓库根 `requirements.txt` 里锁定的全部依赖**（该文件是全项目
Python 依赖的单一来源，与 `部署\Dockerfile` 同源——Dockerfile 用 `pip install -r requirements.txt`
安装，另单独补 `uvicorn[standard]` 的 extras）；`代码\后端\`＋`代码\检索\`＋`代码\问答\`（后端 import
复用上游组件，必须一起进镜像）；数据集 v2.1 的索引与图谱导出物（后端运行期读取的只读输入）。
构建上下文排除 `node_modules\`／`dist\`／`_工作底稿\`／**`config.local.json`**（见仓库根的 `.dockerignore`）。

`--network host` 的用意：容器与 Neo4j 容器共用 WSL 的网络命名空间，于是容器内 `127.0.0.1:7687`
直连 Neo4j。`部署\config.docker.json` 是容器专用的本机配置模板（**同样不入库**）。

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
   并重启服务；② 另起一个 `mysql:8.4` 容器并用 `代码\后端\tools\import_data.py` 导入同一份数据。
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
6. **不引入容器编排**：只交付 `Dockerfile` 与启动脚本，**没有** docker-compose 与 K8s 清单。
7. **容器形态下 embedding 模型须用 `-v` 挂载 HF 缓存**：embedding 模型快照
   `BAAI/bge-small-zh-v1.5`（约 183 MB）**不打进镜像**（避免构建上下文携带大文件、便于换机替换），
   容器内以环境变量 `HF_HOME=/app/hf` 为缓存根。**必须**把本机 HF 缓存 bind mount 到 `/app/hf`，
   否则容器内无快照、向量检索不可用（后端以错误码 **3003** 报"向量索引不可用"，不静默降级）。
   本机实测缓存路径 `D:\Cache\huggingface`（其下 `hub\models--BAAI--bge-small-zh-v1.5\snapshots\
   7999e1d3359715c523056ef9478215996d62a620`），挂载命令：
   * WSL2 内执行：`-v /mnt/d/Cache/huggingface:/app/hf:ro`
   * Windows／Docker Desktop：`-v D:/Cache/huggingface:/app/hf:ro`
8. **日志默认只出 stderr、不落盘**（评审 P1-11 已给可选开关）：`errors.setup_logging()` **始终**
   挂 `StreamHandler(stderr)`（容器形态靠 stdout／stderr 采集），**只有当** `代码\后端\config.local.json`
   里给了非空的 `log_path` 时**才追加**一个 `logging.handlers.RotatingFileHandler`
   （单文件 10 MiB、保留 5 个历史文件、UTF-8；目录不存在会自动创建）。**没配就不落文件**，
   行为与本次改动前完全一致。**为什么要配**：错误码的 `detail` 按硬约束「只进日志、不进响应体」，
   日志丢了就没有任何排障依据（第 9 阶段排查 PE-03 时正踩在这条上）。容器形态建议把 `log_path`
   指到挂载出来的卷（`-v <宿主目录>:/app/logs` ＋ `"log_path": "/app/logs/backend.log"`），
   否则容器一删日志即丢。日志格式与日志内容**不含**任何凭据取值。

---

## 四、端口一览（改动即视为口径变更，须回《02》登记）

| 端口 | 用途 |
| --- | --- |
| 3306 | MySQL |
| 7474 / 7687 | Neo4j HTTP（Browser）／bolt |
| 8000 | 后端 API（uvicorn） |
| 5173 | 前端 Vite dev server |

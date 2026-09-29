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
    ashare-qa-backend:local
curl -s http://127.0.0.1:8000/api/health
```

镜像内容：Python 3.12-slim ＋ 锁定版本的 `fastapi==0.141.1`／`uvicorn[standard]==0.54.0`／
`pymysql==2.2.8`／`neo4j==6.3.1`；`代码\后端\`＋`代码\检索\`＋`代码\问答\`（后端 import 复用上游
组件，必须一起进镜像）；数据集 v2.1 的索引与图谱导出物（后端运行期读取的只读输入）。
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
   bolt 7687 不可达（`/api/health` 会如实报 `neo4j: false`、状态 `degraded`）。恢复：
   `wsl -d Ubuntu -u root -- bash -lc "systemctl start docker; docker start ashare-neo4j"`；
   长期运行请保持一个 WSL 会话常驻（例如 `wsl -d Ubuntu -u root -- tail -f /dev/null` 放在另一个窗口）。
4. **WSL 服务偶发 `Wsl/Service/E_UNEXPECTED`**：本阶段实测出现过一次（并发调用 WSL 时），
   `wsl --shutdown` 后重跑启动脚本即可恢复；`启动.ps1` 的所有 WSL 调用都加了超时与作业包装，
   避免裸调挂住脚本。
5. **限流**：单进程内滑动窗口（60 次／60 秒，`/api/health` 豁免），多进程／多实例不共享计数。
6. **不引入容器编排**：只交付 `Dockerfile` 与启动脚本，**没有** docker-compose 与 K8s 清单。

---

## 四、端口一览（改动即视为口径变更，须回《02》登记）

| 端口 | 用途 |
| --- | --- |
| 3306 | MySQL |
| 7474 / 7687 | Neo4j HTTP（Browser）／bolt |
| 8000 | 后端 API（uvicorn） |
| 5173 | 前端 Vite dev server |

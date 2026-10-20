# Neo4j 迁出 WSL（Windows 服务化）方案

> 性质：**方案文档，未执行**。执行需要：① 管理员 PowerShell（安装 Windows 服务）；
> ② 维护窗口约 15～30 分钟（图谱服务中断，问答链路期间不可用）；③ 下载约 150 MB 的安装包。
> 背景：WSL2 会因主机内存压力被系统反复强制关机（`.wslconfig` 自述机制），容器 `ashare-neo4j`
> 随之停止，且 VM 重启后 localhost 转发可能失效——2026-10-20 实际发生多次（登记于
> `过程记录/01-评审与审查/优化执行进展.md`）。`工具/图谱服务自愈.py` 是短期缓解；
> 本方案是长期解：Neo4j 以 Windows 服务常驻宿主机，不再依赖 WSL 生存期。
> 冻结边界：不迁移数据资产本身（dump→load 保持同一份数据）；不改后端/前端任何配置（端口与口令不变）。

---

## 一、环境现状（2026-10-20 实测）

| 项 | 值 | 依据 |
| --- | --- | --- |
| 现实现 | Docker 容器 `ashare-neo4j`（WSL Ubuntu），volume `ashare-neo4j-data` → `/data`（**521 MB**） | `docker inspect` |
| 版本／形态 | Neo4j **community 5.26.31**（unix tarball），heap max 1G，restart `unless-stopped` | 容器 env／HostConfig |
| 认证 | `NEO4J_AUTH=neo4j/<口令>`（与 `交付物/03-代码/后端/config.local.json` 的 `neo4j_password` 一致；**口令随数据卷走，迁移后不用重设**） | 容器 env |
| Windows Java | **Temurin 21.0.11 已装**（Neo4j 5.26 官方支持 21），无需再装 JDK | `java -version` |
| 磁盘 | C 盘剩余约 38 GB（安装包 150 MB + 解压约 500 MB + 数据 521 MB，余量充足） | `df` |
| 目标端口 | 7687（bolt）／7474（http）——**与现配置一致，后端 `neo4j_uri` 零改动** | `config.local.json` |

## 二、迁移步骤（维护窗口内按序执行，全程约 15～30 分钟）

> 执行前跑一次 `python 工具/图谱服务自愈.py --check`，确认当前图谱可用且计数为 3607/3614；
> 迁移完成后用同一命令验证。MySQL 与后端/前端不受影响（仅图谱查询在窗口内失败）。

### T1 导出数据（约 5 分钟，WSL 侧）

```bash
# 停容器（community 版 dump 要求库停止；停容器即满足一致性）
wsl -d Ubuntu -u root -- docker stop ashare-neo4j
# 防止重启策略在回滚窗口前把容器又拉起来（与 Windows 服务抢 7687 端口）
wsl -d Ubuntu -u root -- docker update --restart=no ashare-neo4j
# 在容器内对 neo4j 库做一致性 dump（system 库保留在卷内，回滚时原样可用）
wsl -d Ubuntu -u root -- docker run --rm -v ashare-neo4j-data:/data -v ashare-neo4j-dump:/dump \
  neo4j:5.26.31 neo4j-admin database dump neo4j --to-path=/dump
# 把 dump 复制到 Windows 侧（挂载点路径见下方「卷路径换算」）
wsl -d Ubuntu -u root -- docker run --rm -v ashare-neo4j-dump:/dump -v /mnt/c/neo4j-migration:/out \
  neo4j:5.26.31 cp /dump/neo4j.dump /out/
```

**卷路径换算**（直接复制也可，作为 dump 的替代）：WSL 内 `docker volume inspect ashare-neo4j-data`
取 `_data` 实际路径；该路径从 Windows 侧可用 `\\wsl$\Ubuntu\<路径>` 访问。**替代做法（文件级）**：
停容器后直接把 `<卷>/databases/neo4j` 与 `<卷>/transactions/neo4j` 两个目录拷到 Windows 的
`data\databases\neo4j` 与 `data\transactions\neo4j`——版本完全一致时文件级等价；
dump/load 是官方推荐路径，失败时再用文件级兜底。

### T2 安装 Neo4j（Windows 侧，约 5 分钟）

1. 下载 `neo4j-community-5.26.31-windows.zip`（与容器同版本，**必须同版本**——dump/load 跨版本有兼容规则，同版本零风险；SHA256 与镜像 `NEO4J_SHA256` 同源核对）；
2. 解压到 `C:\neo4j\neo4j-community-5.26.31`（下称 `%NEO4J_HOME%`）；
3. 数据装入（普通 PowerShell，先确保服务未启动）：

```powershell
cd C:\neo4j\neo4j-community-5.26.31
bin\neo4j-admin.bat database load neo4j --from-path=C:\neo4j-migration --overwrite-destination=true
```

4. 编辑 `conf\neo4j.conf`，**只追加/修改以下键**（其余默认）：

```properties
# 安全收口：只监听本机（容器时代监听 0.0.0.0，这一步同时消化 P2-7 的监听面）
server.default_listen_address=127.0.0.1
server.bolt.listen_address=:7687
server.http.listen_address=:7474
# 内存与容器时代对齐
server.memory.heap.max_size=1G
# 认证保持开启（口令随数据装入）
dbms.security.auth_enabled=true
```

5. 设置环境变量（系统级）：`NEO4J_HOME=C:\neo4j\neo4j-community-5.26.31`；
   若 `java -version` 不在系统 PATH，另设 `JAVA_HOME` 指向 Temurin 21 安装目录。

### T3 安装并启动 Windows 服务（**需管理员 PowerShell**，约 2 分钟）

```powershell
cd C:\neo4j\neo4j-community-5.26.31
bin\neo4j.bat windows-service install
bin\neo4j.bat windows-service start
# 服务名 neo4j，启动类型自动——开机自启，不再依赖 WSL 生存期
```

### T4 验证（约 5 分钟，窗口收口判据）

```powershell
python 工具\图谱服务自愈.py --check        # 期望：bolt 可达；3607/3614 与冻结基线一致；exit 0
python 工具\启动自检.py                    # 期望：Neo4j 探针 OK；其余项与基线一致
python 工具\验收第6阶段.py                 # 期望：退出码 0（图谱口径门禁）
# 后端起一次后跑 /api/health（neo4j 探针 true）或直接跑门禁：
python 工具\一键构建.py --gate --skip-deps   # 期望：七步全绿（0 skipped）
```

另用浏览器开 `http://127.0.0.1:7474`（neo4j／原口令）登录一次，确认认证与数据可见。

## 三、回滚（任一步失败即回滚，全程约 5 分钟）

```powershell
# Windows 侧：卸服务
cd C:\neo4j\neo4j-community-5.26.31
bin\neo4j.bat windows-service remove
```

```bash
# WSL 侧：数据卷全程未动，直接起回容器
wsl -d Ubuntu -u root -- docker update --restart=unless-stopped ashare-neo4j
wsl -d Ubuntu -u root -- docker start ashare-neo4j
python 工具/图谱服务自愈.py --check       # 期望 exit 0（计数与迁移前一致）
```

容器回滚后，本次迁移在 Windows 侧的残留（`C:\neo4j\*`、`C:\neo4j-migration\*`）确认不再需要后可整体删除。

## 四、迁移后的行为变化与维护差异

| 维度 | 容器（现状） | Windows 服务（目标） |
| --- | --- | --- |
| 存活 | 随 WSL2 VM 生存，内存压力下被反复关机 | 独立 Windows 服务，开机自启、不随 WSL 关停 |
| 监听 | 0.0.0.0（P2-7 未收口项） | **127.0.0.1**（方案内置收口） |
| 备份 | `工具/备份.py` 走容器内逻辑导出 | 需改走 `neo4j-admin database dump`（改 `备份.py` 前先登记；迁移当轮可先手工 dump 一次留底） |
| 升级 | 换镜像 tag | 下载新 zip 重装服务（版本锁 5.26.31 不受影响） |
| `图谱服务自愈.py` | 按需恢复主力 | 退化为只读探针（`--check`）；修复分支自然不再触发（脚本无需改，wsl 检测不到容器即报 FAIL——迁移后建议加一行「Windows 服务形态」说明，另行小改） |
| 配置 | `config.local.json` 不变 | **不变**（端口、口令、URI 全部一致） |

## 五、风险与未决项（如实登记）

1. **`备份.py` 兼容**：现脚本按容器内 `neo4j-admin` 路径实现，迁移后需小改（改前在《优化执行进展》登记；这是迁移完成后唯一一处代码改动）。
2. **内存账**：Windows 服务常驻后，Neo4j 的 1G heap 从「WSL VM 限额内」变为直接占宿主内存——本机正是因内存压力反复杀 WSL 才要做本迁移，迁移后净收益为正（少了 WSL VM + Docker daemon 两层开销），但需观察一周内是否有新的内存压力迹象。
3. **同版本约束**：`neo4j-admin database load` 在 5.26.31 → 5.26.31 零风险；**不要**顺手升级版本（升级属于另一次变更，另行登记）。
4. **dump 一致性**：community 版 dump 要求库停止——按 T1 先停容器再 dump，不做在线 dump。
5. **管理员权限**：T3 必须管理员 PowerShell；其余步骤普通权限即可。
6. 本文档**只备方案**：执行须作者明确确认维护窗口；执行过程与读数按项目纪律回填《优化执行进展.md》。

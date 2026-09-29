# 第 9 阶段（前后端系统集成）后端镜像
#
# 依据：《24-第9阶段任务书（前后端系统集成）》第4.4节 与第八节 H 组验收；
#      《10-系统总体设计（第四阶段）》第4.1.1节 的部署形态（单体后端 ＋ 前后端分离，
#      **Docker 只用于统一运行环境，不引入容器编排**）。
#
# 构建（在 WSL2 的 Docker Engine 内；本机未安装 Docker Desktop，见 部署\README.md）：
#     docker build -f 部署/Dockerfile -t ashare-qa-backend:local .
# 运行（`--network host` 使容器共用 WSL 的网络命名空间，从而直连同一 WSL 内的 Neo4j 容器）：
#     docker run --rm -d --name ashare-qa-api --network host \
#         -v "$PWD/部署/config.docker.json:/app/代码/后端/config.local.json:ro" \
#         ashare-qa-backend:local
#
# **已知环境限制（如实登记，不是代码缺陷）**：宿主机 Windows 上的 MySQL 8.4 只监听
# 127.0.0.1（my.ini 的 bind-address），WSL 与容器都连不到它的 3306；因此容器形态下
# `/api/health` 的 `mysql` 探针为 false、依赖 MySQL 的接口不可用，而依赖 Neo4j 的
# `/api/graph/*` 与静态页面托管正常。完整形态请用 `部署\启动.ps1` 的**本机形态**。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖：与开发环境实测版本对齐（见 代码\后端\README.md）；不装 ORM、不装可视化/编排类组件。
#
# **版本号一律以发行版号为准**（`importlib.metadata.version()`），**不要**照抄包自报的
# `__version__`：实测 PyMySQL 的发行版 **1.2.3** 会把 `pymysql.__version__` 报成 **2.2.8**，
# 照抄会让 `pip install "pymysql==2.2.8"` 直接失败（PyPI 上不存在这个版本）——本镜像第一版
# 就是这么构筑失败的，属实测踩坑留痕。
RUN pip install --no-cache-dir \
        "fastapi==0.141.1" \
        "uvicorn[standard]==0.54.0" \
        "pymysql==1.2.3" \
        "neo4j==6.3.1"

# 后端代码 ＋ 上游只读代码（后端 import 复用检索与问答组件，故必须一起进镜像）
COPY 代码/后端/ /app/代码/后端/
COPY 代码/检索/ /app/代码/检索/
COPY 代码/问答/ /app/代码/问答/

# 上游数据：数据集（向量索引与文本块）与图谱导出物是后端运行期读取的只读输入。
# 仓库不含它们（.gitignore），故构建时必须由本地工作区提供；缺数据时镜像仍可构建，
# 只是向量检索与内存图后端不可用（会以 3003／3001 明确报错，不会静默降级）。
COPY 阶段05-数据准备/数据集/v2.1/ /app/阶段05-数据准备/数据集/v2.1/
COPY 阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/ /app/阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/

# 端口：后端 8000（《24》第六节 格式决策 5 固定）
EXPOSE 8000

# 健康检查沿用应用自己的 /api/health（外部依赖不可用时它会如实报 degraded）
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=8)); sys.exit(0 if d.get('status')=='ok' else 1)"

CMD ["python", "代码/后端/run.py", "--host", "0.0.0.0"]

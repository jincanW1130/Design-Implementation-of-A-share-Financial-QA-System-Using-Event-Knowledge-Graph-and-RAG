# 第 9 阶段（前后端系统集成）后端镜像
#
# 依据：《24-第9阶段任务书（前后端系统集成）》第4.4节 与第八节 H 组验收；
#      《10-系统总体设计（第四阶段）》第4.1.1节 的部署形态（单体后端 ＋ 前后端分离，
#      **Docker 只用于统一运行环境，不引入容器编排**）。
#
# 构建（在 WSL2 的 Docker Engine 内；本机未安装 Docker Desktop，见 交付物/10-部署\README.md）：
#     docker build -f 交付物/10-部署/Dockerfile -t ashare-qa-backend:local .
# 运行（`--network host` 使容器共用 WSL 的网络命名空间，从而直连同一 WSL 内的 Neo4j 容器）：
#     docker run --rm -d --name ashare-qa-api --network host \
#         -v "$PWD/交付物/10-部署/config.docker.json:/app/交付物/03-代码/后端/config.local.json:ro" \
#         -v /mnt/d/Cache/huggingface:/app/hf:ro \
#         ashare-qa-backend:local
# 　HF 缓存挂载路径随执行环境而变：WSL2 内执行用 /mnt/d/Cache/huggingface；
# 　若在装了 Docker Desktop 的 Windows 主机上执行，则写 D:/Cache/huggingface。
#
# **已知环境限制（如实登记，不是代码缺陷）**：宿主机 Windows 上的 MySQL 8.4 只监听
# 127.0.0.1（my.ini 的 bind-address），WSL 与容器都连不到它的 3306；因此容器形态下
# `/api/health` 的 `mysql` 探针为 false、依赖 MySQL 的接口不可用，而依赖 Neo4j 的
# `/api/graph/*` 与静态页面托管正常。完整形态请用 `交付物/10-部署\启动.ps1` 的**本机形态**。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    HF_HOME=/app/hf

# embedding 模型（BAAI/bge-small-zh-v1.5）快照约 183 MB，**不打进镜像**：
#   ① 避免构建上下文携带大文件、拖慢构建；② 便于换机时替换／复用本机已有缓存。
# 运行容器时用 bind mount 把本机 HF 缓存挂到容器的 HF_HOME（＝/app/hf）：
#     WSL2 内执行：              -v /mnt/d/Cache/huggingface:/app/hf:ro
#     Windows / Docker Desktop： -v D:/Cache/huggingface:/app/hf:ro
# 　（本机 HF_HOME=D:\Cache\huggingface，其下 hub\models--BAAI--bge-small-zh-v1.5\snapshots\
# 　 7999e1d3359715c523056ef9478215996d62a620；挂载后容器内路径与之对齐。）
# 若不挂载，容器内无模型快照，向量检索不可用（后端以错误码 3003 明确报错，不静默降级）。

WORKDIR /app

# 依赖：改为从仓库根 requirements.txt 安装——它是全项目 Python 依赖的【单一来源】，
# 与开发环境实测版本对齐（见 交付物/03-代码\后端\README.md）；不装 ORM、不装可视化/编排类组件。
# 先 COPY 再 RUN，用 Docker 层缓存：只要 requirements.txt 不变，改代码不会重装依赖。
#
# **版本号一律以发行版号为准**（`importlib.metadata.version()`），**不要**照抄包自报的
# `__version__`：实测 PyMySQL 的发行版 **1.2.3** 会把 `pymysql.__version__` 报成 **2.2.8**，
# 照抄会让 `pip install "pymysql==2.2.8"` 直接失败（PyPI 上不存在这个版本）——本镜像第一版
# 就是这么构筑失败的，属实测踩坑留痕。
COPY requirements.txt /app/requirements.txt
# **torch 先按 CPU 源单独安装（2026-10-10 登记）**：requirements.txt 文件头本就写明这一选项
# （「如需安装 CPU-only 轮子以显著减小体积，可改用 PyTorch 官方 CPU 源：版本号不变，只换来源」）。
# 首次重建实测：默认 PyPI 拉的是 **CUDA 版 torch ＋ nvidia-* 依赖（合计数 GB）**，在本机到
# files.pythonhosted.org 约 400 KB/s 的带宽下不可行（首轮还因读超时失败）；而 CPU 源实测
# **约 1.9 MB/s、wheel 小一个量级**。容器无 GPU、只用 CPU 推理，故按 CPU 源两步安装：
# torch 先装（版本号不变 ==2.12.1），随后整表安装时 pip 视其已满足而跳过。
# 超时／重试参数一并放宽（--timeout 120 --retries 15），提高弱网下的构建成功率。
RUN pip install --no-cache-dir --timeout 120 --retries 15 "torch==2.12.1" \
        --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 120 --retries 15 -r /app/requirements.txt

# uvicorn[standard] 的 extras 语义保留在此处（requirements.txt 只写不带 extras 的
# `uvicorn==0.54.0` 作为版本单一来源）：版本号与 requirements 一致，仅在容器内就地补
# websockets／httptools 等 extras，避免 requirements 与 Dockerfile 两处写法打架。
RUN pip install --no-cache-dir --timeout 120 --retries 15 "uvicorn[standard]==0.54.0"

# 后端代码 ＋ 上游只读代码（后端 import 复用检索与问答组件，故必须一起进镜像）
COPY 交付物/03-代码/后端/ /app/交付物/03-代码/后端/
COPY 交付物/03-代码/检索/ /app/交付物/03-代码/检索/
COPY 交付物/03-代码/问答/ /app/交付物/03-代码/问答/

# 上游数据：数据集（向量索引与文本块）与图谱导出物是后端运行期读取的只读输入。
# 仓库不含它们（.gitignore），故构建时必须由本地工作区提供；缺数据时镜像仍可构建，
# 只是向量检索与内存图后端不可用（会以 3003／3001 明确报错，不会静默降级）。
# **2026-10-10 修复**：图谱导出物原写死 `v2.1_v1_2`（2026-10-03 图谱口径切到 `v2.1_v1_3` 时
# 本行未随动，镜像里带的仍是归档口径）；现改到现行 `v2.1_v1_3`，与《02》v3.6、六表与图谱计数
# （3607／3614）一致。**归档目录 v2.1_v1_2 不进镜像**（已归档、不再作为任何现行输入）。
COPY 交付物/04-数据与知识图谱/数据准备/数据集/v2.1/ /app/交付物/04-数据与知识图谱/数据准备/数据集/v2.1/
COPY 交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/ /app/交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/

# 端口：后端 8000（《24》第六节 格式决策 5 固定）
EXPOSE 8000

# 健康检查沿用应用自己的 /api/health（外部依赖不可用时它会如实报 degraded）
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=8)); sys.exit(0 if d.get('status')=='ok' else 1)"

CMD ["python", "交付物/03-代码/后端/run.py", "--host", "0.0.0.0"]

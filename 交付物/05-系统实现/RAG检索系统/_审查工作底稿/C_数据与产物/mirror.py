import io, json, os, shutil, sys

SRC = r"C:\Users\15129\Desktop\毕业设计"
DST = r"C:\Users\15129\AppData\Local\Temp\re7_C\mirror"

PAIRS = [
    ("交付物/03-代码/检索", "交付物/03-代码/检索"),
    ("交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean", "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean"),
    ("交付物/04-数据与知识图谱/数据准备/数据集/v2.1/chunks", "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/chunks"),
    ("交付物/04-数据与知识图谱/数据准备/数据集/v2.1/index", "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/index"),
    ("交付物/04-数据与知识图谱/数据准备/数据集/v2.1/meta", "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/meta"),
    ("交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2", "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2"),
    ("交付物/05-系统实现/RAG检索系统/预实验问题集", "交付物/05-系统实现/RAG检索系统/预实验问题集"),
]


def main():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)
    for a, b in PAIRS:
        s = os.path.join(SRC, a.replace("/", os.sep))
        d = os.path.join(DST, b.replace("/", os.sep))
        shutil.copytree(s, d)
        n = sum(len(fs) for _, _, fs in os.walk(d))
        print("copied", a, "->", b, "files:", n)
    os.makedirs(os.path.join(DST, "交付物/05-系统实现/RAG检索系统", "检索产出"), exist_ok=True)
    os.makedirs(os.path.join(DST, "交付物/05-系统实现/RAG检索系统", "_工作底稿"), exist_ok=True)
    print("mirror ready:", DST)


if __name__ == "__main__":
    main()

import hashlib, io, json, os

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出")

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

rm = json.load(io.open(os.path.join(OUT, "run_manifest.json"), encoding="utf-8"))
for name, rec in rm["determinism"]["files"].items():
    p = os.path.join(OUT, name)
    a = sha256_file(p)
    print("%-28s ws_recorded=%s actual=%s match=%s | run1==run2:%s" % (
        name, rec["workspace_sha256"][:16], a[:16], rec["workspace_sha256"] == a,
        rec["run1_sha256"] == rec["run2_sha256"]))

print()
print("== run_manifest top-level sha list (if any) ==")
for k, v in rm.items():
    if "sha" in k.lower() or "hash" in k.lower():
        print(k, v)

# Also record the exact bytes/sha of the 6 delivered artifacts in 检索产出
print()
print("== 检索产出 6 artifacts: bytes/sha256 (现场) ==")
for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    if os.path.isfile(p):
        print("%-32s %9d %s" % (f, os.path.getsize(p), sha256_file(p)))

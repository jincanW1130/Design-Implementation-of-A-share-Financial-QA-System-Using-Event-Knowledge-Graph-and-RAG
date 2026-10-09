import hashlib, io, json, os, sys

ROOT = r"C:\Users\15129\Desktop\毕业设计"
P7 = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统")
OUT = os.path.join(P7, "检索产出")

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    im_path = os.path.join(OUT, "input_manifest.json")
    im = json.load(io.open(im_path, encoding="utf-8"))
    print("== input_manifest.json: 11 files ==")
    bad = []
    for f in im["files"]:
        p = os.path.join(ROOT, f["path"].replace("/", os.sep))
        exists = os.path.exists(p)
        actual_bytes = os.path.getsize(p) if exists else None
        actual_sha = sha256_file(p) if exists else None
        ok_b = (actual_bytes == f.get("bytes"))
        ok_s = (actual_sha == f.get("sha256"))
        print("%-20s exists=%s bytes=%s/%s ok=%s sha=%s ok=%s %s" % (
            f["key"], exists, actual_bytes, f.get("bytes"), ok_b,
            (actual_sha or "")[:16], ok_s, "" if (ok_b and ok_s) else "  <<< MISMATCH"))
        if not (exists and ok_b and ok_s):
            bad.append((f["key"], exists, actual_bytes, f.get("bytes"), actual_sha, f.get("sha256")))
    print("input_manifest all_ok field =", im.get("all_ok"), "; recomputed mismatches =", len(bad))

    print()
    print("== input_manifest.json self sha256 vs run_manifest.json ==")
    rm = json.load(io.open(os.path.join(OUT, "run_manifest.json"), encoding="utf-8"))
    recorded = rm["input_manifest"]["sha256"]
    actual = sha256_file(im_path)
    print("recorded:", recorded)
    print("actual  :", actual)
    print("match   :", recorded == actual)

    print()
    print("== run_manifest.determinism.files vs workspace ==")
    print(json.dumps(rm["determinism"]["files"], ensure_ascii=False, indent=1))
    for name, rec in rm["determinism"]["files"].items():
        if isinstance(rec, dict):
            rel = rec.get("path")
            rsha = rec.get("sha256")
        else:
            rel, rsha = None, rec
        if rel:
            p = os.path.join(ROOT, rel.replace("/", os.sep))
            a = sha256_file(p) if os.path.exists(p) else None
            print(name, "recorded=", rsha, "actual=", a, "match=", rsha == a)
        else:
            print(name, "recorded=", rsha, "(no path)")

    print()
    print("== determinism.commands / other readings ==")
    print(json.dumps(rm["determinism"]["commands"], ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()

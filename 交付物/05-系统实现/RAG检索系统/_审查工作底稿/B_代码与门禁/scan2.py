import io, re
FILES = {
 "config.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\config.py",
 "vector_search.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\vector_search.py",
 "graph_query.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\graph_query.py",
 "pipeline.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\pipeline.py",
 "metrics.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\metrics.py",
 "pre_experiment.py": r"C:\Users\15129\Desktop\毕业设计\交付物/03-代码\检索\pre_experiment.py",
}
sdks = re.compile(r"^\s*(?:from|import)\s+(openai|anthropic|requests|urllib|httpx|aiohttp|socket|transformers|torch|huggingface_hub|sentence_transformers|faiss|numpy|pandas)", re.M)
cred = re.compile(r"api[_-]?key|apikey|credential|os\.environ\.get\([\"'][A-Z_]*(KEY|TOKEN|SECRET)", re.I)
net  = re.compile(r"https?://|\burlopen\b|\brequests\.|\bsocket\.", re.I)
for n,p in FILES.items():
    t=io.open(p,encoding="utf-8").read()
    print("%-22s imports=%s" % (n, sorted(set(m.group(1) for m in sdks.finditer(t)))))
    print("%-22s   cred_hits=%s" % ("", sorted({(t[:m.start()].count(chr(10))+1, m.group(0)[:28]) for m in cred.finditer(t)})[:8]))
    print("%-22s   net_hits =%s" % ("", sorted({(t[:m.start()].count(chr(10))+1, m.group(0)[:40]) for m in net.finditer(t)})[:8]))

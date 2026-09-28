import io, os, re, sys
TARGETS = {
 "build_questions.py": r"C:\Users\15129\Desktop\毕业设计\代码\检索\build_questions.py",
 "run_query.py": r"C:\Users\15129\Desktop\毕业设计\代码\检索\run_query.py",
 "third_party_review.py": r"C:\Users\15129\Desktop\毕业设计\代码\检索\third_party_review.py",
 "POSCTRL_poscontrol.py": r"C:\Users\15129\AppData\Local\Temp\re7_B\poscontrol.py",
}
NET = re.compile(r"\b(?:socket|ssl|ftplib|smtplib|telnetlib|http\.client|requests|urllib|urlopen|httpx|aiohttp|websocket|paramiko|boto3)\b|https?://", re.I)
SDK = re.compile(r"\b(?:openai|anthropic|dashscope|zhipuai|google\.generativeai|genai|cohere|ollama|mistralai|langchain_openai|transformers)\b", re.I)
CALL= re.compile(r"\.chat\.completions\.create|\.messages\.create|\.embeddings\.create|OpenAI\(|Anthropic\(|api_key\s*=", re.I)
CRED= re.compile(r"api[_-]?key|apikey|secret|passwd|password|access[_-]?token|credential", re.I)
OUT = []
for name, path in TARGETS.items():
    t = io.open(path, encoding="utf-8").read()
    for label, pat in (("网络",NET),("厂商SDK",SDK),("模型调用",CALL),("凭据读取",CRED)):
        hits = sorted({(t[:m.start()].count("\n")+1, m.group(0)) for m in pat.finditer(t)})
        OUT.append("%-26s %-8s %s" % (name, label, hits if hits else "无"))
io.open("scan.txt","w",encoding="utf-8").write("\n".join(OUT))
print("done")

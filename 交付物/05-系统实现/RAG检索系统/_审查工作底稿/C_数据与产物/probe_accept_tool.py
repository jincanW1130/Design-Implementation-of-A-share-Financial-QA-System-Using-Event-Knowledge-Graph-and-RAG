# -*- coding: utf-8 -*-
import io, re

p = r"C:\Users\15129\Desktop\毕业设计\工具\验收第7阶段.py"
s = io.open(p, encoding="utf-8").read()

print("--- writes (open(..., 'w')) ---")
for m in re.finditer(r"open\([^)]*['\"]w", s):
    a = max(0, m.start() - 140)
    print(re.sub(r"\s+", " ", s[a:m.start() + 180]))

print()
print("--- run_cmd( calls ---")
for m in re.finditer(r"run_cmd\(", s):
    a = max(0, m.start() - 260)
    print(re.sub(r"\s+", " ", s[a:m.start() + 260]))
    print()

print("--- main body near mirror ---")
i = s.find("mirror, copied, skipped")
print(s[max(0, i - 2500):i + 1800])

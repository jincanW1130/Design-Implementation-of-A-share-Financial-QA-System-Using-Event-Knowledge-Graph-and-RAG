# -*- coding: utf-8 -*-
"""run_verify.py —— 依次跑 sN 脚本并把 UTF-8 输出同时落盘 sN.out.txt。"""
import subprocess, sys, os
D = os.path.dirname(os.path.abspath(__file__))
for n in ("s1_readings.py", "s2_graph_facts.py", "s3_citation_audit.py", "s4_term_scan.py", "s5_doc_chain.py"):
    r = subprocess.run([sys.executable, os.path.join(D, n)], capture_output=True)
    out = r.stdout.decode("utf-8", "replace"); err = r.stderr.decode("utf-8", "replace")
    open(os.path.join(D, n.replace(".py", ".out.txt")), "w", encoding="utf-8").write(out + ("\n--- stderr ---\n" + err if err.strip() else ""))
    print("=== %s  exit=%d ===" % (n, r.returncode))

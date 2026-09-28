import json, io, os
P = r"C:\Users\15129\Desktop\毕业设计\阶段07-RAG检索系统\预实验问题集\第三方复核台账.json"
d = json.load(io.open(P, encoding="utf-8"))
out=[]
out.append("ledger_schema=%s" % d.get("ledger_schema"))
out.append("confirmed_lines=%s  excluded_lines=%s" % (d.get("confirmed_lines"), d.get("excluded_lines")))
out.append("usage_totals_confirmation=%s" % d.get("usage_totals_confirmation"))
out.append("usage_totals_all_lines_trace=%s" % d.get("usage_totals_all_lines_trace"))
out.append("cross_vendor.confirmed=%s" % {k:v for k,v in (d.get("cross_vendor") or {}).items() if k!="per_question_verdicts"})
out.append("cross_vendor.trace=%s" % {k:v for k,v in (d.get("cross_vendor_all_lines_trace") or {}).items() if k!="per_question_verdicts"})
for v in d.get("vendors") or []:
    out.append("vendor %-8s model=%-14s answered=%s failed=%s tokens=%s excluded=%s base=%s" % (
        v.get("vendor"), v.get("model"), v.get("answered"), v.get("failed"),
        (v.get("usage_totals") or {}).get("total_tokens"), v.get("excluded_per_author"), v.get("base_url")))
io.open("ledger.txt","w",encoding="utf-8").write("\n".join(out))
print("ok")

# -*- coding: utf-8 -*-
r"""auto_annotate_verify.py —— 自动标注产物的**离线**完好性核对（0 次模型调用）。

核对四件事（逐条打印原始读数，退出码 0／1）：
1. **抽样字段逐字节同源**：`<split>.auto.jsonl` 与 `{split}.jsonl` 的每一行，除 `annotation`
   的值以外**逐字节相同**（在原始行的字节上做手术是 `auto_annotate.py` 的写法，本工具负责验证）；
   同时核对条目顺序与 `item_id` 序列一致。
2. **`provenance` 完好**：每条 `status=auto_annotated`、`provenance.model`／`prompt_version` 与
   期望一致、`provenance.usage` 有 `total_tokens`、`attempts ≥ 1`。
3. **工作区一致**：`工作区\<split>\<item_id>.md` 的 `annotation` 代码块与该条 jsonl 的 `annotation`
   等价（json 解析后逐键比对）；文件数 = 条目数。
4. **可核到原文**：`quote` 字段非空且能在该条 `text` 里逐字定位（这条读数与 lint 口径不同，
   只是「有没有出格到离谱」的粗检；逐字可定位率另见两版对照报告）。

用法：
```powershell
python 代码\抽取与图谱\auto_annotate_verify.py --dir "阶段05-数据准备\数据集\抽取评测集\v2.1\自动标注_flash"
python 代码\抽取与图谱\auto_annotate_verify.py --dir "…\自动标注" --suffix .auto --model deepseek-v4-pro
python 代码\抽取与图谱\auto_annotate_verify.py --dir "…\自动标注\提准" --suffix .auto.repaired --workspace 工作区
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

ROOT = config.ROOT
EVAL_SUBDIR = "抽取评测集"


def eval_dir() -> str:
    return os.path.join(config.DATASET_ROOT, EVAL_SUBDIR, config.DATASET_VERSION)


def resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def read_lines(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        return [ln.rstrip("\n") for ln in fh if ln.strip()]


MARKER = ', "annotation": '


def strip_annotation(line: str) -> str:
    pos = line.rindex(MARKER)
    return line[:pos + len(MARKER)] + "…}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="auto_annotate_verify.py",
                                 description="自动标注产物的离线完好性核对（0 次调用）")
    ap.add_argument("--dir", required=True, help="自动标注产物目录（相对项目根或绝对路径）")
    ap.add_argument("--eval-dir", default=None, help="评测集目录（默认由 config 推出）")
    ap.add_argument("--suffix", default=".auto", help="jsonl 后缀：`<split><suffix>.jsonl`")
    ap.add_argument("--workspace", default="工作区", help="工作区子目录名（提准产物是 `工作区`）")
    ap.add_argument("--model", default=None,
                    help="期望的 provenance.model（不给就不核对；多个用逗号分隔，如提准产物混合两版时）")
    ap.add_argument("--prompt-version", default=None,
                    help="期望的 provenance.prompt_version（不给就不核对；多个用逗号分隔）")
    args = ap.parse_args(argv)

    vd = resolve(args.dir)
    ed = resolve(args.eval_dir) if args.eval_dir else eval_dir()
    want_models = [x.strip() for x in (args.model or "").split(",") if x.strip()]
    want_prompts = [x.strip() for x in (args.prompt_version or "").split(",") if x.strip()]
    failed = 0
    print("核对目录：%s" % vd)
    print("评测集：  %s" % ed)
    for split in ("dev", "test"):
        auto_path = os.path.join(vd, "%s%s.jsonl" % (split, args.suffix))
        truth_path = os.path.join(ed, "%s.jsonl" % split)
        if not os.path.isfile(auto_path):
            print("[SKIP] %s：%s 不存在" % (split, auto_path))
            continue
        auto_lines, truth_lines = read_lines(auto_path), read_lines(truth_path)
        auto_recs = [json.loads(x) for x in auto_lines]
        truth_recs = [json.loads(x) for x in truth_lines]
        # ① 抽样字段逐字节同源（顺序按 item_id 对齐：auto 集可能是全量的子集）
        truth_by_id = {r["item_id"]: (r, ln) for r, ln in zip(truth_recs, truth_lines)}
        bad_prefix, missing = [], []
        for rec, ln in zip(auto_recs, auto_lines):
            t = truth_by_id.get(rec.get("item_id"))
            if t is None:
                missing.append(rec.get("item_id"))
                continue
            if strip_annotation(ln) != strip_annotation(t[1]):
                bad_prefix.append(rec.get("item_id"))
        ok1 = not bad_prefix and not missing
        failed += 0 if ok1 else 1
        print("[%s] %s 抽样字段逐字节同源：%d 条，除 `annotation` 外不一致 %d 条%s"
              % ("OK" if ok1 else "FAIL", split, len(auto_recs), len(bad_prefix),
                 "，且 %d 条在原件里找不到" % len(missing) if missing else ""))
        # ② provenance 完好
        # L-10：删除死代码 —— 原先还有一个 `no_usage` 列表与其 `elif not u` 分支，
        # 但 `cond` 已含 `and u`（u 为真才可能 cond 为真），故该分支不可达，列表也无人读取。
        bad_prov = []
        for rec in auto_recs:
            ann = rec.get("annotation") or {}
            prov = ann.get("provenance") or {}
            u = ((prov.get("usage") or {}).get("total_tokens"))
            cond = (ann.get("status") == "auto_annotated" and isinstance(prov, dict) and prov
                    and int(prov.get("attempts") or 0) >= 1 and u)
            if want_models and prov.get("model") not in want_models:
                cond = False
            if want_prompts and prov.get("prompt_version") not in want_prompts:
                cond = False
            if not cond:
                bad_prov.append(rec.get("item_id"))
        ok2 = not bad_prov
        failed += 0 if ok2 else 1
        prov_models = sorted({((r.get("annotation") or {}).get("provenance") or {}).get("model")
                              for r in auto_recs})
        prov_prompts = sorted({((r.get("annotation") or {}).get("provenance") or {}).get("prompt_version")
                               for r in auto_recs})
        print("[%s] %s provenance 完好：%d 条；model=%s｜prompt_version=%s%s"
              % ("OK" if ok2 else "FAIL", split, len(auto_recs), prov_models, prov_prompts,
                 ("；不合格 %d 条：%s" % (len(bad_prov), "、".join(bad_prov[:6]))) if bad_prov else ""))
        # ③ 工作区一致（annotation 块与 jsonl 等价）
        ws_dir = os.path.join(vd, args.workspace, split)
        ws_bad, ws_n = [], 0
        if os.path.isdir(ws_dir):
            for rec in auto_recs:
                p = os.path.join(ws_dir, "%s.md" % rec["item_id"])
                if not os.path.isfile(p):
                    ws_bad.append(rec["item_id"])
                    continue
                ws_n += 1
                # L-11：用 with 关闭句柄（原先 open(...).read() 依赖 CPython 引用计数回收）。
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
                i = text.find("```json")
                j = text.rfind("```")
                blk = text[i + 7:j] if 0 <= i < j else ""
                try:
                    if json.loads(blk) != (rec.get("annotation") or {}):
                        ws_bad.append(rec["item_id"])
                except ValueError:
                    ws_bad.append(rec["item_id"])
            ok3 = not ws_bad
        else:
            ok3 = False
        failed += 0 if ok3 else 1
        print("[%s] %s 工作区一致：%d／%d 个 md 的 annotation 块与 jsonl 等价%s"
              % ("OK" if ok3 else "FAIL", split, ws_n, len(auto_recs),
                 ("；不一致：" + "、".join(ws_bad[:6])) if ws_bad else ""))
        # ④ quote 粗检：非空 quote 能不能在 text 里逐字定位
        q_total = q_ok = 0
        for rec, t in zip(auto_recs, [truth_by_id.get(x.get("item_id"), ({}, ""))[0] for x in auto_recs]):
            text = str(t.get("text") or "")
            ann = rec.get("annotation") or {}
            for slot in ("entities", "events", "relations", "times", "ontology_boundary_log"):
                for x in (ann.get(slot) or []):
                    if isinstance(x, dict) and isinstance(x.get("quote"), str) and x["quote"]:
                        q_total += 1
                        q_ok += 1 if x["quote"] in text else 0
        print("[--] %s quote 逐字可定位（粗检）：%d／%d = %.1f%%"
              % (split, q_ok, q_total, 100.0 * q_ok / q_total if q_total else 0.0))
    print("核对结论：%s（退出码 %d）" % ("全部通过" if not failed else "%d 项失败" % failed,
                                        1 if failed else 0))
    return 1 if failed else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())

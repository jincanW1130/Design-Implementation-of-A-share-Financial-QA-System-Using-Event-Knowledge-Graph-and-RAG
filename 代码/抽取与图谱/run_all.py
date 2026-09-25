# -*- coding: utf-8 -*-
r"""run_all.py —— 第 6 阶段图谱管线的入口（T7）。

按《15》第4.2节 的顺序把四个组件串起来：

    extract.py（T3 实体与事件抽取）→ disambiguate.py（T4 实体消歧）
    → dedup_events.py（T5 事件去重）→ write_graph.py（T6 图谱写入与导出）

四件事是这一层要保证的：

1. **缓存齐全时零模型调用**：T4～T6 从不调用模型；只有 `extract.py` 可能调用。本入口跑完
   extract 后读它的运行记录（`run_history.jsonl` 的 `api_calls_total`）并把合计写进日志；
   若发生了模型调用而调用方没有显式允许（`--allow-api-calls`），则**阻断并报错退出**——
   复跑必须命中缓存，这一条是可机器核验的（阈值在 `config.RUN_ALL`）。
2. **幂等**：每个阶段自身幂等（T4／T5 按缓存指纹跳过并逐字节可复现，T6 每次重算但产物逐字节
   一致，extract 命中缓存后不重算），所以整条链跑 N 遍与跑 1 遍的产物一致。
3. **可续跑**：`--only <阶段>` 只跑一个阶段，`--from <阶段>` 从某阶段起往后跑；某阶段失败即
   停止并把退出码原样带出，重跑时前面已完成的阶段会被各自的跳过逻辑接上。
4. **留痕**：全过程写一份中文运行日志（首跑 `运行日志_首跑.txt`、之后 `运行日志_复跑.txt`，
   名字在 `config.RUN_ALL`），含每个阶段的命令行、退出码、耗时、关键读数与产物 sha256。

用法：

    python 代码\抽取与图谱\run_all.py                       # 默认 --profile pilot
    python 代码\抽取与图谱\run_all.py --profile v21 --allow-api-calls
    python 代码\抽取与图谱\run_all.py --from dedup_events    # 从 T5 起往后跑
    python 代码\抽取与图谱\run_all.py --only write_graph     # 只跑 T6
    python 代码\抽取与图谱\run_all.py --force                # 重算 T4～T6 的产物
    python 代码\抽取与图谱\run_all.py --force-extract        # 连 extract 也重算（会调模型！）

⚠ `--force` **不会**让 extract 重新调用模型（那会破坏「复跑零调用」）；要重跑抽取请用
`--force-extract`，并同时加 `--allow-api-calls`。

退出码：`0` 全链成功；`1` 参数／前置／模型调用违规；`2` 某阶段数据异常（原样带出该阶段退出码）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402


def now_iso() -> str:
    tz = _dt.timezone(_dt.timedelta(hours=8))
    return _dt.datetime.now(tz).isoformat(timespec="seconds")


def read_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path):
    if not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path):
    return os.path.relpath(path, config.ROOT).replace("\\", "/")


def extract_output_table(profile):
    """extract.py 的产物落点表（pilot → OUTPUT_FILES、v21 → FULL_OUTPUT_FILES）。"""
    name = config.GRAPH_PIPELINE["extract_records_profiles"][profile]
    return getattr(config, name)


# --------------------------------------------------------------------------
# 阶段定义
# --------------------------------------------------------------------------
def stage_command(stage, profile, args):
    script = os.path.join(_HERE, stage["script"])
    command = [sys.executable, script, "--profile", profile]
    if stage["name"] == "extract":
        # extract 的 --force 会重新调用模型：只有显式 --force-extract 才下传。
        if args.force_extract:
            command.append("--force")
    elif args.force:
        command.append("--force")
    return command


def run_stage(stage, command, env):
    started = time.time()
    proc = subprocess.run(command, cwd=config.ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return {
        "name": stage["name"], "label": stage["label"], "command": command,
        "exit_code": proc.returncode, "seconds": round(time.time() - started, 3),
        "stdout": proc.stdout or "", "stderr": proc.stderr or "",
    }


# --------------------------------------------------------------------------
# 读产物（不解析屏幕输出，直接读机器可读产物）
# --------------------------------------------------------------------------
def collect_readings(profile, paths, table):
    readings = []
    extract = read_jsonl(table["extracted"])
    readings.append(("T3 抽取结果", "%s（%d 篇）" % (rel(table["extracted"]), len(extract))))

    history = read_jsonl(table.get("run_history"))
    if history:
        last = history[-1]
        readings.append(("T3 本次运行记录", "api_calls=%s、cache_hits=%s、retries=%s、fetched=%s"
                         % (last.get("api_calls_total", last.get("api_calls")),
                            last.get("cache_hits"), last.get("retries"), last.get("fetched"))))

    disambig = read_json(paths["disambiguation"])
    if disambig:
        counts = disambig.get("counts") or {}
        readings.append(("T4 消歧", "实体 %s；已消歧 %s；待消歧 %s（%s）；公司身份 %s 个"
                         % (counts.get("entities"), counts.get("resolved"),
                            counts.get("unresolved"),
                            counts.get("unresolved_by_reason"),
                            counts.get("company_identities"))))

    merge = read_json(paths["merge_summary"])
    if merge:
        counts = merge.get("counts") or {}
        readings.append(("T5 去重", "事件 %s → %s；候选对 %s；合并组 %s；最大证据文档数 %s"
                         % (counts.get("events_before"), counts.get("events_after"),
                            counts.get("candidate_pairs"), counts.get("merged_groups"),
                            counts.get("max_evidence_docs_in_group"))))
        selftest = read_json(paths["dedup_self_test"]) or {}
        readings.append(("T5 自检（合并后保留全部证据文档）", "passed=%s"
                         % selftest.get("passed")))

    stats = read_json(paths["graph_stats"])
    if stats:
        counts = stats.get("counts") or {}
        readings.append(("T6 图谱", "节点 %s；边 %s；事件 %s（合并 %s）"
                         % (counts.get("nodes_total"), counts.get("edges_total"),
                            counts.get("events"), counts.get("merged_events"))))
    check = read_json(paths["graph_check"])
    if check:
        summary = check.get("summary") or {}
        readings.append(("T6 机检", "%s 项：通过 %s，不通过 %s（硬约束不通过 %s）"
                         % (summary.get("checks"), summary.get("passed"),
                            "、".join(summary.get("failed") or []) or "无",
                            "、".join(summary.get("failed_must") or []) or "无")))
    return readings


def product_hashes(profile, paths):
    keys = ("extract_records", "alias_table", "disambiguation", "unresolved", "merge_log",
            "events_merged", "merge_summary", "dedup_self_test", "nodes", "edges",
            "graph_stats", "replay_cypher", "graph_check", "manifest")
    return [(key, rel(paths[key]), sha256_file(paths[key]), os.path.getsize(paths[key])
             if os.path.isfile(paths[key]) else 0) for key in keys]


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(args) -> int:
    stages = config.RUN_ALL["stages"]
    names = [s["name"] for s in stages]
    if args.only and args.only not in names:
        raise SystemExit("--only 取值必须是 %s 之一" % "／".join(names))
    if args.from_stage and args.from_stage not in names:
        raise SystemExit("--from 取值必须是 %s 之一" % "／".join(names))

    if args.only:
        todo = [s for s in stages if s["name"] == args.only]
    elif args.from_stage:
        todo = stages[names.index(args.from_stage):]
    else:
        todo = list(stages)

    paths = config.pipeline_paths(args.profile)
    table = extract_output_table(args.profile)
    for key in ("work_root", "disambig_dir", "dedup_dir", "export_dir"):
        os.makedirs(paths[key], exist_ok=True)

    first_run = not os.path.isfile(paths["log_first"])
    log_path = paths["log_first"] if first_run else paths["log_second"]
    replay_phase = "首跑" if first_run else "复跑"

    if args.force_extract and not args.allow_api_calls:
        raise SystemExit("--force-extract 会重新调用模型；请同时加 --allow-api-calls 以确认。")

    lines = ["=" * 78,
             "第 6 阶段 事件抽取与知识图谱 —— 管线运行日志（%s）" % replay_phase,
             "=" * 78,
             "时间：%s" % now_iso(),
             "profile：%s；数据集版本：%s" % (args.profile, config.DATASET_VERSION),
             "阶段：%s" % " → ".join(s["name"] for s in todo),
             "参数：--force=%s、--force-extract=%s、--allow-api-calls=%s"
             % (args.force, args.force_extract, args.allow_api_calls),
             "输入（T3 抽取结果）：%s" % rel(table["extracted"]),
             "工作目录：%s" % rel(paths["work_root"]),
             "导出目录：%s" % rel(paths["export_dir"]),
             "说明：本日志不记录任何凭据；模型可用性只由 extract.py 的缓存与运行记录反映。",
             ""]

    results, failures = [], 0
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    for index, stage in enumerate(todo, start=1):
        command = stage_command(stage, args.profile, args)
        print("[%d/%d] %s …" % (index, len(todo), stage["label"]), flush=True)
        result = run_stage(stage, command, env)
        results.append(result)
        status = {0: "成功", 1: "阻断（前置／参数）", 2: "数据异常"}.get(result["exit_code"],
                                                                      "退出码 %d"
                                                                      % result["exit_code"])
        if result["exit_code"] == 1 and "跳过" in result["stdout"]:
            status = "成功（命中已有产物，跳过）"
        print("      %s（%.3fs，退出码 %s）"
              % (status, result["seconds"], result["exit_code"]), flush=True)
        lines += ["-" * 78,
                  "[%d/%d] %s（%s）" % (index, len(todo), stage["label"], stage["name"]),
                  "命令：%s" % " ".join('"%s"' % c if " " in c else c for c in command),
                  "退出码：%s（%s）；耗时：%.3fs" % (result["exit_code"], status,
                                                  result["seconds"]),
                  "stdout："] + ["  " + ln for ln in result["stdout"].rstrip().splitlines()] + \
                 ["stderr："] + ["  " + ln for ln in result["stderr"].rstrip().splitlines()] + [""]
        if result["exit_code"] != 0:
            failures += 1
            print("      停止：该阶段未成功，后面的阶段不再执行（重跑会自动接上）。")
            print("      详见日志：%s" % rel(log_path))
            break

    readings = collect_readings(args.profile, paths, table)
    api_calls = None
    history = read_jsonl(table.get("run_history"))
    if history:
        api_calls = history[-1].get("api_calls_total", history[-1].get("api_calls"))
    limit = int(config.RUN_ALL["max_api_calls_on_replay"])
    api_ok = (api_calls is not None and api_calls <= limit)

    lines += ["=" * 78, "关键读数（直接读机器可读产物，不解析屏幕输出）", "=" * 78]
    lines += ["* %s：%s" % (k, v) for k, v in readings]
    lines += ["* 本次 extract 的模型调用合计：%s（复跑上限 %d）" % (api_calls, limit), ""]

    lines += ["=" * 78, "产物校验和（sha256，逐字节复现的比对依据）", "=" * 78]
    lines += ["%s  %s  %d bytes" % (digest or "(缺)", path, size)
              for _key, path, digest, size in product_hashes(args.profile, paths)]
    lines += ["",
              "注：graph_stats.json 每次运行的 generated_at 不同，其校验和随之变化；"
              "逐字节比对时排除该字段与缓存指纹字段（config.GRAPH_PIPELINE"
              "[\"excluded_from_byte_compare\"]）。",
              "结论：%s" % ("全部阶段成功。" if not failures else "有阶段未成功，见上。")]

    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    print("")
    for key, value in readings:
        print("  · %s：%s" % (key, value))
    print("  · 模型调用合计：%s（复跑上限 %d）" % (api_calls, limit))
    print("运行日志：%s" % rel(log_path))

    if failures:
        return results[-1]["exit_code"] or 2
    if not api_ok and not args.allow_api_calls:
        print("[阻断] 本次运行发生了 %s 次模型调用（复跑上限 %d）。缓存不齐时不放行；"
              "确认要放量请加 --allow-api-calls。" % (api_calls, limit))
        return 1
    if api_calls is None:
        print("[注意] 读不到 extract 的运行记录（%s），无法核对模型调用次数。"
              % rel(table.get("run_history")))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段图谱管线入口（T7：extract → disambiguate → dedup_events → "
                    "write_graph；复跑零模型调用；幂等可续跑）")
    parser.add_argument("--profile", default="pilot", choices=["pilot", "v21"])
    parser.add_argument("--force", action="store_true",
                        help="重算 T4／T5／T6 的产物（**不会**让 extract 重新调用模型）")
    parser.add_argument("--force-extract", action="store_true",
                        help="连 extract 也重算（会调用模型；需同时加 --allow-api-calls）")
    parser.add_argument("--allow-api-calls", action="store_true",
                        help="允许本次运行发生模型调用（放量时用）")
    parser.add_argument("--only", default=None, help="只跑一个阶段（extract／disambiguate／"
                                                   "dedup_events／write_graph）")
    parser.add_argument("--from", dest="from_stage", default=None,
                        help="从某阶段起往后跑")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SystemExit as exc:
        print("[阻断] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""工具\\契约快照.py —— 后端 OpenAPI 契约的**字段级快照门禁**。

做什么
------
1. `--write`：在**不启动服务**的前提下装配后端应用（`后端/main.py` 的 `create_app()`），
   读取 `app.openapi()`，把以下内容写到 `交付物/03-代码/后端/_契约快照.json`（**入库**）：
   * 路径集合与每路径方法集（既有口径）；
   * `components.schemas` 的**字段级**签名：每个 schema 的属性集合、必填项、
     `additionalProperties` 与每个属性的类型／`$ref`／数组项／联合类型；
   * **主要错误响应样例**：每个操作 ≥400 状态码的响应 schema（字段级）与 `example`
     （`{"code": …, "message": …}`）；
   * **操作级契约**（独立审查 2026-10-19 P2-8 扩面）：每个操作的参数（名称／in／
     必填／默认值／类型）、请求体 schema（required＋media type＋字段级）、有效
     `security` 声明、2xx 响应是否存在／状态码集合／content schema。
2. 默认模式：重新生成当前契约并与快照逐项比对；任何差异（路径／方法／schema 名／
   **schema 字段／必填／类型**／错误响应样例／**操作参数／请求体／鉴权／2xx 响应**）
   都打印出来并以**退出码 1** 结束，便于并入 `--gate`。

为什么要字段级
--------------
第二轮只记「路径／方法／schema 名」，计数不变时仍可能把请求体字段改名、把可选改必填、
把 `string` 改成 `integer`。本版把字段名、必填集合与类型签名为**集合**比对：
任何契约变动都必须显式 `--write` 重登记，评审 diff 一眼可见。

口径边界
--------
* 只读：装配应用不会访问 MySQL／Neo4j／模型，也不会写库；
* 不新增依赖：只用标准库 + FastAPI 自带的 `app.openapi()`；
* **不记录 schema 的 `description` 文本**（避免文档措辞变更误报），只记录结构；
* 内联错误体 schema 也做字段级记录（`code: integer`／`message: string` 必填），
  它不会新增 `components.schemas` 条目。

用法
----
    python 工具\\契约快照.py            # 比对当前契约与快照（退出码 0/1）
    python 工具\\契约快照.py --write    # 重新生成快照（显式登记契约变更）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "交付物", "03-代码", "后端")
SNAPSHOT = os.path.join(BACKEND, "_契约快照.json")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# --------------------------------------------------------------------------
# 1. 类型签名的规范化（只留结构，不留说明文字）
# --------------------------------------------------------------------------
_MAX_DEPTH = 12


def describe_type(schema, depth: int = 0) -> dict:
    """把一个属性 schema 归一成稳定的类型签名（`$ref`／type／items／anyOf…）。"""
    if not isinstance(schema, dict) or depth > _MAX_DEPTH:
        return {"kind": "unknown"}
    if "$ref" in schema:
        return {"ref": str(schema["$ref"]).rsplit("/", 1)[-1]}
    out: dict = {}
    if "type" in schema:
        value = schema["type"]
        out["type"] = sorted(value) if isinstance(value, list) else value
    for key in ("format", "const"):
        if key in schema:
            out[key] = schema[key]
    if "enum" in schema:
        out["enum"] = list(schema["enum"])
    if "items" in schema:
        out["items"] = describe_type(schema["items"], depth + 1)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            out[key] = [describe_type(item, depth + 1) for item in schema[key]]
    if "additionalProperties" in schema:
        value = schema["additionalProperties"]
        out["additionalProperties"] = (describe_type(value, depth + 1)
                                       if isinstance(value, dict) else bool(value))
    if not out:
        out["kind"] = "any"
    return out


def schema_signature(schema) -> dict:
    """schema 的字段级签名：类型／必填／属性集合／额外属性。"""
    if not isinstance(schema, dict):
        return {"kind": "unknown"}
    if "$ref" in schema:
        return {"ref": str(schema["$ref"]).rsplit("/", 1)[-1]}
    props = schema.get("properties") or {}
    out = {
        "type": schema.get("type"),
        "required": sorted(str(x) for x in (schema.get("required") or [])),
        "properties": {str(name): describe_type(value)
                       for name, value in sorted(props.items())},
    }
    if "additionalProperties" in schema:
        value = schema["additionalProperties"]
        out["additionalProperties"] = (describe_type(value) if isinstance(value, dict)
                                       else bool(value))
    return out


def content_signature(media) -> dict | None:
    """响应／请求体 media type 的签名：对象走字段级，`$ref` 保留引用名，
    其余（`anyOf`／标量）走类型归一。"""
    if not isinstance(media, dict):
        return None
    schema = media.get("schema")
    if not isinstance(schema, dict):
        return None
    sig = schema_signature(schema)
    if sig.get("properties") or sig.get("ref"):
        return sig
    return describe_type(schema)


def _parameters_contract(operation) -> list:
    """操作级查询／路径／头参数：名称、位置、必填、默认值与类型签名。"""
    params = []
    for raw in operation.get("parameters") or []:
        if not isinstance(raw, dict):
            continue
        schema = raw.get("schema") if isinstance(raw.get("schema"), dict) else {}
        entry = {
            "name": str(raw.get("name", "")),
            "in": str(raw.get("in", "")),
            "required": bool(raw.get("required", False)),
            "schema": describe_type(schema),
        }
        if "default" in schema:                 # 默认值单独记录：新增/删除默认值也应被检出
            entry["default"] = schema["default"]
        params.append(entry)
    params.sort(key=lambda item: (item["in"], item["name"]))
    return params


def _request_body_contract(operation) -> dict | None:
    """请求体（若有）：required 与每个 media type 的 schema 签名（含字段级）。"""
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return None
    content = {}
    for media_type, media in sorted((body.get("content") or {}).items()):
        sig = content_signature(media)
        if sig is not None:
            content[str(media_type)] = sig
    return {"required": bool(body.get("required", False)), "content": content}


def _security_contract(operation, spec) -> list:
    """操作的有效 security 声明（操作级优先，其次全局）；无声明记录为空列表。"""
    raw = operation.get("security")
    if raw is None:
        raw = spec.get("security")
    normalized = []
    for requirement in raw or []:
        if not isinstance(requirement, dict):
            continue
        normalized.append({
            str(name): sorted(str(scope) for scope in (scopes or []))
            for name, scopes in sorted(requirement.items())
        })
    normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return normalized


def _success_contract(operation) -> dict:
    """2xx 响应是否存在、状态码集合与 content schema（有则记录）。"""
    responses = {}
    for status, response in sorted((operation.get("responses") or {}).items()):
        text = str(status)
        if not text.isdigit() or not (200 <= int(text) < 300):
            continue
        if not isinstance(response, dict):
            continue
        entry: dict = {"present": True}
        content = {}
        for media_type, media in sorted((response.get("content") or {}).items()):
            sig = content_signature(media)
            if sig is not None:
                content[str(media_type)] = sig
        if content:
            entry["content"] = content
        responses[text] = entry
    return {"present": bool(responses), "statuses": sorted(responses), "responses": responses}


# --------------------------------------------------------------------------
# 2. 契约抽取
# --------------------------------------------------------------------------
def _iter_operations(spec: dict):
    for path in sorted(spec.get("paths") or {}):
        for method in sorted(spec["paths"][path]):
            yield path, method.upper(), spec["paths"][path][method]


def current_contract() -> dict:
    """装配后端应用并抽取字段级契约（与是否已启动 :8000 无关）。"""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    logging.disable(logging.CRITICAL)          # 静默装配日志；契约输出保持干净
    warnings.filterwarnings("ignore")          # HEAD/GET 同函数会产生重复 operationId 警告
    import main                                # noqa: PLC0415（需先注入 sys.path）

    spec = main.app.openapi()
    paths = {}
    for path in sorted(spec.get("paths", {})):
        methods = sorted(m.upper() for m in spec["paths"][path])
        paths[path] = methods
    operations = sorted("%s %s" % (method, path)
                        for path, methods in paths.items() for method in methods)

    components = (spec.get("components") or {}).get("schemas") or {}
    schema_fields = {name: schema_signature(components[name]) for name in sorted(components)}

    error_responses: dict = {}
    operation_contract: dict = {}
    for path, method, op in _iter_operations(spec):
        entries = {}
        for status, response in sorted((op.get("responses") or {}).items()):
            text = str(status)
            if not text.isdigit() or int(text) < 400:
                continue
            media = ((response.get("content") or {}).get("application/json") or {})
            entry: dict = {}
            if "schema" in media:
                entry["schema"] = schema_signature(media["schema"])
            if "example" in media:
                entry["example"] = media["example"]
            entries[text] = entry
        if entries:
            error_responses["%s %s" % (method, path)] = entries

        operation_contract["%s %s" % (method, path)] = {
            "parameters": _parameters_contract(op),
            "request_body": _request_body_contract(op),
            "security": _security_contract(op, spec),
            "success_responses": _success_contract(op),
        }

    return {
        "generated_by": "工具/契约快照.py",
        "snapshot_level": "operation",
        "openapi_version": str(spec.get("openapi", "")),
        "path_count": len(paths),
        "operation_count": len(operations),
        "paths": paths,
        "operations": operations,
        "schemas": sorted(components),
        "schema_fields": schema_fields,
        "error_responses": error_responses,
        "operation_contract": operation_contract,
    }


# --------------------------------------------------------------------------
# 3. 快照读写与差异
# --------------------------------------------------------------------------
def load_snapshot() -> dict | None:
    if not os.path.isfile(SNAPSHOT):
        return None
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_snapshot(contract: dict) -> None:
    with open(SNAPSHOT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(contract, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def _diff_value(old, new, where: str, diffs: list[str]) -> None:
    """递归比较两个 JSON 值；列表按整体比较（快照里的列表均已排序或语义定序）。"""
    if type(old) is not type(new):
        diffs.append("%s 类型变化：%r → %r" % (where, old, new))
        return
    if isinstance(old, dict):
        for key in sorted(set(old) - set(new)):
            diffs.append("%s.%s 删除（原 %r）" % (where, key, old[key]))
        for key in sorted(set(new) - set(old)):
            diffs.append("%s.%s 新增（%r）" % (where, key, new[key]))
        for key in sorted(set(old) & set(new)):
            _diff_value(old[key], new[key], "%s.%s" % (where, key), diffs)
    elif isinstance(old, list):
        if old != new:
            diffs.append("%s 变化：%r → %r" % (where, old, new))
    elif old != new:
        diffs.append("%s 变化：%r → %r" % (where, old, new))


def diff_contract(old: dict, new: dict) -> list[str]:
    """返回人类可读的差异行（空列表＝一致）。"""
    diffs: list[str] = []

    old_paths = old.get("paths") or {}
    new_paths = new.get("paths") or {}
    for path in sorted(set(new_paths) - set(old_paths)):
        diffs.append("新增路径：%s（%s）" % (path, "、".join(new_paths[path])))
    for path in sorted(set(old_paths) - set(new_paths)):
        diffs.append("删除路径：%s（原 %s）" % (path, "、".join(old_paths[path])))
    for path in sorted(set(old_paths) & set(new_paths)):
        added = sorted(set(new_paths[path]) - set(old_paths[path]))
        removed = sorted(set(old_paths[path]) - set(new_paths[path]))
        if added:
            diffs.append("方法新增：%s ＋%s" % (path, "、".join(added)))
        if removed:
            diffs.append("方法删除：%s －%s" % (path, "、".join(removed)))

    old_schemas = set(old.get("schemas") or [])
    new_schemas = set(new.get("schemas") or [])
    for name in sorted(new_schemas - old_schemas):
        diffs.append("新增 schema：%s" % name)
    for name in sorted(old_schemas - new_schemas):
        diffs.append("删除 schema：%s" % name)

    if str(old.get("openapi_version", "")) != str(new.get("openapi_version", "")):
        diffs.append("OpenAPI 版本变化：%s → %s"
                     % (old.get("openapi_version"), new.get("openapi_version")))

    for key in ("schema_fields", "error_responses", "operation_contract"):
        if key not in old:
            diffs.append("快照缺少操作／字段级区块：%s（请复核后 --write 升级）" % key)
    if str(old.get("snapshot_level", "")) != "operation":
        diffs.append("快照级别不是 operation（原 %r；请 --write 升级）"
                     % old.get("snapshot_level"))

    old_fields = old.get("schema_fields") or {}
    new_fields = new.get("schema_fields") or {}
    for name in sorted(set(old_fields) & set(new_fields)):
        _diff_value(old_fields[name], new_fields[name], "schema_fields.%s" % name, diffs)

    old_err = old.get("error_responses") or {}
    new_err = new.get("error_responses") or {}
    for op in sorted(set(new_err) - set(old_err)):
        diffs.append("新增错误响应样例：%s（%s）"
                     % (op, "、".join(sorted(new_err[op]))))
    for op in sorted(set(old_err) - set(new_err)):
        diffs.append("删除错误响应样例：%s（原 %s）"
                     % (op, "、".join(sorted(old_err[op]))))
    for op in sorted(set(old_err) & set(new_err)):
        old_status, new_status = set(old_err[op]), set(new_err[op])
        for status in sorted(new_status - old_status):
            diffs.append("错误状态码新增：%s → %s" % (op, status))
        for status in sorted(old_status - new_status):
            diffs.append("错误状态码删除：%s → %s" % (op, status))
        for status in sorted(old_status & new_status):
            _diff_value(old_err[op][status], new_err[op][status],
                        "error_responses.%s[%s]" % (op, status), diffs)

    # 操作级：查询参数（名称/必填/默认/类型）、请求体 schema、security、2xx 响应。
    old_ops = old.get("operation_contract") or {}
    new_ops = new.get("operation_contract") or {}
    for op in sorted(set(new_ops) - set(old_ops)):
        diffs.append("新增操作契约：%s" % op)
    for op in sorted(set(old_ops) - set(new_ops)):
        diffs.append("删除操作契约：%s" % op)
    for op in sorted(set(old_ops) & set(new_ops)):
        _diff_value(old_ops[op], new_ops[op], "operation_contract.%s" % op, diffs)
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="后端 OpenAPI 契约快照：字段级生成与比对")
    ap.add_argument("--write", action="store_true", help="生成/覆盖 _契约快照.json")
    args = ap.parse_args(argv)

    contract = current_contract()
    prop_count = sum(len(entry.get("properties") or {})
                     for entry in contract["schema_fields"].values())
    error_entries = sum(len(v) for v in contract["error_responses"].values())
    ops = contract["operation_contract"]
    param_count = sum(len(op["parameters"]) for op in ops.values())
    body_count = sum(1 for op in ops.values() if op["request_body"] is not None)
    secured_count = sum(1 for op in ops.values() if op["security"])
    success_count = sum(1 for op in ops.values()
                        if op["success_responses"]["present"])
    print("=" * 78)
    print("OpenAPI 契约快照（字段＋操作级；%s）" % SNAPSHOT)
    print("实测：OpenAPI %s；%d 条路径／%d 个操作；schema %d 个（属性 %d 个）；"
          "错误响应样例 %d 条"
          % (contract["openapi_version"], contract["path_count"],
             contract["operation_count"], len(contract["schemas"]),
             prop_count, error_entries))
    print("      操作级：参数 %d 个；请求体 %d 个操作；鉴权声明 %d 个操作；"
          "2xx 响应 %d 个操作" % (param_count, body_count, secured_count, success_count))
    print("=" * 78)

    if args.write:
        write_snapshot(contract)
        print("已写入字段＋操作级快照：%s（%.1f KB）"
              % (SNAPSHOT, os.path.getsize(SNAPSHOT) / 1024.0))
        for name, fields in contract["schema_fields"].items():
            print("  schema %-24s 必填 %s；属性 %s"
                  % (name, fields.get("required") or [],
                     "、".join(fields.get("properties") or {}) or "（无）"))
        return 0

    old = load_snapshot()
    if old is None:
        print("FAIL：快照不存在。首次使用请执行：python 工具\\契约快照.py --write")
        return 1

    diffs = diff_contract(old, contract)
    if diffs:
        print("FAIL：当前契约与字段级快照不一致（%d 处）：" % len(diffs))
        for line in diffs:
            print("  - %s" % line)
        print("\n若变更属预期，请复核后用 `--write` 重登记快照并随代码一起提交。")
        return 1

    print("OK：契约与字段＋操作级快照一致（%d 条路径／%d 个操作／%d 个 schema／"
          "%d 个属性／%d 条错误响应样例／%d 个参数／%d 个请求体操作／"
          "%d 个鉴权操作／%d 个 2xx 操作）。"
          % (contract["path_count"], contract["operation_count"],
             len(contract["schemas"]), prop_count, error_entries,
             param_count, body_count, secured_count, success_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

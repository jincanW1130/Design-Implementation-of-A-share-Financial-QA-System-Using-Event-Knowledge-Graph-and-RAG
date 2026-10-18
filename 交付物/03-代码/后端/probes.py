# -*- coding: utf-8 -*-
"""代码\\后端\\probes.py —— `GET /api/health` 的四项就绪探针。

从 `main.py` 拆出的理由：探针只读 `config` 与依赖库，不参与路由装配；单独成模块后
`main.py` 只保留「装配」这一件事。`main.probe_mysql()` 等名字仍重导出，调用方不变。

四项探针的共同纪律：
* **只报状态，不含口令**（Neo4j 探针只打印连接串，不打印密码）；
* **单项失败不拖垮探针**：依赖不可用／文件缺失都折成 `ok=False` ＋ `info`；
* `info` 而非 `detail`：`detail` 在本项目里是「只进日志、绝不进响应体」的调试字段。
"""

from __future__ import annotations

import os

import cache
import config
import observability


def probe_mysql() -> dict:
    """MySQL 探针（委派 `db.probe()`；**只报状态，不含口令**）。"""
    try:
        import db
    except Exception as exc:                      # 依赖不可用也不该拖垮探针
        return {"ok": False, "info": "db 模块不可用：%s" % type(exc).__name__}
    info = db.probe()
    return {"ok": bool(info.get("ok")), "info": info.get("detail", "")}


def probe_neo4j() -> dict:
    """Neo4j 探针：连一次即断，连接超时 2 秒；**不打印口令**。"""
    try:
        from neo4j import GraphDatabase
    except Exception as exc:
        return {"ok": False, "info": "neo4j 驱动不可用：%s" % type(exc).__name__}
    params = config.neo4j_params()
    driver = None
    try:
        driver = GraphDatabase.driver(
            params["uri"], auth=(params["user"], params["password"] or None),
            connection_timeout=2.0)
        driver.verify_connectivity()
        return {"ok": True, "info": "%s 可连接" % params["uri"]}
    except Exception as exc:
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return {"ok": False, "info": "%s 不可连接：%s" % (params["uri"], first)}
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


def probe_vector_index() -> dict:
    """向量索引探针：向量索引三件（索引／映射／构建元信息）齐备且与数据集版本一致。

    **不做向量检索**（那是 `/api/qa` 的事），只判「索引可用」。术语一律写「向量索引」。
    """
    triple = [("索引文件", config.VECTOR_INDEX_PATH),
              ("映射文件", config.VECTOR_MAP_PATH),
              ("构建元信息", config.BUILD_META_PATH)]
    missing = [name for name, path in triple if not os.path.isfile(path)]
    if missing:
        return {"ok": False, "info": "缺文件：%s" % "、".join(missing)}
    try:
        meta = config.read_json(config.BUILD_META_PATH)
    except Exception as exc:
        return {"ok": False, "info": "构建元信息不可解析：%s" % type(exc).__name__}
    version = meta.get("dataset_version")
    if version != config.DATASET_VERSION:
        return {"ok": False, "info": "构建元信息的数据集版本 %r ≠ %r"
                % (version, config.DATASET_VERSION)}
    return {"ok": True,
            "info": "向量 %s 条，维度 %s，%s／%s"
            % (meta.get("vector_count"), meta.get("dim"),
               meta.get("index_type"), meta.get("similarity"))}


def model_config_block() -> dict:
    """生成与检索侧的**定值**是否齐备（`config.FIXED` 逐项 `require_fixed()`）。"""
    try:
        values = {name: config.require_fixed(name) for name in sorted(config.FIXED)}
    except SystemExit as exc:
        return {"ok": False, "info": str(exc).splitlines()[0]}
    return {"ok": True,
            "info": "模型 %s／Prompt %s；K=%s N=%s 预算=%s g=%s"
            % (values["model_name"], values["prompt_version"], values["K"],
               values["N"], values["context_token_budget"], values["graph_retention_share"]),
            "model_name": values["model_name"],
            "prompt_version": values["prompt_version"],
            "K": values["K"], "N": values["N"],
            "context_token_budget": values["context_token_budget"],
            "graph_retention_share": values["graph_retention_share"]}


def health_payload() -> dict:
    """`/api/health` 的响应体：四项依赖 ＋ `status` ＋ `metrics` 摘要。

    * `status` 仍只由四项依赖决定（`metrics` 是观测信息，不参与就绪判定）；
    * `metrics` 是第 4 轮新增的**进程内**指标摘要（8.2），**不新增路由**；
    * 指标快照失败时不拖垮探针：只把 `metrics.available` 置 false 并给出异常类型，
      不返回堆栈、不返回任何凭据。
    **HTTP 状态恒为 200**（服务本身活着；某一项不 ok 是依赖状态，不是接口失败）。
    """
    blocks = {"mysql": probe_mysql(), "neo4j": probe_neo4j(),
              "vector_index": probe_vector_index(), "model_config": model_config_block()}
    payload = {"status": "ok" if all(b["ok"] for b in blocks.values()) else "degraded"}
    payload.update(blocks)
    try:
        payload["metrics"] = observability.snapshot()
    except Exception as exc:                              # 观测失败不影响就绪判定
        payload["metrics"] = {"available": False, "info": type(exc).__name__}
    try:
        payload["cache"] = cache.snapshot()               # 第 6 轮：进程内缓存命中率
    except Exception as exc:                              # 缓存统计失败同样不拖垮探针
        payload["cache"] = {"available": False, "info": type(exc).__name__}
    return payload

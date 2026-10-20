# -*- coding: utf-8 -*-
"""Y 组 · 检索融合档（2026-10-20 落地）—— 被测文件：pipeline／run_query／run_answer／后端 config。

三条硬口径：

1. **不传参数＝原行为**：`pipeline.run_question()` 的默认档仍是 `vector`，同一输入两次运行的
   去耗时记录逐字节一致，且与改动前捕获的指纹完全相同；
2. **`hybrid-zscore` 走融合分支**：只在第①步替换向量候选，其余五步不变，trace 追加
   `retrieval` 字段（默认档不追加）；
3. **后端透传**：`ASHARE_RETRIEVAL_MODE`（缺省 `hybrid-zscore`）经 `config.RETRIEVAL_MODE`
   进入 `qa_service._run_chain` 的 `run_answer.py` 命令行。

全部离线：向量替身取自 `conftest.FakeSearcher`，融合实现用进程内可注入的
`hybrid_search_fn`（不建 BM25 索引、不碰真实数据集、不调模型）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import types

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402
from conftest import QUESTION  # noqa: E402

pipe = _bootstrap.load_module("检索", "pipeline.py")
cfg = _bootstrap.component_config("检索")

# **改动前**（2026-10-20 引入可选档之前）用同一合成输入捕获的默认路径指纹。
# 断言方式与当时一致：strip_timings 后按 sort_keys、紧凑分隔符序列化，取 SHA-256。
BASELINE_SHA256 = "42895aa9f7570611feb204e24a8fd8edb5050b929ba7017b8f1f8cea0f10ef49"


def _record_digest(record: dict) -> tuple:
    clean = pipe.strip_timings(record)
    text = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), text


def _run(graph_case, searcher, retrieval=None, vector_cache=None):
    switches = {"graph_depth": 2, "time_filter": True, "evidence_sort": False, "_group": "D"}
    kwargs = {} if retrieval is None else {"retrieval": retrieval}
    return pipe.run_question(
        QUESTION, switches, graph_case.graph, searcher, graph_case.chunks,
        graph_case.documents,
        n=int(cfg.require_fixed("N")), k=int(cfg.require_fixed("K")),
        budget=int(cfg.require_fixed("context_token_budget")),
        g=int(cfg.require_fixed("graph_retention_share")),
        vector_cache={} if vector_cache is None else vector_cache,
        graph_cache={}, full_pool_cache={}, **kwargs)


# ---------------------------------------------------------------------------
# Y1 默认档：不传参数＝原行为（两次运行一致 ＋ 改动前指纹）
# ---------------------------------------------------------------------------
def test_default_retrieval_is_byte_identical_and_matches_baseline(
        synthetic_graph, fake_searcher, monkeypatch):
    def _must_not_load():
        raise AssertionError("默认档不得加载融合模块")

    monkeypatch.setattr(pipe, "_load_hybrid_module", _must_not_load)

    first = _run(synthetic_graph, fake_searcher())
    second = _run(synthetic_graph, fake_searcher())
    digest_first, text_first = _record_digest(first)
    digest_second, text_second = _record_digest(second)

    assert text_first == text_second, "同一输入两次运行的默认输出必须逐字节一致"
    assert digest_first == BASELINE_SHA256, "默认路径相对改动前发生了漂移"
    assert "retrieval" not in json.loads(text_first), "默认档不得新增 trace 字段"
    assert first["evidence"] == [105, 101, 999, 104]


# ---------------------------------------------------------------------------
# Y2 融合档：走融合分支、映射与缓存键正确、其余四步契约不变
# ---------------------------------------------------------------------------
def test_hybrid_mode_uses_fusion_branch(synthetic_graph, fake_searcher, monkeypatch):
    calls = []

    def fake_hybrid_search(question, **kwargs):
        calls.append({"question": question, **kwargs})
        return [
            {"chunk_id": 105, "fusion_score": 0.90, "vector_score": 0.80, "fusion_rank": 1},
            {"chunk_id": 101, "fusion_score": 0.70, "vector_score": 0.60, "fusion_rank": 2},
            # BM25 独有命中：没有 vector_score，`similarity` 回落到融合分；vector_id 用 -1 兜底
            {"chunk_id": 999, "fusion_score": 0.50, "fusion_rank": 3},
        ]

    monkeypatch.setattr(pipe, "_HYBRID_MODULE",
                        types.SimpleNamespace(hybrid_search=fake_hybrid_search))
    searcher = fake_searcher()
    cache = {}

    default_record = _run(synthetic_graph, searcher, retrieval="vector", vector_cache=cache)
    hybrid_record = _run(synthetic_graph, searcher, retrieval="hybrid-zscore",
                         vector_cache=cache)

    assert calls, "融合档必须调用 hybrid_search"
    assert calls[0]["question"] == QUESTION["question"]
    assert calls[0]["k"] == int(cfg.require_fixed("N"))
    assert calls[0]["retrieval_k"] == int(cfg.require_fixed("N"))
    assert calls[0]["method"] == "zscore"
    assert calls[0]["alpha"] == 0.3
    assert calls[0]["expand"] is False
    assert calls[0]["vector_searcher"] is searcher

    assert hybrid_record["retrieval"] == "hybrid-zscore"
    assert "retrieval" not in default_record
    assert hybrid_record["segments"]["① 两路取候选"]["vector"]["output_candidates"] == 3
    assert hybrid_record["checks"] == {"evidence_unique": True, "candidates_unique": True,
                                       "within_budget": True, "kept_le_k": True}
    # 默认档与融合档共用同一个 vector_cache 时不得串味（缓存键不同）
    assert len(cache) == 2


def test_hybrid_candidate_mapping(synthetic_graph, fake_searcher):
    rows = pipe.collect_hybrid_vector_candidates(
        fake_searcher(), QUESTION["question"], 3, synthetic_graph.chunks,
        hybrid_search_fn=lambda question, **kwargs: [
            {"chunk_id": 999, "fusion_score": 0.5, "fusion_rank": 1},
            {"chunk_id": 105, "fusion_score": 0.9, "vector_score": 0.7, "fusion_rank": 2},
        ])
    assert [row["chunk_id"] for row in rows["rows"]] == [999, 105]
    assert [row["vector_rank"] for row in rows["rows"]] == [1, 2]
    assert rows["rows"][0]["similarity"] == 0.5          # 无向量分 → 融合分
    assert rows["rows"][1]["similarity"] == 0.7          # 有向量分 → 保留原始相似度
    assert rows["rows"][0]["vector_id"] == -1
    assert rows["rows"][0]["doc_id"] == 4
    assert rows["n"] == 3


def test_invalid_retrieval_mode_is_rejected():
    with pytest.raises(ValueError):
        pipe.check_retrieval_mode("rrf")
    with pytest.raises(ValueError):
        pipe.check_retrieval_mode(None)


def test_real_hybrid_module_loads():
    """真模块必须能按文件路径加载（2026-10-20 真链路复跑抓到 dataclass 的 sys.modules 坑）。

    该用例不走替身：只执行模块导入本身（不建 BM25 索引、不载 BGE、不联网），
    防止 `module_from_spec` 未登记 `sys.modules` 时 `@dataclass` 初始化失败。
    """
    module = pipe._load_hybrid_module()
    assert module.__name__ == "_pipeline_hybrid_retrieval"
    assert callable(module.hybrid_search)
    assert callable(module.score_fusion)


# ---------------------------------------------------------------------------
# Y3 后端：ASHARE_RETRIEVAL_MODE → config.RETRIEVAL_MODE → run_answer 命令行
# ---------------------------------------------------------------------------
def _load_backend_config_fresh(name: str):
    path = os.path.join(_bootstrap.CODE_DIR, "后端", "config.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_retrieval_mode_default_and_env_override(monkeypatch):
    monkeypatch.delenv("ASHARE_RETRIEVAL_MODE", raising=False)
    default_cfg = _load_backend_config_fresh("_test_backend_retrieval_default")
    assert default_cfg.DEFAULT_RETRIEVAL_MODE == "hybrid-zscore"
    assert default_cfg.RETRIEVAL_MODE == "hybrid-zscore"

    monkeypatch.setenv("ASHARE_RETRIEVAL_MODE", "vector")
    vector_cfg = _load_backend_config_fresh("_test_backend_retrieval_vector")
    assert vector_cfg.RETRIEVAL_MODE == "vector"

    monkeypatch.setenv("ASHARE_RETRIEVAL_MODE", "rrf")
    with pytest.raises(SystemExit):
        _load_backend_config_fresh("_test_backend_retrieval_invalid")


def test_run_chain_passes_retrieval_mode(monkeypatch, tmp_path):
    qa = _bootstrap.load_backend("services.qa_service")
    backend_cfg = _bootstrap.load_backend("config")
    captured = {}

    monkeypatch.setattr(qa, "RUN_DIR", str(tmp_path / "qa_runs"))
    monkeypatch.setattr(qa, "_cleanup_qa_runs_throttled", lambda: None)

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        raise OSError("stub: stop before spawning")

    monkeypatch.setattr(qa.subprocess, "Popen", fake_popen)
    with pytest.raises(qa.ApiError):
        qa._run_chain("测试问题", "C", "session-1", "2026-10-20T00:00:00+08:00")

    cmd = captured["cmd"]
    assert cmd[-2:] == ["--retrieval", backend_cfg.RETRIEVAL_MODE]
    assert "--question" in cmd and "测试问题" in cmd

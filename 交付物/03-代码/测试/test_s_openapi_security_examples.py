# -*- coding: utf-8 -*-
"""S 组 · OpenAPI 的后台鉴权方案与错误响应示例（第三轮 13.5）。

第三轮给 `api/admin.py` 增加了 `APIKeyHeader` 安全方案、给 `errors.error_responses()`
增加了 `example`。本组只装配应用读 `app.openapi()`，**不启动服务、不连库**：

* `components.securitySchemes.AdminToken` 是 header 型 apiKey，名字为 `X-Admin-Token`；
* 全部 `/api/admin/*` 操作声明该安全要求，普通接口不声明；
* 错误响应保留内联 `{code, message}` schema，并给出与错误码表一致的示例。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

main_mod = _bootstrap.load_backend("main")
errors_mod = _bootstrap.load_backend("errors")


@pytest.fixture(scope="module")
def spec():
    return main_mod.app.openapi()


def test_admin_token_security_scheme_declared(spec):
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    scheme = schemes.get("AdminToken")
    assert scheme is not None
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "X-Admin-Token"


def test_all_admin_operations_require_admin_token(spec):
    checked = 0
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/admin/"):
            continue
        for method, op in methods.items():
            if method not in ("get", "post", "put", "delete", "patch", "head"):
                continue
            checked += 1
            assert op.get("security") == [{"AdminToken": []}], (method, path)
    assert checked >= 12, "后台操作数异常偏少：%d" % checked


def test_public_operations_do_not_require_admin_token(spec):
    for path in ("/api/health", "/api/qa/ask", "/api/history"):
        methods = spec["paths"][path]
        for method, op in methods.items():
            if method in ("get", "post", "head"):
                assert not op.get("security"), (method, path)


def test_error_responses_have_examples(spec):
    ask = spec["paths"]["/api/qa/ask"]["post"]
    _400 = ask["responses"]["400"]
    media = _400["content"]["application/json"]
    assert media["schema"]["required"] == ["code", "message"]
    assert media["schema"]["additionalProperties"] is False
    example = media["example"]
    assert example == {"code": 1001,
                       "message": errors_mod.message_of(1001)}
    # 429/1004 是 error_responses 默认附带项，也应有示例
    assert ask["responses"]["429"]["content"]["application/json"]["example"] == {
        "code": 1004, "message": errors_mod.message_of(1004)}


def test_error_response_groups_match_status_table(spec):
    ask = spec["paths"]["/api/qa/ask"]["post"]
    for status, payload in ask["responses"].items():
        if status == "200":
            continue
        assert "content" in payload and "application/json" in payload["content"], status

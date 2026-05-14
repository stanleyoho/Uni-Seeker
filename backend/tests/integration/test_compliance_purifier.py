"""Plan 4.5 T9 — CompliancePurifier response middleware."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.compliance_purifier import (
    CompliancePurifierMiddleware,
    PURIFIER_REPLACEMENTS,
)


def _make_app(payload: dict | str, media_type: str = "application/json") -> FastAPI:
    """Build a tiny app that echoes a fixed payload under the purifier."""
    from fastapi.responses import JSONResponse, PlainTextResponse, Response

    app = FastAPI()
    app.add_middleware(CompliancePurifierMiddleware)

    @app.get("/")
    async def root():
        if media_type == "application/json":
            return JSONResponse(payload)
        if media_type.startswith("text/"):
            return PlainTextResponse(payload, media_type=media_type)
        return Response(payload, media_type=media_type)

    return app


async def _get(app: FastAPI, path: str = "/") -> tuple[int, str, dict[str, str]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(path)
        return r.status_code, r.text, dict(r.headers)


@pytest.mark.asyncio
async def test_rewrites_buy_recommendation_in_json():
    app = _make_app({"msg": "建議買入 2330"})
    status, text, _ = await _get(app)
    assert status == 200
    assert "建議買入" not in text
    assert "模型分析強度為 85%" in text


@pytest.mark.asyncio
async def test_rewrites_multiple_phrases_in_one_body():
    app = _make_app({"a": "買入點", "b": "跟隨法人方向", "c": "必賺", "d": "穩定獲利"})
    _, text, _ = await _get(app)
    assert "買入點" not in text and "信號觸發區" in text
    assert "跟隨法人方向" not in text and "法人部位特徵符合" in text
    # "必賺" 與 "穩定獲利" 都映射到 "歷史回測統計結果"
    assert "必賺" not in text and "穩定獲利" not in text
    assert text.count("歷史回測統計結果") >= 2


@pytest.mark.asyncio
async def test_pass_through_for_non_textual_content():
    """Binary / unknown content type bodies must NOT be touched."""
    # application/octet-stream 含「建議買入」字串 → 必須保留
    app = _make_app("建議買入".encode("utf-8"), media_type="application/octet-stream")
    _, text, _ = await _get(app)
    assert "建議買入" in text


@pytest.mark.asyncio
async def test_text_plain_is_rewritten():
    app = _make_app("這檔股票建議買入", media_type="text/plain; charset=utf-8")
    _, text, _ = await _get(app)
    assert "建議買入" not in text


@pytest.mark.asyncio
async def test_no_match_leaves_body_unchanged():
    app = _make_app({"clean": "技術面背離"})
    _, text, _ = await _get(app)
    assert "技術面背離" in text


@pytest.mark.asyncio
async def test_content_length_header_consistent_with_body():
    """If we rewrite, content-length must either be absent or match new body length."""
    app = _make_app({"msg": "建議買入測試"})
    _, text, headers = await _get(app)
    cl = headers.get("content-length")
    if cl is not None:
        assert int(cl) == len(text.encode("utf-8"))


@pytest.mark.asyncio
async def test_replacement_table_exposed_for_audit():
    """The replacement table must be a non-empty tuple of (pattern, replacement)
    so audit reviewers can inspect what's being rewritten."""
    assert len(PURIFIER_REPLACEMENTS) >= 4
    for pat, repl in PURIFIER_REPLACEMENTS:
        assert hasattr(pat, "sub")  # compiled regex
        assert isinstance(repl, str)

"""CompliancePurifier — outgoing response body sanitizer.

Plan 4.5 T9. Regex-replaces marketing language that could be construed as
investment advice (a Taiwan SFA/投顧法 risk) with neutral, statistical
phrasing. Applied at the outermost middleware layer so it sees fully
serialized JSON / text bodies.

Pass-through rules:
    - Only ``application/json`` and ``text/*`` bodies are rewritten.
    - Binary content types are returned untouched.

Header rules:
    - ``Content-Length`` is rebuilt from the rewritten body (the upstream
      value would be wrong after substitution and trip strict clients).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# (compiled pattern, replacement) tuples. Order does not matter (no overlap).
PURIFIER_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"建議買入"), "模型分析強度為 85%"),
    (re.compile(r"買入點"), "信號觸發區"),
    (re.compile(r"跟隨法人方向"), "法人部位特徵符合"),
    (re.compile(r"必賺|穩定獲利"), "歷史回測統計結果"),
)


def _purify(text: str) -> str:
    for pat, repl in PURIFIER_REPLACEMENTS:
        text = pat.sub(repl, text)
    return text


def _is_purifiable(content_type: str) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    return ct == "application/json" or ct.startswith("text/")


class CompliancePurifierMiddleware(BaseHTTPMiddleware):
    """Rewrite outgoing JSON / text responses through PURIFIER_REPLACEMENTS."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if not _is_purifiable(response.headers.get("content-type", "")):
            return response

        chunks: list[bytes] = []
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            chunks.append(chunk)
        body = b"".join(chunks).decode("utf-8", errors="replace")
        new_body = _purify(body)

        # Rebuild headers without the now-stale Content-Length.
        new_headers = [(k, v) for k, v in response.headers.items() if k.lower() != "content-length"]
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=dict(new_headers),
            media_type=response.media_type,
        )

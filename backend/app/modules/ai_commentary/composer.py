"""Deterministic template engine for per-stock daily AI commentary.

Design notes
------------
- Pure function: takes a `CommentaryContext` dataclass, returns a
  `(narrative_str, confidence_float, sources_list)` tuple.
- No I/O. All DB / Redis / indicator lookups happen in the API layer
  (see `app/api/v1/ai_commentary.py`) and are fed in as plain numbers.
  This keeps the composer trivially unit-testable.
- Output length target: 100-300 Traditional Chinese characters
  (roughly 4-7 sentences). We measure with `len(text)` post-compose
  and append a fallback "請參閱完整指標分析" line if we ended up
  too short (e.g. early-series with no MA20).
- Confidence: starts at 1.0 and gets shaved when individual signals
  are missing (no MA20 because the price series is too short, no
  RSI because it wasn't computed, no sector context, etc).

LLM upgrade hook
----------------
`compose_commentary` returns a deterministic narrative today. A future
LLM step can be wired by:
  1. building the same `CommentaryContext`
  2. rendering the deterministic narrative as a "facts" prompt
  3. asking Claude to rewrite for tone / variety
  4. caching the LLM result alongside the deterministic one
The TODO marker below shows where to slot that in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type


@dataclass
class CommentarySource:
    """A factual source used in the narrative — surfaces for transparency."""

    kind: str  # e.g. "price", "rsi", "macd", "bb", "sector", "patterns"
    detail: str  # human-readable summary, e.g. "RSI=72.4"


@dataclass
class CommentaryContext:
    """All inputs the deterministic template engine needs.

    Designed so the API layer can fill what it has and leave the rest
    as None — the composer degrades gracefully when signals are missing.
    """

    symbol: str
    name: str | None = None
    target_date: date_type | None = None

    # --- Price action ---
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    volume: int | None = None
    avg_volume_20: float | None = None  # 20-day average volume
    ma20: float | None = None  # 20-day moving average of close

    # --- Indicators (latest values) ---
    rsi: float | None = None  # 14-period RSI
    macd: float | None = None  # MACD line
    macd_signal: float | None = None  # MACD signal line
    macd_histogram: float | None = None  # MACD histogram
    bb_upper: float | None = None  # Bollinger upper band
    bb_lower: float | None = None  # Bollinger lower band
    bb_middle: float | None = None  # Bollinger middle band (= MA20 typically)

    # --- Sector context ---
    industry: str | None = None
    sector_is_hot_top3: bool = False
    sector_rank: int | None = None  # 1, 2, 3 if in top 3
    sector_avg_change_pct: float | None = None

    # --- Candlestick patterns (K8 / PR #114) ---
    # When patterns module lands, fill in detected pattern names.
    # For v1, leaving this empty triggers the "patterns to be added" note.
    patterns: list[str] = field(default_factory=list)
    patterns_module_available: bool = False


# ---------------------------------------------------------------------------
# Sentence builders — each returns (sentence | None, source | None, weight)
# weight contributes to the confidence aggregate.
# ---------------------------------------------------------------------------


def _price_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if ctx.close is None or ctx.prev_close is None:
        return None, None, 0.0

    change = ctx.close - ctx.prev_close
    pct = (change / ctx.prev_close * 100) if ctx.prev_close else 0.0
    direction = "上漲" if change >= 0 else "下跌"
    sign = "+" if change >= 0 else ""

    parts = [f"{ctx.symbol} 今日收盤 {ctx.close:.2f}，{direction} {abs(change):.2f} ({sign}{pct:.2f}%)"]

    if ctx.high is not None and ctx.low is not None:
        parts.append(f"，盤中區間 {ctx.low:.2f}–{ctx.high:.2f}")

    if ctx.volume is not None and ctx.avg_volume_20 is not None and ctx.avg_volume_20 > 0:
        vol_ratio = ctx.volume / ctx.avg_volume_20
        if vol_ratio >= 1.5:
            parts.append(f"，成交量約為 20 日均量的 {vol_ratio:.1f} 倍，量能明顯放大")
        elif vol_ratio <= 0.7:
            parts.append(f"，成交量僅 20 日均量的 {vol_ratio:.1f} 倍，量能偏縮")
        else:
            parts.append("，量能接近 20 日均量水準")

    source = CommentarySource(kind="price", detail=f"close={ctx.close:.2f}, prev={ctx.prev_close:.2f}")
    return "".join(parts) + "。", source, 1.0


def _ma20_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if ctx.close is None or ctx.ma20 is None:
        return None, None, 0.0

    diff_pct = (ctx.close - ctx.ma20) / ctx.ma20 * 100
    if diff_pct >= 3:
        position = f"明顯站上 20 日均線（高出 {diff_pct:.1f}%）"
    elif diff_pct >= 0:
        position = f"位於 20 日均線上方（+{diff_pct:.1f}%）"
    elif diff_pct >= -3:
        position = f"略低於 20 日均線（{diff_pct:.1f}%）"
    else:
        position = f"明顯跌破 20 日均線（{diff_pct:.1f}%）"

    source = CommentarySource(kind="ma20", detail=f"ma20={ctx.ma20:.2f}, diff={diff_pct:.2f}%")
    return f"股價{position}。", source, 0.8


def _rsi_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if ctx.rsi is None:
        return None, None, 0.0
    if ctx.rsi >= 70:
        state = "超買區間，技術面短線過熱"
    elif ctx.rsi >= 55:
        state = "偏強區間，多方仍具動能"
    elif ctx.rsi >= 45:
        state = "中性區間，多空拉鋸"
    elif ctx.rsi >= 30:
        state = "偏弱區間，賣壓尚未停歇"
    else:
        state = "超賣區間，短線可留意反彈機會"
    return f"RSI 為 {ctx.rsi:.1f}，處於{state}。", CommentarySource(kind="rsi", detail=f"RSI={ctx.rsi:.1f}"), 0.8


def _macd_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if ctx.macd is None or ctx.macd_signal is None:
        return None, None, 0.0
    histogram = ctx.macd_histogram if ctx.macd_histogram is not None else ctx.macd - ctx.macd_signal
    if ctx.macd > ctx.macd_signal and histogram > 0:
        msg = "MACD 位於訊號線上方，柱狀體為正，動能偏多"
    elif ctx.macd < ctx.macd_signal and histogram < 0:
        msg = "MACD 位於訊號線下方，柱狀體為負，動能偏空"
    else:
        msg = "MACD 與訊號線糾結，動能尚未明朗"
    return msg + "。", CommentarySource(kind="macd", detail=f"MACD={ctx.macd:.3f}, signal={ctx.macd_signal:.3f}"), 0.7


def _bollinger_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if ctx.close is None or ctx.bb_upper is None or ctx.bb_lower is None:
        return None, None, 0.0
    if ctx.close >= ctx.bb_upper:
        msg = "股價已觸及布林通道上軌，短線過熱風險升高"
    elif ctx.close <= ctx.bb_lower:
        msg = "股價已觸及布林通道下軌，短線跌深可能"
    elif ctx.bb_middle is not None:
        if ctx.close > ctx.bb_middle:
            msg = "股價位於布林通道上半部，趨勢偏多"
        else:
            msg = "股價位於布林通道下半部，趨勢偏弱"
    else:
        msg = "股價位於布林通道內部"
    return msg + "。", CommentarySource(kind="bb", detail=f"close={ctx.close:.2f} in [{ctx.bb_lower:.2f}, {ctx.bb_upper:.2f}]"), 0.6


def _sector_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if not ctx.industry:
        return None, None, 0.0
    if not ctx.sector_is_hot_top3:
        return None, None, 0.0

    rank_text = f"第 {ctx.sector_rank} 名" if ctx.sector_rank else "前段班"
    pct_text = ""
    if ctx.sector_avg_change_pct is not None:
        sign = "+" if ctx.sector_avg_change_pct >= 0 else ""
        pct_text = f"（平均 {sign}{ctx.sector_avg_change_pct:.2f}%）"
    return (
        f"所屬產業「{ctx.industry}」今日落在熱門族群{rank_text}{pct_text}，類股資金動能值得留意。",
        CommentarySource(kind="sector", detail=f"{ctx.industry} rank={ctx.sector_rank}"),
        0.6,
    )


def _patterns_sentence(ctx: CommentaryContext) -> tuple[str | None, CommentarySource | None, float]:
    if not ctx.patterns_module_available:
        return (
            "K 線型態判讀模組即將上線，後續將補上型態訊號。",
            CommentarySource(kind="patterns", detail="module-pending"),
            0.3,
        )
    if not ctx.patterns:
        return None, None, 0.0
    joined = "、".join(ctx.patterns[:3])
    return (
        f"近日 K 線出現 {joined} 等型態訊號，建議結合量價確認。",
        CommentarySource(kind="patterns", detail=joined),
        0.6,
    )


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


# Core signal builders + their max attainable weight (when the signal
# has full inputs). The weight here defines how complete the picture is
# when this signal *is* included — and is also the share it would have
# contributed had it been available. Total confidence denominator is
# the sum of these weights, regardless of which signals had inputs;
# that way a stock with only price action does NOT score 1.0, which
# matches Stanley's "sparse data should surface a confidence hint" UX.
#
# The patterns notice is appended *after* these run, and only when at
# least one real signal contributed.
_CORE_BUILDERS: tuple[tuple[object, float], ...] = (
    (_price_sentence, 1.0),
    (_ma20_sentence, 0.8),
    (_rsi_sentence, 0.8),
    (_macd_sentence, 0.7),
    (_bollinger_sentence, 0.6),
    (_sector_sentence, 0.6),
)
_MAX_TOTAL_WEIGHT = sum(w for _, w in _CORE_BUILDERS)


def compose_commentary(ctx: CommentaryContext) -> tuple[str, float, list[CommentarySource]]:
    """Build a deterministic Traditional-Chinese narrative from numeric facts.

    Returns:
        (narrative, confidence, sources)

    Confidence is the fraction of signals that contributed a sentence,
    weighted by each signal's relative importance. 1.0 = full picture
    available; <0.5 = sparse data, surface a caveat in the UI.
    """
    sentences: list[str] = []
    sources: list[CommentarySource] = []
    used_weight = 0.0

    for builder, _max_weight in _CORE_BUILDERS:
        sentence, source, weight = builder(ctx)  # type: ignore[operator]
        if sentence:
            sentences.append(sentence)
            used_weight += weight
            if source:
                sources.append(source)

    # If no core signal produced anything, the caller passed an empty /
    # near-empty context — return a stub and skip the patterns notice.
    if not sentences:
        return (
            f"{ctx.symbol} 今日資料不足，無法產生 AI 解讀。",
            0.0,
            [],
        )

    # Patterns notice is purely informational and only meaningful when
    # we already produced real signal sentences. It does NOT change the
    # confidence numerator (real signals do).
    patterns_sentence, patterns_source, _ = _patterns_sentence(ctx)
    if patterns_sentence:
        sentences.append(patterns_sentence)
        if patterns_source:
            sources.append(patterns_source)

    narrative = "".join(sentences)

    # If too short (< 80 字), append a soft pointer.
    if len(narrative) < 80:
        narrative += "更完整的指標細節請切換至分析頁面查看。"

    confidence = round(used_weight / _MAX_TOTAL_WEIGHT, 3) if _MAX_TOTAL_WEIGHT > 0 else 0.0

    # TODO(stanley): LLM upgrade hook. When ready, replace the body of
    # this branch with a Claude call that takes `narrative` as facts
    # and rewrites for tone. Keep the deterministic version as fallback
    # when the LLM call fails or budget is exhausted.
    # if settings.ai_commentary_use_llm:
    #     llm_result = await rewrite_with_claude(narrative, ctx)
    #     if llm_result: narrative = llm_result

    return narrative, confidence, sources

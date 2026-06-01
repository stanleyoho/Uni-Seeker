"""Unit tests for the AI commentary template engine.

The composer is pure — it takes a `CommentaryContext` and returns
`(narrative, confidence, sources)`. These tests assert:
  - all signals present → confidence == 1.0 and narrative contains
    the expected Chinese phrases for each branch
  - missing signals → narrative still composes, confidence shrinks
  - empty context → safe stub output
  - RSI / MACD / Bollinger branches cover each band
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.ai_commentary import CommentaryContext, compose_commentary


def _full_context() -> CommentaryContext:
    return CommentaryContext(
        symbol="2330.TW",
        name="台積電",
        target_date=date(2026, 6, 2),
        open=900.0,
        high=910.0,
        low=895.0,
        close=905.0,
        prev_close=890.0,
        volume=40_000_000,
        avg_volume_20=25_000_000,
        ma20=870.0,
        rsi=72.4,
        macd=3.21,
        macd_signal=2.15,
        macd_histogram=1.06,
        bb_upper=912.0,
        bb_lower=830.0,
        bb_middle=871.0,
        industry="半導體業",
        sector_is_hot_top3=True,
        sector_rank=1,
        sector_avg_change_pct=2.45,
        patterns_module_available=False,
        patterns=[],
    )


def test_full_context_produces_rich_narrative() -> None:
    ctx = _full_context()
    narrative, confidence, sources = compose_commentary(ctx)

    # Length budget per brief: 100-300 字.
    assert 80 <= len(narrative) <= 400, f"got {len(narrative)} chars: {narrative}"

    # Price branch
    assert "2330.TW" in narrative
    assert "上漲" in narrative
    # Volume ratio = 1.6x → "明顯放大"
    assert "放大" in narrative

    # MA20 branch — close 905 vs MA 870 → +4% → "明顯站上"
    assert "明顯站上 20 日均線" in narrative

    # RSI 72.4 → 超買
    assert "超買區間" in narrative

    # MACD > signal, hist > 0 → 動能偏多
    assert "動能偏多" in narrative

    # Bollinger close 905 < upper 912, > middle → 上半部
    assert "布林通道" in narrative

    # Sector top-3
    assert "半導體業" in narrative
    assert "熱門族群" in narrative

    # Patterns module pending → notice surfaced
    assert "K 線型態" in narrative

    # All branches contributed → confidence 1.0
    assert confidence == pytest.approx(1.0, abs=0.01)
    # Sources include each kind
    kinds = {s.kind for s in sources}
    assert {"price", "ma20", "rsi", "macd", "bb", "sector", "patterns"}.issubset(kinds)


def test_minimal_context_still_produces_narrative() -> None:
    """No indicators, no sector — only price action."""
    ctx = CommentaryContext(
        symbol="0050.TW",
        close=180.0,
        prev_close=178.0,
        high=181.0,
        low=177.5,
        volume=10_000_000,
    )
    narrative, confidence, sources = compose_commentary(ctx)
    assert "0050.TW" in narrative
    assert "上漲" in narrative
    # Confidence < 1.0 since most signals absent
    assert confidence < 0.5
    assert any(s.kind == "price" for s in sources)


def test_empty_context_returns_stub() -> None:
    ctx = CommentaryContext(symbol="9999.TW")
    narrative, confidence, sources = compose_commentary(ctx)
    assert "資料不足" in narrative
    assert confidence == 0.0
    assert sources == []


def test_rsi_bands() -> None:
    base = CommentaryContext(symbol="X", close=100.0, prev_close=99.0)

    def variant(rsi_val: float) -> str:
        ctx = CommentaryContext(**{**base.__dict__, "rsi": rsi_val})
        narrative, _, _ = compose_commentary(ctx)
        return narrative

    assert "超買" in variant(75.0)
    assert "偏強" in variant(60.0)
    assert "中性" in variant(50.0)
    assert "偏弱" in variant(40.0)
    assert "超賣" in variant(20.0)


def test_macd_directions() -> None:
    base = CommentaryContext(symbol="X", close=100.0, prev_close=99.0)
    bull = CommentaryContext(
        **{**base.__dict__, "macd": 2.0, "macd_signal": 1.0, "macd_histogram": 1.0}
    )
    bear = CommentaryContext(
        **{**base.__dict__, "macd": -1.0, "macd_signal": 0.5, "macd_histogram": -1.5}
    )
    mixed = CommentaryContext(
        **{**base.__dict__, "macd": 1.0, "macd_signal": 1.0, "macd_histogram": 0.0}
    )

    assert "動能偏多" in compose_commentary(bull)[0]
    assert "動能偏空" in compose_commentary(bear)[0]
    assert "尚未明朗" in compose_commentary(mixed)[0]


def test_bollinger_bands() -> None:
    base = CommentaryContext(symbol="X", close=100.0, prev_close=99.0)

    upper_touch = CommentaryContext(
        **{**base.__dict__, "close": 120.0, "bb_upper": 120.0, "bb_lower": 80.0, "bb_middle": 100.0}
    )
    lower_touch = CommentaryContext(
        **{**base.__dict__, "close": 80.0, "bb_upper": 120.0, "bb_lower": 80.0, "bb_middle": 100.0}
    )
    upper_half = CommentaryContext(
        **{**base.__dict__, "close": 110.0, "bb_upper": 120.0, "bb_lower": 80.0, "bb_middle": 100.0}
    )
    lower_half = CommentaryContext(
        **{**base.__dict__, "close": 90.0, "bb_upper": 120.0, "bb_lower": 80.0, "bb_middle": 100.0}
    )

    assert "過熱風險" in compose_commentary(upper_touch)[0]
    assert "跌深可能" in compose_commentary(lower_touch)[0]
    assert "上半部" in compose_commentary(upper_half)[0]
    assert "下半部" in compose_commentary(lower_half)[0]


def test_sector_only_when_top3() -> None:
    base = CommentaryContext(symbol="2330.TW", close=900.0, prev_close=890.0, industry="半導體業")
    not_hot = CommentaryContext(**{**base.__dict__, "sector_is_hot_top3": False})
    is_hot = CommentaryContext(
        **{
            **base.__dict__,
            "sector_is_hot_top3": True,
            "sector_rank": 2,
            "sector_avg_change_pct": 1.85,
        }
    )
    assert "熱門族群" not in compose_commentary(not_hot)[0]
    hot_narrative, _, _ = compose_commentary(is_hot)
    assert "熱門族群" in hot_narrative
    assert "第 2 名" in hot_narrative


def test_volume_ratio_branches() -> None:
    base = {
        "symbol": "X",
        "close": 100.0,
        "prev_close": 99.0,
        "high": 101.0,
        "low": 98.0,
    }
    surge = CommentaryContext(**base, volume=30_000_000, avg_volume_20=15_000_000)
    quiet = CommentaryContext(**base, volume=5_000_000, avg_volume_20=15_000_000)
    normal = CommentaryContext(**base, volume=15_000_000, avg_volume_20=15_000_000)

    assert "放大" in compose_commentary(surge)[0]
    assert "偏縮" in compose_commentary(quiet)[0]
    assert "接近 20 日均量" in compose_commentary(normal)[0]


def test_short_narrative_gets_fallback_suffix() -> None:
    """When < 80 字, a soft pointer line should be appended."""
    ctx = CommentaryContext(symbol="X", close=10.0, prev_close=9.9, volume=100)
    narrative, _, _ = compose_commentary(ctx)
    if len(narrative.replace("更完整的指標細節請切換至分析頁面查看。", "")) < 80:
        assert "更完整的指標細節" in narrative

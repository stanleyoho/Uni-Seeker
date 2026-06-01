"""AI commentary module: per-stock daily narrative generation.

v1 ships a deterministic template engine that fills pre-written
Chinese sentence templates with numeric facts (price action vs MA20,
RSI / MACD / Bollinger state, hot-sector context, candlestick pattern
hints). NO LLM call — fast, no API cost, predictable, testable.

A future LLM upgrade path is sketched in `composer.compose_commentary`
(see TODO marker). The template engine produces a 100-300 字 paragraph
which the LLM step could later post-edit for tone.
"""

from app.modules.ai_commentary.composer import (
    CommentaryContext,
    CommentarySource,
    compose_commentary,
)

__all__ = [
    "CommentaryContext",
    "CommentarySource",
    "compose_commentary",
]

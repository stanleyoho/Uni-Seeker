"""Broker-specific CSV import adapters — Round 10 Phase 4+ hook.

Public surface:

    BrokerParser   — Protocol every adapter implements
    ParsedRow      — normalized row dataclass
    DEFAULT_PARSERS — ordered registry used for auto-detect / dispatch
    get_parser(key) — lookup by stable wire key
    iter_parsers() — iteration helper used by /imports/brokers
    detect_parser(content) — auto-detection helper

The registry order matters: auto-detect runs `can_handle()` in this
order and the first hit wins. We list broker-specific parsers BEFORE
`generic` so a real broker file is never mis-classified as generic.
"""

from __future__ import annotations

from typing import Iterator

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_DIVIDEND,
    ACTION_SELL,
    ACTION_SPLIT,
    BrokerParser,
    ParsedRow,
)
from app.modules.portfolio.broker_parsers.fidelity import FidelityParser
from app.modules.portfolio.broker_parsers.fubon import FubonParser
from app.modules.portfolio.broker_parsers.generic import GenericCsvParser
from app.modules.portfolio.broker_parsers.interactive_brokers import (
    InteractiveBrokersParser,
)
from app.modules.portfolio.broker_parsers.schwab import SchwabParser
from app.modules.portfolio.broker_parsers.yuanta import YuantaParser

# Auto-detect order. The first parser whose `can_handle()` returns True
# wins. Broker-specific adapters come first so a real broker export is
# never silently misread as generic. `generic` is always last so it
# acts as the implicit fallback for the canonical Uni-Seeker template.
DEFAULT_PARSER_CLASSES: tuple[type[BrokerParser], ...] = (
    InteractiveBrokersParser,
    YuantaParser,
    FubonParser,
    SchwabParser,
    FidelityParser,
    GenericCsvParser,
)


def build_default_parsers() -> dict[str, BrokerParser]:
    """Instantiate the default registry — broker_key → parser instance.

    Parsers are stateless so we keep one shared instance per process.
    The service layer accepts an override mapping for tests.
    """
    return {cls.BROKER_KEY: cls() for cls in DEFAULT_PARSER_CLASSES}


_DEFAULT_REGISTRY = build_default_parsers()


def get_parser(broker_key: str) -> BrokerParser | None:
    """Return the parser registered under `broker_key`, or None."""
    return _DEFAULT_REGISTRY.get(broker_key)


def iter_parsers() -> Iterator[BrokerParser]:
    """Iterate parsers in the canonical auto-detect order."""
    yield from _DEFAULT_REGISTRY.values()


def detect_parser(csv_content: str) -> BrokerParser:
    """Pick the right parser for a CSV — auto-detect, with generic fallback.

    Walks the registry in declaration order; first parser whose
    `can_handle()` returns True wins. Falls back to GenericCsvParser
    when nothing matches (the parser itself will then 422 if the
    header is genuinely malformed).
    """
    for parser in iter_parsers():
        if parser is _DEFAULT_REGISTRY["generic"]:
            continue
        if parser.can_handle(csv_content):
            return parser
    return _DEFAULT_REGISTRY["generic"]


__all__ = [
    "ACTION_BUY",
    "ACTION_DIVIDEND",
    "ACTION_SELL",
    "ACTION_SPLIT",
    "DEFAULT_PARSER_CLASSES",
    "BrokerParser",
    "FidelityParser",
    "FubonParser",
    "GenericCsvParser",
    "InteractiveBrokersParser",
    "ParsedRow",
    "SchwabParser",
    "YuantaParser",
    "build_default_parsers",
    "detect_parser",
    "get_parser",
    "iter_parsers",
]

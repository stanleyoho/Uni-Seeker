"""Provider registry / resolver for market-data sources.

The registry holds an ordered list of :class:`MarketDataProvider`
instances and resolves the right one for a symbol via each provider's
``supports`` capability check. Call sites depend on this resolver instead
of importing concrete sources:

    registry = build_default_registry(client=client)
    provider = registry.for_symbol("2330.TW")
    bars = await provider.get_daily_ohlcv("2330.TW", start, end)

Resolution is *first-match-wins* over the registration order, so order
encodes preference. The default registry registers TWSE/TPEX snapshot
adapters before the FinMind adapter so an explicitly board-suffixed TW
symbol uses its native board snapshot, while a *bare* TW code (which the
snapshot adapters abstain from) falls through to FinMind.
"""

from __future__ import annotations

import httpx

from app.services.market_data.adapters import (
    FinMindMarketDataAdapter,
    TPEXMarketDataAdapter,
    TWSEMarketDataAdapter,
    YFinanceMarketDataAdapter,
)
from app.services.market_data.base import MarketDataProvider


class NoProviderError(LookupError):
    """Raised when no registered provider supports a symbol."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"No market-data provider supports symbol {symbol!r}")


class MarketDataRegistry:
    """Ordered collection of providers with capability-based resolution."""

    def __init__(self, providers: list[MarketDataProvider] | None = None) -> None:
        self._providers: list[MarketDataProvider] = list(providers or [])

    def register(self, provider: MarketDataProvider) -> None:
        """Append a provider; later registrations have lower priority."""
        self._providers.append(provider)

    @property
    def providers(self) -> list[MarketDataProvider]:
        """The registered providers, in resolution order (read-only copy)."""
        return list(self._providers)

    def resolve(self, symbol: str) -> MarketDataProvider | None:
        """Return the first provider that ``supports(symbol)``, or ``None``."""
        for provider in self._providers:
            if provider.supports(symbol):
                return provider
        return None

    def for_symbol(self, symbol: str) -> MarketDataProvider:
        """Like :meth:`resolve` but raises :class:`NoProviderError` if none.

        This is the primary call-site entrypoint: ``registry.for_symbol(
        sym).get_daily_ohlcv(...)``.
        """
        provider = self.resolve(symbol)
        if provider is None:
            raise NoProviderError(symbol)
        return provider


def build_default_registry(
    *,
    client: httpx.AsyncClient | None = None,
    include_finmind: bool = True,
) -> MarketDataRegistry:
    """Build the standard registry.

    Order (preference):

    1. ``TWSEMarketDataAdapter``  — claims ``*.TW`` symbols
    2. ``TPEXMarketDataAdapter``  — claims ``*.TWO`` symbols
    3. ``FinMindMarketDataAdapter`` — claims bare TW codes + any TW symbol
    4. ``YFinanceMarketDataAdapter`` — claims everything else (US)

    Parameters
    ----------
    client : httpx.AsyncClient | None
        Required to construct the TWSE/TPEX snapshot adapters. When
        ``None``, only the FinMind + yfinance adapters are registered
        (useful where a TW snapshot is not needed).
    include_finmind : bool
        Allow callers to opt out of the FinMind adapter (e.g. when no
        token is configured).
    """
    providers: list[MarketDataProvider] = []
    if client is not None:
        providers.append(TWSEMarketDataAdapter(client=client))
        providers.append(TPEXMarketDataAdapter(client=client))
    if include_finmind:
        providers.append(FinMindMarketDataAdapter())
    providers.append(YFinanceMarketDataAdapter())
    return MarketDataRegistry(providers)

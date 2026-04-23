from app.cache import make_cache_key


def test_cache_key_deterministic() -> None:
    key1 = make_cache_key("indicator", "2330.TW", "RSI", {"period": 14})
    key2 = make_cache_key("indicator", "2330.TW", "RSI", {"period": 14})
    assert key1 == key2


def test_cache_key_different_params() -> None:
    key1 = make_cache_key("indicator", "2330.TW", "RSI", {"period": 14})
    key2 = make_cache_key("indicator", "2330.TW", "RSI", {"period": 7})
    assert key1 != key2


def test_cache_key_prefix() -> None:
    key = make_cache_key("indicator", "AAPL")
    assert key.startswith("uni:indicator:")


def test_cache_key_different_prefix() -> None:
    key1 = make_cache_key("indicator", "AAPL")
    key2 = make_cache_key("price", "AAPL")
    assert key1 != key2

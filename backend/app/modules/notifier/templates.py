from typing import Any


def format_price_alert(symbol: str, name: str, price: float, condition: str) -> str:
    return f"<b>[到價通知]</b> {symbol} {name}\n價格: ${price}\n條件: {condition}"


def format_screener_hit(strategy: str, symbol: str, name: str, detail: str) -> str:
    return f"  {strategy}: {symbol} {name} ({detail})"


def format_post_market_summary(
    market: str,
    date: str,
    holdings: list[dict[str, Any]],
    screener_hits: list[dict[str, Any]],
) -> str:
    lines = [f"<b>[盤後總結]</b> {date} {market}", ""]
    if holdings:
        lines.append("<b>持股表現：</b>")
        for h in holdings:
            sign = "+" if h["change_pct"] >= 0 else ""
            lines.append(f"  {h['symbol']} {h['name']}  ${h['price']} ({sign}{h['change_pct']}%)")
        lines.append("")
    if screener_hits:
        lines.append("<b>今日篩選命中：</b>")
        for hit in screener_hits:
            lines.append(
                format_screener_hit(hit["strategy"], hit["symbol"], hit["name"], hit["detail"]),
            )
    return "\n".join(lines)

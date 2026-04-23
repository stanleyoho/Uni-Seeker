from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarginData:
    symbol: str
    name: str
    date: date
    # 融資 (margin purchase)
    margin_buy: int
    margin_sell: int
    margin_cash_repay: int
    margin_balance_prev: int
    margin_balance: int
    margin_limit: int
    # 融券 (short sale)
    short_buy: int
    short_sell: int
    short_cash_repay: int
    short_balance_prev: int
    short_balance: int
    short_limit: int
    # 資券互抵
    offset: int

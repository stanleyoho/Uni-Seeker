import enum


class Market(str, enum.Enum):
    TW_TWSE = "TW_TWSE"
    TW_TPEX = "TW_TPEX"
    US_NYSE = "US_NYSE"
    US_NASDAQ = "US_NASDAQ"

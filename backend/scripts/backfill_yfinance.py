"""Backfill historical stock prices via yfinance.

Usage:
    uv run python scripts/backfill_yfinance.py [--symbols 2330,2317,2454] [--start 2007-01-01]

yfinance supports Taiwan stocks with .TW suffix and has data back to ~2000.
No API rate limits like FinMind.
"""
import asyncio
import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

# Top 50 Taiwan stocks by market cap
TOP_STOCKS = [
    "2330", "2317", "2454", "2308", "2881", "2882", "2891", "2303", "1301", "1303",
    "2886", "2884", "3711", "2412", "1216", "2002", "5880", "2885", "3008", "2357",
    "2382", "1101", "2892", "5876", "2207", "3045", "2395", "6505", "1326", "2912",
    "4904", "2327", "9910", "3034", "2379", "6669", "2345", "4938", "8046", "3231",
    "2301", "2105", "1590", "6415", "2474", "5871", "2880", "6488", "3037", "2603",
]

async def backfill_stock(symbol_no_suffix: str, start_date: str):
    """Download and insert historical prices for one stock."""
    import yfinance as yf

    ticker = f"{symbol_no_suffix}.TW"
    print(f"  Fetching {ticker} from {start_date}...", end=" ", flush=True)

    try:
        df = yf.download(ticker, start=start_date, progress=False, auto_adjust=True)
    except Exception as e:
        print(f"FAILED: {e}")
        return 0

    if df.empty:
        print("NO DATA")
        return 0

    # Flatten multi-level columns if present
    if hasattr(df.columns, 'levels'):
        df.columns = df.columns.get_level_values(0)

    from app.database import async_session
    from app.models.stock import Stock
    from app.models.price import StockPrice
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with async_session() as db:
        # Get stock_id
        result = await db.execute(select(Stock).where(Stock.symbol == f"{symbol_no_suffix}.TW"))
        stock = result.scalar_one_or_none()
        if stock is None:
            print(f"NOT IN DB")
            return 0

        count = 0
        for idx, row in df.iterrows():
            try:
                row_date = idx.date() if hasattr(idx, 'date') else date.fromisoformat(str(idx)[:10])
                open_val = Decimal(str(round(float(row["Open"]), 2)))
                high_val = Decimal(str(round(float(row["High"]), 2)))
                low_val = Decimal(str(round(float(row["Low"]), 2)))
                close_val = Decimal(str(round(float(row["Close"]), 2)))
                volume = int(row["Volume"])
            except (KeyError, ValueError, InvalidOperation):
                continue

            # Compute change
            change = Decimal("0")
            change_pct = Decimal("0")

            stmt = pg_insert(StockPrice).values(
                stock_id=stock.id,
                date=row_date,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                volume=volume,
                change=change,
                change_percent=change_pct,
            )
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_stock_prices_stock_id_date",
            )
            await db.execute(stmt)
            count += 1

        await db.commit()
        print(f"{count} rows")
        return count

async def main(symbols: list[str], start_date: str):
    print(f"Backfilling {len(symbols)} stocks from {start_date}")
    total = 0
    for sym in symbols:
        n = await backfill_stock(sym, start_date)
        total += n
    print(f"\nDone! Total: {total} rows inserted/skipped")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical prices via yfinance")
    parser.add_argument("--symbols", type=str, default=",".join(TOP_STOCKS),
                        help="Comma-separated stock symbols (without .TW)")
    parser.add_argument("--start", type=str, default="2007-01-01",
                        help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # Need to be in backend dir for imports
    import os
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, ".")

    asyncio.run(main(symbols, args.start))

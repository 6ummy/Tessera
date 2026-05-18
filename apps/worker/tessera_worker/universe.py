"""Pilot ticker universe.

~50 names spanning the sectors and styles each persona cares about. Curated
so each persona has at least 10 plausible candidates from their lens:

- Warren (value):       FCF-rich compounders, financials, staples
- Cathie (disruptive):  AI semis, software, biotech, crypto-proxy
- Ray (macro):          broad-market + asset-class ETFs (no single names)
- Peter (GARP):         growth-at-reasonable-price across tech + industrial + consumer

Expand to 500 in Phase B when LLM screen needs it. For now this is enough to
prove the pipeline end-to-end and run a meaningful backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Sector = Literal[
    "Technology", "Financials", "Healthcare", "Consumer Discretionary",
    "Consumer Staples", "Communication Services", "Industrials", "Energy",
    "Utilities", "Materials", "Real Estate",
    "Equity ETF", "Bond ETF", "Commodity ETF", "Crypto",
]


@dataclass(frozen=True, slots=True)
class TickerMeta:
    ticker: str
    name: str
    sector: Sector
    asset_class: Literal["equity", "etf", "crypto"]


_RAW: list[TickerMeta] = [
    # ─── Tech (mega + selected mid) ───
    TickerMeta("AAPL",  "Apple",                          "Technology",            "equity"),
    TickerMeta("MSFT",  "Microsoft",                      "Technology",            "equity"),
    TickerMeta("GOOGL", "Alphabet (A)",                   "Communication Services","equity"),
    TickerMeta("META",  "Meta Platforms",                 "Communication Services","equity"),
    TickerMeta("NVDA",  "NVIDIA",                         "Technology",            "equity"),
    TickerMeta("AVGO",  "Broadcom",                       "Technology",            "equity"),
    TickerMeta("AMD",   "Advanced Micro Devices",         "Technology",            "equity"),
    TickerMeta("ASML",  "ASML",                           "Technology",            "equity"),
    TickerMeta("TSM",   "Taiwan Semi",                    "Technology",            "equity"),
    TickerMeta("ANET",  "Arista Networks",                "Technology",            "equity"),
    TickerMeta("LRCX",  "Lam Research",                   "Technology",            "equity"),
    TickerMeta("CRWD",  "CrowdStrike",                    "Technology",            "equity"),
    TickerMeta("PLTR",  "Palantir",                       "Technology",            "equity"),
    TickerMeta("NOW",   "ServiceNow",                     "Technology",            "equity"),
    TickerMeta("SHOP",  "Shopify",                        "Technology",            "equity"),
    # ─── Financials ───
    TickerMeta("BRK.B", "Berkshire Hathaway (B)",         "Financials",            "equity"),
    TickerMeta("JPM",   "JPMorgan Chase",                 "Financials",            "equity"),
    TickerMeta("V",     "Visa",                           "Financials",            "equity"),
    TickerMeta("MA",    "Mastercard",                     "Financials",            "equity"),
    TickerMeta("MCO",   "Moody's",                        "Financials",            "equity"),
    TickerMeta("COIN",  "Coinbase",                       "Financials",            "equity"),
    # ─── Healthcare ───
    TickerMeta("UNH",   "UnitedHealth",                   "Healthcare",            "equity"),
    TickerMeta("JNJ",   "Johnson & Johnson",              "Healthcare",            "equity"),
    TickerMeta("LLY",   "Eli Lilly",                      "Healthcare",            "equity"),
    TickerMeta("ISRG",  "Intuitive Surgical",             "Healthcare",            "equity"),
    TickerMeta("TEM",   "Tempus AI",                      "Healthcare",            "equity"),
    # ─── Consumer ───
    TickerMeta("AMZN",  "Amazon",                         "Consumer Discretionary","equity"),
    TickerMeta("TSLA",  "Tesla",                          "Consumer Discretionary","equity"),
    TickerMeta("HD",    "Home Depot",                     "Consumer Discretionary","equity"),
    TickerMeta("BKNG",  "Booking Holdings",               "Consumer Discretionary","equity"),
    TickerMeta("DECK",  "Deckers Outdoor",                "Consumer Discretionary","equity"),
    TickerMeta("RBLX",  "Roblox",                         "Communication Services","equity"),
    TickerMeta("COST",  "Costco",                         "Consumer Staples",      "equity"),
    TickerMeta("WMT",   "Walmart",                        "Consumer Staples",      "equity"),
    TickerMeta("PG",    "Procter & Gamble",               "Consumer Staples",      "equity"),
    # ─── Industrials / Energy / Materials ───
    TickerMeta("URI",   "United Rentals",                 "Industrials",           "equity"),
    TickerMeta("CAT",   "Caterpillar",                    "Industrials",           "equity"),
    TickerMeta("HON",   "Honeywell",                      "Industrials",           "equity"),
    TickerMeta("XOM",   "Exxon Mobil",                    "Energy",                "equity"),
    TickerMeta("LIN",   "Linde",                          "Materials",             "equity"),
    # ─── Real Estate / Utilities ───
    TickerMeta("PLD",   "Prologis",                       "Real Estate",           "equity"),
    TickerMeta("NEE",   "NextEra Energy",                 "Utilities",             "equity"),
    # ─── Ray's ETF universe (asset-class only) ───
    TickerMeta("VTI",   "Vanguard Total US Market",       "Equity ETF",            "etf"),
    TickerMeta("VXUS",  "Vanguard Total Intl ex-US",      "Equity ETF",            "etf"),
    TickerMeta("SPY",   "SPDR S&P 500",                   "Equity ETF",            "etf"),
    TickerMeta("QQQ",   "Invesco QQQ (Nasdaq 100)",       "Equity ETF",            "etf"),
    TickerMeta("IEF",   "iShares 7-10y Treasuries",       "Bond ETF",              "etf"),
    TickerMeta("TLT",   "iShares 20+y Treasuries",        "Bond ETF",              "etf"),
    TickerMeta("TIP",   "iShares TIPS",                   "Bond ETF",              "etf"),
    TickerMeta("GLD",   "SPDR Gold",                      "Commodity ETF",         "etf"),
    TickerMeta("DBC",   "Invesco DB Commodity Index",     "Commodity ETF",         "etf"),
]


# Crypto handled separately by the Coinbase ingestor; not in equity ingestor's
# universe to avoid market-hours / exchange confusion.
CRYPTO: list[TickerMeta] = [
    TickerMeta("BTC/USD", "Bitcoin",  "Crypto", "crypto"),
    TickerMeta("ETH/USD", "Ethereum", "Crypto", "crypto"),
]


UNIVERSE: list[TickerMeta] = _RAW
TICKERS: list[str] = [t.ticker for t in UNIVERSE]
META_BY_TICKER: dict[str, TickerMeta] = {t.ticker: t for t in UNIVERSE}


def sectors() -> set[str]:
    return {t.sector for t in UNIVERSE}


def by_sector(sector: Sector) -> list[TickerMeta]:
    return [t for t in UNIVERSE if t.sector == sector]


def by_asset_class(asset_class: str) -> list[TickerMeta]:
    return [t for t in UNIVERSE if t.asset_class == asset_class]

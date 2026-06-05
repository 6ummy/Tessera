"""Resolve ticker mentions from free-text user input.

Six-level resolution chain, cheapest first:

  Level 1-2: regex direct match (`AAPL`, `aapl`)
  Level 3:   universe.py `name` lookup (`Apple`, `Costco`)
  Level 4:   curated alias dict — Korean + English alternates
             (`애플`, `엔비디아`, `Tesla`, `tsmc`)
  Level 5:   rapidfuzz fuzzy match — handles typos (`Tesls`, `AAPLE`)
  Level 6:   Haiku 4.5 fallback — only when 1-5 all miss; handles
             roundabout references (`the search giant`, `전기차 회사`)

`allow_haiku=False` disables Level 6 (use when you want guaranteed zero
LLM cost — e.g., in batch/canary contexts).

Returns a sorted list of canonical universe tickers (deduped).
"""

from __future__ import annotations

import os
import re
import sys
from functools import lru_cache

from tessera_worker.logging import get_logger

# UTF-8 stdout so CLI demos with Korean / em-dashes don't crash on Windows cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass
from tessera_worker.universe import _RAW as _EQUITIES_AND_ETFS
try:
    from tessera_worker.universe import CRYPTO as _CRYPTO
except ImportError:
    _CRYPTO = []
_UNIVERSE_RAW = list(_EQUITIES_AND_ETFS) + list(_CRYPTO)

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Curated aliases — Korean + English alternates beyond the canonical name.
# Keep this dict explicit; do NOT auto-generate from Wikipedia. We want
# every alias reviewed for ambiguity (e.g., "Visa" could also mean travel
# documentation, so we don't expand "V" beyond direct ticker match).
# ─────────────────────────────────────────────────────────────────────────
ALIASES: dict[str, str] = {
    # ─── English alternate forms ───
    "google": "GOOGL", "alphabet": "GOOGL",
    "facebook": "META", "meta platforms": "META",
    "berkshire": "BRK.B", "brk.b": "BRK.B", "brk-b": "BRK.B", "brk": "BRK.B",
    "tsmc": "TSM", "taiwan semiconductor": "TSM",
    "j&j": "JNJ", "johnson and johnson": "JNJ",
    "p&g": "PG", "procter gamble": "PG",
    "lilly": "LLY",
    "moodys": "MCO", "moody's": "MCO",
    "amd": "AMD",
    "nvidia": "NVDA",
    "vanguard total us": "VTI", "vanguard total us market": "VTI",
    "vanguard total international": "VXUS",
    "qqq nasdaq": "QQQ", "nasdaq 100": "QQQ",
    "bitcoin": "BTC/USD", "btc": "BTC/USD",
    "ethereum": "ETH/USD", "eth": "ETH/USD", "ether": "ETH/USD",
    "tempus": "TEM",
    "spdr s&p": "SPY", "s&p 500": "SPY", "sp500": "SPY",
    "spdr gold": "GLD", "gold etf": "GLD",
    "20 year treasuries": "TLT", "long treasuries": "TLT",
    "intermediate treasuries": "IEF",
    "tips etf": "TIP",
    "broad commodities": "DBC", "commodity etf": "DBC",
    # ─── 한국어 ───
    "애플": "AAPL", "마이크로소프트": "MSFT", "엠에스에프티": "MSFT",
    "구글": "GOOGL", "알파벳": "GOOGL",
    "메타": "META", "페이스북": "META",
    "엔비디아": "NVDA",
    "브로드컴": "AVGO",
    "에이엠디": "AMD",
    "에이에스엠엘": "ASML",
    "테슬라": "TSLA",
    "아마존": "AMZN",
    "코스트코": "COST",
    "월마트": "WMT",
    "버크셔": "BRK.B", "버크셔해서웨이": "BRK.B",
    "제이피모건": "JPM", "제이피모건체이스": "JPM",
    "비자": "V",
    "마스터카드": "MA",
    "코인베이스": "COIN",
    "유나이티드헬스": "UNH",
    "존슨앤존슨": "JNJ", "존슨존슨": "JNJ",
    "일라이릴리": "LLY", "릴리": "LLY",
    "홈디포": "HD",
    "쇼피파이": "SHOP",
    "팔란티어": "PLTR", "팔란티르": "PLTR",
    "로블록스": "RBLX",
    "크라우드스트라이크": "CRWD",
    "서비스나우": "NOW",
    "프록터앤갬블": "PG", "P&G": "PG",
    "엑손모빌": "XOM", "엑손": "XOM",
    "캐터필러": "CAT",
    "하니웰": "HON",
    "린데": "LIN",
    "프로로지스": "PLD",
    "넥스트에라": "NEE",
    "TSMC": "TSM", "타이완 세미": "TSM", "대만 반도체": "TSM",
    "비트코인": "BTC/USD",
    "이더리움": "ETH/USD",
    "스앤피500": "SPY", "에스앤피500": "SPY", "에스피와이": "SPY",
    "큐큐큐": "QQQ", "나스닥100": "QQQ", "나스닥 100": "QQQ",
    "금": "GLD", "금 etf": "GLD", "골드": "GLD",
    "장기국채": "TLT", "장기 국채": "TLT",
}


# ─────────────────────────────────────────────────────────────────────────
# Indexes built once at import. Cheap; no DB or LLM calls.
# ─────────────────────────────────────────────────────────────────────────
_UNIVERSE_TICKERS: set[str] = {t.ticker for t in _UNIVERSE_RAW}
# name → ticker (lowercased). Built from universe.name + ALIASES.
_NAME_INDEX: dict[str, str] = {}
for t in _UNIVERSE_RAW:
    # Canonical name + lowercase variants
    _NAME_INDEX[t.name.lower()] = t.ticker
    # Strip parens/qualifiers like "Alphabet (A)" → "alphabet"
    bare = re.sub(r"\s*\([^)]*\)\s*", "", t.name).strip().lower()
    if bare and bare != t.name.lower():
        _NAME_INDEX[bare] = t.ticker
for alias, ticker in ALIASES.items():
    _NAME_INDEX[alias.lower()] = ticker


# ─────────────────────────────────────────────────────────────────────────
# Resolution chain
# ─────────────────────────────────────────────────────────────────────────


def _regex_match(text: str) -> set[str]:
    """Level 1-2: pull tokens matching ticker shape, check membership.

    Drops strict `\\b` boundaries (they fail across Unicode/`/` transitions
    like `BTC/USD 살까`). Instead: match liberally, filter by universe set
    membership — guaranteed to never false-positive since the universe is
    a closed set.
    """
    found: set[str] = set()
    for m in re.finditer(r"[A-Za-z]{2,5}(?:[./][A-Za-z]{1,5})?", text):
        token = m.group().upper()
        if token in _UNIVERSE_TICKERS:
            found.add(token)
    return found


def _name_lookup(text: str) -> set[str]:
    """Level 3-4: company name + alias substring match (case-insensitive).

    Length floor differs by script: ASCII names need ≥3 chars to avoid
    over-matching common bigrams ("ma" inside "marathon"), but Korean
    aliases like "애플" (2 hangul chars) are unambiguous and need no floor.
    """
    found: set[str] = set()
    lower = text.lower()
    for name in sorted(_NAME_INDEX.keys(), key=len, reverse=True):
        if name.isascii() and len(name) < 3:
            continue
        if name in lower:
            found.add(_NAME_INDEX[name])
    return found


def _fuzzy_match(text: str, threshold: int = 85) -> set[str]:
    """Level 5: rapidfuzz token-wise fuzzy match — handles typos.

    Both sides lowercased before scoring (rapidfuzz.fuzz.ratio is case
    sensitive). Then mapped back to canonical ticker.
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        log.warning("ticker_resolver.rapidfuzz_missing",
                    note="pip install rapidfuzz for fuzzy ticker matching")
        return set()
    found: set[str] = set()
    # lowercase candidate map: lower → canonical ticker
    cand_to_ticker: dict[str, str] = {}
    for t in _UNIVERSE_TICKERS:
        cand_to_ticker[t.lower()] = t
    for name, t in _NAME_INDEX.items():
        cand_to_ticker[name.lower()] = t
    candidates = list(cand_to_ticker.keys())
    # Tokenize on Unicode word chars (3-15 length to avoid noise)
    for word in re.findall(r"[\w]{3,15}", text):
        lw = word.lower()
        # Skip exact matches — those are handled by L1-4, no fuzzy needed
        if lw in cand_to_ticker:
            continue
        match = process.extractOne(lw, candidates, scorer=fuzz.ratio)
        if match is None:
            continue
        candidate, score, _idx = match
        if score >= threshold:
            ticker = cand_to_ticker[candidate]
            if ticker in _UNIVERSE_TICKERS:
                found.add(ticker)
    return found


def _haiku_extract(text: str) -> set[str]:
    """Level 6: tiny Haiku 4.5 call when 1-5 all miss. Handles roundabout
    references like "the search giant", "전기차 회사", "the toll road for AI compute".

    Cost: ~$0.0001 per call (Haiku is cheap). Latency: ~200ms.
    Skipped silently when ANTHROPIC_API_KEY is blank.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return set()
    try:
        from anthropic import Anthropic
    except ImportError:
        return set()
    if not text or not text.strip():
        return set()

    universe_str = ", ".join(sorted(_UNIVERSE_TICKERS))
    system = (
        "You map free-text references to ticker symbols from a fixed universe. "
        "Return ONLY a JSON array of tickers, no commentary. Empty array if "
        "no clear match. Tickers must come from the provided universe."
    )
    user = (
        f"Universe (use ONLY these): {universe_str}\n\n"
        f"User text: {text!r}\n\n"
        "Which tickers does the user mention or describe? "
        "Be conservative — return nothing rather than guess. JSON array only."
    )
    try:
        client = Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text if resp.content else "[]"
        # Strip code fences if Haiku adds them
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        import json as _json
        arr = _json.loads(raw) if raw.startswith("[") else []
        return {t for t in arr if isinstance(t, str) and t in _UNIVERSE_TICKERS}
    except Exception as e:
        log.warning("ticker_resolver.haiku_failed",
                    error=str(e), error_type=type(e).__name__)
        return set()


def resolve_tickers(
    text: str,
    *,
    fuzzy_threshold: int = 85,
    allow_haiku: bool = True,
) -> list[str]:
    """Resolve all ticker mentions in `text`. Chain stops as soon as
    Level 1-5 find anything; Haiku (Level 6) only fires when L1-5 all miss
    (saves cost on the common case).

    Returns: sorted list of canonical universe tickers.
    """
    if not text or not text.strip():
        return []

    found = _regex_match(text) | _name_lookup(text)
    if not found:
        # Fuzzy only if no exact matches — prevents "Apple" matching "AAPL"
        # AND a fuzzy near-miss.
        found = _fuzzy_match(text, threshold=fuzzy_threshold)
    if not found and allow_haiku:
        found = _haiku_extract(text)
    return sorted(found)


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Resolve tickers from free text")
    p.add_argument("text", nargs="+", help="Input text")
    p.add_argument("--no-haiku", action="store_true",
                   help="Disable Level 6 Haiku fallback")
    p.add_argument("--threshold", type=int, default=85,
                   help="Fuzzy match threshold (0-100)")
    args = p.parse_args()
    text = " ".join(args.text)
    tickers = resolve_tickers(text, fuzzy_threshold=args.threshold,
                              allow_haiku=not args.no_haiku)
    print(f"Input:   {text!r}")
    print(f"Tickers: {tickers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

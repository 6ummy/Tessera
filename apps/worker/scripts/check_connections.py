"""Smoke test: verify every external connection works before writing ingestors.

Run:
    cd apps/worker
    .venv/Scripts/python.exe scripts/check_connections.py
"""

from __future__ import annotations

import re
import sys

from tessera_worker.config import get_settings

# Redact common secret patterns so error output never leaks keys to chat / logs.
_SECRET_PATTERNS = [
    re.compile(r"(apikey=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(api_key=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(api-key:\s*)[^\s]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"(sk-ant-[A-Za-z0-9_\-]+)"),
    re.compile(r"(npg_[A-Za-z0-9_\-]+)"),  # Neon password format
]


def redact(text: str) -> str:
    s = str(text)
    for pat in _SECRET_PATTERNS:
        s = pat.sub(r"\g<1><REDACTED>" if pat.groups else "<REDACTED>", s)
    return s


def check_neon() -> bool:
    print("─── Neon Postgres ───")
    try:
        import psycopg
    except ImportError:
        print("  ✗ psycopg not installed")
        return False
    s = get_settings()
    if not s.database_url or "USER:PASS" in s.database_url:
        print("  ✗ DATABASE_URL not configured (.env)")
        return False
    try:
        conn = psycopg.connect(s.database_url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
        tables = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT extname FROM pg_extension "
            "WHERE extname IN ('timescaledb','vector','uuid-ossp') ORDER BY extname"
        )
        exts = [r[0] for r in cur.fetchall()]
        conn.close()
        expected_tables = {
            "analyst_reports", "filings", "fundamentals", "llm_call_log",
            "macro_series", "news", "ohlcv_1d", "persona_memory",
            "persona_performance", "persona_portfolios", "persona_trades",
            "ticker_features", "user_portfolios", "users",
        }
        missing = expected_tables - set(tables)
        print(f"  ✓ connected; {len(tables)} tables, extensions: {exts}")
        if missing:
            print(f"  ✗ missing tables: {sorted(missing)}")
            return False
        if "timescaledb" not in exts or "vector" not in exts:
            print(f"  ✗ missing extensions (need timescaledb + vector)")
            return False
        return True
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


def check_alpaca() -> bool:
    print("─── Alpaca (paper) ───")
    s = get_settings()
    if not s.alpaca_api_key or not s.alpaca_api_secret:
        print("  ⊘ keys not set; skipping")
        return True  # not a failure during scaffold phase
    try:
        from alpaca.trading.client import TradingClient

        tc = TradingClient(s.alpaca_api_key, s.alpaca_api_secret, paper=True)
        acct = tc.get_account()
        print(
            f"  ✓ account {acct.account_number} status={acct.status} "
            f"cash=${float(acct.cash):,.2f} equity=${float(acct.equity):,.2f}"
        )
        return True
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


def check_anthropic() -> bool:
    print("─── Anthropic ───")
    s = get_settings()
    if not s.anthropic_api_key:
        print("  ⊘ ANTHROPIC_API_KEY not set; skipping")
        return True
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=s.anthropic_api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=20,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        )
        reply = msg.content[0].text if msg.content else ""
        print(f"  ✓ Haiku replied: {reply!r}  (in={msg.usage.input_tokens} out={msg.usage.output_tokens})")
        return True
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


def check_fred() -> bool:
    print("─── FRED ───")
    s = get_settings()
    if not s.fred_api_key:
        print("  ⊘ key not set; skipping")
        return True
    try:
        import httpx

        r = httpx.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "DGS10",
                "api_key": s.fred_api_key,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc",
            },
            timeout=10,
        )
        r.raise_for_status()
        obs = r.json()["observations"][0]
        print(f"  ✓ DGS10 latest: {obs['date']} = {obs['value']}%")
        return True
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


def check_fmp() -> bool:
    print("─── FMP ───")
    s = get_settings()
    if not s.fmp_api_key:
        print("  ⊘ key not set; skipping")
        return True
    try:
        import httpx

        # FMP 2025+: legacy /api/v3/* endpoints all return 403 ("Legacy Endpoint").
        # Free tier now lives at /stable/* with `symbol=` query param.
        r = httpx.get(
            "https://financialmodelingprep.com/stable/profile",
            params={"symbol": "AAPL", "apikey": s.fmp_api_key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data and isinstance(data, list):
            p = data[0]
            mcap = p.get("marketCap") or p.get("mktCap") or 0
            print(f"  ✓ AAPL profile fetched (stable); market cap ${mcap:,}")
            return True
        print(f"  ✗ unexpected response shape: {type(data).__name__}")
        return False
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


def check_newsapi() -> bool:
    print("─── NewsAPI ───")
    s = get_settings()
    if not s.newsapi_api_key:
        print("  ⊘ key not set; skipping")
        return True
    try:
        import httpx

        r = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "AAPL",
                "pageSize": 1,
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": s.newsapi_api_key,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "ok":
            n = data.get("totalResults", 0)
            print(f"  ✓ got {n} AAPL articles available")
            return True
        print(f"  ✗ status={data.get('status')}, message={data.get('message')}")
        return False
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {redact(e)}")
        return False


if __name__ == "__main__":
    checks = [check_neon, check_alpaca, check_anthropic, check_fred, check_fmp, check_newsapi]
    results = [(c.__name__, c()) for c in checks]
    print()
    print("─── Summary ───")
    for name, ok in results:
        flag = "✓" if ok else "✗"
        print(f"  {flag} {name.removeprefix('check_')}")
    sys.exit(0 if all(ok for _, ok in results) else 1)

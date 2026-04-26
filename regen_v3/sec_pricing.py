"""Historical price lookup for SEC Form 4 gift valuation.

Form 4 G-transactions report `price_per_share = $0` (gifts have no
consideration). To put a dollar figure on a gift we need the issuer's
closing price on the transaction date. This module provides:

  resolve_ticker(company_name, source_url) -> "META" | None
  get_close_price(ticker, date)            -> float | None
  value_gift(gift)                         -> float | None

Caches:
  regen_v3/cache/tickers/<sha1(source_url)>.json   -> {"ticker": "META"}
  regen_v3/cache/prices/<TICKER>_<YYYY-MM-DD>.json -> {"close": 596.6, ...}

Determinism: once cached, (ticker, date) always returns the same close.
We cache misses too (so we don't keep retrying the same dead ticker).

Provider order:
  1. yfinance (no API key). May rate-limit; we tolerate failures.
  2. Stooq CSV endpoint (no API key) as a fallback.
  3. Give up -> return None; the caller keeps `reference_only` behavior.

If `yfinance` is not installed, the import is skipped and we fall back
to Stooq directly. The pipeline never breaks on missing deps.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests

HERE = Path(__file__).parent
CACHE_PRICES = HERE / "cache" / "prices"
CACHE_TICKERS = HERE / "cache" / "tickers"
CACHE_PRICES.mkdir(parents=True, exist_ok=True)
CACHE_TICKERS.mkdir(parents=True, exist_ok=True)

_USER_AGENT = "Scrooge Research Bot (research@example.com)"

# Optional: yfinance is the primary data source. If it isn't installed
# (or breaks), we fall back to Stooq. Wrap the import so the pipeline
# stays usable in either state.
try:
    import yfinance as _yf  # type: ignore
    _HAS_YF = True
except Exception:  # pragma: no cover - optional dep
    _yf = None
    _HAS_YF = False


# Hand-curated company-name -> ticker for the issuers we know are
# in our SEC cache. Keys lowercased and stripped of punctuation.
# This is the fast path; if a name isn't here we read the Form 4 XML
# at `source_url` and pull `issuerTradingSymbol`.
KNOWN_TICKERS: dict[str, str] = {
    "meta platforms inc": "META",
    "meta platforms": "META",
    "facebook inc": "META",  # pre-2022 filings
    "facebook": "META",
    "berkshire hathaway inc": "BRK-B",  # Class B is the liquid one
    "berkshire hathaway inc.": "BRK-B",
    "berkshire hathaway": "BRK-B",
    "amazon com inc": "AMZN",
    "amazon.com inc": "AMZN",
    "amazon.com, inc.": "AMZN",
    "amazon": "AMZN",
    "tesla inc": "TSLA",
    "tesla, inc.": "TSLA",
    "tesla": "TSLA",
    "google inc": "GOOG",  # pre-2015 reorg; close to GOOGL
    "google inc.": "GOOG",
    "alphabet inc": "GOOG",
    "alphabet inc.": "GOOG",
    "alphabet": "GOOG",
    "blackstone inc": "BX",
    "blackstone inc.": "BX",
    "the blackstone group inc.": "BX",
    "the blackstone group l.p.": "BX",
    "blackstone group inc": "BX",
    "blackstone": "BX",
    "microsoft corporation": "MSFT",
    "microsoft corp": "MSFT",
    "microsoft": "MSFT",
    "oracle corp": "ORCL",
    "oracle corporation": "ORCL",
    "nvidia corp": "NVDA",
    "nvidia corporation": "NVDA",
    "netflix inc": "NFLX",
    "netflix, inc.": "NFLX",
    "salesforce inc": "CRM",
    "salesforce.com, inc.": "CRM",
    "salesforce.com inc": "CRM",
    "dell technologies inc": "DELL",
    "dell technologies inc.": "DELL",
}


def _norm_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"[\.,]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------------------
# Ticker resolution
# ---------------------------------------------------------------------------

def _ticker_cache_key(source_url: str) -> str:
    return hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]


def _load_ticker_cache(source_url: str) -> Optional[dict]:
    p = CACHE_TICKERS / f"{_ticker_cache_key(source_url)}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_ticker_cache(source_url: str, payload: dict) -> None:
    p = CACHE_TICKERS / f"{_ticker_cache_key(source_url)}.json"
    p.write_text(json.dumps(payload, indent=2))


def _fetch_ticker_from_form4(source_url: str) -> Optional[str]:
    """Read the Form 4 XML and return its issuerTradingSymbol."""
    try:
        resp = requests.get(
            source_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        root = ET.fromstring(resp.content)
        sym = root.find(".//issuerTradingSymbol")
        if sym is not None and sym.text:
            return sym.text.strip().upper()
    except Exception:
        return None
    return None


def resolve_ticker(company: str, source_url: str = "") -> Optional[str]:
    """Best-effort ticker for an SEC issuer. Cached per source_url so
    repeated lookups are free."""
    # 1. Hand-curated table (fast, deterministic)
    norm = _norm_name(company or "")
    if norm in KNOWN_TICKERS:
        return KNOWN_TICKERS[norm]

    # 2. Cached XML lookup
    if not source_url:
        return None
    cached = _load_ticker_cache(source_url)
    if cached is not None:
        t = cached.get("ticker")
        return t if t else None

    # 3. Fetch the Form 4 XML and read issuerTradingSymbol
    t = _fetch_ticker_from_form4(source_url)
    _save_ticker_cache(source_url, {"ticker": t, "company": company})
    time.sleep(0.15)  # SEC fair-use rate
    return t


# ---------------------------------------------------------------------------
# Price lookup
# ---------------------------------------------------------------------------

def _price_cache_path(ticker: str, date: str) -> Path:
    safe_ticker = re.sub(r"[^A-Z0-9.\-]", "_", ticker.upper())
    return CACHE_PRICES / f"{safe_ticker}_{date}.json"


def _load_price_cache(ticker: str, date: str) -> Optional[dict]:
    p = _price_cache_path(ticker, date)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_price_cache(ticker: str, date: str, payload: dict) -> None:
    _price_cache_path(ticker, date).write_text(json.dumps(payload, indent=2))


def _next_business_day(date_str: str, max_step: int = 5) -> list[str]:
    """Return a list of candidate dates: the requested day plus up to
    `max_step` following calendar days, in case the gift fell on a
    weekend/holiday and we need the next trading session's close."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return [(d + timedelta(days=i)).isoformat() for i in range(0, max_step + 1)]


def _yf_lookup(ticker: str, date: str) -> Optional[float]:
    if not _HAS_YF:
        return None
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
        end = (d + timedelta(days=7)).isoformat()
        hist = _yf.Ticker(ticker).history(
            start=date, end=end, auto_adjust=False, actions=False
        )
        if hist is None or hist.empty:
            return None
        # Take the first row at-or-after `date`
        row = hist.iloc[0]
        close = float(row.get("Close"))
        if close <= 0:
            return None
        return close
    except Exception:
        return None


def _stooq_lookup(ticker: str, date: str) -> Optional[float]:
    """Fallback to Stooq daily CSV (no key, no auth). Stooq uses
    lowercased ticker with `.us` suffix for US equities. We pull the
    full CSV once and look up the closest trading day at-or-after."""
    sym = ticker.lower().replace("-", "-") + ".us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": _USER_AGENT})
        if resp.status_code != 200 or not resp.text:
            return None
        lines = resp.text.strip().splitlines()
        if len(lines) < 2 or not lines[0].lower().startswith("date"):
            return None
        # Build a quick map of date -> close
        idx_close = lines[0].lower().split(",").index("close")
        targets = set(_next_business_day(date, max_step=5))
        for ln in lines[1:]:
            parts = ln.split(",")
            if not parts:
                continue
            if parts[0] in targets:
                try:
                    return float(parts[idx_close])
                except Exception:
                    continue
        return None
    except Exception:
        return None


def get_close_price(ticker: str, date: str) -> Optional[float]:
    """Return historical closing price for `ticker` at-or-after `date`.

    Cached forever per (ticker, date). Misses are also cached so we
    don't hammer the providers on every run."""
    if not ticker or not date or len(date) < 10:
        return None
    date = date[:10]

    cached = _load_price_cache(ticker, date)
    if cached is not None:
        c = cached.get("close")
        return float(c) if isinstance(c, (int, float)) and c > 0 else None

    close = _yf_lookup(ticker, date)
    source = "yfinance"
    if close is None:
        close = _stooq_lookup(ticker, date)
        source = "stooq"

    payload = {
        "ticker": ticker,
        "date": date,
        "close": close,
        "source": source if close else None,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_price_cache(ticker, date, payload)
    return close


# ---------------------------------------------------------------------------
# High-level helper used by sec.py
# ---------------------------------------------------------------------------

def value_gift(gift: dict) -> Optional[float]:
    """Return the USD value of a Form 4 G-transaction, or None if we
    can't price it. The input dict is one entry from the sec.py cache
    (`regen_v3/cache/sec/<cik>.json`)."""
    shares = gift.get("shares") or 0
    if shares <= 0:
        return None
    date = (gift.get("transaction_date") or "")[:10]
    if not date or len(date) < 10:
        return None

    ticker = resolve_ticker(
        gift.get("company") or "",
        gift.get("source_url") or "",
    )
    if not ticker:
        return None

    close = get_close_price(ticker, date)
    if not close:
        return None

    return float(shares) * float(close)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Test price lookup")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    p = get_close_price(args.ticker.upper(), args.date)
    print(f"{args.ticker.upper()} @ {args.date}: {p}")

#!/usr/bin/env python3
"""Fetch a live intraday volume snapshot for every ticker on the chart.

Writes its own `/* <<<VOL>>> */ … /* <<<END VOL>>> */` region in index.html so it
never touches the `/* <<<DATA>>> */` region that fetch-company-data.py rewrites.

The ticker universe is read straight out of index.html (the `cos:` lists in NODES
and ENABLERS), so the feed always matches exactly the chips the diagram draws.

Source (no API keys): the CNBC quote web-service — it takes many symbols per
request (`XOM|CVX|…`), returns real-time last / change / volume per symbol and
needs no key. Each run replaces the previous snapshot; the rail labels it with
the quote timestamp, so a stale snapshot is visible as one.

Usage:
  python3 tools/fetch-market-volume.py            # write data/market-volume.json
  python3 tools/fetch-market-volume.py --inject   # …and splice it into index.html
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
BATCH = 26                      # symbols per request — keeps the URL sane
QUOTE_URL = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
             "?symbols={syms}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1"
             "&output=json&events=1")


# ------------------------------------------------------------------ universe
def chart_universe(html: str):
    """([tickers in draw order], {ticker: chart name}) — straight from index.html."""
    tickers: list[str] = []
    for m in re.finditer(r"cos:\[([^\]]*)\]", html):
        for t in m.group(1).split(","):
            t = t.strip().strip('"')
            if t and t not in tickers:
                tickers.append(t)
    names = {m.group(1): m.group(2)
             for m in re.finditer(r'^\s*([A-Z][A-Z0-9]{0,5}):\["([^"]*)"', html, re.M)}
    return tickers, names


# ------------------------------------------------------------------ quotes
def num(v):
    if v in (None, "", "--", "N/A", "UNCH"):
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("+", ""))
    except ValueError:
        return None


def fetch_batch(syms, tries: int = 4):
    """{ticker: row} for one request's worth of symbols."""
    url = QUOTE_URL.format(syms=urllib.parse.quote("|".join(syms), safe=""))
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json",
                "Referer": "https://www.cnbc.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            items = ((j.get("FormattedQuoteResult") or {}).get("FormattedQuote")) or []
            if isinstance(items, dict):
                items = [items]
            out = {}
            for it in items:
                tk = it.get("symbol")
                if not tk:
                    continue
                out[tk] = {
                    "tk": tk,
                    "v": num(it.get("volume")),
                    "valt": it.get("volume_alt") or None,
                    "p": num(it.get("last")),
                    "c": num(it.get("change")),
                    "cp": num(it.get("change_pct")),
                    "cur": it.get("currencyCode") or None,
                    "ex": it.get("exchange") or None,
                    "nm": it.get("onAirName") or it.get("name") or None,
                    "mkt": it.get("curmktstatus") or None,
                    "t": it.get("last_time") or None,
                    "td": it.get("last_timedate") or None,
                    "rt": it.get("realTime") == "true",
                }
            return out
        except Exception as e:                     # noqa: BLE001 — 404/429/timeout
            last = e
            time.sleep(1.5 * (i + 1))
    print(f"  !! batch {syms[0]}…{syms[-1]}: {type(last).__name__} {last}", flush=True)
    return {}


def main():
    inject = "--inject" in sys.argv
    html_path = ROOT / "index.html"
    html = html_path.read_text()
    tickers, names = chart_universe(html)
    print(f"quoting {len(tickers)} chart tickers in "
          f"{(len(tickers) + BATCH - 1) // BATCH} batches …", flush=True)

    quotes = {}
    for i in range(0, len(tickers), BATCH):
        quotes.update(fetch_batch(tickers[i:i + BATCH]))
        time.sleep(0.6)

    # a chart ticker CNBC did not answer for: try it alone once, then drop it
    missing = [t for t in tickers if t not in quotes]
    for t in list(missing):
        got = fetch_batch([t], tries=2)
        if t in got:
            quotes[t] = got[t]
            missing.remove(t)

    rows = [quotes[t] for t in tickers if t in quotes]
    # market status of the widest sample wins the header label
    status = next((q["mkt"] for q in rows if q.get("mkt")), None)

    asof = datetime.now(timezone.utc)
    payload = {
        "asof": asof.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asofDate": asof.strftime("%Y-%m-%d"),
        "status": status,
        "source": "CNBC quote web-service",
        "quotes": {q["tk"]: {k: v for k, v in q.items()
                             if k != "tk" and v is not None} for q in rows},
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "market-volume.json").write_text(json.dumps(payload, indent=1))

    print(f"wrote data/market-volume.json — {len(rows)}/{len(tickers)} quotes "
          f"(market: {status})")
    if missing:
        print(f"  no quote for {len(missing)}: {missing}")
    top = sorted(rows, key=lambda q: -(q["v"] or 0))[:6]
    print("  most volume: " + ", ".join(
        f"{q['tk']} {int(q['v']):,}" if q["v"] else q["tk"] for q in top))

    if inject:
        inject_into_html(html_path, payload, names)


def inject_into_html(html_path: Path, payload: dict, names: dict):
    """Refresh the VOL region in place (or add it after the DATA region)."""
    slim = {}
    for tk, q in payload["quotes"].items():
        if q.get("v") is None:                         # no volume → nothing to rank
            continue
        item = {"v": q["v"]}
        if q.get("valt"):
            item["va"] = q["valt"]                     # pre-formatted "3.7M"
        if q.get("p") is not None:
            item["p"] = round(float(q["p"]), 2)
        if q.get("cp") is not None:
            item["c"] = round(float(q["cp"]), 2)
        if q.get("p") is not None and q.get("c") is not None:
            item["d"] = round(float(q["c"]), 2)        # absolute change
        if q.get("ex"):
            item["x"] = q["ex"]
        if q.get("nm"):
            item["n"] = q["nm"]
        slim[tk] = item
    js = json.dumps(slim, separators=(",", ":"), sort_keys=True)
    block = ("/* <<<VOL>>> */\nconst VOL=" + js + ";\n"
             f'const VOL_ASOF="{payload["asof"]}";\n'
             f'const VOL_STATUS="{payload.get("status") or ""}";\n'
             "/* <<<END VOL>>> */")

    html = html_path.read_text()
    new, n = re.subn(r"/\* <<<VOL>>> \*/.*?/\* <<<END VOL>>> \*/", block, html, flags=re.S)
    if not n:
        anchor = "/* <<<END DATA>>> */"
        if anchor not in html:
            print("!! neither VOL markers nor the DATA anchor found — nothing injected")
            return
        new = html.replace(anchor, anchor + "\n" + block, 1)
    html_path.write_text(new)
    print(f"injected {len(slim)} quotes into index.html")


if __name__ == "__main__":
    main()

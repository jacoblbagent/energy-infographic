#!/usr/bin/env python3
"""Fetch real financial metrics for every ticker in the energy value chain.

Nothing here is invented. Each number is either read straight off a source page
or computed from sourced inputs by the arithmetic spelled out at the top of each
block below. A metric whose inputs are missing comes back null and the panel
omits that row rather than guessing.

Sources (no API keys):
  * stockanalysis.com/stocks/<t>/statistics/          current ratios + levels
  * stockanalysis.com/stocks/<t>/financials/          TTM/FY income statement,
                                                      revenue/EPS/FCF growth
  * stockanalysis.com/stocks/<t>/financials/ratios/   5 fiscal years of P/E,
                                                      EV/EBITDA, ROIC, net debt
  * stockanalysis.com/stocks/<t>/financials/balance-sheet/
                                                      5 fiscal years of shares
  * FRED DGS10 (curl) or Yahoo ^TNX                  10y Treasury yield

Computed here:
  FCF vs net income      FCF / net income
  share count trend      CAGR of total shares outstanding over the FY series
  peer comparison        median P/E and EV/EBITDA of the same stage of the chain
  moat                   median ROIC over 5 FY against WACC, in points
  DCF                    two-stage FCF model, r = 10y + 5.0pp, terminal 2.5%
  reverse DCF            the FCF growth rate at which the DCF equals the price

Usage:
  python3 tools/fetch-financials.py            # write data/financials.json
  python3 tools/fetch-financials.py --inject   # …and splice it into index.html
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "data" / "financials.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
WORKERS = 3
PAUSE = 0.25          # between page fetches, to stay under the rate limit

ERP = 0.050           # equity risk premium added to the 10y for the discount rate
TERM_G = 0.025        # terminal growth in the DCF
YEARS = 5             # explicit forecast years
CAP_G = 0.15          # cap on the near-term growth fed to the DCF

PAGES = {"stats": "statistics/", "fin": "financials/",
         "ratio": "financials/ratios/", "bs": "financials/balance-sheet/"}


# ---------------------------------------------------------------- fetch
def page(slug: str, kind: str) -> str:
    """GET one stockanalysis page, cached for six hours."""
    f = CACHE / f"sa_{slug}_{kind}.html"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        return f.read_text(errors="replace")
    url = f"https://stockanalysis.com/stocks/{slug}/{PAGES[kind]}"
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "text/html",
                "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            if len(body) < 5000:
                raise RuntimeError("short page")
            CACHE.mkdir(exist_ok=True)
            f.write_text(body)
            return body
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(2.5 * (i + 1))
    raise last


def rows(html: str) -> dict:
    """label -> list of raw cell strings, first occurrence wins."""
    out: dict[str, list[str]] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) < 2 or not cells[0]:
            continue
        lab = re.sub(r"\s+", " ", cells[0].replace("&amp;", "&")).strip()
        # statement rows hold two spans ("Revenue" + "Revenue Growth"), which
        # tag-stripping concatenates — reduce that back to the base label
        m = re.fullmatch(r"(.+?)\s+\1\s+Growth", lab)
        if m:
            lab = m.group(1)
        if lab.lower().startswith(("fiscal year", "period ending")) or lab in out:
            continue
        out[lab] = cells[1:]
    return out


SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def num(s) -> float | None:
    """'676.62B' -> 6.7662e11, '-$5.42' -> -5.42, '29.81%' -> 29.81, '-' -> None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("$", "").replace("%", "")
    t = t.replace("\u2212", "-").replace("(", "-").replace(")", "")
    if t in ("", "-", "–", "N/A", "n/a"):
        return None
    m = re.fullmatch(r"(-?\d*\.?\d+)\s*([KMBT])?", t, re.I)
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2):
        v *= SUFFIX[m.group(2).upper()]
    return v if math.isfinite(v) else None


def cell(r: dict, label: str, i: int = 0, scale: float = 1.0) -> float | None:
    v = r.get(label)
    if v is None:                                  # "Earnings Per Share EPS Growth"
        for k, val in r.items():
            if k.startswith(label + " "):
                v = val
                break
    if not v or i >= len(v):
        return None
    x = num(v[i])
    return None if x is None else x * scale


def cand(r: dict, labels, i: int = 0, scale: float = 1.0) -> float | None:
    for lb in labels:
        x = cell(r, lb, i, scale)
        if x is not None:
            return x
    return None


def med(xs):
    xs = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def cagr(first: float | None, last: float | None, n: int) -> float | None:
    if not first or not last or n <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / n) - 1


def div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def pos(x):
    return None if x is None or x <= 0 else x


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- DCF
def dcf(base: float, g1: float, r: float, tg: float, net_debt: float,
        shares: float):
    """Two-stage FCF model, per share. base/net_debt in dollars, shares in units."""
    if r <= tg or not shares:
        return None
    pv, f = 0.0, base
    for t in range(1, YEARS + 1):
        f *= (1 + g1)
        pv += f / (1 + r) ** t
    pv += (f * (1 + tg) / (r - tg)) / (1 + r) ** YEARS
    eq = pv - net_debt
    return eq / shares if eq > 0 else None


def reverse(base: float, price: float, r: float, tg: float,
            net_debt: float, shares: float, lo=-0.30, hi=0.60):
    """Solve the near-term FCF growth at which the DCF lands on today's price."""
    def gap(g):
        v = dcf(base, g, r, tg, net_debt, shares)
        return None if v is None else v - price
    glo, ghi = gap(lo), gap(hi)
    if glo is None or ghi is None or glo * ghi > 0:
        return None
    for _ in range(70):
        mid = (lo + hi) / 2
        g = gap(mid)
        if g is None:
            return None
        if abs(g) < 1e-4:
            return mid
        if g * glo > 0:
            lo, glo = mid, g
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------- one ticker
def build(tk: str, dgs10: float) -> dict:
    slug = tk.lower().replace(".", "-")
    st = rows(page(slug, "stats"))
    ratio = rows(page(slug, "ratio"))
    fin = rows(page(slug, "fin"))
    try:
        bs = rows(page(slug, "bs"))
    except Exception:                                   # noqa: BLE001
        bs = {}

    mcap = cand(st, ["Market Cap"])
    shares = cand(st, ["Shares Outstanding", "Current Share Class"])
    # price: the site's own market cap over shares is exact and always present
    price = div(mcap, shares) or cell(ratio, "Last Close Price")
    rev = cand(st, ["Revenue"])
    ni = cand(st, ["Net Income"])
    fcf = cand(st, ["Free Cash Flow"])
    net_cash = cand(st, ["Net Cash"])                  # negative => net debt
    net_debt = -net_cash if net_cash is not None else None

    # ---- price relative to earnings power
    pe_t = pos(cand(st, ["PE Ratio"]))
    pe_f = pos(cand(st, ["Forward PE"]))
    ev_e = pos(cand(st, ["EV / EBITDA", "EV/EBITDA"]))
    pfcf = pos(cand(st, ["P/FCF Ratio", "P / FCF Ratio"]))
    fcfy = cand(st, ["FCF Yield"], scale=1 / 100)
    ps = pos(cand(st, ["PS Ratio"]))
    peg = pos(cand(st, ["PEG Ratio", "PEG"]))

    # ---- growth (TTM column of the income statement, i.e. latest year on year)
    rev_g = cand(fin, ["Revenue Growth"], scale=1 / 100)
    eps_g = cand(fin, ["EPS Growth"], scale=1 / 100)
    fcf_g = cand(fin, ["Free Cash Flow Growth"], scale=1 / 100)
    rev_row = fin.get("Revenue") or []
    rev_c3 = None
    if len(rev_row) >= 5:
        a, b = num(rev_row[4]), num(rev_row[1])       # FY-3 → latest FY
        rev_c3 = cagr(a, b, 3)

    # ---- profitability and quality
    gm = cand(st, ["Gross Margin"], scale=1 / 100)
    om = cand(st, ["Operating Margin"], scale=1 / 100)
    roic = cand(st, ["Return on Invested Capital (ROIC)", "ROIC"], scale=1 / 100)
    moat_s = med([cell(ratio, "Return on Invested Capital (ROIC)", i, 1 / 100)
                  for i in range(1, 6)])
    fcf_ni = div(fcf, ni) if (ni or 0) > 0 else None

    # ---- balance sheet risk
    nd_e = pos(cand(ratio, ["Net Debt / EBITDA Ratio", "Net Debt/EBITDA"]))
    if nd_e is None:
        nd_e = cand(st, ["Net Debt / EBITDA"])
    icov = pos(cand(st, ["Interest Coverage"]))

    sh_row = bs.get("Total Common Shares Outstanding") or []
    sh_vals = [(i, num(v)) for i, v in enumerate(sh_row[1:])]
    sh_vals = [(i, v) for i, v in sh_vals if v]
    sh_c = None
    if len(sh_vals) >= 3:
        sh_c = cagr(sh_vals[-1][1], sh_vals[0][1], len(sh_vals) - 1)

    # ---- context: historical band from the five fiscal years on the ratios page
    hist_pe = med([pos(cell(ratio, "PE Ratio", i)) for i in range(1, 6)])
    hist_ev = med([pos(cell(ratio, "EV/EBITDA Ratio", i)) for i in range(1, 6)])
    # a 5y median lifted by a single near-zero-earnings year says nothing useful
    if hist_pe is not None and hist_pe > 100:
        hist_pe = None
    if hist_ev is not None and hist_ev > 60:
        hist_ev = None

    r = dgs10 + ERP
    dcf_v = dcf_g = rdcf = None
    base = pos(fcf) if fcf else None
    if base and shares and net_debt is not None and price:
        # FCF CAGR over the fiscal-year series, floored at zero and capped
        fcf_row = fin.get("Free Cash Flow") or []
        g0 = None
        if len(fcf_row) >= 5:
            g0 = cagr(num(fcf_row[4]), num(fcf_row[1]), 3)
        if g0 is None:
            g0 = TERM_G
        dcf_g = clamp(g0, 0.0, CAP_G)
        dcf_v = dcf(base, dcf_g, r, TERM_G, net_debt, shares)
        rdcf = reverse(base, price, r, TERM_G, net_debt, shares)

    return {
        "p": price, "mc": mcap, "sh": shares,
        "peT": pe_t, "peF": pe_f, "evE": ev_e, "pfcf": pfcf, "fcfy": fcfy, "ps": ps,
        "revG": rev_g, "revC3": rev_c3, "epsG": eps_g, "fcfG": fcf_g, "peg": peg,
        "gm": gm, "om": om, "roic": roic, "roicM": moat_s,
        "fcfNi": fcf_ni,
        "ndE": nd_e, "icov": icov, "shC": sh_c,
        "histPe": hist_pe, "histEv": hist_ev,
        "dcfV": dcf_v, "dcfG": dcf_g, "rdcf": rdcf,
        "ev": cand(st, ["Enterprise Value"]),
    }


# ---------------------------------------------------------------- rate
def ten_year() -> float:
    """10y Treasury yield as a decimal; FRED first, Yahoo ^TNX as the fallback."""
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", "25",
             "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"],
            capture_output=True, text=True, timeout=40).stdout.strip()
        return float(out.splitlines()[-1].split(",")[1]) / 100   # FRED quotes percent
    except Exception:                                   # noqa: BLE001
        pass
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1mo&interval=1d",
        headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    closes = ((d["chart"]["result"][0]["indicators"]["quote"][0]["close"]))
    return [c for c in closes if c][-1] / 100


# ---------------------------------------------------------------- universe
def universe() -> dict:
    """ticker -> [node labels], read from the energy view's own node lists."""
    html = (ROOT / "index.html").read_text()
    out: dict[str, list[str]] = {}
    for block in ("ENERGY_NODES", "ENERGY_ENABLERS"):
        m = re.search(rf"const {block}=\[(.*?)\n\];", html, re.S)
        if not m:
            raise SystemExit(f"{block} not found in index.html")
        for lab, cos in re.findall(r'label:"([^"]+)"[^}]*?cos:\[([^\]]*)\]',
                                   m.group(1)):
            for t in re.findall(r'"([A-Z.\-]{1,6})"', cos):
                out.setdefault(t, []).append(lab)
    return out


def main() -> None:
    inj = "--inject" in sys.argv
    uni = universe()
    print(f"{len(uni)} tickers in the energy view", flush=True)
    dgs10 = ten_year()
    print(f"10y Treasury {dgs10*100:.2f}%", flush=True)

    fin, fails = {}, []
    def work(t):
        time.sleep(PAUSE)
        return build(t, dgs10)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(work, t): t for t in uni}
        done = 0
        for f in futs:
            t = futs[f]
            try:
                fin[t] = f.result()
            except Exception as e:                      # noqa: BLE001
                fails.append((t, f"{type(e).__name__}: {e}"))
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(uni)} …", flush=True)
    for t, e in fails:
        print(f"  !! {t}: {e}", flush=True)

    # peer medians: the same stage of the chain, charted companies only
    for t in fin:
        node = (uni.get(t) or [None])[0]
        if not node:
            continue
        peers = [k for k, v in uni.items() if node in v and k in fin]
        if len(peers) < 2:
            continue
        pes = [fin[k]["peT"] for k in peers if fin[k].get("peT")]
        evs = [fin[k]["evE"] for k in peers if fin[k].get("evE")]
        mine = fin[t].get("peT")
        fin[t].update({
            "peerPe": med(pes), "peerEv": med(evs),
            "peerN": len(peers), "peerM": len(pes),
            "peerRank": (1 + sum(1 for x in pes if x < mine)) if mine else None,
        })

    meta = {
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dgs10": dgs10, "erp": ERP, "term": TERM_G, "yrs": YEARS, "cap": CAP_G,
        "src": "stockanalysis.com statements and ratios, FRED DGS10",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(fin, indent=1, sort_keys=True))
    print(f"wrote {OUT} ({len(fin)}/{len(uni)} ok, {len(fails)} failed)", flush=True)
    if inj:
        inject(fin, meta)


def inject(fin: dict, meta: dict) -> None:
    p = ROOT / "index.html"
    html = p.read_text()
    body = ("const FIN=" + json.dumps(fin, sort_keys=True, separators=(",", ":"))
            + ";\nconst FIN_META=" + json.dumps(meta, separators=(",", ":")) + ";\n")
    new, n = re.subn(r"/\* <<<FIN>>> \*/.*?/\* <<<END FIN>>> \*/",
                     "/* <<<FIN>>> */\n" + body + "/* <<<END FIN>>> */",
                     html, flags=re.S)
    if not n:
        raise SystemExit("FIN markers not present in index.html")
    p.write_text(new)
    print(f"injected {len(fin)} tickers into index.html", flush=True)


if __name__ == "__main__":
    main()

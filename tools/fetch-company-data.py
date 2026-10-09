#!/usr/bin/env python3
"""Fetch real company facts + recent news for the Energy Value Chain infographic.

Everything here is sourced live — nothing is invented. Any field that cannot be
resolved comes back null and the panel simply omits that row.

Sources (no API keys):
  * Wikidata wbsearchentities -> the company entity (QID) + its enwiki sitelink
  * Wikidata claims           -> inception P571, employees P1128, exchange P414,
                                 ticker P249, HQ P159, industry P452, website P856
  * Wikipedia REST summary    -> short description + "headquartered in ..." string
  * Wikipedia wikitext        -> infobox fallbacks when Wikidata lacks a claim
  * Google News RSS           -> recent dated headlines with source + link

Usage:
  python3 tools/fetch-company-data.py            # write data/company-data.json
  python3 tools/fetch-company-data.py --inject   # …and splice it into index.html
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
UA = "energy-infographic/1.0 (personal project; +https://github.com/jacoblbagent/energy-infographic)"
NEWS_DAYS = 120
NEWS_KEEP = 4
WORKERS = 4

# ticker -> (wikidata search name, news query, optional pinned QID)
COMPANIES = {
    "XOM":   ("ExxonMobil", "ExxonMobil", None),
    "CVX":   ("Chevron Corporation", "Chevron", None),
    "COP":   ("ConocoPhillips", "ConocoPhillips", None),
    "OXY":   ("Occidental Petroleum", "Occidental Petroleum", None),
    "EOG":   ("EOG Resources", "EOG Resources", None),
    "FANG":  ("Diamondback Energy", "Diamondback Energy", None),
    "BTU":   ("Peabody Energy", "Peabody Energy", None),
    "CEIX":  ("CONSOL Energy", "CONSOL Energy", None),
    "ARLP":  ("Alliance Resource Partners", "Alliance Resource Partners", None),
    "CCJ":   ("Cameco", "Cameco", None),
    "LEU":   ("Centrus Energy", "Centrus Energy", None),
    "BWXT":  ("BWX Technologies", "BWX Technologies", None),
    "FSLR":  ("First Solar", "First Solar", None),
    "ENPH":  ("Enphase Energy", "Enphase Energy", None),
    "SEDG":  ("SolarEdge", "SolarEdge", None),
    "RUN":   ("Sunrun", "Sunrun", None),
    "DAR":   ("Darling Ingredients", "Darling Ingredients", None),
    "GPRE":  ("Green Plains", "Green Plains", None),
    "BEP":   ("Brookfield Renewable Partners", "Brookfield Renewable", None),
    "ENB":   ("Enbridge", "Enbridge", None),
    "KMI":   ("Kinder Morgan", "Kinder Morgan", None),
    "WMB":   ("Williams Companies", "Williams Companies", None),
    "OKE":   ("ONEOK", "ONEOK", None),
    "ET":    ("Energy Transfer LP", "Energy Transfer", None),
    "LNG":   ("Cheniere Energy", "Cheniere Energy", None),
    "NFE":   ("New Fortress Energy", "New Fortress Energy", None),
    "VLO":   ("Valero Energy", "Valero Energy", None),
    "MPC":   ("Marathon Petroleum", "Marathon Petroleum", None),
    "PSX":   ("Phillips 66", "Phillips 66", None),
    "PBF":   ("PBF Energy", "PBF Energy", None),
    "DOW":   ("Dow Inc.", "Dow Inc", None),
    "LYB":   ("LyondellBasell", "LyondellBasell", None),
    "NEE":   ("NextEra Energy", "NextEra Energy", None),
    "CEG":   ("Constellation Energy", "Constellation Energy", None),
    "VST":   ("Vistra Corp", "Vistra", None),
    "NRG":   ("NRG Energy", "NRG Energy", None),
    "AES":   ("AES Corporation", "AES Corporation", None),
    "FLNC":  ("Fluence", "Fluence Energy", "Q131886718"),
    "TSLA":  ("Tesla, Inc.", "Tesla energy storage", None),
    "ALB":   ("Albemarle Corporation", "Albemarle Corporation", None),
    "PLUG":  ("Plug Power", "Plug Power", None),
    "DUK":   ("Duke Energy", "Duke Energy", None),
    "SO":    ("Southern Company", "Southern Company", None),
    "D":     ("Dominion Energy", "Dominion Energy", None),
    "AEP":   ("American Electric Power", "American Electric Power", None),
    "EXC":   ("Exelon", "Exelon", None),
    "SRE":   ("Sempra", "Sempra", None),
    "NI":    ("NiSource", "NiSource", None),
    "ATO":   ("Atmos Energy", "Atmos Energy", None),
    "SLB":   ("Schlumberger", "SLB oilfield", None),
    "HAL":   ("Halliburton", "Halliburton", None),
    "BKR":   ("Baker Hughes", "Baker Hughes", None),
    "NOV":   ("NOV Inc.", "NOV Inc drilling", None),
    "GEV":   ("GE Vernova", "GE Vernova", None),
    "ETN":   ("Eaton Corporation", "Eaton Corporation", None),
    "PWR":   ("Quanta Services", "Quanta Services", None),
    "EMR":   ("Emerson Electric", "Emerson Electric", None),
    "HUBB":  ("Hubbell Incorporated", "Hubbell", None),
    "SQM":   ("Sociedad Química y Minera", "SQM lithium", None),
    "MP":    ("MP Materials", "MP Materials", None),
    "FCX":   ("Freeport-McMoRan", "Freeport-McMoRan", None),
    "MSFT":  ("Microsoft", "Microsoft data center power", None),
    "AMZN":  ("Amazon (company)", "Amazon data center energy", None),
    "GOOGL": ("Alphabet Inc.", "Google data center energy", None),
    "META":  ("Meta Platforms", "Meta data center energy", None),
}

EXCHANGE_SHORT = {
    "New York Stock Exchange": "NYSE", "Nasdaq": "NASDAQ", "Nasdaq Stock Market": "NASDAQ",
    "Toronto Stock Exchange": "TSX", "New York Stock Exchange Arca": "NYSE Arca",
    "Santiago Stock Exchange": "BCS", "Australian Securities Exchange": "ASX",
    "London Stock Exchange": "LSE", "Frankfurt Stock Exchange": "FRA",
    "Copenhagen Stock Exchange": "CSE", "Nasdaq Nordic": "NASDAQ Nordic",
}

CORP_HINT = re.compile(
    r"company|corporation|corporat|business|enterprise|firm|utility|manufacturer|"
    r"producer|operator|provider|supplier|retailer|holding|subsidiary|bank|"
    r"conglomerate|multinational|developer|refiner|mining|energy|oil|gas|electric|"
    r"petroleum|chemical|semiconductor|technology", re.I)
NOT_PERSON = re.compile(
    r"businessman|businesswoman|entrepreneur|\bborn\b|human|politician|investor|"
    r"person|actor|athlete|singer|footballer", re.I)


# ------------------------------------------------------------------ plumbing
def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:20]
    return CACHE / h


def get(url: str, tries: int = 4) -> bytes:
    """GET with an on-disk cache and backoff. Raises on the final failure."""
    CACHE.mkdir(exist_ok=True)
    cp = _cache_path(url)
    if cp.exists():
        return cp.read_bytes()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            cp.write_bytes(body)
            return body
        except Exception as e:            # noqa: BLE001 - 404 and 429 both land here
            last = e
            if "404" in str(e):
                raise
            time.sleep(1.5 * (i + 1))
    raise last if last else RuntimeError("fetch failed")


def get_json(url: str):
    return json.loads(get(url).decode("utf-8", "replace"))


def strip_markup(s: str) -> str:
    s = re.sub(r"<br\s*/?>", ", ", s, flags=re.I)
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ,;|")


# ------------------------------------------------------------------ wikidata
def wd_search(name: str):
    """(qid, enwiki_title, description) for the best entity match."""
    url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
           "&language=en&uselang=en&type=item&limit=8&search=" + urllib.parse.quote(name))
    try:
        hits = get_json(url).get("search") or []
    except Exception:
        return None, None, None
    best = None
    hits = [h for h in hits if not NOT_PERSON.search(h.get("description") or "")] or hits
    for h in hits:
        if CORP_HINT.search(h.get("description") or ""):
            best = h
            break
    if best is None:
        withdesc = [h for h in hits if h.get("description")]
        best = withdesc[0] if withdesc else (hits[0] if hits else None)
    if not best:
        return None, None, None
    return best["id"], None, best.get("description")


def sitelink(qid: str):
    url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
           "&props=sitelinks/urls|labels&sitefilter=enwiki&ids=" + qid)
    try:
        e = get_json(url)["entities"][qid]
    except Exception:
        return None
    sl = ((e.get("sitelinks") or {}).get("enwiki") or {})
    return sl.get("title")


def wd_claims(qids):
    out = {}
    qids = [q for q in qids if q]
    for i in range(0, len(qids), 45):
        chunk = qids[i:i + 45]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=claims&ids=" + "|".join(chunk))
        try:
            j = get_json(url)
        except Exception:
            continue
        for qid, ent in (j.get("entities") or {}).items():
            out[qid] = (ent or {}).get("claims") or {}
    return out


def wd_labels(qids):
    out = {}
    qids = sorted({q for q in qids if q})
    for i in range(0, len(qids), 45):
        chunk = qids[i:i + 45]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=labels&languages=en&ids=" + "|".join(chunk))
        try:
            j = get_json(url)
        except Exception:
            continue
        for qid, ent in (j.get("entities") or {}).items():
            v = (((ent or {}).get("labels") or {}).get("en") or {}).get("value")
            if v:
                out[qid] = v
    return out


def c_qids(claims, prop):
    out = []
    for c in claims.get(prop, []):
        v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def c_year(claims, prop):
    for c in claims.get(prop, []):
        v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        m = re.match(r"[+-](\d{4})", str(v.get("time", "")))
        if m:
            return int(m.group(1))
    return None


def c_amount(claims, prop):
    for c in claims.get(prop, []):
        v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        try:
            n = int(float(str(v.get("amount"))))
        except Exception:
            continue
        year = None
        for q in ((c.get("qualifiers") or {}).get("P585") or []):
            m = re.match(r"[+-](\d{4})",
                         str((((q.get("datavalue") or {}).get("value")) or {}).get("time", "")))
            if m:
                year = int(m.group(1))
        return n, year
    return None, None


def c_string(claims, prop):
    for c in claims.get(prop, []):
        v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ------------------------------------------------------------------ wikipedia
def wiki_summary(title: str):
    """(description, extract) — follows redirects."""
    t = urllib.parse.quote(title.replace(" ", "_"))
    try:
        j = get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}?redirect=true")
    except Exception:
        return None, ""
    if j.get("type") == "disambiguation":
        return None, ""
    return (j.get("description") or None), (j.get("extract") or "")


def wiki_infobox(title: str):
    """{num_employees, founded, hq} scraped from the infobox as a fallback."""
    url = ("https://en.wikipedia.org/w/api.php?action=parse&format=json&prop=wikitext"
           "&redirects=1&page=" + urllib.parse.quote(title))
    try:
        wt = get_json(url)["parse"]["wikitext"]["*"]
    except Exception:
        return {}
    out = {}

    def field(*names):
        for n in names:
            m = re.search(r"\|\s*" + n + r"\s*=\s*([^\n|]*(?:\[\[[^\]]*\]\][^\n|]*)*)", wt, re.I)
            if m:
                v = strip_markup(m.group(1))
                if v:
                    return v
        return None

    # read employees off the RAW value: the number often lives inside a template
    # ({{circa|56,000}}, {{increase}} 134,785) that markup-stripping would eat
    emp_raw = re.search(r"\|\s*(?:num_employees|number_of_employees|employees)\s*=\s*([^\n]*)",
                        wt, re.I)
    if emp_raw:
        v = emp_raw.group(1)
        nums = re.findall(r"\d[\d,]{2,}", v)
        if nums:
            out["employees"] = int(nums[0].replace(",", ""))
        ym = re.search(r"\b(19\d\d|20[0-4]\d)\b", v)
        if ym:
            out["employeesYear"] = int(ym.group(1))
    fnd_raw = re.search(r"\|\s*(?:founded|foundation|formed)\s*=\s*([^\n|]*)", wt, re.I)
    if fnd_raw:
        ys = [int(y) for y in re.findall(r"\b(1[6-9]\d\d|20[0-4]\d)\b", fnd_raw.group(1))]
        if ys:
            out["founded"] = min(ys)
    hq = field("hq_location", "headquarters", "hq_location_city", "location_city")
    if hq:
        out["hq"] = hq[:70]
    return out


def hq_from_extract(extract: str):
    """'…Headquartered in Austin, Texas, it designs…' -> 'Austin, Texas'.

    The keyword is case-insensitive but the place tokens stay case-sensitive
    (`[A-Z]` without a global re.I) — otherwise the trailing lowercase clause
    would be swallowed as a third token. No '.' in the class, so a place never
    runs across a sentence boundary.
    """
    m = re.search(r"(?i:headquartered in )([A-Z][\w'\- ]+(?:,\s*[A-Z][\w'\- ]+){0,2})",
                  extract or "")
    if not m:
        return None
    hq = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")
    return hq if 2 < len(hq) < 60 else None


ADDR = re.compile(r"\b\d+\b|\b(street|st\.|avenue|ave\.|boulevard|blvd|road|rd\.|drive|dr\.|"
                  r"plaza|tower|campus|building|parkway|lane|suite|floor|center)\b", re.I)


def clean_hq(v):
    """Turn an infobox/P159 value into a city-like string, dropping address parts.

    '225 Bush Street' -> None  ·  'Heritage Plaza, Houston, Texas, U.S.' -> 'Houston, Texas, U.S.'
    """
    v = strip_markup(v or "")
    parts = [p.strip() for p in v.split(",") if p.strip()]
    while parts and ADDR.search(parts[0]):
        parts.pop(0)
    v = ", ".join(parts).strip()
    if not v or len(v) > 60 or re.search(r"[{}\[\]<>|]", v):
        return None
    return v


def hq_rank(v):
    """Higher is better: a full 'City, State, Country' beats a bare city name."""
    if not v:
        return -1
    if ADDR.search(v):
        return 0
    if "," in v:
        return 3
    return 2 if len(v) > 3 else 1


def best_hq(*cands):
    scored = []
    for i, c in enumerate(cands):
        c = clean_hq(c) if c else None
        if c:
            scored.append((hq_rank(c), -len(c), -i, c))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][3]


# ------------------------------------------------------------------ news
def news_for(query: str):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query) +
           "&hl=en-US&gl=US&ceid=US:en")
    try:
        root = ET.fromstring(get(url))
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        src = item.find("source")
        source = (src.text or "").strip() if src is not None else ""
        try:
            when = parsedate_to_datetime((item.findtext("pubDate") or "").strip())
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if when < cutoff or not title or not link:
            continue
        # Google titles are "Headline - Source"; the source is also a <source> element,
        # so drop the trailing duplicate (but keep a headline that merely ends in " - x")
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)]
        elif not source and " - " in title:
            title, _, source = title.rpartition(" - ")
        title = title.strip()
        if len(title.split()) < 4:
            continue
        out.append({"t": title.strip(), "s": source.strip(), "d": when.strftime("%Y-%m-%d"),
                    "u": link})
        if len(out) >= 30:
            break
    # Google's feed order is relevance-ish; the panel wants the newest items first
    out.sort(key=lambda x: x["d"], reverse=True)
    return out[:NEWS_KEEP]


# ------------------------------------------------------------------ per company
def build(ticker, spec):
    name, news_q, pinned = spec
    if pinned:
        qid, wddesc = pinned, None
    else:
        qid, _, wddesc = wd_search(name)
    title = sitelink(qid) if qid else None
    desc, extract = wiki_summary(title) if title else (None, "")
    box = wiki_infobox(title) if title else {}
    return {
        "ticker": ticker, "name": name, "qid": qid, "wiki": title,
        "desc": desc or wddesc,
        "hq": hq_from_extract(extract),
        "founded": None, "employees": None, "employeesYear": None,
        "listed": None, "industry": None, "site": None,
        "news": news_for(f"{news_q} when:{NEWS_DAYS}d"),
        "_infobox": box,
        "_extract": extract[:400] if extract else "",
    }


def main():
    inject = "--inject" in sys.argv
    tickers = list(COMPANIES)

    print(f"resolving {len(tickers)} companies + news …", flush=True)
    base = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(build, t, COMPANIES[t]): t for t in tickers}
        for i, f in enumerate(futs, 1):
            t = futs[f]
            try:
                base[t] = f.result()
            except Exception as e:                     # noqa: BLE001
                print(f"  !! {t}: {type(e).__name__} {e}")
                base[t] = {"ticker": t, "name": COMPANIES[t][0], "news": [], "_infobox": {}}

    qids = [r.get("qid") for r in base.values() if r.get("qid")]
    print(f"wikidata claims for {len(qids)} entities …", flush=True)
    claims = wd_claims(qids)

    want = set()
    for r in base.values():
        cl = claims.get(r.get("qid") or "", {})
        want.update(c_qids(cl, "P414")[:1])
        want.update(c_qids(cl, "P452")[:1])
        want.update(c_qids(cl, "P159")[:1])
    labels = wd_labels(want)
    print(f"labels for {len(labels)} entities …", flush=True)

    for t, r in base.items():
        cl = claims.get(r.get("qid") or "", {})
        r["founded"] = c_year(cl, "P571")
        r["employees"], r["employeesYear"] = c_amount(cl, "P1128")
        tk = c_string(cl, "P249")
        ex = [labels.get(q, "") for q in c_qids(cl, "P414")[:1]]
        if ex and ex[0]:
            short = EXCHANGE_SHORT.get(ex[0], ex[0]) or None
            r["listed"] = f"{short}: {tk}" if (short and tk) else short
        elif tk:
            r["listed"] = tk
        ind = [labels.get(q, "") for q in c_qids(cl, "P452")[:1]]
        if ind and ind[0]:
            r["industry"] = ind[0]
        site = c_string(cl, "P856")
        if site:
            r["site"] = site
        box = r.pop("_infobox", {}) or {}
        # HQ: rank the prose string, the Wikidata entity label and the infobox
        # value, so a full "City, State, Country" wins over a bare street address
        r["hq"] = best_hq(r.get("hq"),
                          *[labels.get(q, "") for q in c_qids(cl, "P159")[:1]],
                          box.get("hq"))
        # employees: whichever source carries the newer point-in-time
        # (Wikidata P1128 is often years stale; the infobox is usually current)
        wd_emp, wd_yr = r["employees"], r["employeesYear"]
        bx_emp, bx_yr = box.get("employees"), box.get("employeesYear")
        if bx_emp and (not wd_emp or not wd_yr or wd_yr < 2022 or (bx_yr and bx_yr >= wd_yr)):
            r["employees"], r["employeesYear"] = bx_emp, bx_yr
        if not r["founded"] and box.get("founded"):
            r["founded"] = box["founded"]
        r.pop("_extract", None)

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "source": "Wikidata + Wikipedia + Google News RSS",
           "companies": {k: base[k] for k in tickers}}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "company-data.json").write_text(json.dumps(out, indent=1))

    def missing(f):
        return [k for k, v in base.items() if not v.get(f)]
    print("\nwrote data/company-data.json")
    for f in ("hq", "founded", "employees", "listed", "industry", "site", "desc"):
        m = missing(f)
        print(f"  {f:10} missing {len(m):2}" + (f"  {m}" if len(m) <= 12 else ""))
    print(f"  news       missing {len(missing('news')):2}"
          f"   items total {sum(len(v.get('news') or []) for v in base.values())}")
    if inject:
        inject_into_html(out)


def inject_into_html(data):
    html_path = ROOT / "index.html"
    html = html_path.read_text()
    comp = data["companies"]
    trimmed = {}
    for k, v in comp.items():
        trimmed[k] = {kk: v[kk] for kk in
                      ("name", "desc", "hq", "founded", "employees", "employeesYear",
                       "listed", "industry", "site", "wiki", "news") if v.get(kk)}
    js = json.dumps(trimmed, indent=0, ensure_ascii=False, separators=(",", ":"))
    block = ("/* <<<DATA>>> */\nconst DATA=" + js + ";\n"
             f'const NEWS_ASOF="{data["generated"]}";\n/* <<<END DATA>>> */')
    new, n = re.subn(r"/\* <<<DATA>>> \*/.*?/\* <<<END DATA>>> \*/", block, html, flags=re.S)
    if not n:
        print("!! DATA markers not found in index.html — nothing injected")
        return
    html_path.write_text(new)
    print(f"injected {len(trimmed)} companies into index.html")


if __name__ == "__main__":
    main()

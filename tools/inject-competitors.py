#!/usr/bin/env python3
"""Inject data/competitors.json into the `/* <<<PEERS>>> */ … /* <<<END PEERS>>> */`
region of index.html.

The competitor map is hand-authored (data/competitors.json) — there is no
machine-readable "competitor" field on Wikidata, so this is curated from each
company's disclosed business segments rather than fetched. This script only
formats and validates it.

Run:
    python3 tools/inject-competitors.py            # inject
    python3 tools/inject-competitors.py --check    # validate only, no write
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
SRC = ROOT / "data" / "competitors.json"

PEER_RE = re.compile(
    r'id:\s*"([^"]+)",\s*c:\s*\d+,\s*label:\s*"([^"]+)",\s*g:\s*"[^"]+",\s*cos:\s*\[([^\]]*)\]')
ENABLER_RE = re.compile(
    r'id:\s*"([^"]+)",\s*g:\s*"[^"]+",\s*label:\s*"([^"]+)",\s*cos:\s*\[([^\]]*)\]')


def charted(html: str) -> dict[str, str]:
    """ticker -> node id, for every chip every view draws.

    The chart's node/enabler lists are per-view (`ENERGY_NODES`, `AI_NODES`, …),
    so scan them all rather than one hard-coded pair.
    """
    out: dict[str, str] = {}
    for blocks_rx, rx in ((r"const [A-Z_]*NODES=\[(.*?)\n\];", PEER_RE),
                          (r"const [A-Z_]*ENABLERS=\[(.*?)\n\];", ENABLER_RE)):
        blocks = re.findall(blocks_rx, html, re.S)
        if not blocks:
            raise SystemExit(f"!! could not find a node/enabler list matching {blocks_rx!r}")
        for body in blocks:
            for m in rx.finditer(body):
                node, cos = m.group(1), re.findall(r'"([^"]+)"', m.group(3))
                for t in cos:
                    out[t] = node
    return out


def main() -> None:
    check_only = "--check" in sys.argv
    html = HTML.read_text()
    data = json.loads(SRC.read_text())
    peers = data["peers"]
    on_chart = charted(html)

    missing = [t for t in on_chart if t not in peers]
    extra = [t for t in peers if t not in on_chart]
    if missing:
        print(f"!! no competitor entry for charted tickers: {', '.join(sorted(missing))}")
    if extra:
        print(f"!! competitor entry for tickers not on the chart: {', '.join(sorted(extra))}")

    # a charted peer needs no display name (CO supplies it); drop it so the
    # region stays as small as possible
    trimmed = {}
    for tk, rec in peers.items():
        clean = []
        for p in rec["peers"]:
            p = dict(p)
            if p.get("t") in on_chart:
                p.pop("n", None)
            elif not p.get("n"):
                print(f"!! {tk}: off-chart peer {p.get('t')!r} has no display name")
            clean.append(p)
        rec = {"basis": rec["basis"], "peers": clean}
        if rec.get("note"):
            rec["note"] = rec["note"]
        trimmed[tk] = rec

    js = json.dumps(trimmed, indent=0, ensure_ascii=False, separators=(",", ":"))
    block = ("/* <<<PEERS>>> */\nconst PEERS=" + js + ";\n"
             'const PEERS_NOTE="Curated from each company\'s disclosed business segments. '
             'Charted tickers open their own panel; off-chart peers are listed for context.";\n'
             "/* <<<END PEERS>>> */")

    if re.search(r"/\* <<<PEERS>>> \*/.*?/\* <<<END PEERS>>> \*/", html, re.S):
        new, n = re.subn(r"/\* <<<PEERS>>> \*/.*?/\* <<<END PEERS>>> \*/", block,
                         html, flags=re.S)
    else:
        anchor = "/* <<<END VOL>>> */"
        if anchor not in html:
            raise SystemExit("!! no <<<END VOL>>> anchor to insert the PEERS region after")
        new = html.replace(anchor, anchor + "\n" + block, 1)
        n = 1
    if not n:
        raise SystemExit("!! injection failed")

    if check_only:
        print(f"checked {len(trimmed)} companies / {sum(len(v['peers']) for v in trimmed.values())} peer links "
              f"(no write)")
        return
    HTML.write_text(new)
    print(f"injected {len(trimmed)} companies / "
          f"{sum(len(v['peers']) for v in trimmed.values())} peer links into index.html")


if __name__ == "__main__":
    main()

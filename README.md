# The Energy Value Chain — web infographic

**🔗 Live:** https://jacoblbagent.github.io/energy-infographic/
**Repo:** https://github.com/jacoblbagent/energy-infographic
**Local:** http://localhost:5184/  ·  **Tailnet:** http://jlb-hermes.tail1caa84.ts.net:5184/

A single-file, dependency-free web infographic showing the public companies in
each sector of the energy industry and how the sectors interact. Data-driven
SVG built at load time from a few JS structures, no build step, no framework.

**Purpose:** one screen that answers "who is in this sector, and how does what
they make reach the next sector" — minimal chrome, minimal text.

**Stack:** plain HTML + inline CSS + vanilla JS; the diagram is generated SVG
(`index.html` is the whole app). No npm, no bundler.

**Servers:** `python3 -m http.server 5184 --bind 127.0.0.1`, started by the
Hermes web UI Projects tab via `~/Code/hermes-web-ui/scripts/start-energy-infographic.sh`.

## What it shows

Five stages read left to right, 89 tickers across 20 sector nodes:

1. **Primary Energy** — Oil & Gas (XOM CVX COP OXY EOG FANG EQT), Coal (BTU CEIX
   ARLP), Uranium & Fuel (CCJ LEU BWXT), Solar & Wind (FSLR ENPH SEDG RUN),
   Bio & Hydro (DAR GPRE BEP)
2. **Midstream & Transport** — Pipelines & Storage (ENB KMI WMB OKE ET EPD TRGP),
   LNG & Export (LNG NFE VG), Marine Transport (FRO INSW GLNG FLNG)
3. **Conversion & Generation** — Refining & Fuels (VLO MPC PSX PBF), Chemicals
   (DOW LYB), Power Generation (NEE CEG VST NRG AES TLN), Storage & Hydrogen
   (FLNC TSLA ALB PLUG APD LIN BE)
4. **Delivery** — Electric Utilities (DUK SO D AEP EXC), Gas Utilities (SRE NI ATO)
5. **End Use** — Homes & Buildings (GNRC JCI TT), Transport (CHPT EVGO CLNE),
   Industry (NUE AA), Data Centers (MSFT AMZN GOOGL META)

Plus an **ENABLERS** band — Services & Drilling (SLB HAL BKR NOV RIG VAL NE),
Power & Grid Equipment (GEV ETN PWR EMR HUBB VRT) and Materials & Mining
(SQM MP FCX) — that feeds every stage, and a dashed **revenue & capital returns**
loop from end use back to the producers.

The shape is deliberate: every stage holds real companies, including the demand
side, so the end-use column is not a label. Marine Transport exists because
stage 02 is the transport stage and pipelines alone left the marine leg of the
chain invisible; the same-column `lng → marine` edge is drawn as a hook out of
the right side of the column rather than a backwards line through the cards.

Three edge styles carry the meaning: solid arrows = energy flow, dashed grey =
supplies/services, dashed orange = capital returns.

## Interaction

- Hovering any node dims everything unrelated, thickens the traced edges, and
  reveals the flow labels for those edges (only a curated subset is labelled in
  the static view — the rest appear on trace; unrelated labels fade back).
- **Clicking a node card pins its path.** The trace then holds — the node keeps a
  slightly stronger outline and unrelated nodes stay dimmed — and hover previews
  are suppressed, so the selection cannot shift until you click away: the canvas,
  another node, another ticker, Esc, or the panel's ×. Clicking a ticker chip pins
  the same way and opens the panel.
- Hovering a ticker chip shows a one-line tooltip: ticker + company name (no
  sector subtext — the sector lives in the panel and the diagram's own card).
- **Clicking a ticker chip opens the company panel** on the right: ticker (in its
  sector colour), company name, a 2–3 word type tag, the Wikidata descriptor, its
  stage in the chain (`03 CONVERSION & GENERATION · Power Generation`), a one-line
  description, a **Company** block of sourced facts (Listed / Industry / HQ /
  Founded / Employees), its **Flows** — `→` what it supplies and `←` what it
  receives, with the edge's label where one exists — a **Recent news** list of
  dated, sourced, linked headlines, and links out to the company's site, its
  Wikipedia article and a live news search. The selected chip is outlined in its
  sector colour and the diagram traces that company's connections while the panel
  is open. Esc, a click on the diagram background, or the × closes it.
- The panel is a real flex column, not an overlay: opening it reflows the diagram
  (the SVG is `width:100%`), so nothing is ever covered. Below 1180px viewport it
  switches to a right-side overlay with a shadow instead of crushing the diagram.
- **The market rail** is the persistent section on the right, with two tabs.
  **Volume** ranks every ticker on the chart by shares traded in the current
  session — rank, ticker, name, a proportional bar, volume and % change (hover a
  row for price and venue). **News** merges every headline in `DATA` into one
  feed: filter it to a ticker or company name, and order it by *Priority* (source
  tier, then recency) or *Newest*. Any row, and the ticker chip on any headline,
  opens the same company panel a chip click does. The `›` control collapses the
  rail; below 1180px it becomes an overlay toggled by the floating **Feed**
  button, and opening a company from it steps the rail aside.

## Company data and news

Two layers, both data-driven:

- `CO` in `index.html` — the hand-written layer: `TK: ["Name", "Type tag",
  "One-liner"]`. The stage, sector colour and flow lists are derived from the graph
  (`NODES`/`EDGES`) at click time.
- `DATA` in `index.html`, between the `/* <<<DATA>>> */` and `/* <<<END DATA>>> */`
  markers — the fetched layer: descriptor, HQ, founded, employees (+year), exchange,
  industry, official site, Wikipedia title and up to four dated news items. **Never
  hand-edit inside those markers**; they are rewritten wholesale by the fetcher.

`tools/fetch-company-data.py` builds `DATA` from live sources, with no API keys:

| Source | Gives |
|---|---|
| Wikidata `wbsearchentities` / `wbgetentities` | the company entity, inception `P571`, employees `P1128`, exchange `P414`, ticker `P249`, HQ `P159`, industry `P452`, website `P856` |
| Wikipedia REST summary | the one-line descriptor + a `headquartered in …` string |
| Wikipedia infobox (wikitext) | fallbacks when Wikidata lacks a claim — the employee count is usually only in the infobox, and it is generally *fresher* than `P1128` |
| Google News RSS | recent dated headlines with source name and article link |

```bash
python3 tools/fetch-company-data.py            # write data/company-data.json
python3 tools/fetch-company-data.py --inject   # …and splice it into index.html
```

Nothing is invented. Every field that cannot be sourced comes back `null` and the
panel omits that row, so six companies (ARLP, DAR, NFE, FLNC, INSW, FLNG) show a
shorter Company block — none of them has a Wikipedia article to fall back on.
Headlines are
filtered to the last 120 days, sorted newest-first, and the panel footers the list
with the fetch date ("Headlines via Google News, as of 9 Oct 2026") so a stale
snapshot is always visible as one. HTTP responses are cached under `.cache/`
(gitignored) so re-runs are cheap and the sources are hit once.

## The market rail

The section on the right is two panes over the same universe the diagram draws —
the `cos:` lists of `NODES` + `ENABLERS` — so a ticker added to the chart shows up
there with no further work.

- **Volume** ranks the chart's tickers by shares traded in the current session
  (bar, volume, % change; price and venue on hover). It reads the `VOL` snapshot:

  ```bash
  python3 tools/fetch-market-volume.py            # data/market-volume.json
  python3 tools/fetch-market-volume.py --inject   # …and splice VOL into index.html
  ```

  The script quotes every chart ticker in one pass from the CNBC quote
  web-service — no key, many symbols per request — and writes a
  `/* <<<VOL>>> */ … /* <<<END VOL>>> */` region of its own, so it never touches
  the `DATA` block the other fetcher rewrites. The rail labels the list with the
  market timestamp behind it ("Top volume · as of 1:13 PM EDT, 9 Oct"), so a stale
  snapshot reads as one, and it lists only the tickers that actually report a
  volume. Re-run it to refresh; nothing is invented.
- **News** takes every dated headline already in `DATA[tk].news`, merges them,
  drops duplicate copies of the same story (the best-sourced one wins) and sorts
  either by source tier then recency (**Priority** — Reuters / Bloomberg / WSJ /
  CNBC first) or purely by date (**Newest**). The filter box narrows the feed to
  one ticker or company name; 40 are shown at a time with "show more" for the rest.

Both panes open the company panel, and the rail collapses with the `›` control.

## Verified

Rendered in Chromium at 1660×1000 (the SVG viewBox): 18 nodes, 32 edges, 89
ticker chips, no chip escaping its card, no label collisions (13 static labels,
none within 11px vertically and 70px horizontally of another), content inside the
viewBox, horizontal scroll below 900px (`min-width` on the SVG, scrollable
`#stage`). Hover/trace behaviour checked by dispatching `mouseenter` and asserting
the edge and dim classes. Panel checked by dispatching `click` on chips: XOM →
ExxonMobil with three SUPPLIES TO rows and its three edges highlighted; NEE → four
RECEIVES FROM + two SUPPLIES TO; SLB (enabler) → "supplies every stage"; MSFT →
Data Centers. Esc, background click and the × all close it and leave no `.sel`,
`.dim`, `.hl` or `.fade` classes behind. The panel's fetched layer was asserted for
several tickers — XOM renders five fact rows (NYSE / Petroleum industry / Spring,
Texas / 1882 / 57,900 (2025)), four dated Reuters/WSJ/Yahoo headlines and both the
Website and Wikipedia links; ARLP degrades to a single Industry row and a Website
link with no Wikipedia article; CEG shows live Oct-2026 headlines about Google's
3.6 GW nuclear PPA, which is the same `gen → dc` PPA edge the diagram traces. No
document overflow at 1560px with the 400px panel open.

The market rail was verified at 1600×1000 and 820×900: 87 volume rows sorted
descending (TSLA 27.4M … ARLP 82.8K) from a live CNBC snapshot covering all 89
chart tickers; the News tab merges 356 headlines into 346 after de-duplication
and shows 40 with a "show more of 346"; *Priority* orders Reuters/CNBC first,
*Newest* puts the latest date first, and filtering to `XOM` returns only XOM rows.
Clicking a volume row opens the panel on that company (AMZN → Data Centers, 400px,
5 fact rows, 4 headlines), outlines its chip and dims the rest of the diagram; the
`›` control gives the 320px back to the diagram, and at 820px the rail is a fixed
overlay reached from the **Feed** button with the panel stacked above it (z-index
35 over 30). No document overflow at 1600px with the panel and the rail both open.

Data coverage from the last fetch: HQ 83/89, founded 73/89, employees 78/89
(headcounts older than 2018 are dropped rather than shown stale), exchange 80/89,
industry 67/89, official site 87/89, descriptor 85/89, news 89/89
(356 items, all within the last 120 days, none of them ticker/quote pages).

## Note

Illustrative only — tickers are examples of public listings and the flows and
ownership shown are simplified. Not investment advice.

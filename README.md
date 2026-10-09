# The Energy Value Chain — web infographic

**🔗 Local:** http://localhost:5184/  ·  **Tailnet:** http://jlb-hermes.tail1caa84.ts.net:5184/

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

Five stages read left to right:

1. **Primary Energy** — Oil & Gas (XOM CVX COP OXY EOG FANG), Coal (BTU CEIX
   ARLP), Uranium & Fuel (CCJ LEU BWXT), Solar & Wind (FSLR ENPH SEDG RUN),
   Bio & Hydro (DAR GPRE BEP)
2. **Midstream & Transport** — Pipelines & Storage (ENB KMI WMB OKE ET),
   LNG & Export (LNG NFE)
3. **Conversion & Generation** — Refining & Fuels (VLO MPC PSX PBF), Chemicals
   (DOW LYB), Power Generation (NEE CEG VST NRG AES), Storage & Hydrogen
   (FLNC TSLA ALB PLUG)
4. **Delivery** — Electric Utilities (DUK SO D AEP EXC), Gas Utilities (SRE NI ATO)
5. **End Use** — Homes & Buildings, Transport, Industry, Data Centers
   (MSFT AMZN GOOGL META)

Plus an **ENABLERS** band (oilfield services, power & grid equipment, materials
& mining) that feeds every stage, and a dashed **revenue & capital returns**
loop from end use back to the producers.

Three edge styles carry the meaning: solid arrows = energy flow, dashed grey =
supplies/services, dashed orange = capital returns.

## Interaction

- Hovering any node dims everything unrelated, thickens the traced edges, and
  reveals the flow labels for those edges (only a curated subset is labelled in
  the static view — the rest appear on trace; unrelated labels fade back).
- Hovering a ticker chip shows a tooltip with the full company name and sector.
- **Clicking a ticker chip opens the company panel** on the right: ticker (in its
  sector colour), company name, a 2–3 word type tag, its stage in the chain
  (`03 CONVERSION & GENERATION · Power Generation`), a one-line description, and
  its flows — **SUPPLIES TO** / **RECEIVES FROM** each neighbouring node, with the
  edge's label where one exists. The selected chip is outlined in its sector
  colour and the diagram traces that company's connections while the panel is
  open. Esc, a click on the diagram background, or the × closes it.
- The panel is a real flex column, not an overlay: opening it reflows the diagram
  (the SVG is `width:100%`), so nothing is ever covered. Below 880px viewport it
  switches to a right-side overlay with a shadow instead of crushing the diagram.

## Company data

All 65 tickers live in one `CO` map in `index.html`:
`TK: ["Full name", "Type tag", "One-line description"]`. The stage, sector colour
and flow lists are derived from the graph (`NODES`/`EDGES`) at click time, so a
new ticker only needs an entry in `CO` plus its node's `cos` array.

## Verified

Rendered in Chromium at 1660×1000 (the SVG viewBox): 17 nodes, 29 edges, 65
ticker chips, no chip escaping its card, no label collisions, content inside the
viewBox, horizontal scroll below 900px (`min-width` on the SVG, scrollable
`#stage`). Hover/trace behaviour checked by dispatching `mouseenter` and asserting
the edge and dim classes. Panel checked by dispatching `click` on chips: XOM →
ExxonMobil with three SUPPLIES TO rows and its three edges highlighted; NEE → four
RECEIVES FROM + two SUPPLIES TO; SLB (enabler) → "supplies every stage"; MSFT →
Data Centers. Esc, background click and the × all close it and leave no `.sel`,
`.dim`, `.hl` or `.fade` classes behind.

## Note

Illustrative only — tickers are examples of public listings and the flows and
ownership shown are simplified. Not investment advice.

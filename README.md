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
  the static view — the rest appear on trace).
- Hovering a ticker chip shows the full company name and its sector.

## Verified

Rendered in Chromium at 1660×1000 (the SVG viewBox): 17 nodes, 28 edges, no chip
escaping its card, no label collisions, content inside the viewBox, horizontal
scroll below 1060px (`min-width` on the SVG, scrollable `#frame`). Hover/trace
behaviour checked by dispatching `mouseenter` and asserting the edge and dim
classes.

## Note

Illustrative only — tickers are examples of public listings and the flows and
ownership shown are simplified. Not investment advice.

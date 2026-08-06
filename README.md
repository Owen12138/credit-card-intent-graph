# Credit Card Intent Graph

Interactive Streamlit + NetworkX + Plotly visualisation of a bank's Credit Card
intent taxonomy.

**[View the live graph →](https://owen12138.github.io/credit-card-intent-graph/)**

That link is a *static export*. GitHub Pages serves files only — it cannot run
Python — but the timeline, play button, click-to-focus, hover, zoom and pan are
all client-side, so the published page behaves exactly like the app's canvas.
Only the layout switching, filtering and sizing controls are Streamlit-only; run
the app locally for those.

## Graph structure

| Layer | Count | Connects to |
|---|---|---|
| Product — `Credit Card` | 1 | all unified intents |
| Unified intents (services) | 31 | the product, and their own 8 sub-intents |
| Sub-intents | 248 (8 per unified intent) | their parent unified intent |
| Life events | 10 | sub-intents only |
| Complaints | 10 | sub-intents only |

**300 nodes, 380 edges.**

Life events and complaints are standalone groups — they hang off sub-intents
only, never off the product or the unified intents. A single life event or
complaint can link to many sub-intents across different services (e.g.
*Travelling Abroad* touches 7 sub-intents spread over 6 unified intents).

## Conversation volumes and the timeline

Every unified intent and sub-intent carries a conversation count **for each of 5
monthly periods** (Apr–Aug 2026), and **node size is proportional to that
count**. Drag the timeline above the canvas to move through the months; the
graph re-sizes in place.

| Level | Per-period range |
|---|---|
| Unified intents | 804 – 500,000 |
| Sub-intents | 100 – ~113,000 |

A unified intent's volume is exactly the sum of its 8 sub-intents **in every
period**, so the hierarchy adds up at every point on the timeline and the app
can total conversations for any filtered view without double counting. The
slider's last stop, *All periods*, switches to all-time totals.

Each service is assigned a trend — steady, growth, decline, seasonal, or spike
(with the peak landing on a different month per service) — so a whole service
grows or shrinks as a block, which is what makes movement legible on the graph.
Individual sub-intents wobble around their parent's trend.

The numbers are synthetic but **deterministic** — the same seed always yields
the same volumes, so node sizes never shift between reruns. Replace
`volumes.generate()` with a real load (CSV, warehouse query) when actual counts
are available; nothing downstream needs to change.

### Why the graph doesn't jump when you scrub

**The timeline never reaches the server.** Every Streamlit rerun rebuilds the
chart from scratch and throws away the viewport; `uirevision` and a stable
widget `key` are supposed to survive that and don't do so reliably. So the fix
isn't to preserve state across a rerun — it's to not rerun at all.

The canvas is a self-contained page (`interactive_html.py`) embedded via
`st.iframe`, and both frequent interactions run entirely in the browser:

- **Timeline** — Plotly animation frames driven by a native slider. Each frame
  carries *only* marker sizes and hover text: no coordinates, no layout, no axis
  ranges. A period change therefore physically cannot move a node or rescale an
  axis. `export_test.py` asserts this against the serialised frames.
- **Focus** — a `plotly_click` handler that restyles opacity in place.

Neither triggers a rerun, so zoom, pan *and* the selected period all survive.
Sidebar changes still rerun and still reset the view — correctly, since every
one of them genuinely moves nodes.

On top of that, positions are pinned by construction: the layout depends only on
graph structure, never on volume, and is cached on the node set, so it's
byte-identical across periods. Axis ranges are fixed to the layout's own extent,
since Plotly would otherwise autorange around the markers and let a growing node
nudge the whole view.

### Clustered organic hubs (default layout)

Three stages, each solving a different part of the mess:

1. **Only the 31 service hubs are laid out with a spring**, so where the services
   sit stays irregular and force-directed — no ring, no fixed slots. Crucially,
   that hub graph carries an extra edge between any two services that share a
   life event or complaint. The cross-links are what wreck a plain spring; here
   they're lifted one level up, where they *place related services near each
   other* instead of dragging sub-intents around.
2. **Each service's 8 sub-intents are placed in an even flower** around their own
   parent, with the gap in the petals pointing back toward the middle so the
   product edge reaches the hub without cutting through. The radius adapts to the
   tightest hub spacing, so flowers never collide however the spring arranged
   things.
3. **Life events and complaints settle among the sub-intents they touch**, with
   everything else held fixed, so they spread out instead of stacking on a shared
   centroid.

| Layout | Cluster purity | Overlapping pairs | Related-service distance |
|---|---|---|---|
| **Clustered organic hubs** | **98.0%** | 0.011% | **0.51×** |
| Anchored wedges | 94.4% | 0.016% | — |
| Spring (force-directed) | 49.6% | 0.000% | 0.65× |

The last column is the payoff from stage 1: services that share a life event or
complaint sit at roughly half the distance of unrelated ones, so proximity on the
canvas now carries meaning.

### Anchored wedges

A plain spring layout on this graph turns into a hairball for three specific
reasons: the product hub pulls all 31 services toward the centre where they
compete for the same ring; sub-intents are degree-1 leaves with no angular
discipline, so each service's cloud overlaps its neighbours'; and the 101
life-event/complaint cross-links act as long springs that drag unrelated
services together.

The anchored layout addresses all three:

- The **product is pinned at the origin** and the **31 services pinned evenly
  around a ring**, held fixed through a short spring relax. Each service
  therefore owns an angular slice that nothing can encroach on.
- Ring order is by volume, walked in **golden-ratio strides** so the busiest
  services land on opposite sides instead of bunching into one arc.
- Each service's **8 sub-intents are seeded in a fan** just beyond its parent, at
  alternating radii so a cluster reads as a clump rather than a neat arc, with a
  little deterministic jitter.
- Sub-intents, life events and complaints are **only seeded, never pinned** — the
  relax pass lets them settle, so the result still looks force-directed rather
  than drawn with a compass.
- During that relax, **parent→child edges pull 3×** and **cross-links only 0.18×**,
  so services ball up while the cross-links stay visible without distorting the
  geometry. Those weights are applied to a throwaway copy of the graph, so the
  plain `Spring (force-directed)` option is untouched and behaves exactly as
  before.

Measured on the share of sub-intents whose *nearest* unified intent is their own
parent — which is what "messy" really meant:

| Layout | Cluster purity | Overlapping pairs |
|---|---|---|
| **Anchored wedges** | **94.4%** | 0.016% |
| Spring (force-directed) | 49.6% | 0.000% |

Loosening the relax constant to `k=0.7` pushes purity to 97% but multiplies
overlaps sevenfold, so the tuning stops short of that. `smoke_test.py` asserts
purity stays above 90% and at least 25 points ahead of the plain spring.

### Nodes are circles drawn on the graph

Zoom out and the nodes shrink with everything else, so the gaps between them
survive and they never pile up; zoom in and they grow with the layout. A node's
size relative to the drawing never changes — it reads as one dot *on the graph*
rather than a fixed blob stuck to the screen.

Plotly cannot do this natively. `scatter.marker.sizemode` offers only
`"diameter"` and `"area"`, both in **screen pixels**, so a marker keeps its pixel
size however far you zoom and appears to swell as the drawing shrinks around it.
(`layout.shapes` circles *are* data-space, but shapes carry no hover or click.)

So the scaling is done in the page — and **where** it happens is the whole
trick:

> Driving it from `plotly_relayout` does not work. That event fires *after*
> Plotly has already painted the new range using the old sizes, and once per
> scroll notch, so every notch paints twice and the nodes visibly spring between
> sizes.

Instead the page **owns zooming**. A wheel handler (plus `+` / `−` / `Reset
view`) computes the new axis ranges, the new marker sizes and the new label set,
and pushes all three through a **single `Plotly.update`** — one repaint per step,
nothing to catch up. Plotly's own zoom paths are switched off (`scrollZoom`,
double-click, and the modebar zoom buttons), because each would move the range
without touching the markers.

Zoom is clamped to `ZOOM_MIN`–`ZOOM_MAX` (0.25×–25×), and `MIN_MARKER_PX` keeps
the smallest node visible when zoomed right out.

`js_test.js` drives real wheel events and asserts the invariant directly: a
marker's pixel size times the axis span — its true width on the graph — is
identical at every zoom, and **every** range change arrives in one combined
update carrying sizes and labels with it.

### Labels appear as you zoom in

All 248 sub-intent labels at once is the single biggest source of visual noise,
so they are hidden until you zoom past **2.2×** — roughly when the middle 45% of
the canvas fills the view and only a fraction of them are on screen. The other
node types (1 product, 31 services, 10 life events, 10 complaints) are few
enough to stay labelled at every zoom.

Two details worth knowing:

- Sub-intent labels are **never emitted in the initial render**, rather than
  emitted and blanked by script. Otherwise all 248 would flash on screen while
  the page settles.
- **Focusing a node labels its neighbourhood at any zoom**, since only a handful
  of nodes are left — the zoom rule only applies when nothing is focused.

The **Sub-intent labels** button overrides the behaviour: `auto` (default) →
`always` → `off`. The `Hide sub-intent labels below` volume slider in the
sidebar is separate and composes with this — it decides which labels are
*eligible*, and zoom decides when eligible ones are *shown*.

Tune the threshold with `LABEL_ZOOM` in `interactive_html.py`.

### Click to focus

Click any node to isolate it and everything it connects to — the rest of the
graph drops to 10% opacity, unrelated edges to 5%, the focused edges are drawn
in a bold overlay, and labels are hidden outside the focus set so the
neighbourhood is readable. Click the same node again, or press **Clear**, to
restore.

**Focus depth: 1** shows direct neighbours — a unified intent gives you its 8
sub-intents plus the product; a sub-intent gives you its parent plus every life
event and complaint attached to it. **Focus depth: 2** extends to
neighbours-of-neighbours, so a service also picks up the life events and
complaints hanging off its sub-intents (Balance Transfer: 9 nodes at depth 1, 44
at depth 2).

This works on the GitHub Pages site too — it's the same page.

### Why sizes are normalised across all periods

The size scale is computed over **every period at once**, not just the selected
one. Rescaling per period would peg the busiest node to the maximum size at every
step and hide the very movement the timeline exists to show. A consequence worth
recognising: in any given month the largest node usually won't hit the maximum
size, because the all-time peak belongs to some other month.

Two further sizing details:

- **Each level is scaled within itself.** A parent is the sum of 8 children, so
  a shared scale would flatten every sub-intent to a dot. Unified intents map to
  10–72 px and sub-intents to 4–42 px, each normalised across its own level.
- **Scaling is computed on the full graph, never the filtered view**, so a node
  keeps the same size as you filter and stays comparable across views.

### Making change visible

Two controls govern how loudly a change in volume reads on the canvas.

**Scale by conversation volume** — log (default), square root, linear, uniform.
Log is the default because it makes equal *ratios* travel equal distances: a
node that doubles moves the same number of pixels whether it went 300 → 600 or
30,000 → 60,000. Square root makes a circle's *area* proportional to volume,
which is dramatic for the biggest movers but leaves ordinary nodes nearly still.
Measured across the 108 sub-intents whose volume moves more than 1.5× between
April and August:

| Scale | Typical mover | Biggest mover |
|---|---|---|
| **Log, emphasis 1.8** (default) | **4.6 px** | **12.7 px** |
| Log, no emphasis | 5.5 px | 6.8 px |
| Square root, no emphasis | 2.5 px | 16.8 px |
| Linear, no emphasis | 0.6 px | 24.9 px |

**Emphasis** (1.0–4.0, default 1.8) stretches mid-sized nodes across more of the
size range, so ordinary intents visibly move and not just the outliers. It is a
monotonic curve, so it never reorders anything — a busier node is always the
bigger node.

At the defaults a typical mover changes its drawn **area by ~1.4×**, which is
what the eye actually reads.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

## Controls

- **Timeline** (above the canvas) — drag or click through Apr–Aug 2026, or *All periods* for totals.
- **Layout** — Clustered organic hubs (default), Anchored wedges, Spring (force-directed), Radial by type, Kamada-Kawai, or Layered hierarchy.
- **View** — full graph, or focus on a single unified intent and its 2-hop neighbourhood.
- **Unified intents shown** — trim the 31 services to compare a handful side by side.
- **Scale by conversation volume** — log / square root / linear / uniform, plus **Emphasis** and a size multiplier.
- **Node types / Labels** — toggle each layer's visibility and its text labels independently.
- **Hide sub-intent labels below** — all 248 sub-intent labels show by default; raise this to keep only the busier ones when the canvas gets crowded.
- **Canvas height** — 500–1400 px.

On the canvas: scroll to zoom, drag to pan, hover a node for its conversation
volume, change since the previous month, trend, parent and degree, click a
legend entry to hide that group. The **Data** tab charts conversations over
time, ranks unified intents and sub-intents period by period, and lists both
link tables.

## Changing the timeline

Periods are defined by `volumes.PERIODS` — add or rename entries and extend
`TREND_PATTERNS` to match the new length. Everything else (slider, metrics,
sizing, tables) reads the list, so nothing is hard-coded to five.

## Files

| File | Purpose |
|---|---|
| `taxonomy.py` | All names and links. Self-validates on import. **Edit this to change the data.** |
| `volumes.py` | Conversation volumes per intent. **Swap `generate()` for real data here.** |
| `graph_builder.py` | Builds the NetworkX graph, plus filtering, layouts, and node sizing. |
| `figure.py` | Plotly rendering. Streamlit-free, so it's testable and reusable. |
| `app.py` | Streamlit UI. |
| `interactive_html.py` | The canvas: timeline frames + click-to-focus JS. Shared by the app and the export. |
| `export_static.py` | Writes `docs/index.html`, the page GitHub Pages serves. |
| `smoke_test.py` | Structural checks (counts, parentage, layouts, sizing, timeline). |
| `app_test.py` | End-to-end run of the app via `streamlit.testing.v1.AppTest`. |
| `export_test.py` | Verifies the export animates, hides labels and is self-contained. |
| `js_test.js` | Runs the shipped canvas script against a stubbed Plotly/DOM. |

```bash
python smoke_test.py
python app_test.py
python export_test.py
node js_test.js        # needs docs/index.html, so run export_static.py first
```

`js_test.js` is the one that exercises browser behaviour without a browser: it
pulls the script straight out of `docs/index.html`, stubs `Plotly` and the DOM,
then drives real zoom, click and label-mode events and asserts on the resulting
`restyle` calls.

## Publishing

`docs/index.html` is committed, and GitHub Pages serves the repo's `/docs`
folder on the `main` branch. After changing the taxonomy or volumes, regenerate
and commit it:

```bash
python export_static.py                 # all sub-intent labels, matching the app
python export_static.py --label-min 20000   # declutter: label only busier sub-intents
```

The page inlines plotly.js (~5 MB) rather than pulling it from a CDN, so it
renders offline and behind restrictive corporate proxies.

### Hosting the real Streamlit app

Pages can't run it. [Streamlit Community Cloud](https://share.streamlit.io) can:
point it at this repo, set `app.py` as the entry point, and it installs
`requirements.txt` automatically.

## Editing the taxonomy

Everything lives in `taxonomy.py`:

- `UNIFIED_INTENTS` — dict of `service name -> list of 8 sub-intent names`.
- `LIFE_EVENTS` / `COMPLAINTS` — dict of `label -> list of (unified intent, sub-intent)` pairs.

`validate()` runs on import and raises immediately on a miscount, a duplicate,
or a link that points at a sub-intent which doesn't exist under the named
unified intent — so typos surface at startup rather than as a silently missing
edge. Adjust the counts in `validate()` and `smoke_test.py` if you intentionally
move away from 31 / 8 / 10 / 10.

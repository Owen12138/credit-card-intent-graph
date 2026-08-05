# Credit Card Intent Graph

Interactive Streamlit + NetworkX + Plotly visualisation of a bank's Credit Card
intent taxonomy.

**[View the live graph →](https://owen12138.github.io/credit-card-intent-graph/)**

That link is a *static export*. GitHub Pages serves files only — it cannot run
Python — so the published page is built with Plotly animation frames instead of
Streamlit: the timeline, play button, hover, zoom and pan all work client-side,
but the layout switching, filtering and sizing controls are Streamlit-only. Run
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

Four things are deliberately pinned so that *only* size changes as you move
through time:

- **Positions.** The layout depends only on graph structure, never on volume, and
  it's cached on the node set — so it's byte-identical across periods.
- **Axis ranges.** Fixed to the layout's own extent. Plotly would otherwise
  autorange around the markers, so one node growing would nudge the whole view.
- **Zoom and pan.** A Plotly `uirevision` (see `figure.view_revision`) keyed on
  the layout algorithm and visible node set, deliberately *excluding* the period
  — so scrubbing keeps your viewport, while switching layout or filters correctly
  resets it.
- **Component identity.** `st.plotly_chart` is given a stable `key`. Without one
  Streamlit hands the chart a fresh identity on every rerun and remounts it,
  discarding the very zoom state `uirevision` exists to preserve. This is the
  part people usually miss.

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
- **Layout** — Spring (force-directed), Radial by type, Kamada-Kawai, or Layered hierarchy.
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
| `export_static.py` | Builds `docs/index.html`, the static page GitHub Pages serves. |
| `smoke_test.py` | Structural checks (counts, parentage, layouts, sizing, timeline). |
| `app_test.py` | End-to-end run of the app via `streamlit.testing.v1.AppTest`. |
| `export_test.py` | Verifies the static export animates and is self-contained. |

```bash
python smoke_test.py
python app_test.py
python export_test.py
```

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

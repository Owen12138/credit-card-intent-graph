"""Export the graph to a self-contained HTML page for GitHub Pages.

GitHub Pages serves static files only, so the Streamlit app itself cannot run
there. This builds the same graph as a single HTML file using Plotly's native
animation frames: the timeline slider, play button, hover, zoom and pan all run
client-side with no server.

    python export_static.py [--out docs/index.html] [--label-min N]

`--label-min` hides sub-intent labels below that all-time volume, which is the
static equivalent of the app's label threshold slider. The default shows every
label, matching the app.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import plotly.graph_objects as go

import graph_builder as gb
import taxonomy
import volumes
from figure import build_figure

LAYOUT = "Spring (force-directed)"
SCALE = gb.SCALE_LOG
EMPHASIS = 1.8
HEIGHT = 780

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credit Card intent graph</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2rem 1.25rem 3rem;
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1a1a1a;
    background: #ffffff;
  }}
  main {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .35rem; letter-spacing: -.01em; }}
  p.lede {{ margin: 0 0 1.25rem; color: #555; max-width: 68ch; }}
  .stats {{
    display: flex; flex-wrap: wrap; gap: .5rem 2rem;
    margin: 0 0 1.25rem; padding: .85rem 1rem;
    border: 1px solid #e4e4e7; border-radius: 8px; background: #fafafa;
  }}
  .stats div {{ font-size: .9rem; color: #555; }}
  .stats b {{ display: block; font-size: 1.15rem; color: #111; font-weight: 600; }}
  .chart {{ border: 1px solid #e4e4e7; border-radius: 8px; overflow: hidden; }}
  .chart > div {{ width: 100% !important; }}
  footer {{ margin-top: 1.5rem; font-size: .85rem; color: #666; max-width: 68ch; }}
  code {{ background: #f4f4f5; padding: .12em .4em; border-radius: 4px; font-size: .9em; }}
  a {{ color: #1d70b8; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0e0e10; color: #e8e8ea; }}
    p.lede, .stats div, footer {{ color: #a1a1aa; }}
    .stats {{ background: #161618; border-color: #2a2a2e; }}
    .stats b {{ color: #f4f4f5; }}
    .chart {{ border-color: #2a2a2e; }}
    code {{ background: #1c1c1f; }}
    a {{ color: #6cb4ee; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Credit Card intent graph</h1>
  <p class="lede">
    Product &rarr; unified intents &rarr; sub-intents, with life events and
    complaints linking in from their own groups. Node size is conversation
    volume; press <b>Play</b> or drag the timeline to move through the months.
    Positions are pinned, so everything you see moving is a real change in volume.
  </p>
  <div class="stats">
    <div>Nodes<b>{nodes}</b></div>
    <div>Edges<b>{edges}</b></div>
    <div>Unified intents<b>{unified}</b></div>
    <div>Sub-intents<b>{subs}</b></div>
    <div>Life events<b>{life}</b></div>
    <div>Complaints<b>{complaints}</b></div>
    <div>Periods<b>{periods}</b></div>
  </div>
  <div class="chart">{chart}</div>
  <footer>
    Static export of a Streamlit app &mdash; GitHub Pages cannot run Python, so
    the timeline here is driven by Plotly animation frames instead. Run
    <code>streamlit run app.py</code> from the repo for the full version with
    layout switching, filtering and per-level controls. Conversation volumes are
    synthetic but deterministic.
  </footer>
</main>
</body>
</html>
"""


def node_lists(g) -> list[tuple[str, list[str]]]:
    """Node ids per type, in exactly the order build_figure emits them."""
    out = []
    for ntype in gb.NODE_TYPES:
        nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == ntype]
        if nodes:
            out.append((ntype, nodes))
    return out


def hover_for(g, nodes: list[str], ntype: str, period: int) -> list[str]:
    """Same hover text build_figure produces, rebuilt per frame."""
    when = volumes.PERIODS[period]
    texts = []
    for n in nodes:
        data = g.nodes[n]
        parts = [f"<b>{data['label']}</b>", gb.TYPE_LABELS[ntype]]
        if data.get("parent"):
            parts.append(f"Parent: {data['parent']}")
        noun = (
            "Conversations in linked sub-intents"
            if ntype in (gb.LIFE_EVENT, gb.COMPLAINT)
            else "Conversations"
        )
        parts.append(f"{noun} ({when}): {volumes.fmt(gb.node_volume(g, n, period))}")
        change = volumes.delta(data["series"], period)
        if change is not None:
            prev = data["series"][period - 1]
            pct = f" ({change / prev:+.0%})" if prev else ""
            parts.append(f"vs {volumes.PERIODS[period - 1]}: {change:+,}{pct}")
        if data.get("trend"):
            parts.append(f"Trend: {data['trend']}")
        parts.append(f"Connections: {g.degree(n)}")
        texts.append("<br>".join(parts))
    return texts


def build(label_min: int) -> tuple[go.Figure, dict]:
    g = gb.build_graph()
    pos = gb.compute_layout(g, LAYOUT)

    labelled = {
        n
        for n, d in g.nodes(data=True)
        if d["node_type"] != gb.SUB_INTENT or d["volume"] >= label_min
    }

    # Base figure shows the first period; Play walks forward from there.
    sizes0 = gb.compute_node_sizes(g, SCALE, 1.0, 0, EMPHASIS)
    fig = build_figure(
        g, pos, sizes0, labelled, set(gb.EDGE_COLORS), HEIGHT, 0, "static"
    )

    # Map each node trace to its index so frames can target them without
    # re-sending the (much larger) edge traces on every step.
    by_name = {t.name: i for i, t in enumerate(fig.data) if t.name}
    targets = []
    for ntype, nodes in node_lists(g):
        targets.append((by_name[f"{gb.TYPE_LABELS[ntype]} ({len(nodes)})"], ntype, nodes))

    frames = []
    for t, label in enumerate(volumes.PERIODS):
        sizes = gb.compute_node_sizes(g, SCALE, 1.0, t, EMPHASIS)
        frames.append(
            go.Frame(
                name=label,
                traces=[idx for idx, _, _ in targets],
                data=[
                    go.Scatter(
                        marker=dict(size=[sizes[n] for n in nodes]),
                        hovertext=hover_for(g, nodes, ntype, t),
                    )
                    for _, ntype, nodes in targets
                ],
            )
        )
    fig.frames = frames

    def step(label):
        return dict(
            label=label,
            method="animate",
            args=[
                [label],
                dict(
                    mode="immediate",
                    frame=dict(duration=500, redraw=True),
                    transition=dict(duration=400, easing="cubic-in-out"),
                ),
            ],
        )

    fig.update_layout(
        sliders=[
            dict(
                active=0,
                x=0.06,
                len=0.94,
                y=0,
                yanchor="top",
                pad=dict(t=40, b=10),
                currentvalue=dict(prefix="Period: ", font=dict(size=14)),
                steps=[step(p) for p in volumes.PERIODS],
            )
        ],
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                showactive=False,
                x=0.005,
                y=0,
                yanchor="top",
                pad=dict(t=45, b=10),
                buttons=[
                    dict(
                        label="Play",
                        method="animate",
                        args=[
                            None,
                            dict(
                                mode="immediate",
                                fromcurrent=True,
                                frame=dict(duration=900, redraw=True),
                                transition=dict(duration=600, easing="cubic-in-out"),
                            ),
                        ],
                    ),
                    dict(
                        label="Pause",
                        method="animate",
                        args=[
                            [None],
                            dict(
                                mode="immediate",
                                frame=dict(duration=0, redraw=False),
                                transition=dict(duration=0),
                            ),
                        ],
                    ),
                ],
            )
        ],
        margin=dict(l=10, r=10, t=40, b=90),
    )

    counts = gb.summary(g)
    return fig, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument(
        "--label-min",
        type=int,
        default=0,
        help="hide sub-intent labels below this all-time volume (0 = show all)",
    )
    args = ap.parse_args()

    fig, counts = build(args.label_min)

    chart = fig.to_html(
        full_html=False,
        include_plotlyjs=True,  # inline, so the page works offline and behind proxies
        config={"scrollZoom": True, "displaylogo": False, "responsive": True},
        default_width="100%",
        default_height=f"{HEIGHT}px",
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        PAGE.format(
            chart=chart,
            nodes=counts["nodes"],
            edges=counts["edges"],
            unified=counts[gb.UNIFIED_INTENT],
            subs=counts[gb.SUB_INTENT],
            life=counts[gb.LIFE_EVENT],
            complaints=counts[gb.COMPLAINT],
            periods=volumes.N_PERIODS,
        ),
        encoding="utf-8",
    )

    # Stops GitHub Pages running the file through Jekyll.
    (out.parent / ".nojekyll").write_text("", encoding="utf-8")

    size_mb = out.stat().st_size / 1_048_576
    print(f"wrote {out} ({size_mb:.1f} MB, {len(fig.frames)} frames)")


if __name__ == "__main__":
    main()

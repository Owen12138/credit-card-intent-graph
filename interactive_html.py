"""Self-contained interactive graph page: timeline + click-to-focus, all client-side.

Both the Streamlit app and the GitHub Pages export render through here.

Why client-side
---------------
Every Streamlit rerun rebuilds the chart from scratch, which throws away the
viewport. `uirevision` is supposed to survive that and does not reliably, so
the only robust fix is to stop the frequent interactions from reaching the
server at all:

* the timeline is Plotly animation frames driven by a native slider, and the
  frames carry ONLY marker sizes and hover text - never x/y, never axis ranges,
  so a period change physically cannot move or rescale anything;
* focus is a `plotly_click` handler that restyles opacity in place.

Neither triggers a rerun, so zoom, pan and the selected period all survive.
Sidebar changes still rerun - those genuinely change node positions, so
resetting the view there is correct.
"""

from __future__ import annotations

import json

import networkx as nx
import plotly.graph_objects as go

import graph_builder as gb
import volumes
from figure import build_figure

DIV_ID = "intent-graph"

DIM_NODE = 0.10
DIM_EDGE = 0.05
FOCUS_EDGE_COLOR = "#111827"


def _hover(g: nx.Graph, nodes: list[str], ntype: str, period: int) -> list[str]:
    """Hover text for one node trace in one period."""
    when = volumes.PERIODS[period]
    out = []
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
        out.append("<br>".join(parts))
    return out


def build_figure_with_timeline(
    g: nx.Graph,
    pos: dict,
    labelled: set[str],
    scale: str = gb.SCALE_LOG,
    emphasis: float = 1.8,
    multiplier: float = 1.0,
    height: int = 780,
) -> tuple[go.Figure, dict]:
    """Base figure + one animation frame per period + the focus overlay trace.

    Returns the figure and the metadata the browser needs to run focus.
    """
    sizes0 = gb.compute_node_sizes(g, scale, multiplier, 0, emphasis)
    fig = build_figure(
        g, pos, sizes0, labelled, set(gb.EDGE_COLORS), height, 0, "static"
    )

    edge_trace_idx = [
        i for i, t in enumerate(fig.data) if t.mode == "lines" and t.name
    ]

    # Node traces, in the order build_figure emitted them.
    node_meta = []
    by_name = {t.name: i for i, t in enumerate(fig.data) if t.name}
    for ntype in gb.NODE_TYPES:
        nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == ntype]
        if not nodes:
            continue
        idx = by_name[f"{gb.TYPE_LABELS[ntype]} ({len(nodes)})"]
        node_meta.append({"trace": idx, "type": ntype, "ids": nodes})
        # customdata lets a click resolve straight back to a node id
        fig.data[idx].customdata = [[n] for n in nodes]

    # Overlay trace for the focused edges. Appended last, so it cannot disturb
    # the indices the frames target.
    fig.add_trace(
        go.Scatter(
            x=[],
            y=[],
            mode="lines",
            line=dict(width=2.4, color=FOCUS_EDGE_COLOR),
            hoverinfo="skip",
            showlegend=False,
            name="focus-edges",
        )
    )
    focus_trace = len(fig.data) - 1

    # --- frames: sizes and hover only -----------------------------------------
    frames = []
    for t, label in enumerate(volumes.PERIODS):
        sizes = gb.compute_node_sizes(g, scale, multiplier, t, emphasis)
        frames.append(
            go.Frame(
                name=label,
                traces=[m["trace"] for m in node_meta],
                data=[
                    go.Scatter(
                        marker=dict(size=[sizes[n] for n in m["ids"]]),
                        hovertext=_hover(g, m["ids"], m["type"], t),
                    )
                    for m in node_meta
                ],
            )
        )
    fig.frames = frames

    def step(label, t):
        total = volumes.fmt(
            sum(
                gb.node_volume(g, n, t)
                for n, d in g.nodes(data=True)
                if d["node_type"] == gb.SUB_INTENT
            )
        )
        return dict(
            label=label,
            method="animate",
            args=[
                [label],
                dict(
                    mode="immediate",
                    frame=dict(duration=450, redraw=True),
                    transition=dict(duration=380, easing="cubic-in-out"),
                ),
            ],
            # shown by the slider's currentvalue
            value=f"{label}  -  {total} conversations",
        )

    fig.update_layout(
        sliders=[
            dict(
                active=0,
                x=0.08,
                len=0.92,
                y=0,
                yanchor="top",
                pad=dict(t=44, b=8),
                currentvalue=dict(prefix="", font=dict(size=13)),
                steps=[step(p, t) for t, p in enumerate(volumes.PERIODS)],
            )
        ],
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                showactive=False,
                x=0,
                y=0,
                yanchor="top",
                pad=dict(t=49, b=8),
                buttons=[
                    dict(
                        label="Play",
                        method="animate",
                        args=[
                            None,
                            dict(
                                mode="immediate",
                                fromcurrent=True,
                                frame=dict(duration=850, redraw=True),
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
        margin=dict(l=10, r=10, t=40, b=95),
    )

    meta = {
        "nodeTraces": node_meta,
        "edgeTraces": edge_trace_idx,
        "focusTrace": focus_trace,
        "adjacency": {n: sorted(g.neighbors(n)) for n in g.nodes()},
        "pos": {n: [float(pos[n][0]), float(pos[n][1])] for n in g.nodes()},
        "labels": {n: g.nodes[n]["label"] for n in g.nodes()},
        "dimNode": DIM_NODE,
        "dimEdge": DIM_EDGE,
    }
    return fig, meta


FOCUS_JS = """
(function () {
  var META = __META__;
  var gd = document.getElementById("__DIV__");
  if (!gd) return;

  var current = null;
  var depth = 1;

  // Original label text per node trace, so clearing focus restores exactly.
  var originalText = {};
  META.nodeTraces.forEach(function (t) {
    originalText[t.trace] = (gd.data[t.trace].text || []).slice();
  });

  function neighbourhood(id, d) {
    var seen = {}, frontier = [id], i, j;
    seen[id] = true;
    for (i = 0; i < d; i++) {
      var next = [];
      frontier.forEach(function (n) {
        (META.adjacency[n] || []).forEach(function (m) {
          if (!seen[m]) { seen[m] = true; next.push(m); }
        });
      });
      frontier = next;
      if (!frontier.length) break;
    }
    return seen;
  }

  function edgeSegments(set) {
    var xs = [], ys = [];
    Object.keys(set).forEach(function (u) {
      (META.adjacency[u] || []).forEach(function (v) {
        if (!set[v] || u >= v) return;      // each undirected edge once
        var a = META.pos[u], b = META.pos[v];
        if (!a || !b) return;
        xs.push(a[0], b[0], null);
        ys.push(a[1], b[1], null);
      });
    });
    return [xs, ys];
  }

  function apply(set) {
    var opacities = [], texts = [], idx = [];
    META.nodeTraces.forEach(function (t) {
      idx.push(t.trace);
      opacities.push(t.ids.map(function (id) { return set[id] ? 1 : META.dimNode; }));
      texts.push(t.ids.map(function (id) { return set[id] ? META.labels[id] : ""; }));
    });
    Plotly.restyle(gd, { "marker.opacity": opacities, text: texts }, idx);
    Plotly.restyle(gd, { opacity: META.dimEdge }, META.edgeTraces);
    var seg = edgeSegments(set);
    Plotly.restyle(gd, { x: [seg[0]], y: [seg[1]] }, [META.focusTrace]);
  }

  function clear() {
    current = null;
    var opacities = [], texts = [], idx = [];
    META.nodeTraces.forEach(function (t) {
      idx.push(t.trace);
      opacities.push(t.ids.map(function () { return 1; }));
      texts.push(originalText[t.trace]);
    });
    Plotly.restyle(gd, { "marker.opacity": opacities, text: texts }, idx);
    Plotly.restyle(gd, { opacity: 0.55 }, META.edgeTraces);
    Plotly.restyle(gd, { x: [[]], y: [[]] }, [META.focusTrace]);
    setBanner(null);
  }

  function focusOn(id) {
    current = id;
    var set = neighbourhood(id, depth);
    apply(set);
    setBanner(id, Object.keys(set).length - 1);
  }

  function setBanner(id, n) {
    var el = document.getElementById("focus-banner");
    if (!el) return;
    if (!id) {
      el.innerHTML = "<span class='hint'>Click any node to focus it and its "
        + "connections. Click it again, or press Clear, to show everything.</span>";
      return;
    }
    el.innerHTML = "<b>" + META.labels[id] + "</b> &middot; " + n
      + " connected node" + (n === 1 ? "" : "s") + " at depth " + depth
      + " <button id='focus-clear'>Clear</button>";
    document.getElementById("focus-clear").onclick = clear;
  }

  gd.on("plotly_click", function (ev) {
    if (!ev || !ev.points || !ev.points.length) return;
    var p = ev.points[0];
    if (!p.customdata) return;                 // an edge, not a node
    var id = Array.isArray(p.customdata) ? p.customdata[0] : p.customdata;
    if (id === current) { clear(); } else { focusOn(id); }
  });

  // Frames only carry marker.size and hovertext, so opacity should survive an
  // animation. Re-assert it when one finishes, in case a Plotly version merges
  // the whole marker object instead of just the size.
  gd.on("plotly_animated", function () {
    if (current) apply(neighbourhood(current, depth));
  });

  var depthBtn = document.getElementById("focus-depth");
  if (depthBtn) {
    depthBtn.onclick = function () {
      depth = depth === 1 ? 2 : 1;
      depthBtn.textContent = "Focus depth: " + depth;
      if (current) focusOn(current);
    };
  }

  var clearBtn = document.getElementById("focus-clear-top");
  if (clearBtn) clearBtn.onclick = clear;

  setBanner(null);
})();
"""


def focus_script(meta: dict, div_id: str = DIV_ID) -> str:
    return (
        "<script>"
        + FOCUS_JS.replace("__META__", json.dumps(meta)).replace("__DIV__", div_id)
        + "</script>"
    )


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
    margin: 0; padding: {pad};
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1a1a1a; background: #fff;
  }}
  main {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.55rem; margin: 0 0 .3rem; letter-spacing: -.01em; }}
  p.lede {{ margin: 0 0 1rem; color: #555; max-width: 70ch; }}
  .stats {{
    display: flex; flex-wrap: wrap; gap: .4rem 2rem; margin: 0 0 1rem;
    padding: .8rem 1rem; border: 1px solid #e4e4e7; border-radius: 8px;
    background: #fafafa;
  }}
  .stats div {{ font-size: .85rem; color: #555; }}
  .stats b {{ display: block; font-size: 1.1rem; color: #111; font-weight: 600; }}
  .bar {{
    display: flex; align-items: center; gap: .75rem; flex-wrap: wrap;
    margin: 0 0 .5rem; padding: .55rem .8rem; min-height: 2.6rem;
    border: 1px solid #e4e4e7; border-radius: 8px; background: #fff; font-size: .9rem;
  }}
  .bar .hint {{ color: #666; }}
  button {{
    font: inherit; font-size: .85rem; padding: .25rem .7rem; cursor: pointer;
    border: 1px solid #cfcfd4; border-radius: 6px; background: #fff; color: #222;
  }}
  button:hover {{ background: #f4f4f5; }}
  .chart {{ border: 1px solid #e4e4e7; border-radius: 8px; overflow: hidden; }}
  .chart > div {{ width: 100% !important; }}
  footer {{ margin-top: 1.2rem; font-size: .82rem; color: #666; max-width: 70ch; }}
  code {{ background: #f4f4f5; padding: .12em .4em; border-radius: 4px; font-size: .9em; }}
  a {{ color: #1d70b8; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0e0e10; color: #e8e8ea; }}
    p.lede, .stats div, footer, .bar .hint {{ color: #a1a1aa; }}
    .stats, .bar {{ background: #161618; border-color: #2a2a2e; }}
    .stats b {{ color: #f4f4f5; }}
    .chart {{ border-color: #2a2a2e; }}
    button {{ background: #1c1c1f; color: #e8e8ea; border-color: #3a3a40; }}
    button:hover {{ background: #26262a; }}
    code {{ background: #1c1c1f; }}
    a {{ color: #6cb4ee; }}
  }}
</style>
</head>
<body>
<main>
{header}
  <div class="bar">
    <button id="focus-depth">Focus depth: 1</button>
    <button id="focus-clear-top">Clear</button>
    <span id="focus-banner"></span>
  </div>
  <div class="chart">{chart}</div>
{footer}
</main>
{script}
</body>
</html>
"""

HEADER = """  <h1>Credit Card intent graph</h1>
  <p class="lede">
    Product &rarr; unified intents &rarr; sub-intents, with life events and
    complaints linking in from their own groups. Node size is conversation
    volume. Press <b>Play</b> or drag the timeline to move through the months;
    click any node to focus it and everything it connects to.
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
"""

FOOTER = """  <footer>
    Static export of a Streamlit app &mdash; GitHub Pages cannot run Python, so
    the timeline runs on Plotly animation frames and focus on a click handler,
    both entirely in the browser. Run <code>streamlit run app.py</code> from the
    repo for layout switching, filtering and the sizing controls. Conversation
    volumes are synthetic but deterministic.
  </footer>
"""


def render_page(
    g: nx.Graph,
    pos: dict,
    labelled: set[str],
    scale: str = gb.SCALE_LOG,
    emphasis: float = 1.8,
    multiplier: float = 1.0,
    height: int = 780,
    include_plotlyjs=True,
    chrome: bool = True,
) -> str:
    """Complete HTML document. `chrome=False` drops the heading and footer for
    embedding inside the Streamlit app, which supplies its own."""
    fig, meta = build_figure_with_timeline(
        g, pos, labelled, scale, emphasis, multiplier, height
    )

    chart = fig.to_html(
        full_html=False,
        include_plotlyjs=include_plotlyjs,
        div_id=DIV_ID,
        config={
            "scrollZoom": True,
            "displaylogo": False,
            "responsive": True,
            # Double-click would reset the zoom, which is exactly what we are
            # trying to protect. Clearing focus is handled by the buttons.
            "doubleClick": False,
        },
        default_width="100%",
        default_height=f"{height}px",
    )

    counts = gb.summary(g)
    header = (
        HEADER.format(
            nodes=counts["nodes"],
            edges=counts["edges"],
            unified=counts[gb.UNIFIED_INTENT],
            subs=counts[gb.SUB_INTENT],
            life=counts[gb.LIFE_EVENT],
            complaints=counts[gb.COMPLAINT],
            periods=volumes.N_PERIODS,
        )
        if chrome
        else ""
    )

    return PAGE.format(
        header=header,
        footer=FOOTER if chrome else "",
        chart=chart,
        script=focus_script(meta),
        pad="2rem 1.25rem 3rem" if chrome else "0.25rem",
    )

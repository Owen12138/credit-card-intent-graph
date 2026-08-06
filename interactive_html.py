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

# How far in you must zoom before sub-intent labels appear. 1.0 is the whole
# graph; 2.2 means roughly the middle 45% of the canvas fills the view, by which
# point only a fraction of the 248 sub-intents are on screen and their labels
# have room to sit apart. The other node types are few enough (1 product, 31
# services, 10 life events, 10 complaints) to stay labelled at every zoom.
LABEL_ZOOM = 2.2

# Nodes are meant to read as circles drawn ON the graph: zoom out and they
# shrink with everything else, so the gaps between them survive and they never
# pile up. Plotly cannot do that natively - scatter marker.sizemode offers only
# "diameter" and "area", both in screen pixels - so the scaling is done here.
#
# The trap is WHERE. Driving it from plotly_relayout means Plotly has already
# painted the new range with the old sizes before the handler runs, so each
# scroll tick paints twice and the nodes visibly spring between sizes. Instead
# the page takes over zooming entirely and pushes the new ranges and the new
# sizes through a single Plotly.update, which is one repaint per step.
ZOOM_MIN = 0.25          # how far out you may go, as a fraction of the fitted view
ZOOM_MAX = 25.0
ZOOM_STEP = 1.18         # per wheel notch
MIN_MARKER_PX = 1.2      # keeps a node visible when zoomed right out


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

    # Sub-intent labels are left out of the initial render and switched on by the
    # browser once you zoom past LABEL_ZOOM. Emitting them here and blanking them
    # in script would flash all 248 on screen while the page settles.
    initial = {n for n in labelled if g.nodes[n]["node_type"] != gb.SUB_INTENT}
    fig = build_figure(
        g, pos, sizes0, initial, set(gb.EDGE_COLORS), height, 0, "static"
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
    frame_sizes = []  # [period][trace] -> sizes at 1x, scaled by the browser
    for t, label in enumerate(volumes.PERIODS):
        sizes = gb.compute_node_sizes(g, scale, multiplier, t, emphasis)
        per_trace = [[round(sizes[n], 3) for n in m["ids"]] for m in node_meta]
        frame_sizes.append(per_trace)
        frames.append(
            go.Frame(
                name=label,
                traces=[m["trace"] for m in node_meta],
                data=[
                    go.Scatter(
                        marker=dict(size=per_trace[i]),
                        hovertext=_hover(g, m["ids"], m["type"], t),
                    )
                    for i, m in enumerate(node_meta)
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

    xr = list(fig.layout.xaxis.range)
    yr = list(fig.layout.yaxis.range)

    meta = {
        "nodeTraces": node_meta,
        "edgeTraces": edge_trace_idx,
        "focusTrace": focus_trace,
        "adjacency": {n: sorted(g.neighbors(n)) for n in g.nodes()},
        "pos": {n: [float(pos[n][0]), float(pos[n][1])] for n in g.nodes()},
        "labels": {n: g.nodes[n]["label"] for n in g.nodes()},
        # Which nodes are allowed a label at all, after the per-type toggles and
        # the volume threshold. Zoom and focus can only narrow this, never widen.
        "labelled": sorted(labelled),
        "subIntent": gb.SUB_INTENT,
        "baseSpan": abs(xr[1] - xr[0]),
        "labelZoom": LABEL_ZOOM,
        # Sizes at 1x for every period. The browser multiplies these by the
        # current zoom so a node keeps its size relative to the graph.
        "frameSizes": frame_sizes,
        "periods": list(volumes.PERIODS),
        "baseX": xr,
        "baseY": yr,
        "zoomMin": ZOOM_MIN,
        "zoomMax": ZOOM_MAX,
        "zoomStep": ZOOM_STEP,
        "minMarkerPx": MIN_MARKER_PX,
        "dimNode": DIM_NODE,
        "dimEdge": DIM_EDGE,
    }
    return fig, meta


FOCUS_JS = """
(function () {
  var META = __META__;
  var gd = document.getElementById("__DIV__");
  if (!gd) return;

  var current = null;      // focused node id, or null
  var focusSet = null;     // ids in the current focus, or null
  var depth = 1;
  var labelMode = "auto";  // auto | always | off
  var zoomedIn = false;

  var allowed = {};
  META.labelled.forEach(function (id) { allowed[id] = true; });

  // ---- labels ---------------------------------------------------------------
  // Every label decision funnels through here, so zoom and focus compose
  // instead of overwriting one another.
  function subsVisible() {
    if (labelMode === "always") return true;
    if (labelMode === "off") return false;
    return zoomedIn;
  }

  function textFor(id, isSub) {
    if (!allowed[id]) return "";                       // filtered out server-side
    if (focusSet) return focusSet[id] ? META.labels[id] : "";
    if (isSub && !subsVisible()) return "";            // too far out to be readable
    return META.labels[id];
  }

  function refreshLabels() {
    var texts = [], idx = [];
    META.nodeTraces.forEach(function (t) {
      var isSub = t.type === META.subIntent;
      idx.push(t.trace);
      texts.push(t.ids.map(function (id) { return textFor(id, isSub); }));
    });
    Plotly.restyle(gd, { text: texts }, idx);
  }

  // ---- zoom -----------------------------------------------------------------
  // The page owns zooming so that the axis ranges and the marker sizes change
  // in the SAME repaint. Letting Plotly zoom and correcting the sizes afterwards
  // from plotly_relayout paints twice per wheel notch, and the nodes visibly
  // spring between sizes.
  var period = 0;
  var zoom = 1;
  var traceIdx = META.nodeTraces.map(function (t) { return t.trace; });

  function spanX() { return META.baseX[1] - META.baseX[0]; }
  function spanY() { return META.baseY[1] - META.baseY[0]; }

  function sizesAt(z) {
    return META.frameSizes[period].map(function (arr) {
      return arr.map(function (s) {
        return Math.max(META.minMarkerPx, s * z);
      });
    });
  }

  function labelArrays() {
    return META.nodeTraces.map(function (t) {
      var isSub = t.type === META.subIntent;
      return t.ids.map(function (id) { return textFor(id, isSub); });
    });
  }

  // Keep the stored frames in step, so stepping the timeline while zoomed
  // animates to correctly scaled sizes rather than jumping back to the 1x ones.
  function rescaleFrames(z) {
    var stored = gd._transitionData && gd._transitionData._frames;
    if (!stored) return;
    stored.forEach(function (f) {
      var t = META.periods.indexOf(f.name);
      if (t === -1 || !f.data) return;
      f.data.forEach(function (d, j) {
        if (!d.marker) return;
        d.marker.size = META.frameSizes[t][j].map(function (s) {
          return Math.max(META.minMarkerPx, s * z);
        });
      });
    });
  }

  // anchorX/anchorY are data coords to hold still - the cursor, or the centre.
  function setZoom(next, anchorX, anchorY) {
    next = Math.min(META.zoomMax, Math.max(META.zoomMin, next));

    var xr = currentRange("xaxis", META.baseX);
    var yr = currentRange("yaxis", META.baseY);
    if (anchorX === undefined) anchorX = (xr[0] + xr[1]) / 2;
    if (anchorY === undefined) anchorY = (yr[0] + yr[1]) / 2;

    var newW = spanX() / next;
    var newH = spanY() / next;
    var fx = (anchorX - xr[0]) / (xr[1] - xr[0]);
    var fy = (anchorY - yr[0]) / (yr[1] - yr[0]);

    var x0 = anchorX - fx * newW;
    var y0 = anchorY - fy * newH;

    zoom = next;
    zoomedIn = zoom >= META.labelZoom;
    rescaleFrames(zoom);

    // One call: ranges, sizes and labels land in a single repaint.
    Plotly.update(
      gd,
      { "marker.size": sizesAt(zoom), text: labelArrays() },
      {
        "xaxis.range": [x0, x0 + newW],
        "yaxis.range": [y0, y0 + newH],
      },
      traceIdx
    );

    setBanner(current, current && focusSet ? Object.keys(focusSet).length - 1 : 0);
  }

  function currentRange(axis, fallback) {
    var ax = (gd._fullLayout && gd._fullLayout[axis]) || (gd.layout && gd.layout[axis]);
    return ax && ax.range ? [ax.range[0], ax.range[1]] : fallback.slice();
  }

  // Pixel -> data, using only the plot area box, so no axis internals are needed.
  function pointerData(ev) {
    var size = gd._fullLayout && gd._fullLayout._size;
    if (!size || !gd.getBoundingClientRect) return [undefined, undefined];
    var rect = gd.getBoundingClientRect();
    var fx = (ev.clientX - rect.left - size.l) / size.w;
    var fy = (ev.clientY - rect.top - size.t) / size.h;
    if (!(fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1)) return [undefined, undefined];
    var xr = currentRange("xaxis", META.baseX);
    var yr = currentRange("yaxis", META.baseY);
    return [xr[0] + fx * (xr[1] - xr[0]), yr[1] - fy * (yr[1] - yr[0])];
  }

  if (gd.addEventListener) {
    gd.addEventListener(
      "wheel",
      function (ev) {
        ev.preventDefault();
        var at = pointerData(ev);
        var dir = ev.deltaY < 0 ? META.zoomStep : 1 / META.zoomStep;
        setZoom(zoom * dir, at[0], at[1]);
      },
      { passive: false }
    );
  }

  ["zoom-in", "zoom-out", "zoom-reset"].forEach(function (id) {
    var b = document.getElementById(id);
    if (!b) return;
    b.onclick = function () {
      if (id === "zoom-reset") setZoom(1, (META.baseX[0] + META.baseX[1]) / 2,
                                          (META.baseY[0] + META.baseY[1]) / 2);
      else setZoom(zoom * (id === "zoom-in" ? META.zoomStep : 1 / META.zoomStep));
    };
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
    focusSet = set;
    var opacities = [], idx = [];
    META.nodeTraces.forEach(function (t) {
      idx.push(t.trace);
      opacities.push(t.ids.map(function (id) { return set[id] ? 1 : META.dimNode; }));
    });
    Plotly.restyle(gd, { "marker.opacity": opacities }, idx);
    Plotly.restyle(gd, { opacity: META.dimEdge }, META.edgeTraces);
    var seg = edgeSegments(set);
    Plotly.restyle(gd, { x: [seg[0]], y: [seg[1]] }, [META.focusTrace]);
    refreshLabels();
  }

  function clear() {
    current = null;
    focusSet = null;
    var opacities = [], idx = [];
    META.nodeTraces.forEach(function (t) {
      idx.push(t.trace);
      opacities.push(t.ids.map(function () { return 1; }));
    });
    Plotly.restyle(gd, { "marker.opacity": opacities }, idx);
    Plotly.restyle(gd, { opacity: 0.55 }, META.edgeTraces);
    Plotly.restyle(gd, { x: [[]], y: [[]] }, [META.focusTrace]);
    refreshLabels();
    setBanner(null);
  }

  function focusOn(id) {
    current = id;
    var set = neighbourhood(id, depth);
    apply(set);
    setBanner(id, Object.keys(set).length - 1);
  }

  function labelHint() {
    if (labelMode === "always") return "Sub-intent labels: always on.";
    if (labelMode === "off") return "Sub-intent labels: off.";
    return zoomedIn
      ? "Sub-intent labels on — zoom out to hide them again."
      : "Zoom in to reveal sub-intent labels.";
  }

  function setBanner(id, n) {
    var el = document.getElementById("focus-banner");
    if (!el) return;
    if (!id) {
      el.innerHTML = "<span class='hint'>Click any node to focus it and its "
        + "connections. " + labelHint() + "</span>";
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
  gd.on("plotly_animatingframe", function (ev) {
    if (!ev || !ev.name) return;
    var t = META.periods.indexOf(ev.name);
    if (t !== -1) period = t;
  });

  gd.on("plotly_animated", function () {
    // Frames carry marker sizes, so re-assert the focus dimming once one lands.
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

  var modes = ["auto", "always", "off"];
  var modeBtn = document.getElementById("label-mode");
  if (modeBtn) {
    modeBtn.onclick = function () {
      labelMode = modes[(modes.indexOf(labelMode) + 1) % modes.length];
      modeBtn.textContent = "Sub-intent labels: " + labelMode;
      refreshLabels();
      setBanner(current, current ? Object.keys(focusSet).length - 1 : 0);
    };
  }

  zoomedIn = zoom >= META.labelZoom;
  refreshLabels();
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
    <button id="zoom-out">&minus;</button>
    <button id="zoom-in">+</button>
    <button id="zoom-reset">Reset view</button>
    <button id="focus-depth">Focus depth: 1</button>
    <button id="label-mode">Sub-intent labels: auto</button>
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
        # plotly.py defaults auto_play to True, so ANY figure with frames starts
        # animating the moment the page loads - it emits a Plotly.animate() call
        # right after newPlot. The timeline is here to be driven, not to run on
        # its own, so it must open on the first period and stay there.
        auto_play=False,
        config={
            # Plotly's own zoom paths are switched off. Every one of them would
            # change the axis range without touching the marker sizes, leaving
            # the nodes the wrong size until something else corrected them. The
            # wheel handler and the +/- buttons are the only ways to zoom, and
            # they move ranges and sizes together.
            "scrollZoom": False,
            "doubleClick": False,
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": [
                "zoom2d",
                "zoomIn2d",
                "zoomOut2d",
                "autoScale2d",
                "resetScale2d",
                "select2d",
                "lasso2d",
            ],
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

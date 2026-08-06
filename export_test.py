"""Checks the interactive page: timeline frames, click-focus wiring, self-containment.

Covers both the GitHub Pages export and the identical canvas the Streamlit app
embeds. Run: python export_test.py
"""

import json
import re
from pathlib import Path

import graph_builder as gb
import volumes
from export_static import build_html
from interactive_html import DIV_ID, FOCUS_JS, build_figure_with_timeline

g = gb.build_graph()
pos = gb.compute_layout(g, "Spring (force-directed)")
fig, meta = build_figure_with_timeline(g, pos, set(g.nodes))

# =============================================================================
# Timeline: frames may change size and hover, and nothing else
# =============================================================================
assert len(fig.frames) == volumes.N_PERIODS, len(fig.frames)
assert [f.name for f in fig.frames] == volumes.PERIODS

# Assert on the SERIALISED frame, since that is what actually reaches the
# browser. Anything absent here cannot be animated, by construction.
ALLOWED_TRACE_KEYS = {"marker", "hovertext", "type"}
for frame in fig.frames:
    payload = frame.to_plotly_json()
    assert payload["traces"], f"frame {frame.name} targets no traces"
    assert len(payload["data"]) == len(payload["traces"]), frame.name
    # THE guarantee: a frame carries no coordinates and no layout, so changing
    # period physically cannot move a node or rescale an axis.
    assert payload.get("layout") is None, f"frame {frame.name} relayouts"
    for tr in payload["data"]:
        extra = set(tr) - ALLOWED_TRACE_KEYS
        assert not extra, f"frame {frame.name} would animate {extra}"
        assert set(tr["marker"]) == {"size"}, f"frame {frame.name}: {set(tr['marker'])}"

sizes_per_frame = [tuple(s for tr in f.data for s in tr.marker.size) for f in fig.frames]
assert len(set(sizes_per_frame)) == volumes.N_PERIODS, "frames repeat the same sizes"

# frames only target node traces, never the edge traces
node_trace_ids = {m["trace"] for m in meta["nodeTraces"]}
for frame in fig.frames:
    assert set(frame.traces) <= node_trace_ids, frame.name
assert not (set(meta["edgeTraces"]) & node_trace_ids), "edge/node traces overlap"

# axes are pinned, and double-click cannot reset them out from under the user
assert fig.layout.xaxis.autorange is False and fig.layout.xaxis.range is not None
assert fig.layout.yaxis.autorange is False and fig.layout.yaxis.range is not None

# No layout-level transition. It would apply to every re-render - including the
# initial mount and the responsive resize right after it - so the graph would
# animate its sizes into place each time the page opened. Easing between periods
# is specified per animate() call instead, below.
layout_json = fig.to_plotly_json()["layout"]
assert "transition" not in layout_json, "layout.transition makes the graph play on load"

# ...and those per-interaction transitions do exist, so Play and the slider ease
step_args = fig.layout.sliders[0].steps[0].args[1]
assert step_args["transition"]["duration"] > 0, "slider steps should ease"
play_args = fig.layout.updatemenus[0].buttons[0].args[1]
assert play_args["transition"]["duration"] > 0, "Play should ease"

# controls
assert [s.label for s in fig.layout.sliders[0].steps] == volumes.PERIODS
assert all(s.method == "animate" for s in fig.layout.sliders[0].steps)
assert [b.label for b in fig.layout.updatemenus[0].buttons] == ["Play", "Pause"]
print(f"timeline: {len(fig.frames)} frames, sizes+hover only, axes pinned")

# =============================================================================
# Focus: every node is clickable and resolves to a real node id
# =============================================================================
covered = []
for m in meta["nodeTraces"]:
    trace = fig.data[m["trace"]]
    assert trace.customdata is not None, f"trace {m['trace']} has no customdata"
    got = [row[0] for row in trace.customdata]
    assert got == m["ids"], f"customdata out of step with ids on trace {m['trace']}"
    covered += got

assert sorted(covered) == sorted(g.nodes()), "not every node is clickable"
assert set(meta["adjacency"]) == set(g.nodes())
assert set(meta["pos"]) == set(g.nodes())
assert set(meta["labels"]) == set(g.nodes())

# adjacency matches the graph, so the browser highlights the true neighbourhood
for n in g.nodes():
    assert meta["adjacency"][n] == sorted(g.neighbors(n)), n

# =============================================================================
# Semantic zoom: sub-intent labels are absent until you zoom in
# =============================================================================
for m in meta["nodeTraces"]:
    trace = fig.data[m["trace"]]
    shown = sum(1 for t in (trace.text or []) if t)

    # Every node trace must keep "+text" in its mode even when it starts with no
    # labels at all. Plotly silently ignores text restyled into a "markers"
    # trace, so without this the zoom reveal does nothing - which is exactly the
    # bug that shipped when sub-intent labels stopped being emitted up front.
    assert "text" in trace.mode, (
        f"{m['type']} trace is mode={trace.mode!r}; labels revealed later "
        "would never render"
    )

    if m["type"] == gb.SUB_INTENT:
        # Not merely blanked by script after paint - never emitted, so all 248
        # cannot flash on screen while the page settles.
        assert shown == 0, f"{shown} sub-intent labels in the initial render"
    else:
        assert shown == len(m["ids"]), (m["type"], shown, len(m["ids"]))

# ...but the browser still knows every label it may reveal
assert set(meta["labelled"]) == set(g.nodes()), "label set lost on the way out"
assert meta["subIntent"] == gb.SUB_INTENT
assert meta["labelZoom"] > 1, meta["labelZoom"]

assert meta["periods"] == volumes.PERIODS

# Nodes are circles drawn on the graph, so the browser scales them with the
# zoom. It needs the 1x sizes for every period, and they must agree with what
# the frames carry or stepping the timeline would jump to a different size.
assert len(meta["frameSizes"]) == volumes.N_PERIODS, len(meta["frameSizes"])
for t, frame in enumerate(fig.frames):
    for j, tr in enumerate(frame.data):
        assert list(tr.marker.size) == meta["frameSizes"][t][j], (t, j)
assert meta["baseX"] == list(fig.layout.xaxis.range)
assert meta["baseY"] == list(fig.layout.yaxis.range)
assert 0 < meta["zoomMin"] < 1 < meta["zoomMax"], meta
assert meta["zoomStep"] > 1 and meta["minMarkerPx"] > 0, meta

# Comments stripped, since they discuss the mechanism on purpose.
CODE = "\n".join(line.split("//")[0] for line in FOCUS_JS.splitlines())

# The page owns zooming, and range + size + labels go out in ONE Plotly.update.
# Splitting them across calls is what made the nodes spring between sizes: the
# range landed in one repaint and the sizes caught up in the next.
assert "Plotly.update(" in CODE, "zoom no longer applies changes atomically"
assert "xaxis.range" in CODE, "zoom does not set the range"
assert "marker.opacity" in CODE, "focus dimming lost"
assert 'addEventListener' in CODE and '"wheel"' in CODE, "wheel zoom not handled"

# Dragging: Plotly cannot move scatter points, so the page hit-tests and moves
# the coordinates itself. Nothing may read META.pos after startup, or a dragged
# node's edges and focus overlay would still point at where it used to be.
assert '"mousedown"' in CODE and '"mouseup"' in CODE, "drag not wired up"
assert "springHome" in CODE, "released nodes do not spring back"


def _fn(name):
    """Body of a top-level function in the canvas script."""
    start = CODE.index("function " + name)
    depth, i = 0, CODE.index("{", start)
    for j in range(i, len(CODE)):
        depth += CODE[j] == "{"
        depth -= CODE[j] == "}"
        if depth == 0:
            return CODE[start : j + 1]
    raise AssertionError(name)


# Everything that DRAWS must read the live positions. META.pos is the starting
# arrangement and the spring's target, nothing else - a renderer reading it would
# leave a dragged node's edges pointing at where it used to be.
for fn in ("redrawPositions", "edgeSegments", "hitTest"):
    assert "META.pos" not in _fn(fn), f"{fn} reads the starting positions, not POS"
assert "META.pos" in _fn("springHome"), "the spring has no home to return to"

# every edge trace must be reconstructable, or a drag cannot redraw the lines
assert len(meta["edgePairs"]) == len(meta["edgeTraces"]), meta["edgePairs"]
assert [e["trace"] for e in meta["edgePairs"]] == meta["edgeTraces"]
drawn = sum(len(e["pairs"]) for e in meta["edgePairs"])
assert drawn == g.number_of_edges(), (drawn, g.number_of_edges())
for e in meta["edgePairs"]:
    for u, v in e["pairs"]:
        assert g.has_edge(u, v), (u, v)

# ...and marker sizes must never be pushed through a plain restyle, which would
# be a second repaint after the range had already moved.
for chunk in CODE.split("Plotly.restyle(")[1:]:
    head = chunk[: chunk.find(");")]
    assert "marker.size" not in head, "markers resized in a separate repaint"
assert meta["baseSpan"] > 0, meta["baseSpan"]
# baseSpan must match the pinned axis, or the zoom factor is measured against
# the wrong reference and labels appear at the wrong moment
xr = fig.layout.xaxis.range
assert abs(meta["baseSpan"] - abs(xr[1] - xr[0])) < 1e-9, (meta["baseSpan"], xr)

# a server-side label filter narrows what zoom can reveal
sparse = {n for n, d in g.nodes(data=True) if d["node_type"] != gb.SUB_INTENT}
_, sparse_meta = build_figure_with_timeline(g, pos, sparse)
assert set(sparse_meta["labelled"]) == sparse
print(
    f"semantic zoom: sub-intent labels hidden until {meta['labelZoom']}x, "
    f"{len(meta['labelled'])} labels available"
)

# the focus overlay trace exists and starts empty
overlay = fig.data[meta["focusTrace"]]
assert overlay.name == "focus-edges"
assert not overlay.x and not overlay.y, "focus overlay should start empty"

# spot-check the neighbourhood a click would produce
ui = "Balance Transfer"
depth1 = set(meta["adjacency"][ui])
assert len(depth1) == 9, len(depth1)  # 8 sub-intents + the product node
assert gb.taxonomy.PRODUCT in depth1
subs = [n for n in depth1 if g.nodes[n]["node_type"] == gb.SUB_INTENT]
assert len(subs) == 8, len(subs)

depth2 = set(depth1)
for n in depth1:
    depth2 |= set(meta["adjacency"][n])
extra = {g.nodes[n]["node_type"] for n in depth2 - depth1}
assert gb.LIFE_EVENT in extra or gb.COMPLAINT in extra, extra
print(
    f"focus: all {len(covered)} nodes clickable; '{ui}' -> {len(depth1)} at depth 1, "
    f"{len(depth2)} at depth 2"
)

# =============================================================================
# The written page
# =============================================================================
html = build_html(label_min=0)
assert html.lstrip().startswith("<!doctype html"), html[:40]
assert "</html>" in html
assert "Plotly.newPlot" in html, "plotly bundle not inlined"
assert f'id="{DIV_ID}"' in html, "chart div id missing - focus JS cannot bind"

# self-contained: nothing fetched from another host at load time
external_scripts = re.findall(r"<script[^>]*\ssrc=[\"']([^\"']+)", html, re.I)
external_links = re.findall(r"<link[^>]*\shref=[\"'](https?://[^\"']+)", html, re.I)
assert not external_scripts, f"page loads external scripts: {external_scripts}"
assert not external_links, f"page loads external stylesheets: {external_links}"

# The page must NOT start animating on load. plotly.py defaults auto_play=True
# for any figure with frames, which emits a Plotly.animate() straight after
# newPlot and plays the timeline through on every open. Nothing here calls
# Plotly.animate directly - focus uses restyle - so any occurrence is auto-play
# having crept back.
assert "Plotly.animate(" not in html, "page auto-plays the timeline on load"

# focus wiring is present and its embedded metadata is valid JSON
assert "plotly_click" in html, "no click handler"
assert "plotly_animated" in html, "no post-animation reassert"
assert 'id="focus-depth"' in html and 'id="focus-clear-top"' in html
assert 'id="label-mode"' in html, "no label mode override"
for bid in ("zoom-in", "zoom-out", "zoom-reset"):
    assert f'id="{bid}"' in html, f"missing {bid} control"

# Plotly's own zoom paths must stay off: each one moves the range without
# touching the markers, which is exactly the mismatch being avoided.
assert '"scrollZoom": false' in html, "plotly scroll zoom still on"
assert '"doubleClick": false' in html, "double-click zoom still on"
for removed in ("zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"):
    assert removed in html, f"{removed} not removed from the modebar"
embedded = re.search(r"var META = (\{.*?\});\s*\n", html, re.S)
assert embedded, "focus metadata not embedded"
parsed = json.loads(embedded.group(1))
assert set(parsed["adjacency"]) == set(g.nodes())
assert parsed["focusTrace"] == meta["focusTrace"]

for label in volumes.PERIODS:
    assert label in html, f"{label} missing from page"

# written to disk by export_static
page = Path("docs/index.html")
if page.exists():
    mb = page.stat().st_size / 1_048_576
    assert mb < 90, f"{mb:.1f} MB exceeds GitHub's per-file comfort zone"
    assert Path("docs/.nojekyll").exists(), ".nojekyll missing"
    print(f"docs/index.html: {mb:.1f} MB, self-contained")

print("\nEXPORT TESTS PASSED")

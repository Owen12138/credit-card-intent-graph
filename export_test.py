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
from interactive_html import DIV_ID, build_figure_with_timeline

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

# focus wiring is present and its embedded metadata is valid JSON
assert "plotly_click" in html, "no click handler"
assert "plotly_animated" in html, "no post-animation reassert"
assert 'id="focus-depth"' in html and 'id="focus-clear-top"' in html
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

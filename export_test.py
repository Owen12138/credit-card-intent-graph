"""Checks the static export really is a working, self-contained page.

Run: python export_test.py
"""

import json
import re
from pathlib import Path

import graph_builder as gb
import volumes
from export_static import build

fig, counts = build(label_min=0)

# --- frames: one per period, targeting the node traces only -------------------
assert len(fig.frames) == volumes.N_PERIODS, len(fig.frames)
assert [f.name for f in fig.frames] == volumes.PERIODS, [f.name for f in fig.frames]

node_trace_names = {
    f"{gb.TYPE_LABELS[nt]} ({sum(1 for _, d in gb.build_graph().nodes(data=True) if d['node_type'] == nt)})"
    for nt in gb.NODE_TYPES
}
for frame in fig.frames:
    assert frame.traces, f"frame {frame.name} targets no traces"
    assert len(frame.data) == len(frame.traces), frame.name
    # frames must NOT carry x/y - that is what guarantees positions cannot move
    for tr in frame.data:
        assert tr.x is None and tr.y is None, f"frame {frame.name} moves nodes"
        assert tr.marker.size is not None, f"frame {frame.name} has no sizes"

# --- sizes actually differ between frames ------------------------------------
sizes_per_frame = [
    tuple(s for tr in f.data for s in tr.marker.size) for f in fig.frames
]
assert len(set(sizes_per_frame)) == volumes.N_PERIODS, "frames repeat the same sizes"

# a growing sub-intent is bigger in the last frame than the first
grower = max(
    volumes.SUB_SERIES,
    key=lambda k: volumes.SUB_SERIES[k][-1] - volumes.SUB_SERIES[k][0],
)
g = gb.build_graph()
sub_nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == gb.SUB_INTENT]
idx = sub_nodes.index(gb.sub_id(*grower))
sub_frame_data = [
    next(tr for tr in f.data if len(tr.marker.size) == len(sub_nodes))
    for f in fig.frames
]
first, last = sub_frame_data[0].marker.size[idx], sub_frame_data[-1].marker.size[idx]
assert last > first, (first, last)
print(f"'{grower[1]}' animates {first:.1f} -> {last:.1f} px across the timeline")

# --- controls -----------------------------------------------------------------
assert fig.layout.sliders, "no timeline slider"
steps = fig.layout.sliders[0].steps
assert [s.label for s in steps] == volumes.PERIODS, [s.label for s in steps]
assert all(s.method == "animate" for s in steps)
buttons = fig.layout.updatemenus[0].buttons
assert [b.label for b in buttons] == ["Play", "Pause"], [b.label for b in buttons]

# --- axes stay pinned ---------------------------------------------------------
assert fig.layout.xaxis.autorange is False and fig.layout.xaxis.range is not None
assert fig.layout.yaxis.autorange is False and fig.layout.yaxis.range is not None

# --- the written page ---------------------------------------------------------
page = Path("docs/index.html")
assert page.exists(), "run export_static.py first"
html = page.read_text(encoding="utf-8")

assert html.lstrip().startswith("<!doctype html"), html[:40]
assert "</html>" in html
assert "Plotly.newPlot" in html, "plotly bundle not inlined"

# Self-contained: nothing is fetched from another host at load time. (The
# bundle does contain a cdn.plot.ly string, but only as the default topojson
# URL for geo charts, which this page never draws - so match on real tags.)
external_scripts = re.findall(r"<script[^>]*\ssrc=[\"']([^\"']+)", html, re.I)
external_links = re.findall(r"<link[^>]*\shref=[\"'](https?://[^\"']+)", html, re.I)
assert not external_scripts, f"page loads external scripts: {external_scripts}"
assert not external_links, f"page loads external stylesheets: {external_links}"

for label in volumes.PERIODS:
    assert label in html, f"{label} missing from page"
assert ">Play<" in html or '"Play"' in html

# stats block reflects the real graph
assert f"<b>{counts['nodes']}</b>" in html, counts["nodes"]
assert f"<b>{counts[gb.SUB_INTENT]}</b>" in html

assert Path("docs/.nojekyll").exists(), ".nojekyll missing"

mb = page.stat().st_size / 1_048_576
assert mb < 90, f"{mb:.1f} MB exceeds GitHub's per-file comfort zone"
print(f"docs/index.html: {mb:.1f} MB, self-contained, {len(fig.frames)} frames")

print("\nEXPORT TESTS PASSED")

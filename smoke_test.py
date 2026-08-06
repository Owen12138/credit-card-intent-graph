"""Structural checks on the graph. Run: python smoke_test.py"""

import graph_builder as gb
import taxonomy
import volumes

g = gb.build_graph()
c = gb.summary(g)

assert c[gb.PRODUCT] == 1, c
assert c[gb.UNIFIED_INTENT] == 31, c
assert c[gb.SUB_INTENT] == 31 * 8, c
assert c[gb.LIFE_EVENT] == 10, c
assert c[gb.COMPLAINT] == 10, c
assert c["nodes"] == 1 + 31 + 248 + 10 + 10, c

# every unified intent hangs off the product and owns exactly 8 sub-intents
for ui in taxonomy.UNIFIED_INTENTS:
    assert g.has_edge(taxonomy.PRODUCT, ui), ui
    subs = [
        n
        for n in g.neighbors(ui)
        if g.nodes[n]["node_type"] == gb.SUB_INTENT
    ]
    assert len(subs) == 8, (ui, len(subs))

# life events and complaints attach ONLY to sub-intents
for n, d in g.nodes(data=True):
    if d["node_type"] in (gb.LIFE_EVENT, gb.COMPLAINT):
        for nb in g.neighbors(n):
            assert g.nodes[nb]["node_type"] == gb.SUB_INTENT, (n, nb)

def same_positions(a, b, tol=1e-9):
    return set(a) == set(b) and all(
        abs(a[n][0] - b[n][0]) < tol and abs(a[n][1] - b[n][1]) < tol for n in a
    )


# every layout produces a position for every node, deterministically
LAYOUTS = {}
for algo in gb.LAYOUTS:
    pos = gb.compute_layout(g, algo)
    assert set(pos) == set(g.nodes), algo
    assert same_positions(pos, gb.compute_layout(g, algo)), f"{algo} is not deterministic"
    LAYOUTS[algo] = pos

# filtering: one branch keeps 1 UI + 8 subs, and drops orphaned event nodes
one = gb.filter_graph(g, set(gb.NODE_TYPES), {"Travelling Abroad" and "Travel Notification"})
oc = gb.summary(one)
assert oc[gb.UNIFIED_INTENT] == 1 and oc[gb.SUB_INTENT] == 8, oc
assert all(
    any(
        one.nodes[nb]["node_type"] == gb.SUB_INTENT
        for nb in one.neighbors(n)
    )
    for n, d in one.nodes(data=True)
    if d["node_type"] in (gb.LIFE_EVENT, gb.COMPLAINT)
), "orphaned life event / complaint survived the filter"

# --- conversation volumes over time -------------------------------------------
P = volumes.N_PERIODS
assert P == 5, P
assert len(volumes.PERIODS) == P
assert len(volumes.UNIFIED_SERIES) == 31
assert len(volumes.SUB_SERIES) == 248

# every intent has one value per period
assert all(len(s) == P for s in volumes.UNIFIED_SERIES.values())
assert all(len(s) == P for s in volumes.SUB_SERIES.values())

# every sub-intent is at or above the floor in every period
assert min(min(s) for s in volumes.SUB_SERIES.values()) >= volumes.MIN_SUB_VOLUME

# a unified intent is exactly the sum of its 8 sub-intents, in EVERY period
for ui, subs in taxonomy.UNIFIED_INTENTS.items():
    for t in range(P):
        rolled = sum(volumes.SUB_SERIES[(ui, s)][t] for s in subs)
        assert volumes.UNIFIED_SERIES[ui][t] == rolled, (ui, t, rolled)
        assert g.nodes[ui]["series"][t] == rolled, (ui, t)
    assert g.nodes[ui]["volume"] == volumes.UNIFIED_TOTALS[ui], ui

assert volumes.PRODUCT_TOTAL == sum(volumes.UNIFIED_TOTALS.values())
assert c["conversations"] == volumes.PRODUCT_TOTAL, c["conversations"]
for t in range(P):
    assert gb.summary(g, t)["conversations"] == volumes.PRODUCT_SERIES[t], t

# headline volumes land inside the requested range in every period
peaks = [max(s) for s in volumes.UNIFIED_SERIES.values()]
troughs = [min(s) for s in volumes.UNIFIED_SERIES.values()]
assert min(troughs) >= volumes.MIN_UNIFIED_VOLUME, min(troughs)
assert max(peaks) <= volumes.MAX_UNIFIED_VOLUME * 1.02, max(peaks)
# the configured ceiling is actually reached by the busiest service at its peak
assert max(peaks) >= volumes.MAX_UNIFIED_VOLUME * 0.98, max(peaks)

# generation is deterministic
assert volumes.generate()[0] == volumes.UNIFIED_SERIES

# volumes genuinely move over time, in both directions
changes = [(s[-1] - s[0]) / s[0] for s in volumes.UNIFIED_SERIES.values()]
assert any(x > 0.2 for x in changes), "no service grows"
assert any(x < -0.2 for x in changes), "no service shrinks"
assert set(volumes.TRENDS.values()) == set(volumes.TREND_NAMES), set(volumes.TRENDS.values())

# life events / complaints report the traffic of the sub-intents they touch,
# per period
for n, d in g.nodes(data=True):
    if d["node_type"] in (gb.LIFE_EVENT, gb.COMPLAINT):
        for t in range(P):
            assert d["series"][t] == sum(
                g.nodes[nb]["series"][t] for nb in g.neighbors(n)
            ), (n, t)

# --- life event occurrences, and the edge widths they drive --------------------
import math as _m

import figure

occ = volumes.LIFE_OCCURRENCES
assert set(occ) == set(taxonomy.LIFE_EVENTS), set(occ) ^ set(taxonomy.LIFE_EVENTS)
assert min(occ.values()) == volumes.MIN_LIFE_OCCURRENCES, min(occ.values())
assert max(occ.values()) == volumes.MAX_LIFE_OCCURRENCES, max(occ.values())

# Stratified, so the ten events actually spread over the four decades instead of
# clumping. Every decade of the range holds at least one event.
_decades = {int(_m.log10(v)) for v in occ.values()}
assert len(_decades) >= 4, sorted(occ.values())

# The encoding itself: more occurrences must never draw a thinner edge. True of
# either scale, so switching LIFE_EDGE_SCALE can never invert the picture.
_by_occ = sorted(occ, key=lambda e: occ[e])
for _s in (gb.LIFE_EDGE_LINEAR, gb.LIFE_EDGE_LOG):
    _w = [gb.life_edge_width(occ[e], _s) for e in _by_occ]
    assert _w == sorted(_w), (_s, list(zip(_by_occ, _w)))
    assert _w[0] == gb.LIFE_EDGE_WIDTH_RANGE[0], (_s, _w[0])
    assert _w[-1] == gb.LIFE_EDGE_WIDTH_RANGE[1], (_s, _w[-1])

_widths = [gb.life_edge_width(occ[e]) for e in _by_occ]
_median = sorted(_widths)[len(_widths) // 2]

if gb.LIFE_EDGE_SCALE == gb.LIFE_EDGE_LOG:
    # Log's promise is that every event is distinguishable from its neighbours,
    # and that a 10x difference is worth more than a pixel.
    assert len(set(_widths)) == len(_widths), "two events collapsed onto one width"
    _per_decade = (gb.LIFE_EDGE_WIDTH_RANGE[1] - gb.LIFE_EDGE_WIDTH_RANGE[0]) / 4
    assert _per_decade > 1.0, f"a 10x difference is only {_per_decade:.2f}px"
else:
    # Linear's promise is the opposite one: the busiest event towers over the
    # rest. The flip side - everything small collapsing onto the floor - is the
    # accepted cost of the scale, not a defect, which is why the exact number
    # lives on the edge's hover.
    assert _widths[-1] >= 4 * _median, (_widths[-1], _median)
    # Measured in pixels, not in float equality: 1.002px and 1.005px are
    # different numbers and the same line.
    _squashed = [w for w in _widths if w <= gb.LIFE_EDGE_WIDTH_RANGE[0] + 1.0]
    assert len(_squashed) >= len(_widths) // 2, (
        f"only {len(_squashed)} of {len(_widths)} events land near the floor - "
        "is this really the linear scale?"
    )

# Every edge of one event carries that event's count; the number belongs to the
# event, not to the sub-intent it reaches.
for event, links in taxonomy.LIFE_EVENTS.items():
    for ui, sub in links:
        edge = g.edges[event, gb.sub_id(ui, sub)]
        assert edge["occurrences"] == occ[event], (event, edge["occurrences"])
        assert edge["width"] == gb.life_edge_width(occ[event]), event

# Nothing else varies: the structural edges keep their fixed widths.
for u, v, d in g.edges(data=True):
    if d["edge_type"] != gb.EDGE_LIFE_SUB:
        assert d["width"] == gb.EDGE_WIDTHS[d["edge_type"]], (u, v, d)

# --- edge traces ---------------------------------------------------------------
# A Plotly line trace has ONE width, so per-edge widths mean one trace per
# distinct width. The grouping has to stay lossless: every edge drawn exactly
# once, or the picture quietly loses links.
_groups = figure.edge_groups(g, set(gb.EDGE_COLORS))
_drawn = [tuple(sorted(p)) for grp in _groups for p in grp["pairs"]]
assert len(_drawn) == g.number_of_edges(), (len(_drawn), g.number_of_edges())
assert set(_drawn) == {tuple(sorted(e)) for e in g.edges()}, "edges lost in grouping"
assert len(_drawn) == len(set(_drawn)), "an edge is drawn twice"
assert len({grp["name"] for grp in _groups}) == len(_groups), "trace names collide"

for grp in _groups:
    for u, v in grp["pairs"]:
        assert g.edges[u, v]["width"] == grp["width"], (u, v)

_life_groups = [gr for gr in _groups if gr["kind"] == gb.EDGE_LIFE_SUB]
assert len(_life_groups) == len(set(_widths)), len(_life_groups)
assert sum(len(gr["pairs"]) for gr in _life_groups) == sum(
    len(v) for v in taxonomy.LIFE_EVENTS.values()
)

# and the figure really applies them
_pos = gb.compute_layout(g, gb.LAYOUT_CLUSTERS)
_fig = figure.build_figure(
    g, _pos, gb.compute_node_sizes(g, gb.SCALE_LOG), set(), set(gb.EDGE_COLORS)
)
_lines = [t for t in _fig.data if t.mode == "lines"]
assert len(_lines) == len(_groups), (len(_lines), len(_groups))
assert [t.line.width for t in _lines] == [gr["width"] for gr in _groups]

# --- node sizing --------------------------------------------------------------
for period in [None, *range(P)]:
    for scale in gb.SIZE_SCALES:
        for emphasis in (1.0, 1.8, 4.0):
            s = gb.compute_node_sizes(g, scale, period=period, emphasis=emphasis)
            assert set(s) == set(g.nodes), (scale, period, emphasis)
            assert all(v > 0 for v in s.values()), (scale, period, emphasis)

            if scale == gb.SCALE_UNIFORM:
                continue

            lo, hi = gb.SIZE_RANGE
            assert min(s.values()) >= lo - 1e-9, (scale, period, emphasis)
            assert max(s.values()) <= hi + 1e-9, (scale, period, emphasis)

            # THE sizing guarantee, and it spans every node type: more
            # conversations must never be drawn smaller than fewer, whether the
            # two nodes are a complaint and a sub-intent or anything else. A
            # per-type scale broke this - a 49k complaint drew at 22px while a
            # 30k sub-intent drew at 37px.
            ordered = sorted(s, key=lambda n: (gb.node_volume(g, n, period), n))
            vals = [s[n] for n in ordered]
            assert vals == sorted(vals), (scale, period, emphasis)

# Spelled out as a count, because this is the failure the sizing model had: with
# a per-type scale 3,226 of 44,850 node pairs (7.2%) had the bigger number drawn
# smaller. It must be exactly zero.
_s = gb.compute_node_sizes(g, gb.SCALE_LOG, 1.0, 0, 1.8)
_live = [n for n, d in g.nodes(data=True) if d["series"][0] > 0]
inversions = sum(
    1
    for i, a in enumerate(_live)
    for b in _live[i + 1 :]
    if (g.nodes[a]["series"][0] - g.nodes[b]["series"][0]) * (_s[a] - _s[b]) < 0
)
assert inversions == 0, f"{inversions} node pairs drawn out of order by volume"

# the specific pair that exposed it
_complaint = "Hidden or Unexpected Fees"
_sub = gb.sub_id("Cash Advance", "Understand cash advance fees")
assert g.nodes[_complaint]["series"][0] > g.nodes[_sub]["series"][0]
assert _s[_complaint] > _s[_sub], (_s[_complaint], _s[_sub])

# --- overlaps -----------------------------------------------------------------
# A layout places points and knows nothing about how fat the markers on them
# will be, so dense clusters collide. Sized on each node's largest moment across
# the timeline, so no period overlaps.
_per = [gb.compute_node_sizes(g, gb.SCALE_LOG, 1.0, t, 1.8) for t in range(P)]
_big = {n: max(x[n] for x in _per) for n in g.nodes()}

for _layout in (gb.LAYOUT_CLUSTERS, gb.LAYOUT_WEDGES):
    _p = gb.compute_layout(g, _layout)
    _r = gb.relax_overlaps(_p, _big, px_h=640)
    left = gb.count_overlaps(_r, _big)
    assert left == 0, f"{_layout}: {left} markers still overlap"

overlaps_before = gb.count_overlaps(gb.compute_layout(g, gb.LAYOUT_CLUSTERS), _big)
relaxed_pos = gb.relax_overlaps(gb.compute_layout(g, gb.LAYOUT_CLUSTERS), _big, px_h=640)
assert overlaps_before > 0, "nothing overlapped to begin with - test is vacuous"

# emphasis only expands, never reorders
plain = gb.compute_node_sizes(g, gb.SCALE_SQRT, period=0, emphasis=1.0)
pushed = gb.compute_node_sizes(g, gb.SCALE_SQRT, period=0, emphasis=1.8)
subs_only = [n for n, d in g.nodes(data=True) if d["node_type"] == gb.SUB_INTENT]
assert sorted(subs_only, key=plain.get) == sorted(subs_only, key=pushed.get)
assert all(pushed[n] >= plain[n] - 1e-9 for n in subs_only), "emphasis shrank a node"

# the busiest node really is the biggest one drawn, in each period
for period in range(P):
    s = gb.compute_node_sizes(g, gb.SCALE_LOG, period=period)
    busiest = max(volumes.SUB_SERIES, key=lambda k: volumes.SUB_SERIES[k][period])
    sub_sizes = {
        n: s[n] for n, d in g.nodes(data=True) if d["node_type"] == gb.SUB_INTENT
    }
    assert max(sub_sizes, key=sub_sizes.get) == gb.sub_id(*busiest), period

# THE timeline guarantee: a node that grows between two periods must be drawn
# bigger. This is what breaks if sizes are ever normalised per period.
grower = max(
    volumes.SUB_SERIES, key=lambda k: volumes.SUB_SERIES[k][-1] - volumes.SUB_SERIES[k][0]
)
shrinker = min(
    volumes.SUB_SERIES, key=lambda k: volumes.SUB_SERIES[k][-1] - volumes.SUB_SERIES[k][0]
)
# The app's defaults, so these numbers describe what a user actually sees.
DEFAULTS = dict(scale=gb.SCALE_LOG, emphasis=1.8)
first = gb.compute_node_sizes(g, period=0, **DEFAULTS)
last = gb.compute_node_sizes(g, period=P - 1, **DEFAULTS)
assert last[gb.sub_id(*grower)] > first[gb.sub_id(*grower)], "grower did not grow"
assert last[gb.sub_id(*shrinker)] < first[gb.sub_id(*shrinker)], "shrinker did not shrink"

# A sub-intent whose volume genuinely moved has to be visibly redrawn - and not
# just the handful of outliers. These are the assertions that fail if the size
# range is too narrow or the transform too compressed, which is exactly what
# made changes hard to see before.
#
# Note this is measured on DIAMETER and on AREA. Area is what the eye reads, and
# it moves as the square, so a 4 px shift on a 12 px node is a 78% area change.
movers = [
    (
        abs(last[gb.sub_id(*key)] - first[gb.sub_id(*key)]),
        max(last[gb.sub_id(*key)], first[gb.sub_id(*key)]) ** 2
        / min(last[gb.sub_id(*key)], first[gb.sub_id(*key)]) ** 2,
    )
    for key, s in volumes.SUB_SERIES.items()
    if s[0] > 0 and not (0.67 < s[-1] / s[0] < 1.5)
]
moves = sorted(m[0] for m in movers)
areas = sorted(m[1] for m in movers)

median_px = moves[len(moves) // 2]
median_area = areas[len(areas) // 2]

assert median_px > 3.0, f"typical mover shifts only {median_px:.2f} px"
assert max(moves) > 8.0, f"biggest mover shifts only {max(moves):.2f} px"
assert median_area > 1.3, f"typical mover's area changes only {median_area:.2f}x"

# multiplier scales everything proportionally
s = gb.compute_node_sizes(g, gb.SCALE_LOG)
doubled = gb.compute_node_sizes(g, gb.SCALE_LOG, multiplier=2.0)
assert all(abs(doubled[n] - 2 * s[n]) < 1e-9 for n in s)

# --- the organised layouts are measurably tidier ------------------------------
import math as _m

UIS = [n for n, d in g.nodes(data=True) if d["node_type"] == gb.UNIFIED_INTENT]
SUBS = [n for n, d in g.nodes(data=True) if d["node_type"] == gb.SUB_INTENT]


def cluster_purity(pos):
    """Share of sub-intents whose nearest unified intent is their OWN parent.

    This is the number that says whether services occupy distinct regions or
    bleed into each other, which is what 'messy' actually meant.
    """
    hit = 0
    for s in SUBS:
        x, y = pos[s]
        nearest = min(UIS, key=lambda u: (pos[u][0] - x) ** 2 + (pos[u][1] - y) ** 2)
        hit += nearest == g.nodes[s]["parent"]
    return 100 * hit / len(SUBS)


wedge_purity = cluster_purity(LAYOUTS[gb.LAYOUT_WEDGES])
spring_purity = cluster_purity(LAYOUTS[gb.LAYOUT_SPRING])
cluster_pur = cluster_purity(LAYOUTS[gb.LAYOUT_CLUSTERS])
assert wedge_purity > 90, f"wedge layout purity fell to {wedge_purity:.1f}%"
assert wedge_purity > spring_purity + 25, (wedge_purity, spring_purity)
assert cluster_pur > 95, f"clustered layout purity fell to {cluster_pur:.1f}%"

# The clustered layout lifts the cross-links up to the hub graph, so services
# that share a life event or complaint should end up genuinely closer together.
# Without that the whole point of stage 1 is lost.
import itertools as _it

hub = gb._hub_graph(g)
shared = {(a, b) for a, b in _it.combinations(sorted(UIS), 2) if hub.has_edge(a, b)}
assert shared, "no services share a cross-cutting node - affinity is untestable"


def affinity_ratio(pos):
    xs = [pos[u][0] for u in UIS]
    ys = [pos[u][1] for u in UIS]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    rel, unrel = [], []
    for a, b in _it.combinations(sorted(UIS), 2):
        d = _m.dist(tuple(pos[a]), tuple(pos[b])) / span
        (rel if (a, b) in shared else unrel).append(d)
    return (sum(rel) / len(rel)) / (sum(unrel) / len(unrel))


# Separating the markers must not undo the clustering. Pushing nodes wherever
# there was room dropped purity from 98% to 73%; keeping the ceiling on marker
# size is what lets both hold at once.
relaxed_purity = cluster_purity(relaxed_pos)
assert relaxed_purity > 90, f"overlap pass tore the clusters apart ({relaxed_purity:.1f}%)"

cluster_aff = affinity_ratio(LAYOUTS[gb.LAYOUT_CLUSTERS])
spring_aff = affinity_ratio(LAYOUTS[gb.LAYOUT_SPRING])
assert cluster_aff < 0.60, f"related services are not pulled together ({cluster_aff:.2f})"
assert cluster_aff < spring_aff, (cluster_aff, spring_aff)

# Stage 2 must give every service an even flower: all 8 sub-intents sit at
# essentially the same distance from their own parent.
cpos = LAYOUTS[gb.LAYOUT_CLUSTERS]
for ui in UIS:
    kids = [n for n in g.neighbors(ui) if g.nodes[n]["node_type"] == gb.SUB_INTENT]
    radii = [_m.dist(tuple(cpos[ui]), tuple(cpos[k])) for k in kids]
    assert max(radii) / min(radii) < 1.2, (ui, min(radii), max(radii))

# every service occupies its own angular slice, and the busiest are spread
# around the ring rather than bunched into one arc
wedge_pos = LAYOUTS[gb.LAYOUT_WEDGES]

angles = sorted(_m.atan2(wedge_pos[u][1], wedge_pos[u][0]) for u in UIS)
gaps = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
even = 2 * _m.pi / len(UIS)
assert all(abs(gp - even) < 1e-6 for gp in gaps), "services are not evenly spaced"

# the product sits at the centre, not out on the rim
assert wedge_pos[taxonomy.PRODUCT][0] ** 2 + wedge_pos[taxonomy.PRODUCT][1] ** 2 < 0.01

# the top 5 services by volume are not all crammed into one quadrant
top5 = sorted(UIS, key=lambda u: -g.nodes[u]["volume"])[:5]
top_angles = sorted(_m.atan2(wedge_pos[u][1], wedge_pos[u][0]) for u in top5)
spread = max(
    (top_angles[(i + 1) % 5] - top_angles[i]) % (2 * _m.pi) for i in range(5)
)
assert spread < _m.pi, f"busiest services bunched into one arc (largest gap {spread:.2f})"

# a filtered view still lays out cleanly
small = gb.filter_graph(g, set(gb.NODE_TYPES), {"Balance Transfer", "PIN Management"})
small_pos = gb.compute_layout(small, gb.LAYOUT_WEDGES)
assert set(small_pos) == set(small.nodes)

le = sum(len(v) for v in taxonomy.LIFE_EVENTS.values())
cm = sum(len(v) for v in taxonomy.COMPLAINTS.values())
print(f"OK  nodes={c['nodes']}  edges={c['edges']}  periods={P}")
print(
    f"    unified per-period {volumes.fmt(min(troughs))}..{volumes.fmt(max(peaks))}  "
    f"all-time total {volumes.fmt(volumes.PRODUCT_TOTAL)}"
)
print("    conversations by period: " + "  ".join(
    f"{p}={volumes.fmt(v)}" for p, v in zip(volumes.PERIODS, volumes.PRODUCT_SERIES)
))
print(f"    trends: " + ", ".join(
    f"{name}={sum(1 for v in volumes.TRENDS.values() if v == name)}"
    for name in volumes.TREND_NAMES
))
print(
    f"    {len(moves)} sub-intents moved >1.5x in volume: typical shift "
    f"{median_px:.1f}px (area x{median_area:.2f}), largest {max(moves):.1f}px"
)
print(f"    product=1 unified=31 sub=248 life_events=10 complaints=10")
print(f"    life-event links={le}  complaint links={cm}")
print(
    f"    life events {volumes.fmt(min(occ.values()))}..{volumes.fmt(max(occ.values()))} "
    f"occurrences -> edge width {min(_widths)}..{max(_widths)}px "
    f"({gb.LIFE_EDGE_SCALE}, median {_median}px), drawn in {len(_life_groups)} traces"
)
print(
    f"    cluster purity: clustered {cluster_pur:.1f}%  wedges {wedge_purity:.1f}%  "
    f"plain spring {spring_purity:.1f}%  (sub-intents nearest their own parent)"
)
print(
    f"    related services sit at {cluster_aff:.2f}x the distance of unrelated ones "
    f"when clustered, vs {spring_aff:.2f}x under plain spring"
)
print(
    f"    overlaps {overlaps_before} -> 0 after separation; purity holds at "
    f"{relaxed_purity:.1f}%; {inversions} size inversions across all node types"
)

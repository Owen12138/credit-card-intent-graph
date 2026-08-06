"""Builds the NetworkX graph from the taxonomy and computes layouts."""

from __future__ import annotations

import math
import random
from math import cos, gcd, pi, sin

import networkx as nx

import taxonomy
import volumes

# Node types
PRODUCT = "product"
UNIFIED_INTENT = "unified_intent"
SUB_INTENT = "sub_intent"
LIFE_EVENT = "life_event"
COMPLAINT = "complaint"

NODE_TYPES = [PRODUCT, UNIFIED_INTENT, SUB_INTENT, LIFE_EVENT, COMPLAINT]

TYPE_LABELS = {
    PRODUCT: "Product",
    UNIFIED_INTENT: "Unified intent",
    SUB_INTENT: "Sub-intent",
    LIFE_EVENT: "Life event",
    COMPLAINT: "Complaint",
}

TYPE_COLORS = {
    PRODUCT: "#e63946",
    UNIFIED_INTENT: "#1d70b8",
    SUB_INTENT: "#4cc9a0",
    LIFE_EVENT: "#f4a261",
    COMPLAINT: "#9b5de5",
}

# Fallback sizes, used when scaling is switched off ("Uniform").
TYPE_SIZES = {
    PRODUCT: 34,
    UNIFIED_INTENT: 18,
    SUB_INTENT: 8,
    LIFE_EVENT: 22,
    COMPLAINT: 22,
}

# (smallest, largest) marker size per type when sizing by conversation volume.
# Unified intents and sub-intents are scaled within their OWN type, so the two
# levels stay readable side by side (a parent is the sum of 8 children, so a
# shared scale would flatten every sub-intent to a dot).
#
# These spans are deliberately wide: the width of the range is what makes a
# month-on-month change in volume visible as a change in ink.
SIZE_RANGES = {
    PRODUCT: (44.0, 44.0),
    UNIFIED_INTENT: (10.0, 72.0),
    SUB_INTENT: (4.0, 42.0),
    LIFE_EVENT: (22.0, 22.0),
    COMPLAINT: (22.0, 22.0),
}

# Node-size scaling modes offered in the UI.
#
# Log is the default because it makes equal RATIOS travel equal distances: a
# node that doubles moves the same number of pixels whether it went 300 -> 600
# or 30,000 -> 60,000. That is what keeps month-on-month change visible on
# ordinary nodes and not just on the handful of huge ones.
SCALE_LOG = "Log (balanced, recommended)"
SCALE_SQRT = "Square root (area-true, favours the biggest)"
SCALE_LINEAR = "Linear (extremes only)"
SCALE_UNIFORM = "Uniform (ignore volume)"

SIZE_SCALES = [SCALE_LOG, SCALE_SQRT, SCALE_LINEAR, SCALE_UNIFORM]

# Edge kinds
EDGE_PRODUCT_UI = "product-unified_intent"
EDGE_UI_SUB = "unified_intent-sub_intent"
EDGE_LIFE_SUB = "life_event-sub_intent"
EDGE_COMPLAINT_SUB = "complaint-sub_intent"

EDGE_COLORS = {
    EDGE_PRODUCT_UI: "#c1121f",
    EDGE_UI_SUB: "#b8c4d0",
    EDGE_LIFE_SUB: "#f4a261",
    EDGE_COMPLAINT_SUB: "#9b5de5",
}


def sub_id(unified_intent: str, sub_intent: str) -> str:
    """Sub-intent node id, namespaced by its parent unified intent."""
    return f"{unified_intent} :: {sub_intent}"


def build_graph() -> nx.Graph:
    """Assemble the full product / intent / life-event / complaint graph."""
    g = nx.Graph()

    g.add_node(
        taxonomy.PRODUCT,
        label=taxonomy.PRODUCT,
        node_type=PRODUCT,
        parent=None,
        series=list(volumes.PRODUCT_SERIES),
        volume=volumes.PRODUCT_TOTAL,
        trend=None,
    )

    for ui, subs in taxonomy.UNIFIED_INTENTS.items():
        g.add_node(
            ui,
            label=ui,
            node_type=UNIFIED_INTENT,
            parent=taxonomy.PRODUCT,
            series=list(volumes.UNIFIED_SERIES[ui]),
            volume=volumes.UNIFIED_TOTALS[ui],
            trend=volumes.TRENDS[ui],
        )
        g.add_edge(taxonomy.PRODUCT, ui, edge_type=EDGE_PRODUCT_UI)

        for sub in subs:
            node = sub_id(ui, sub)
            g.add_node(
                node,
                label=sub,
                node_type=SUB_INTENT,
                parent=ui,
                series=list(volumes.SUB_SERIES[(ui, sub)]),
                volume=volumes.SUB_TOTALS[(ui, sub)],
                trend=volumes.TRENDS[ui],
            )
            g.add_edge(ui, node, edge_type=EDGE_UI_SUB)

    zeros = [0] * volumes.N_PERIODS
    for event, links in taxonomy.LIFE_EVENTS.items():
        g.add_node(
            event,
            label=event,
            node_type=LIFE_EVENT,
            parent=None,
            series=list(zeros),
            volume=0,
            trend=None,
        )
        for ui, sub in links:
            g.add_edge(event, sub_id(ui, sub), edge_type=EDGE_LIFE_SUB)

    for complaint, links in taxonomy.COMPLAINTS.items():
        g.add_node(
            complaint,
            label=complaint,
            node_type=COMPLAINT,
            parent=None,
            series=list(zeros),
            volume=0,
            trend=None,
        )
        for ui, sub in links:
            g.add_edge(complaint, sub_id(ui, sub), edge_type=EDGE_COMPLAINT_SUB)

    # Life events and complaints carry no volume of their own; report the traffic
    # of the sub-intents they touch so hover still says something useful.
    for node, data in g.nodes(data=True):
        if data["node_type"] in (LIFE_EVENT, COMPLAINT):
            linked = [
                g.nodes[nb]["series"]
                for nb in g.neighbors(node)
                if g.nodes[nb]["node_type"] == SUB_INTENT
            ]
            data["series"] = [sum(s[t] for s in linked) for t in range(volumes.N_PERIODS)]
            data["volume"] = sum(data["series"])

    return g


def node_volume(g: nx.Graph, node: str, period: int | None) -> int:
    """A node's conversations in one period, or its all-time total."""
    data = g.nodes[node]
    return data["volume"] if period is None else data["series"][period]


def compute_node_sizes(
    g: nx.Graph,
    scale: str = SCALE_LOG,
    multiplier: float = 1.0,
    period: int | None = None,
    emphasis: float = 1.0,
) -> dict[str, float]:
    """Marker size per node, scaled by conversation volume within each type.

    Always compute this against the FULL graph, not a filtered view, so a node
    keeps the same size as the user filters — sizes stay comparable across views.

    The scale is normalised across EVERY period, not just the selected one, so a
    node that doubles between April and August actually looks bigger. Rescaling
    per period would peg the busiest node to the maximum size at every step and
    hide the very movement the timeline exists to show.

    `emphasis` above 1.0 stretches the mid-range of the distribution across more
    of the size range, so ordinary nodes - not just the handful of outliers -
    visibly change between periods. It is a monotonic curve, so it never
    reorders anything: a busier node is still always the bigger node.
    """
    sizes: dict[str, float] = {}

    for ntype in NODE_TYPES:
        nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == ntype]
        if not nodes:
            continue

        smin, smax = SIZE_RANGES[ntype]

        if scale == SCALE_UNIFORM or smin == smax:
            base = TYPE_SIZES[ntype] if scale == SCALE_UNIFORM else smin
            for n in nodes:
                sizes[n] = base * multiplier
            continue

        if scale == SCALE_LOG:
            transform = math.log10
        elif scale == SCALE_SQRT:
            transform = math.sqrt
        elif scale == SCALE_LINEAR:
            transform = float
        else:
            raise ValueError(f"unknown size scale: {scale}")

        # Bounds come from every period at once (or from the all-time totals when
        # no period is selected), which is what keeps sizes comparable over time.
        pool: list[int] = []
        for n in nodes:
            if period is None:
                pool.append(g.nodes[n]["volume"])
            else:
                pool.extend(g.nodes[n]["series"])

        lo = transform(max(min(pool), 1))
        hi = transform(max(max(pool), 1))
        span = hi - lo

        for n in nodes:
            value = transform(max(node_volume(g, n, period), 1))
            frac = 0.5 if span == 0 else (value - lo) / span
            frac = min(1.0, max(0.0, frac))
            if emphasis != 1.0:
                frac = frac ** (1.0 / emphasis)
            sizes[n] = (smin + frac * (smax - smin)) * multiplier

    return sizes


def filter_graph(
    g: nx.Graph,
    visible_types: set[str],
    selected_unified_intents: set[str] | None = None,
) -> nx.Graph:
    """Return the subgraph limited to visible node types and selected branches.

    A sub-intent survives the branch filter only if its parent unified intent is
    selected. Life events and complaints survive only if they still connect to at
    least one visible sub-intent (they have no meaning stranded on their own).
    """
    keep: set[str] = set()

    for node, data in g.nodes(data=True):
        ntype = data["node_type"]
        if ntype not in visible_types:
            continue
        if selected_unified_intents is not None:
            if ntype == UNIFIED_INTENT and node not in selected_unified_intents:
                continue
            if ntype == SUB_INTENT and data["parent"] not in selected_unified_intents:
                continue
        keep.add(node)

    visible_subs = {n for n in keep if g.nodes[n]["node_type"] == SUB_INTENT}
    for node in list(keep):
        if g.nodes[node]["node_type"] in (LIFE_EVENT, COMPLAINT):
            if not any(nb in visible_subs for nb in g.neighbors(node)):
                keep.discard(node)

    return g.subgraph(keep).copy()


def neighborhood(g: nx.Graph, focus: str, depth: int = 2) -> nx.Graph:
    """Subgraph of everything within `depth` hops of a focus node."""
    if focus not in g:
        return g
    nodes = nx.single_source_shortest_path_length(g, focus, cutoff=depth).keys()
    return g.subgraph(nodes).copy()


# --- layouts ------------------------------------------------------------------
LAYOUT_WEDGES = "Spring (anchored wedges)"
LAYOUT_SPRING = "Spring (force-directed)"
LAYOUT_RADIAL = "Radial (by type)"
LAYOUT_KK = "Kamada-Kawai"
LAYOUT_LAYERED = "Layered (hierarchy)"

LAYOUTS = [LAYOUT_WEDGES, LAYOUT_SPRING, LAYOUT_RADIAL, LAYOUT_KK, LAYOUT_LAYERED]

# Relative spring strengths used by the anchored layout only. Parent-to-child
# pulls hard so a service balls up; the life-event and complaint cross-links pull
# weakly so they stay visible without dragging unrelated services together -
# those long-range edges are the main reason a plain spring turns into a
# hairball. Deliberately NOT stored on the graph, so the plain spring layout is
# unaffected and keeps behaving exactly as before.
WEDGE_EDGE_WEIGHTS = {
    EDGE_PRODUCT_UI: 1.0,
    EDGE_UI_SUB: 3.0,
    EDGE_LIFE_SUB: 0.18,
    EDGE_COMPLAINT_SUB: 0.18,
}

# Tuned by sweeping against two measures: what share of sub-intents end up
# nearest their OWN parent (94.4% here, against 49.6% for the plain spring), and
# how many node pairs end up overlapping. Loosening k to 0.7 pushes the first to
# 97% but multiplies overlaps sevenfold, which is not a trade worth taking.
RING_RADIUS = 1.0
FAN_GAP = 0.34        # how far a sub-intent sits beyond its parent's ring
FAN_STAGGER = 0.20    # alternate radii so a fan reads as a cluster, not an arc
FAN_WEDGE = 0.78      # fraction of its angular slice a service's fan may fill
WEDGE_ITERATIONS = 60


def _spread_slots(n: int) -> list[int]:
    """Ring slots for a volume-sorted list, so the busiest services end up far
    apart instead of bunching into one arc.

    Walks the ring in golden-ratio strides, which lands consecutive entries on
    opposite sides. The stride is nudged until it is coprime with n, otherwise
    it would revisit the same few slots.
    """
    if n <= 2:
        return list(range(n))

    step = max(1, round(n / 1.6180339887))
    for candidate in range(step, step + n):
        if gcd(candidate % n or 1, n) == 1:
            step = candidate % n or 1
            break
    else:
        step = 1

    return [(i * step) % n for i in range(n)]


def _anchored_wedge_layout(g: nx.Graph, seed: int = 42) -> dict[str, tuple]:
    """Product at the centre, services pinned around a ring, children fanned.

    The product node and the unified intents are placed deterministically and
    then held FIXED through a short spring relax. Everything else - sub-intents,
    life events, complaints - is only seeded and is free to settle, so each
    service keeps its own angular wedge while the picture still looks
    force-directed rather than drawn with a compass.
    """
    rng = random.Random(seed)
    init: dict[str, tuple[float, float]] = {}
    anchors: list[str] = []

    if taxonomy.PRODUCT in g:
        init[taxonomy.PRODUCT] = (0.0, 0.0)
        anchors.append(taxonomy.PRODUCT)

    uis = [n for n, d in g.nodes(data=True) if d["node_type"] == UNIFIED_INTENT]
    uis.sort(key=lambda n: (-g.nodes[n]["volume"], n))
    slots = _spread_slots(len(uis))
    slice_width = 2 * pi / max(len(uis), 1)

    for i, ui in enumerate(uis):
        theta = 2 * pi * slots[i] / max(len(uis), 1)
        init[ui] = (RING_RADIUS * cos(theta), RING_RADIUS * sin(theta))
        anchors.append(ui)

        subs = [
            n
            for n in g.neighbors(ui)
            if g.nodes[n]["node_type"] == SUB_INTENT and g.nodes[n]["parent"] == ui
        ]
        subs.sort()
        for j, sub in enumerate(subs):
            offset = ((j + 0.5) / len(subs)) - 0.5
            angle = theta + offset * slice_width * FAN_WEDGE
            radius = (
                RING_RADIUS
                + FAN_GAP
                + FAN_STAGGER * (j % 2)
                + rng.uniform(-0.035, 0.035)
            )
            init[sub] = (radius * cos(angle), radius * sin(angle))

    # Life events and complaints start near the middle of whatever they touch,
    # pulled inward so the cross-links read as spokes across the disc.
    for node, data in g.nodes(data=True):
        if data["node_type"] not in (LIFE_EVENT, COMPLAINT) or node in init:
            continue
        linked = [init[nb] for nb in g.neighbors(node) if nb in init]
        if linked:
            cx = sum(p[0] for p in linked) / len(linked)
            cy = sum(p[1] for p in linked) / len(linked)
            init[node] = (cx * 0.55, cy * 0.55)
        else:
            init[node] = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3))

    # Anything left over - e.g. sub-intents whose parent type is hidden - goes on
    # an outer ring so it is still placed deterministically.
    leftover = [n for n in g.nodes() if n not in init]
    for i, node in enumerate(sorted(leftover)):
        angle = 2 * pi * i / max(len(leftover), 1)
        r = RING_RADIUS + FAN_GAP + 0.5
        init[node] = (r * cos(angle), r * sin(angle))

    if g.number_of_edges() == 0:
        return init

    weighted = g.copy()
    for _, _, data in weighted.edges(data=True):
        data["weight"] = WEDGE_EDGE_WEIGHTS.get(data["edge_type"], 1.0)

    return nx.spring_layout(
        weighted,
        pos=init,
        fixed=anchors or None,
        k=1.1 / max(g.number_of_nodes(), 1) ** 0.5,
        iterations=WEDGE_ITERATIONS,
        seed=seed,
        weight="weight",
    )


def compute_layout(g: nx.Graph, algorithm: str, seed: int = 42) -> dict[str, tuple]:
    """Positions for every node, keyed by node id."""
    if g.number_of_nodes() == 0:
        return {}

    if algorithm == LAYOUT_WEDGES:
        return _anchored_wedge_layout(g, seed)

    if algorithm == "Spring (force-directed)":
        k = 2.2 / max(g.number_of_nodes(), 1) ** 0.5
        return nx.spring_layout(g, k=k, iterations=120, seed=seed)

    if algorithm == "Kamada-Kawai":
        return nx.kamada_kawai_layout(g)

    if algorithm == "Radial (by type)":
        shells = [
            [n for n, d in g.nodes(data=True) if d["node_type"] == PRODUCT],
            [n for n, d in g.nodes(data=True) if d["node_type"] == UNIFIED_INTENT],
            [n for n, d in g.nodes(data=True) if d["node_type"] == SUB_INTENT],
            [
                n
                for n, d in g.nodes(data=True)
                if d["node_type"] in (LIFE_EVENT, COMPLAINT)
            ],
        ]
        shells = [s for s in shells if s]
        return nx.shell_layout(g, nlist=shells)

    if algorithm == "Layered (hierarchy)":
        layer = {
            PRODUCT: 0,
            UNIFIED_INTENT: 1,
            SUB_INTENT: 2,
            LIFE_EVENT: 3,
            COMPLAINT: 4,
        }
        h = g.copy()
        for node, data in h.nodes(data=True):
            h.nodes[node]["layer"] = layer[data["node_type"]]
        return nx.multipartite_layout(h, subset_key="layer", align="horizontal")

    raise ValueError(f"unknown layout algorithm: {algorithm}")


def summary(g: nx.Graph, period: int | None = None) -> dict[str, int]:
    counts = {t: 0 for t in NODE_TYPES}
    for _, data in g.nodes(data=True):
        counts[data["node_type"]] += 1
    counts["edges"] = g.number_of_edges()
    counts["nodes"] = g.number_of_nodes()
    # Sub-intent volumes roll up into their parents, so summing only the
    # sub-intents avoids double counting the same conversations.
    subs = [n for n, d in g.nodes(data=True) if d["node_type"] == SUB_INTENT]
    counts["conversations"] = sum(node_volume(g, n, period) for n in subs)
    if period is not None and period > 0:
        previous = sum(node_volume(g, n, period - 1) for n in subs)
        counts["conversations_delta"] = counts["conversations"] - previous
    return counts

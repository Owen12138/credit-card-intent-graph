"""Plotly rendering of the intent graph.

Kept free of Streamlit so the figure can be built and asserted on directly in
tests, and reused outside the app (notebook, static HTML export).
"""

from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go

import graph_builder as gb
import volumes


def edge_groups(g: nx.Graph, edge_kinds: set[str]) -> list[dict]:
    """One entry per edge trace, in the order `build_figure` emits them.

    A Plotly line trace carries a single `line.width` for every segment in it,
    so edges that differ in width cannot share a trace. Life-event edges are the
    only ones that vary, and their width comes from the event's occurrence
    count - so they split into one trace per distinct width, which is at most
    one per life event.

    interactive_html needs the same grouping to tell the browser which node
    pairs each trace draws, so the ordering lives here rather than being
    reconstructed - two implementations of this that drift apart would silently
    redraw the wrong edges when a node is dragged.
    """
    groups: list[dict] = []
    for kind in gb.EDGE_COLORS:
        if kind not in edge_kinds:
            continue

        by_width: dict[float, list[list[str]]] = {}
        for u, v, data in g.edges(data=True):
            if data["edge_type"] != kind:
                continue
            by_width.setdefault(data["width"], []).append([u, v])

        label = kind.replace("-", " -> ").replace("_", " ")
        for width in sorted(by_width, reverse=True):
            groups.append(
                {
                    "kind": kind,
                    "width": width,
                    "color": gb.EDGE_COLORS[kind],
                    "pairs": by_width[width],
                    # Unique per trace: the meta builder indexes traces by name.
                    "name": label if len(by_width) == 1 else f"{label} @{width}",
                }
            )
    return groups


def build_figure(
    g: nx.Graph,
    pos: dict,
    sizes: dict,
    labelled: set[str],
    edge_kinds: set[str],
    height: int = 800,
    period: int | None = None,
    uirevision: str = "static",
) -> go.Figure:
    fig = go.Figure()

    # --- edges, grouped by kind and width (see edge_groups) -------------------
    for group in edge_groups(g, edge_kinds):
        xs: list = []
        ys: list = []
        for u, v in group["pairs"]:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
        if not xs:
            continue
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(width=group["width"], color=group["color"]),
                hoverinfo="skip",
                opacity=0.55,
                name=group["name"],
                showlegend=False,
            )
        )

    # --- nodes, one trace per type ------------------------------------------
    for ntype in gb.NODE_TYPES:
        nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == ntype]
        if not nodes:
            continue

        xs = [pos[n][0] for n in nodes]
        ys = [pos[n][1] for n in nodes]
        node_sizes = [sizes.get(n, gb.TYPE_SIZES[ntype]) for n in nodes]
        texts = [g.nodes[n]["label"] if n in labelled else "" for n in nodes]

        when = volumes.PERIODS[period] if period is not None else "all periods"

        hovers = []
        for n in nodes:
            data = g.nodes[n]
            value = gb.node_volume(g, n, period)
            parts = [f"<b>{data['label']}</b>", gb.TYPE_LABELS[ntype]]
            if data.get("parent"):
                parts.append(f"Parent: {data['parent']}")

            noun = (
                "Conversations in linked sub-intents"
                if ntype in (gb.LIFE_EVENT, gb.COMPLAINT)
                else "Conversations"
            )
            parts.append(f"{noun} ({when}): {volumes.fmt(value)}")

            # The life event's own metric, and what its edge widths encode.
            if ntype == gb.LIFE_EVENT:
                parts.append(f"Occurrences: {volumes.fmt(data['occurrences'])}")

            if period is not None:
                change = volumes.delta(data["series"], period)
                if change is not None:
                    prev = data["series"][period - 1]
                    pct = f" ({change / prev:+.0%})" if prev else ""
                    parts.append(f"vs {volumes.PERIODS[period - 1]}: {change:+,}{pct}")
                if data.get("trend"):
                    parts.append(f"Trend: {data['trend']}")

            parts.append(f"Connections: {g.degree(n)}")
            hovers.append("<br>".join(parts))

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                # Always keep "+text", even when every label starts empty. A
                # trace set to plain "markers" ignores any text restyled into it
                # later, so semantic zoom could never reveal a label.
                mode="markers+text",
                text=texts,
                textposition="top center",
                textfont=dict(size=9 if ntype == gb.SUB_INTENT else 11),
                hovertext=hovers,
                hoverinfo="text",
                marker=dict(
                    size=node_sizes,
                    color=gb.TYPE_COLORS[ntype],
                    line=dict(width=1, color="white"),
                ),
                name=f"{gb.TYPE_LABELS[ntype]} ({len(nodes)})",
            )
        )

    # Pin the axes to the layout's own extent. Plotly would otherwise autorange
    # around the markers, so a node growing between periods would nudge the whole
    # view - the positions must look nailed down while only the sizes move.
    xr, yr = _axis_ranges(pos)

    fig.update_layout(
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="closest",
        xaxis=dict(visible=False, showgrid=False, zeroline=False, range=xr, autorange=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False, range=yr, autorange=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        dragmode="pan",
        # Keeps the user's zoom/pan across reruns. Changing the layout algorithm
        # or the visible nodes changes this string, which resets the view.
        uirevision=uirevision,
        # No layout-level `transition` here on purpose. It would apply to EVERY
        # re-render, including the initial mount and the responsive resize that
        # fires as soon as the iframe settles - so the graph would animate its
        # node sizes into place every time you opened it. Easing between periods
        # belongs in the animate arguments of the slider steps and Play button
        # (see interactive_html), which only run when the user asks for them.
    )
    return fig


def _axis_ranges(pos: dict, pad: float = 0.12) -> tuple[list[float], list[float]]:
    """Fixed axis ranges covering every node position, with a margin."""
    if not pos:
        return [-1.0, 1.0], [-1.0, 1.0]

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]

    def bounds(vals: list[float]) -> list[float]:
        lo, hi = min(vals), max(vals)
        margin = (hi - lo) * pad or 1.0
        return [lo - margin, hi + margin]

    return bounds(xs), bounds(ys)

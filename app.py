"""Streamlit app: Credit Card intent graph.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import networkx as nx
import pandas as pd
import streamlit as st

import graph_builder as gb
import taxonomy
import volumes
from figure import build_figure, view_revision

st.set_page_config(page_title="Credit Card Intent Graph", layout="wide")

ALL_PERIODS = "All periods"


@st.cache_data(show_spinner=False)
def load_graph() -> nx.Graph:
    return gb.build_graph()


@st.cache_data(show_spinner=False)
def layout_for(node_key: tuple, algorithm: str, _graph: nx.Graph) -> dict:
    # node_key participates in the cache key so a filtered graph gets a fresh layout
    return gb.compute_layout(_graph, algorithm)


@st.cache_data(show_spinner=False)
def sizes_for(
    scale: str,
    multiplier: float,
    period: int | None,
    emphasis: float,
    _graph: nx.Graph,
) -> dict:
    return gb.compute_node_sizes(_graph, scale, multiplier, period, emphasis)


# =============================================================================
# Sidebar controls
# =============================================================================
full = load_graph()

st.sidebar.title("Graph controls")

layout_algo = st.sidebar.selectbox(
    "Layout",
    ["Spring (force-directed)", "Radial (by type)", "Kamada-Kawai", "Layered (hierarchy)"],
    key="layout",
)

view_mode = st.sidebar.radio(
    "View", ["Full graph", "Focus on one unified intent"], index=0, key="view_mode"
)

all_uis = list(taxonomy.UNIFIED_INTENTS)

if view_mode == "Focus on one unified intent":
    focus_ui = st.sidebar.selectbox("Unified intent", all_uis)
    selected_uis = {focus_ui}
else:
    focus_ui = None
    selected_uis = set(
        st.sidebar.multiselect(
            "Unified intents shown",
            all_uis,
            default=all_uis,
            help="Trim the 31 services down to compare a handful side by side.",
        )
    )

st.sidebar.markdown("**Node size**")
size_scale = st.sidebar.selectbox(
    "Scale by conversation volume",
    gb.SIZE_SCALES,
    help=(
        "Log makes equal ratios travel equal distances, so a node that doubles "
        "moves the same amount whether it is small or huge - the most reliable "
        "way to see change across the timeline. Square root makes a circle's "
        "AREA proportional to volume, which is dramatic for the biggest movers "
        "but leaves ordinary nodes barely moving."
    ),
    key="size_scale",
)
size_emphasis = st.sidebar.slider(
    "Emphasis",
    1.0,
    4.0,
    1.8,
    step=0.2,
    key="size_emphasis",
    help=(
        "Stretches mid-sized nodes across more of the size range, so ordinary "
        "intents visibly grow and shrink between periods instead of only the "
        "handful of outliers. Never reorders anything - a busier node is always "
        "the bigger node."
    ),
)
size_multiplier = st.sidebar.slider(
    "Size multiplier", 0.5, 2.0, 1.0, step=0.1, key="size_multiplier"
)

st.sidebar.markdown("**Node types**")
visible_types = set()
for ntype in gb.NODE_TYPES:
    if st.sidebar.checkbox(gb.TYPE_LABELS[ntype], value=True, key=f"type_{ntype}"):
        visible_types.add(ntype)

st.sidebar.markdown("**Labels**")
label_types = set()
for ntype in gb.NODE_TYPES:
    if st.sidebar.checkbox(gb.TYPE_LABELS[ntype], value=True, key=f"label_{ntype}"):
        label_types.add(ntype)

max_sub_volume = max(max(s) for s in volumes.SUB_SERIES.values())
label_threshold = st.sidebar.slider(
    "Hide sub-intent labels below",
    min_value=0,
    max_value=int(max_sub_volume),
    value=0,
    step=500,
    help=(
        "All 248 sub-intent labels are shown by default. Raise this to keep only "
        "the busier ones labelled when the canvas gets crowded."
    ),
    key="label_threshold",
)

height = st.sidebar.slider("Canvas height (px)", 500, 1400, 800, step=50)

# =============================================================================
# Build the view
# =============================================================================
view = gb.filter_graph(full, visible_types, selected_uis)
if focus_ui and focus_ui in view:
    view = gb.neighborhood(view, focus_ui, depth=2)

edge_kinds = set(gb.EDGE_COLORS)

st.title("Credit Card intent graph")
st.caption(
    "Product -> unified intents -> sub-intents, with life events and complaints "
    "linking in from their own groups. Node size = conversation volume in the "
    "selected period."
)

# --- timeline ----------------------------------------------------------------
# Sits above the canvas rather than in the sidebar so it can be dragged while
# watching the graph.
period_label = st.select_slider(
    "Timeline",
    options=volumes.PERIODS + [ALL_PERIODS],
    value=volumes.PERIODS[-1],
    key="period",
    help=(
        "Drag or click through the months. Node positions are fixed, so only the "
        "sizes move. 'All periods' totals every month together."
    ),
)
period = None if period_label == ALL_PERIODS else volumes.PERIODS.index(period_label)

counts = gb.summary(view, period)
sizes = sizes_for(size_scale, size_multiplier, period, size_emphasis, full)

labelled = set()
for node, data in view.nodes(data=True):
    ntype = data["node_type"]
    if ntype not in label_types:
        continue
    if ntype == gb.SUB_INTENT and gb.node_volume(view, node, period) < label_threshold:
        continue
    labelled.add(node)

cols = st.columns(6)
cols[0].metric(
    f"Conversations ({period_label})",
    volumes.fmt(counts["conversations"]),
    delta=(
        volumes.fmt(counts["conversations_delta"])
        if counts.get("conversations_delta") is not None
        else None
    ),
)
cols[1].metric("Nodes", counts["nodes"])
cols[2].metric("Unified intents", counts[gb.UNIFIED_INTENT])
cols[3].metric("Sub-intents", counts[gb.SUB_INTENT])
cols[4].metric("Life events", counts[gb.LIFE_EVENT])
cols[5].metric("Complaints", counts[gb.COMPLAINT])

tab_graph, tab_tables = st.tabs(["Graph", "Data"])

with tab_graph:
    if view.number_of_nodes() == 0:
        st.warning("Nothing to draw - widen the filters in the sidebar.")
    else:
        pos = layout_for(tuple(sorted(view.nodes())), layout_algo, view)
        # Changing the layout or the visible nodes resets the viewport; stepping
        # through the timeline must not, so the period is deliberately excluded.
        revision = view_revision(layout_algo, view.nodes(), selected_uis)
        fig = build_figure(
            view, pos, sizes, labelled, edge_kinds, height, period, revision
        )
        # The stable key matters: without it Streamlit gives the chart a fresh
        # identity on every rerun, remounting the component and throwing away the
        # zoom/pan state that `uirevision` exists to preserve.
        st.plotly_chart(
            fig,
            width="stretch",
            key="intent_graph",
            config={"scrollZoom": True, "doubleClick": "reset"},
        )
        st.caption(
            "Scroll to zoom, drag to pan, hover a node for its volume, change since "
            "the previous month, parent and degree. Positions are pinned across the "
            "timeline, so any movement you see is real change in volume. Unified "
            "intents and sub-intents are each sized within their own level, and the "
            "scale spans every period so growth between months is visible."
        )

with tab_tables:
    st.subheader("Conversations over time")
    totals_df = pd.DataFrame(
        {"Period": volumes.PERIODS, "Conversations": volumes.PRODUCT_SERIES}
    ).set_index("Period")
    st.bar_chart(totals_df, height=220)

    st.subheader("Busiest services over time")
    top_uis = sorted(
        volumes.UNIFIED_TOTALS, key=volumes.UNIFIED_TOTALS.get, reverse=True
    )[:8]
    trend_df = pd.DataFrame(
        {ui: volumes.UNIFIED_SERIES[ui] for ui in top_uis}, index=volumes.PERIODS
    )
    st.line_chart(trend_df, height=300)

    st.subheader("Unified intents by conversation volume")
    ui_rows = []
    for ui, series in volumes.UNIFIED_SERIES.items():
        row = {"Unified intent": ui, "Trend": volumes.TRENDS[ui]}
        row.update({p: series[t] for t, p in enumerate(volumes.PERIODS)})
        row["Total"] = volumes.UNIFIED_TOTALS[ui]
        row["Change"] = (series[-1] - series[0]) / series[0] if series[0] else 0.0
        ui_rows.append(row)

    ui_df = pd.DataFrame(ui_rows).sort_values("Total", ascending=False)
    st.dataframe(
        ui_df,
        width="stretch",
        height=320,
        hide_index=True,
        column_config={
            **{p: st.column_config.NumberColumn(format="%,d") for p in volumes.PERIODS},
            "Total": st.column_config.NumberColumn(format="%,d"),
            "Change": st.column_config.NumberColumn(
                "First to last", format="%+.1f%%", help="Apr 2026 -> Aug 2026"
            ),
        },
    )

    st.subheader("Sub-intents by conversation volume")
    sub_rows = []
    for (ui, sub), series in volumes.SUB_SERIES.items():
        row = {"Unified intent": ui, "Sub-intent": sub}
        row.update({p: series[t] for t, p in enumerate(volumes.PERIODS)})
        row["Total"] = volumes.SUB_TOTALS[(ui, sub)]
        sub_rows.append(row)

    sub_df = pd.DataFrame(sub_rows).sort_values("Total", ascending=False)
    st.dataframe(
        sub_df,
        width="stretch",
        height=320,
        hide_index=True,
        column_config={
            **{p: st.column_config.NumberColumn(format="%,d") for p in volumes.PERIODS},
            "Total": st.column_config.NumberColumn(format="%,d"),
        },
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Life event links")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Life event": ev,
                        "Unified intent": ui,
                        "Sub-intent": sub,
                        f"Conversations ({period_label})": (
                            volumes.SUB_TOTALS[(ui, sub)]
                            if period is None
                            else volumes.SUB_SERIES[(ui, sub)][period]
                        ),
                    }
                    for ev, links in taxonomy.LIFE_EVENTS.items()
                    for ui, sub in links
                ]
            ),
            width="stretch",
            height=320,
            hide_index=True,
        )
    with right:
        st.subheader("Complaint links")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Complaint": c,
                        "Unified intent": ui,
                        "Sub-intent": sub,
                        f"Conversations ({period_label})": (
                            volumes.SUB_TOTALS[(ui, sub)]
                            if period is None
                            else volumes.SUB_SERIES[(ui, sub)][period]
                        ),
                    }
                    for c, links in taxonomy.COMPLAINTS.items()
                    for ui, sub in links
                ]
            ),
            width="stretch",
            height=320,
            hide_index=True,
        )

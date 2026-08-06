"""Streamlit app: Credit Card intent graph.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import networkx as nx
import pandas as pd
import streamlit as st

import channels
import graph_builder as gb
import taxonomy
import volumes
from interactive_html import render_page

st.set_page_config(page_title="Credit Card Intent Graph", layout="wide")


@st.cache_data(show_spinner=False)
def load_graph() -> nx.Graph:
    return gb.build_graph()


@st.cache_data(show_spinner=False)
def load_channels() -> dict:
    """All six channel files, combined. This is the backend step: the three
    channels are loaded separately and merged only when a view asks for them."""
    return channels.load()


@st.cache_data(show_spinner=False)
def layout_for(node_key: tuple, algorithm: str, _graph: nx.Graph) -> dict:
    # node_key participates in the cache key so a filtered graph gets a fresh layout
    return gb.compute_layout(_graph, algorithm)


@st.cache_data(show_spinner=False)
def page_html(
    node_key: tuple,
    labelled_key: tuple,
    layout_algo: str,
    scale: str,
    emphasis: float,
    multiplier: float,
    height: int,
    _graph: nx.Graph,
    _pos: dict,
) -> str:
    """The embedded page. Cached so it is only rebuilt when a sidebar control
    actually changes - the timeline and focus never reach this far."""
    return render_page(
        _graph,
        _pos,
        set(labelled_key),
        scale=scale,
        emphasis=emphasis,
        multiplier=multiplier,
        height=height,
        include_plotlyjs=True,
        chrome=False,
    )


# =============================================================================
# Sidebar controls
# =============================================================================
full = load_graph()

st.sidebar.title("Graph controls")

layout_algo = st.sidebar.selectbox(
    "Layout",
    gb.LAYOUTS,
    key="layout",
    help=(
        "Anchored wedges pins the product at the centre and the 31 services "
        "evenly around a ring, each with its sub-intents fanned outward, then "
        "lets everything else relax - so each service keeps its own slice "
        "instead of clusters overlapping. Plain force-directed is the "
        "unconstrained original."
    ),
)

# Which unified intent the graph shows is chosen in the detail view above the
# canvas, not here - one picker drives both, so the graph is always showing the
# intent the cards describe.

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

st.title("Credit Card intent graph")
st.caption(
    "Product -> unified intents -> sub-intents, with life events and complaints "
    "linking in from their own groups. Node size = conversation volume. The "
    "timeline and click-to-focus run inside the canvas, so neither disturbs your "
    "zoom."
)

tab_graph, tab_tables = st.tabs(["Graph", "Data"])

with tab_graph:
    # =========================================================================
    # Intent detail. The unified intent picked here also decides what the graph
    # below draws, so there is one control rather than two that can disagree.
    # =========================================================================
    st.subheader("Intent detail")

    # Small uppercase field label, so a card can name its sections without
    # spending a full line of body text on each.
    _LABEL = (
        "<div style='font-size:0.72rem; letter-spacing:0.06em; opacity:0.55;"
        " text-transform:uppercase; margin:0.55rem 0 0.1rem;'>{}</div>"
    )

    UNIFIED_ONLY = "— none: show the unified intent —"

    picked_ui = st.selectbox(
        "Unified intent",
        list(taxonomy.UNIFIED_INTENTS),
        key="focus_unified",
        help="Also sets which unified intent the graph below draws.",
    )
    picked_sub = st.selectbox(
        "Sub-intent",
        [UNIFIED_ONLY] + taxonomy.UNIFIED_INTENTS[picked_ui],
        key="focus_sub",
        help=(
            "Optional second level. It changes the detail below it, not the "
            "graph - the graph stays the top-level picture for the service."
        ),
    )

    # The most specific selection wins: a chosen sub-intent overrides its parent.
    if picked_sub == UNIFIED_ONLY:
        name, kind = picked_ui, "unified"
    else:
        name, kind = picked_sub, "sub"

    channel_data = load_channels()
    rows = channels.records(channel_data, name, kind)
    carried = [rec for _, rec in rows if rec]

    st.markdown(f"### {name}")
    if kind == "sub":
        st.caption(f"Sub-intent of **{picked_ui}**")

    description = carried[0]["description"] if carried else "No description available."
    st.markdown(
        "<div style='font-size:1.15rem; line-height:1.6; margin:0.2rem 0 1rem;"
        " padding:0.85rem 1.1rem; border-left:4px solid #1d70b8;"
        " background:rgba(29,112,184,0.08); border-radius:6px;'>"
        f"{description}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### By channel")
    cards = st.columns(len(rows))
    for col, (channel, rec) in zip(cards, rows):
        with col, st.container(border=True):
            st.markdown(f"**{channel.label}**")
            st.caption(channel.blurb)

            if rec is None:
                # Always three cards, even for a channel that does not carry the
                # intent - a missing card would read as a rendering fault, and
                # the gap is itself worth seeing.
                st.info("Not handled on this channel.")
                continue

            # A compact line rather than st.metric, which is several times taller
            # and pushed the graph down the page.
            st.markdown(
                "<div style='margin:0.1rem 0 0.2rem;'>"
                "<span style='font-size:1.4rem; font-weight:600;'>"
                f"{volumes.fmt(rec['numberOfConversations'])}</span>"
                "<span style='opacity:0.6; font-size:0.85rem;'> conversations</span>"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown(_LABEL.format("Channel intents"), unsafe_allow_html=True)
            # Two trailing spaces is a markdown hard break, so each intent gets
            # its own line instead of running together into a paragraph.
            st.markdown("  \n".join(f"**{ci}**" for ci in rec["channelIntent"]))

            text = rec.get("sampleConversation", {}).get("conversationText")
            if text:
                st.markdown(
                    _LABEL.format("Sample conversation")
                    + "<div style='font-size:0.88rem; font-style:italic;"
                    " opacity:0.85; border-left:3px solid rgba(125,125,125,0.35);"
                    f" padding-left:0.6rem;'>{text}</div>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # =========================================================================
    # The graph, for the unified intent picked above. A sub-intent selection
    # deliberately does not narrow it - this stays the whole service.
    # =========================================================================
    view = gb.filter_graph(full, visible_types, {picked_ui})
    if picked_ui in view:
        view = gb.neighborhood(view, picked_ui, depth=2)

    counts = gb.summary(view)

    labelled = set()
    for node, data in view.nodes(data=True):
        ntype = data["node_type"]
        if ntype not in label_types:
            continue
        if ntype == gb.SUB_INTENT and data["volume"] < label_threshold:
            continue
        labelled.add(node)

    # No heading here: the picker directly above already names the service, so
    # repeating it just costs vertical space.
    cols = st.columns(6)
    cols[0].metric("Conversations (all periods)", volumes.fmt(counts["conversations"]))
    cols[1].metric("Nodes", counts["nodes"])
    cols[2].metric("Unified intents", counts[gb.UNIFIED_INTENT])
    cols[3].metric("Sub-intents", counts[gb.SUB_INTENT])
    cols[4].metric("Life events", counts[gb.LIFE_EVENT])
    cols[5].metric("Complaints", counts[gb.COMPLAINT])

    if view.number_of_nodes() == 0:
        st.warning("Nothing to draw - widen the filters in the sidebar.")
    else:
        node_key = tuple(sorted(view.nodes()))
        pos = layout_for(node_key, layout_algo, view)

        # The whole canvas - timeline, play button, focus - runs in the browser.
        # Streamlit only rebuilds it when one of these values changes, and every
        # one of those genuinely moves nodes, so resetting the view there is the
        # correct behaviour.
        html = page_html(
            node_key,
            tuple(sorted(labelled)),
            layout_algo,
            size_scale,
            size_emphasis,
            size_multiplier,
            height,
            view,
            pos,
        )
        st.iframe(html, height=height + 150)

        st.caption(
            "**Timeline** - press Play or drag the slider under the canvas. "
            "**Drag** - pull any node clear to look at it; its edges and labels "
            "follow, and it eases back into place when you let go. "
            "**Focus** - click any node to isolate it and everything it connects "
            "to; click it again or press Clear to restore. "
            "**Labels** - sub-intent labels stay hidden until you zoom in past "
            "~2.2x; focusing a node labels its neighbourhood at any zoom. "
            "**Zoom** - scroll, or use the +/- buttons. Nodes are circles drawn "
            "on the graph: they shrink as you zoom out, so the spacing between "
            "them survives and they never pile up. *Reset view* refits. "
            "All of it runs in the browser, so your zoom and the period you are "
            "on survive. Drag to pan, hover for volumes."
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
                        "Conversations (all periods)": volumes.SUB_TOTALS[(ui, sub)],
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
                        "Conversations (all periods)": volumes.SUB_TOTALS[(ui, sub)],
                    }
                    for c, links in taxonomy.COMPLAINTS.items()
                    for ui, sub in links
                ]
            ),
            width="stretch",
            height=320,
            hide_index=True,
        )

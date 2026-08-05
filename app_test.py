"""End-to-end run of app.py via Streamlit's AppTest. Run: python app_test.py"""

import graph_builder as gb
import volumes
import taxonomy
from figure import build_figure, view_revision
from streamlit.testing.v1 import AppTest

ALL_PERIODS = "All periods"
LATEST = volumes.PERIODS[-1]


def fresh(timeout=180):
    at = AppTest.from_file("app.py", default_timeout=timeout)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


# --- default view: full graph, latest period ---------------------------------
at = fresh()
m = metrics(at)
print("default metrics:", m)
assert m["Nodes"] == "300", m
assert m["Unified intents"] == "31", m
assert m["Sub-intents"] == "248", m
assert m["Life events"] == "10", m
assert m["Complaints"] == "10", m

conv_label = f"Conversations ({LATEST})"
assert conv_label in m, m
assert m[conv_label] == volumes.fmt(volumes.PRODUCT_SERIES[-1]), m
assert len(at.tabs) == 2
assert at.dataframe, "data tab rendered no tables"

# sub-intent labels are on by default, and every sub-intent is labelled
assert at.checkbox(key="label_sub_intent").value is True
assert at.session_state["label_threshold"] == 0

# --- the timeline ------------------------------------------------------------
slider = at.select_slider(key="period")
assert list(slider.options) == volumes.PERIODS + [ALL_PERIODS], list(slider.options)
print(f"timeline options: {list(slider.options)}")

for t, label in enumerate(volumes.PERIODS):
    a = fresh()
    a.select_slider(key="period").set_value(label).run()
    assert not a.exception, (label, [e.value for e in a.exception])
    m = metrics(a)
    got = m[f"Conversations ({label})"]
    assert got == volumes.fmt(volumes.PRODUCT_SERIES[t]), (label, got)
    print(f"period ok: {label} -> {got} conversations")

a = fresh()
a.select_slider(key="period").set_value(ALL_PERIODS).run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
assert m[f"Conversations ({ALL_PERIODS})"] == volumes.fmt(volumes.PRODUCT_TOTAL), m
print(f"period ok: {ALL_PERIODS} -> {m[f'Conversations ({ALL_PERIODS})']} conversations")

# --- every layout option renders without error --------------------------------
for opt in at.selectbox(key="layout").options:
    a = fresh()
    a.selectbox(key="layout").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])
    print(f"layout ok: {opt}")

# --- every size scale renders without error -----------------------------------
for opt in at.selectbox(key="size_scale").options:
    a = fresh()
    a.selectbox(key="size_scale").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])
    print(f"size scale ok: {opt}")

# --- size multiplier and emphasis ---------------------------------------------
a = fresh()
a.slider(key="size_multiplier").set_value(2.0).run()
assert not a.exception, [e.value for e in a.exception]

assert at.slider(key="size_emphasis").value == 1.8, at.slider(key="size_emphasis").value
for value in (1.0, 2.6, 4.0):
    a = fresh()
    a.slider(key="size_emphasis").set_value(value).run()
    assert not a.exception, (value, [e.value for e in a.exception])
    print(f"emphasis ok: {value}")

# --- label threshold culls the small sub-intents ------------------------------
a = fresh()
a.slider(key="label_threshold").set_value(50_000).run()
assert not a.exception, [e.value for e in a.exception]
above = sum(1 for s in volumes.SUB_SERIES.values() if s[-1] >= 50_000)
print(f"label threshold 50,000 -> {above} sub-intents still labelled in {LATEST}")
assert 0 < above < 248, above

# --- focus mode ---------------------------------------------------------------
a = fresh()
a.radio(key="view_mode").set_value("Focus on one unified intent").run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
print("focus metrics:", m)
assert m["Unified intents"] == "1", m
assert m["Sub-intents"] == "8", m

# --- hiding a node type doesn't crash ----------------------------------------
a = fresh()
a.checkbox(key="type_sub_intent").uncheck().run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
print("no sub-intents metrics:", m)
assert m["Sub-intents"] == "0", m
# life events / complaints attach only to sub-intents, so they drop out too
assert m["Life events"] == "0" and m["Complaints"] == "0", m
assert m[conv_label] == "0", m

# =============================================================================
# Figure-level checks, built through the same code path the app uses
# =============================================================================
g = gb.build_graph()
pos = gb.compute_layout(g, "Spring (force-directed)")


EMPHASIS = 1.8  # the app's default


def figure_for(period):
    sizes = gb.compute_node_sizes(g, gb.SCALE_LOG, 1.0, period, EMPHASIS)
    return build_figure(
        g, pos, sizes, set(g.nodes), set(gb.EDGE_COLORS), 800, period, "rev"
    )


def traces(fig):
    named = {t.name: t for t in fig.data if t.name}
    return (
        next(t for n, t in named.items() if n.startswith("Unified intent")),
        next(t for n, t in named.items() if n.startswith("Sub-intent")),
    )


# --- marker sizes vary with volume, within the configured bounds --------------
ui_trace, sub_trace = traces(figure_for(len(volumes.PERIODS) - 1))
for label, trace, ntype in (
    ("unified", ui_trace, gb.UNIFIED_INTENT),
    ("sub", sub_trace, gb.SUB_INTENT),
):
    sizes = list(trace.marker.size)
    lo, hi = gb.SIZE_RANGES[ntype]
    assert len(set(sizes)) > 1, f"{label} markers are all one size"
    assert min(sizes) >= lo - 1e-9 and max(sizes) <= hi + 1e-9, (label, min(sizes), max(sizes))
    print(f"{label} marker sizes: {min(sizes):.1f} .. {max(sizes):.1f}")

# largest unified marker belongs to the highest-volume service in that period
busiest_ui = max(volumes.UNIFIED_SERIES, key=lambda k: volumes.UNIFIED_SERIES[k][-1])
biggest_idx = max(range(len(ui_trace.marker.size)), key=lambda i: ui_trace.marker.size[i])
assert ui_trace.text[biggest_idx] == busiest_ui, (ui_trace.text[biggest_idx], busiest_ui)
print(f"biggest unified node in {LATEST}: {busiest_ui} "
      f"({volumes.fmt(volumes.UNIFIED_SERIES[busiest_ui][-1])})")

# all 248 sub-intent labels present by default
assert sum(1 for t in sub_trace.text if t) == 248, sum(1 for t in sub_trace.text if t)
assert "Conversations" in sub_trace.hovertext[0], sub_trace.hovertext[0]
assert LATEST in sub_trace.hovertext[0], sub_trace.hovertext[0]

# --- POSITIONS ARE PINNED ACROSS THE TIMELINE, ONLY SIZES MOVE ---------------
figs = [figure_for(t) for t in range(len(volumes.PERIODS))]
base_ui, base_sub = traces(figs[0])

for t, fig in enumerate(figs[1:], start=1):
    ui_t, sub_t = traces(fig)
    for label, a_tr, b_tr in (("unified", base_ui, ui_t), ("sub", base_sub, sub_t)):
        assert list(a_tr.x) == list(b_tr.x), f"{label} x moved at period {t}"
        assert list(a_tr.y) == list(b_tr.y), f"{label} y moved at period {t}"
    # axis ranges must be identical too, or the whole view would drift
    assert fig.layout.xaxis.range == figs[0].layout.xaxis.range, t
    assert fig.layout.yaxis.range == figs[0].layout.yaxis.range, t
    assert fig.layout.uirevision == figs[0].layout.uirevision, t
print(f"positions identical across all {len(figs)} periods; axis ranges pinned")

# ...but sizes DO move
size_sets = [tuple(traces(f)[1].marker.size) for f in figs]
assert len(set(size_sets)) == len(figs), "sub-intent sizes repeat across periods"

# a growing sub-intent is drawn bigger in the last period than the first
grower = max(
    volumes.SUB_SERIES, key=lambda k: volumes.SUB_SERIES[k][-1] - volumes.SUB_SERIES[k][0]
)
idx = list(base_sub.text).index(grower[1])
first_size, last_size = size_sets[0][idx], size_sets[-1][idx]
assert last_size > first_size, (grower, first_size, last_size)
print(
    f"'{grower[1]}' grew {volumes.fmt(volumes.SUB_SERIES[grower][0])} -> "
    f"{volumes.fmt(volumes.SUB_SERIES[grower][-1])}, "
    f"marker {first_size:.1f} -> {last_size:.1f} px"
)

# --- ZOOM SURVIVES THE TIMELINE, BUT RESETS WHEN POSITIONS ACTUALLY MOVE -----
# Plotly keeps the user's zoom for as long as uirevision is unchanged, so this
# string is the whole contract.
all_uis = set(taxonomy.UNIFIED_INTENTS)
base_rev = view_revision("Spring (force-directed)", g.nodes(), all_uis)

# nothing about the period feeds into it, so every period yields the same string
assert all(
    view_revision("Spring (force-directed)", g.nodes(), all_uis) == base_rev
    for _ in volumes.PERIODS
)
# ...and the figures built for each period agree
assert len({f.layout.uirevision for f in figs}) == 1, "uirevision drifted across periods"

# but a different layout, or a different set of visible nodes, must reset it
assert view_revision("Kamada-Kawai", g.nodes(), all_uis) != base_rev
fewer = gb.filter_graph(g, set(gb.NODE_TYPES), {"Balance Transfer"})
assert view_revision("Spring (force-directed)", fewer.nodes(), {"Balance Transfer"}) != base_rev
print("uirevision: stable across periods, resets on layout/filter change")

print("\nALL APP TESTS PASSED")

"""End-to-end run of app.py via Streamlit's AppTest. Run: python app_test.py

The canvas itself (timeline frames, click-to-focus) is verified in
export_test.py, since it is the same HTML the Pages export writes. This file
covers the Streamlit shell around it: the sidebar controls, the metrics, and
that no combination of controls raises.
"""

import channels
import graph_builder as gb
import taxonomy
import volumes
from streamlit.testing.v1 import AppTest

CONV = "Conversations (all periods)"
FOCUS = "Focus on one unified intent"
GRAPH_METRICS = (CONV, "Nodes", "Unified intents", "Sub-intents",
                 "Life events", "Complaints")


def fresh(timeout=240):
    at = AppTest.from_file("app.py", default_timeout=timeout)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


def graph_metrics(at):
    return {k: v for k, v in metrics(at).items() if k in GRAPH_METRICS}


def prose(at):
    """All rendered text. Headings are their own element type, not markdown."""
    parts = []
    for collection in (at.markdown, at.subheader, at.header, at.caption):
        parts += [str(x.value) for x in collection]
    return " ".join(parts)


def caption_order(at, *needles):
    """Where each needle's caption sits in document order. Captions render in
    the order the script emits them, which is how section order is checked."""
    caps = [str(c.value) for c in at.caption]
    found = []
    for needle in needles:
        hit = next((i for i, c in enumerate(caps) if needle in c), None)
        assert hit is not None, f"no caption containing {needle!r}"
        found.append(hit)
    return found


def focused(ui):
    """The app in focus mode, showing `ui`."""
    a = fresh()
    a.radio(key="view_mode").set_value(FOCUS).run()
    a.selectbox(key="focus_unified").select(ui).run()
    assert not a.exception, (ui, [e.value for e in a.exception])
    return a


# --- default view -------------------------------------------------------------
at = fresh()
m = metrics(at)
print("default metrics:", m)
assert m["Nodes"] == "300", m
assert m["Unified intents"] == "31", m
assert m["Sub-intents"] == "248", m
assert m["Life events"] == "10", m
assert m["Complaints"] == "10", m
assert m[CONV] == volumes.fmt(volumes.PRODUCT_TOTAL), m
assert len(at.tabs) == 2, len(at.tabs)
assert at.dataframe, "data tab rendered no tables"

# the timeline is no longer a Streamlit widget - that is the point, it lives in
# the browser so moving it cannot trigger a rerun
assert "period" not in at.session_state, "timeline is still a server-side widget"

# sub-intent labels on by default
assert at.checkbox(key="label_sub_intent").value is True
assert at.session_state["label_threshold"] == 0
assert at.slider(key="size_emphasis").value == 1.8

# --- every layout renders ------------------------------------------------------
for opt in at.selectbox(key="layout").options:
    a = fresh()
    a.selectbox(key="layout").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])
    print(f"layout ok: {opt}")

# --- every size scale renders --------------------------------------------------
for opt in at.selectbox(key="size_scale").options:
    a = fresh()
    a.selectbox(key="size_scale").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])
    print(f"size scale ok: {opt}")

# --- sizing sliders ------------------------------------------------------------
for key, value in [
    ("size_multiplier", 2.0),
    ("size_emphasis", 1.0),
    ("size_emphasis", 4.0),
    ("label_threshold", 50_000),
]:
    a = fresh()
    a.slider(key=key).set_value(value).run()
    assert not a.exception, (key, value, [e.value for e in a.exception])
    print(f"slider ok: {key}={value}")

# =============================================================================
# Focus mode: the detail's unified picker is the only thing that chooses the
# service, and it sits above the canvas
# =============================================================================
ALL_UIS = list(taxonomy.UNIFIED_INTENTS)

a = fresh()
a.radio(key="view_mode").set_value(FOCUS).run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
print("focus metrics:", m)
assert m["Unified intents"] == "1", m
assert m["Sub-intents"] == "8", m

# the sidebar's own unified-intent selectbox is gone: focus mode used to render
# a second control with this same label, which could disagree with the detail
labelled_ui = [s for s in a.selectbox if s.label == "Unified intent"]
assert len(labelled_ui) == 1, (
    f"{len(labelled_ui)} 'Unified intent' selectboxes - the sidebar one is still there"
)
assert labelled_ui[0].key == "focus_unified", labelled_ui[0].key

# --- the picker really drives the canvas -------------------------------------
first_ui, other_ui = ALL_UIS[0], ALL_UIS[1]

a, b = focused(first_ui), focused(other_ui)
assert graph_metrics(a) != graph_metrics(b), (
    "changing the unified intent did not change the focused graph"
)
for ui, at_ in ((first_ui, a), (other_ui, b)):
    expected = sum(
        volumes.SUB_TOTALS[(ui, s)] for s in taxonomy.UNIFIED_INTENTS[ui]
    )
    got = graph_metrics(at_)
    assert got[CONV] == volumes.fmt(expected), (ui, got[CONV], expected)
    assert got["Unified intents"] == "1", (ui, got)
print(f"focus graph follows the detail picker: '{other_ui}' -> "
      f"{graph_metrics(b)[CONV]} conversations")

# --- but a sub-intent selection leaves the graph alone ------------------------
c = focused(other_ui)
before = graph_metrics(c)
c.selectbox(key="focus_sub").select(taxonomy.UNIFIED_INTENTS[other_ui][0]).run()
assert not c.exception, [e.value for e in c.exception]
assert graph_metrics(c) == before, (
    f"picking a sub-intent moved the graph: {before} -> {graph_metrics(c)}"
)
print("sub-intent selection leaves the focused graph on the parent service")

# --- the detail sits above the canvas, and only in focus mode ----------------
# "Channel intents" is a card's own caption, so it anchors the detail section;
# "**Timeline**" is the caption under the canvas.
detail_at, graph_at = caption_order(b, "Channel intents", "**Timeline**")
assert detail_at < graph_at, "the detail is still under the canvas in focus mode"

full = fresh()
full_text = prose(full)
for trace in ("Intent detail", "By channel", "Channel intents"):
    assert trace not in full_text, f"'{trace}' still renders on the full graph"
assert not [s for s in full.selectbox if s.key in ("focus_unified", "focus_sub")], (
    "the intent pickers still render on the full graph"
)
print("full graph shows the canvas alone; the detail is focus-mode only")

# --- the graph metrics travel with the canvas, not the top of the page --------
# Metrics render in document order, so the row's position relative to the
# cards' own "Conversations" metrics says which section it belongs to.
GRAPH_ROW = [CONV, "Nodes", "Unified intents", "Sub-intents",
             "Life events", "Complaints"]


def metric_order(at_):
    return [m.label for m in at_.metric]


focus_labels, full_labels = metric_order(b), metric_order(full)
assert full_labels == GRAPH_ROW, (
    f"the full graph renders metrics other than the row: {full_labels}"
)
assert focus_labels.index(CONV) > focus_labels.index("Conversations"), (
    f"the metric row is still above the detail when focused: {focus_labels}"
)
assert focus_labels[focus_labels.index(CONV):] == GRAPH_ROW, focus_labels
print("order ok: the metric row sits directly above the canvas in both views")

# --- the detail's own metric row is gone --------------------------------------
for gone in ("Conversations, all channels", "Channels carrying it",
             "Sub-intents in this service"):
    assert gone not in metrics(b), f"'{gone}' is still rendered"

# --- and so are the per-channel blurbs ----------------------------------------
detail_text = prose(b)
for c in channels.CHANNELS:
    assert c.label in detail_text, f"{c.label} card missing"
    assert c.blurb not in detail_text, f"{c.label}: the blurb is still under the title"
print("removed: the detail metric row and the channel blurbs")

# --- the selection survives a round trip through the full graph ---------------
# Streamlit drops widget state for widgets a run does not instantiate, and the
# full graph does not instantiate the picker. This passes only because the
# detail mirrors its choice into a plain (non-widget) session key.
r = focused(other_ui)
r.radio(key="view_mode").set_value("Full graph").run()
assert not r.exception, [e.value for e in r.exception]
assert graph_metrics(r)["Unified intents"] == "31", graph_metrics(r)

r.radio(key="view_mode").set_value(FOCUS).run()
assert not r.exception, [e.value for e in r.exception]
assert r.selectbox(key="focus_unified").value == other_ui, (
    f"the picker reset to {r.selectbox(key='focus_unified').value!r} after a run "
    f"without it; expected {other_ui!r}"
)
assert graph_metrics(r) == graph_metrics(b), (
    "the focused graph came back on a different service"
)
print(f"'{other_ui}' survives a trip through the full graph and back")

# --- the sub-intent table is gone ---------------------------------------------
assert "Sub-intents of this unified intent" not in prose(b), (
    "the sub-intent table is still rendered"
)
print("removed: the sub-intent table under the detail")

# --- hiding a node type ---------------------------------------------------------
a = fresh()
a.checkbox(key="type_sub_intent").uncheck().run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
print("no sub-intents metrics:", m)
assert m["Sub-intents"] == "0", m
# life events / complaints attach only to sub-intents, so they drop out too
assert m["Life events"] == "0" and m["Complaints"] == "0", m
assert m[CONV] == "0", m

# --- empty view degrades gracefully ---------------------------------------------
a = fresh()
for ntype in gb.NODE_TYPES:
    a.checkbox(key=f"type_{ntype}").uncheck()
a.run()
assert not a.exception, [e.value for e in a.exception]
assert a.warning, "empty view should warn, not crash"
print("empty view warns cleanly")

# =============================================================================
# Intent detail (focus mode only): three channel cards, two-level selection
# =============================================================================
data = channels.load()
ui = ALL_UIS[0]
subs = taxonomy.UNIFIED_INTENTS[ui]

at = focused(ui)
assert len(at.tabs) == 2, len(at.tabs)

# --- unified intent selected, no sub-intent ---------------------------------
# The per-channel numbers are all that is left of the counts, and they still
# have to add up to the intent's total across the three channels.
expected = channels.total(data, ui, "unified")
card_totals = [
    rec["numberOfConversations"]
    for _, rec in channels.records(data, ui, "unified") if rec
]
assert sum(card_totals) == expected, (card_totals, expected)
shown = [m.value for m in at.metric if m.label == "Conversations"]
assert shown == [volumes.fmt(v) for v in card_totals], (shown, card_totals)

body = " ".join(str(x.value) for x in at.markdown)
assert ui in body, "the selected unified intent is not named"
unified_desc = data["virtual-assistant"]["unified"][ui]["description"]
assert unified_desc in prose(at), "the unified intent description is not shown"

# all three channels are named, whether or not they carry the intent
for c in channels.CHANNELS:
    assert c.label in body, f"{c.label} card missing"

# the channel-specific intents for the UNIFIED intent are the ones displayed
shown_intents = " ".join(str(x.value) for x in at.markdown)
assert not at.code, "channel intents should be plain text, not code blocks"
count = 0
for c in channels.CHANNELS:
    for ci in data[c.key]["unified"][ui]["channelIntent"]:
        assert f"**{ci}**" in shown_intents, f"{c.label}: channel intent {ci} not shown"
        count += 1
print(f"unified '{ui}': 3 cards, {count} channel intents, "
      f"{volumes.fmt(expected)} conversations")

# --- sub-intent selected: its data takes precedence --------------------------
picked = subs[0]
a = focused(ui)
a.selectbox(key="focus_sub").select(picked).run()
assert not a.exception, [e.value for e in a.exception]

sub_expected = channels.total(data, picked, "sub")
assert sub_expected != expected, "test is vacuous - sub and unified totals coincide"
sub_cards = [
    rec["numberOfConversations"]
    for _, rec in channels.records(data, picked, "sub") if rec
]
shown = [m.value for m in a.metric if m.label == "Conversations"]
assert shown == [volumes.fmt(v) for v in sub_cards], (shown, sub_cards)
assert sum(sub_cards) == sub_expected, (sub_cards, sub_expected)

sub_body = " ".join(str(x.value) for x in a.markdown)
assert picked in sub_body, "the selected sub-intent is not named"

sub_shown = " ".join(str(x.value) for x in a.markdown)
for c in channels.CHANNELS:
    rec = data[c.key]["sub"].get(picked)
    if rec is None:
        continue
    for ci in rec["channelIntent"]:
        assert f"**{ci}**" in sub_shown, f"{c.label}: sub-intent channel intent {ci} not shown"
# ...and the parent's channel intents are gone, so the switch really happened
for c in channels.CHANNELS:
    for ci in data[c.key]["unified"][ui]["channelIntent"]:
        assert f"**{ci}**" not in sub_shown, f"{c.label}: still showing the parent's {ci}"
# the share-of-channels line under each card's number is gone
for element in a.metric:
    assert not getattr(element, "delta", None), (
        f"metric '{element.label}' still carries a delta line: {element.delta}"
    )
print(f"sub-intent '{picked}': overrides the parent, {volumes.fmt(sub_expected)} conversations")

# --- a sub-intent no channel-complete: the empty card still renders -----------
gap = next(
    (s for s in taxonomy.UNIFIED_INTENTS[ui] if s not in data["ai-voice-assistant"]["sub"]),
    None,
)
if gap is None:
    for other in taxonomy.UNIFIED_INTENTS:
        gap = next(
            (s for s in taxonomy.UNIFIED_INTENTS[other]
             if s not in data["ai-voice-assistant"]["sub"]),
            None,
        )
        if gap:
            ui = other
            break

a = focused(ui)
a.selectbox(key="focus_sub").select(gap).run()
assert not a.exception, [e.value for e in a.exception]
labels = " ".join(str(x.value) for x in a.markdown)
for c in channels.CHANNELS:
    assert c.label in labels, f"{c.label} card vanished for an uncarried sub-intent"
assert any("Not handled" in str(i.value) for i in a.info), "no empty-card message"
print(f"'{gap}' is absent from voice: three cards still shown, one marked unavailable")

# every unified intent renders without error
for name in ALL_UIS[:6]:
    a = focused(name)
    assert not a.exception, (name, [e.value for e in a.exception])
print("intent detail renders for every unified intent sampled")

print("\nALL APP TESTS PASSED")

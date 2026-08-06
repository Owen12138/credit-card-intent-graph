"""End-to-end run of app.py via Streamlit's AppTest. Run: python app_test.py

The canvas itself (timeline frames, drag, click-to-focus) is verified in
export_test.py and js_test.js, since it is the same HTML the Pages export
writes. This file covers the Streamlit shell: the sidebar controls, the intent
detail, and the link between the intent picker and the graph.
"""

import channels
import graph_builder as gb
import taxonomy
import volumes
from streamlit.testing.v1 import AppTest

CONV = "Conversations (all periods)"
UNIFIED_ONLY = "— none: show the unified intent —"

data = channels.load()
ALL_UIS = list(taxonomy.UNIFIED_INTENTS)


def fresh(timeout=240):
    at = AppTest.from_file("app.py", default_timeout=timeout)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


def prose(at):
    """All rendered text. Headings are their own element type, not markdown."""
    parts = []
    for collection in (at.markdown, at.subheader, at.header, at.caption):
        parts += [str(x.value) for x in collection]
    return " ".join(parts)


# --- default view: the graph is already scoped to the first unified intent ----
at = fresh()
m = metrics(at)
print("default metrics:", m)

first_ui = at.selectbox(key="focus_unified").options[0]
assert at.selectbox(key="focus_unified").value == first_ui
assert at.selectbox(key="focus_sub").value == UNIFIED_ONLY

assert m["Unified intents"] == "1", m
assert m["Sub-intents"] == "8", m
assert len(at.tabs) == 2, len(at.tabs)
assert at.dataframe, "data tab rendered no tables"

# the sidebar no longer decides which intents the graph shows
assert "view_mode" not in at.session_state, "the sidebar view mode is still there"

# the timeline lives in the browser, so it is not a Streamlit widget
assert "period" not in at.session_state, "timeline is still a server-side widget"
assert at.checkbox(key="label_sub_intent").value is True
assert at.slider(key="size_emphasis").value == 1.8

# =============================================================================
# The intent picker drives the graph
# =============================================================================
other_ui = next(u for u in ALL_UIS if u != first_ui)

a = fresh()
a.selectbox(key="focus_unified").select(other_ui).run()
assert not a.exception, [e.value for e in a.exception]
switched = metrics(a)

assert f"Graph: {other_ui}" in prose(a), "the graph is not labelled with the selection"
assert switched[CONV] != m[CONV], (
    "changing the unified intent did not change the graph"
)
assert switched["Unified intents"] == "1", switched
assert switched["Sub-intents"] == "8", switched

# the graph really is that service's own subgraph
expected = sum(
    volumes.SUB_TOTALS[(other_ui, s)] for s in taxonomy.UNIFIED_INTENTS[other_ui]
)
assert switched[CONV] == volumes.fmt(expected), (switched[CONV], expected)
print(f"picker drives the graph: '{other_ui}' -> {switched[CONV]} conversations")

# --- but a sub-intent selection must NOT change the graph ---------------------
b = fresh()
b.selectbox(key="focus_unified").select(other_ui).run()
before_graph = {k: v for k, v in metrics(b).items() if k in
                (CONV, "Nodes", "Unified intents", "Sub-intents", "Life events", "Complaints")}

b.selectbox(key="focus_sub").select(taxonomy.UNIFIED_INTENTS[other_ui][0]).run()
assert not b.exception, [e.value for e in b.exception]
after_graph = {k: v for k, v in metrics(b).items() if k in before_graph}

assert after_graph == before_graph, (
    f"picking a sub-intent changed the graph: {before_graph} -> {after_graph}"
)
assert f"Graph: {other_ui}" in prose(b), "the graph stopped showing the parent service"
print("sub-intent selection leaves the graph on the parent service, as intended")

# =============================================================================
# Intent detail
# =============================================================================
at = fresh()
ui = first_ui
subs = taxonomy.UNIFIED_INTENTS[ui]

body = prose(at)
assert ui in body, "the selected unified intent is not named"
unified_desc = data["virtual-assistant"]["unified"][ui]["description"]
assert unified_desc in body, "the unified intent description is not shown"

for c in channels.CHANNELS:
    assert c.label in body, f"{c.label} card missing"

assert not at.code, "channel intents should be plain text, not code blocks"
count = 0
for c in channels.CHANNELS:
    for ci in data[c.key]["unified"][ui]["channelIntent"]:
        assert f"**{ci}**" in body, f"{c.label}: channel intent {ci} not shown"
        count += 1
print(f"unified '{ui}': 3 cards, {count} channel intents")

# --- the trimmed-away pieces are really gone ---------------------------------
labels = set(metrics(at))
for gone in ("Conversations, all channels", "Channels carrying it",
             "Sub-intents in this service"):
    assert gone not in labels, f"'{gone}' is still rendered"

for element in at.metric:
    assert not getattr(element, "delta", None), (
        f"metric '{element.label}' still carries a delta line"
    )

sample = data["virtual-assistant"]["unified"][ui]["sampleConversation"]["conversationText"]
assert sample not in body, "sample conversations are still rendered"
assert "Sub-intents of this unified intent" not in body, "the sub-intent table is still there"
print("removed: detail metric row, deltas, sample conversations, sub-intent table")

# --- sub-intent selected: its data takes precedence in the DETAIL ------------
picked = subs[0]
a = fresh()
a.selectbox(key="focus_sub").select(picked).run()
assert not a.exception, [e.value for e in a.exception]

sub_body = prose(a)
assert picked in sub_body, "the selected sub-intent is not named"
sub_desc = data["virtual-assistant"]["sub"][picked]["description"]
assert sub_desc in sub_body, "the sub-intent description did not take over"

for c in channels.CHANNELS:
    rec = data[c.key]["sub"].get(picked)
    if rec is None:
        continue
    for ci in rec["channelIntent"]:
        assert f"**{ci}**" in sub_body, f"{c.label}: sub-intent intent {ci} not shown"
for c in channels.CHANNELS:
    for ci in data[c.key]["unified"][ui]["channelIntent"]:
        assert f"**{ci}**" not in sub_body, f"{c.label}: still showing the parent's {ci}"
print(f"sub-intent '{picked}': detail switches over to it entirely")

# --- a sub-intent a channel does not carry still renders three cards ----------
gap_ui, gap = None, None
for candidate in ALL_UIS:
    gap = next(
        (s for s in taxonomy.UNIFIED_INTENTS[candidate]
         if s not in data["ai-voice-assistant"]["sub"]),
        None,
    )
    if gap:
        gap_ui = candidate
        break
assert gap, "no uncarried sub-intent to test with"

a = fresh()
a.selectbox(key="focus_unified").select(gap_ui).run()
a.selectbox(key="focus_sub").select(gap).run()
assert not a.exception, [e.value for e in a.exception]
for c in channels.CHANNELS:
    assert c.label in prose(a), f"{c.label} card vanished for an uncarried sub-intent"
assert any("Not handled" in str(i.value) for i in a.info), "no empty-card message"
print(f"'{gap}' is absent from voice: three cards still shown, one marked unavailable")

# =============================================================================
# Sidebar still works
# =============================================================================
for opt in at.selectbox(key="layout").options:
    a = fresh()
    a.selectbox(key="layout").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])
    print(f"layout ok: {opt}")

for opt in at.selectbox(key="size_scale").options:
    a = fresh()
    a.selectbox(key="size_scale").select(opt).run()
    assert not a.exception, (opt, [e.value for e in a.exception])

for key, value in [
    ("size_multiplier", 2.0),
    ("size_emphasis", 4.0),
    ("label_threshold", 50_000),
]:
    a = fresh()
    a.slider(key=key).set_value(value).run()
    assert not a.exception, (key, value, [e.value for e in a.exception])
print("size scales and sliders ok")

# hiding sub-intents drops the life events and complaints hanging off them
a = fresh()
a.checkbox(key="type_sub_intent").uncheck().run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
assert m["Sub-intents"] == "0", m
assert m["Life events"] == "0" and m["Complaints"] == "0", m
assert m[CONV] == "0", m

# every node type off degrades gracefully
a = fresh()
for ntype in gb.NODE_TYPES:
    a.checkbox(key=f"type_{ntype}").uncheck()
a.run()
assert not a.exception, [e.value for e in a.exception]
assert a.warning, "empty view should warn, not crash"
print("empty view warns cleanly")

# every unified intent renders, detail and graph together
for name in ALL_UIS[:6]:
    a = fresh()
    a.selectbox(key="focus_unified").select(name).run()
    assert not a.exception, (name, [e.value for e in a.exception])
    assert f"Graph: {name}" in prose(a), name
print("detail and graph render together for every unified intent sampled")

print("\nALL APP TESTS PASSED")

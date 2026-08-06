"""End-to-end run of app.py via Streamlit's AppTest. Run: python app_test.py

The canvas itself (timeline frames, click-to-focus) is verified in
export_test.py, since it is the same HTML the Pages export writes. This file
covers the Streamlit shell around it: the sidebar controls, the metrics, and
that no combination of controls raises.
"""

import graph_builder as gb
import volumes
from streamlit.testing.v1 import AppTest

CONV = "Conversations (all periods)"


def fresh(timeout=240):
    at = AppTest.from_file("app.py", default_timeout=timeout)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


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

# --- focus mode ----------------------------------------------------------------
a = fresh()
a.radio(key="view_mode").set_value("Focus on one unified intent").run()
assert not a.exception, [e.value for e in a.exception]
m = metrics(a)
print("focus metrics:", m)
assert m["Unified intents"] == "1", m
assert m["Sub-intents"] == "8", m

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
# Intent detail (on the Graph tab): three channel cards, two-level selection
# =============================================================================
import channels
import taxonomy

at = fresh()
assert len(at.tabs) == 2, len(at.tabs)

data = channels.load()
ui = at.selectbox(key="focus_unified").options[0]
subs = taxonomy.UNIFIED_INTENTS[ui]

# --- unified intent selected, no sub-intent ---------------------------------
m = metrics(at)
expected = channels.total(data, ui, "unified")
assert m["Conversations, all channels"] == volumes.fmt(expected), m
assert m["Sub-intents in this service"] == str(len(subs)), m

body = " ".join(str(x.value) for x in at.markdown)
assert ui in body, "the selected unified intent is not named"
unified_desc = data["virtual-assistant"]["unified"][ui]["description"]
prose = " ".join(
    str(x.value) for x in list(at.markdown) + list(at.get("text")) + list(at.caption)
)
assert unified_desc in prose, "the unified intent description is not shown"

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
a = fresh()
a.selectbox(key="focus_unified").select(ui).run()
a.selectbox(key="focus_sub").select(picked).run()
assert not a.exception, [e.value for e in a.exception]

m = metrics(a)
sub_expected = channels.total(data, picked, "sub")
assert m["Conversations, all channels"] == volumes.fmt(sub_expected), m
assert sub_expected != expected, "test is vacuous - sub and unified totals coincide"
assert "Sub-intents in this service" not in m, "sub view still shows the parent's count"

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

a = fresh()
a.selectbox(key="focus_unified").select(ui).run()
a.selectbox(key="focus_sub").select(gap).run()
assert not a.exception, [e.value for e in a.exception]
labels = " ".join(str(x.value) for x in a.markdown)
for c in channels.CHANNELS:
    assert c.label in labels, f"{c.label} card vanished for an uncarried sub-intent"
assert any("Not handled" in str(i.value) for i in a.info), "no empty-card message"
print(f"'{gap}' is absent from voice: three cards still shown, one marked unavailable")

# every unified intent renders without error
for name in list(taxonomy.UNIFIED_INTENTS)[:6]:
    a = fresh()
    a.selectbox(key="focus_unified").select(name).run()
    assert not a.exception, (name, [e.value for e in a.exception])
print("intent detail renders for every unified intent sampled")

print("\nALL APP TESTS PASSED")

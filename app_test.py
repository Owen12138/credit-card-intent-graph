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
assert len(at.tabs) == 2
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

print("\nALL APP TESTS PASSED")

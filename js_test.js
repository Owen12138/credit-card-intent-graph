/*
 * Runs the canvas script from docs/index.html against a stubbed Plotly and DOM,
 * so the browser behaviour (semantic zoom, click focus, label modes) is actually
 * exercised rather than eyeballed.
 *
 *   node js_test.js
 */
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("docs/index.html", "utf8");

const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const src = scripts.find((s) => s.includes("var META ="));
if (!src) throw new Error("canvas script not found in docs/index.html");

const META = JSON.parse(src.match(/var META = (\{[\s\S]*?\});\s*\n/)[1]);
const subTrace = META.nodeTraces.find((t) => t.type === META.subIntent);
const uiTrace = META.nodeTraces.find((t) => t.type === "unified_intent");

// ---- the traces the script restyles must be able to render text --------------
// Plotly silently drops text restyled into a trace whose mode is plain
// "markers", so driving the events is not enough - the trace config has to
// allow a label to appear in the first place.
function extractNewPlotData(page) {
  // Anchor on the div id: the inlined plotly.js bundle contains its own
  // "Plotly.newPlot(" strings in documentation examples.
  const at = page.search(/Plotly\.newPlot\(\s*["']intent-graph["']/);
  if (at === -1) throw new Error("real newPlot call not found");
  const start = page.indexOf("[", at);
  let depth = 0;
  for (let i = start; i < page.length; i++) {
    if (page[i] === "[") depth++;
    else if (page[i] === "]" && --depth === 0) return JSON.parse(page.slice(start, i + 1));
  }
  throw new Error("could not extract the newPlot data array");
}

const traces = extractNewPlotData(html);
META.nodeTraces.forEach((t) => {
  const mode = traces[t.trace].mode || "";
  if (!mode.includes("text")) {
    console.error(
      `FAIL: ${t.type} trace is mode="${mode}" - Plotly would ignore any label ` +
        "the script reveals"
    );
    process.exit(1);
  }
});
console.log(`all ${META.nodeTraces.length} node traces can render text`);

// ---- stubs -------------------------------------------------------------------
const handlers = {};
const calls = [];

const gd = {
  layout: { xaxis: { range: [-META.baseSpan / 2, META.baseSpan / 2] } },
  on: (ev, fn) => (handlers[ev] = fn),
};

const Plotly = {
  restyle: (_g, update, idx) => calls.push({ update, idx }),
};

const elements = {};
const element = (id) =>
  (elements[id] = elements[id] || { id, innerHTML: "", textContent: "", onclick: null });

const document = {
  getElementById: (id) => (id === "intent-graph" ? gd : element(id)),
};

vm.runInContext(
  src,
  vm.createContext({ Plotly, document, Math, JSON, Object, Array, console })
);

// ---- helpers -----------------------------------------------------------------
function lastText(traceIndex) {
  for (let i = calls.length - 1; i >= 0; i--) {
    const c = calls[i];
    if (!c.update.text) continue;
    const at = c.idx.indexOf(traceIndex);
    if (at !== -1) return c.update.text[at];
  }
  return null;
}

function lastOpacity(traceIndex) {
  for (let i = calls.length - 1; i >= 0; i--) {
    const c = calls[i];
    if (!c.update["marker.opacity"]) continue;
    const at = c.idx.indexOf(traceIndex);
    if (at !== -1) return c.update["marker.opacity"][at];
  }
  return null;
}

const shown = (arr) => arr.filter((t) => t).length;

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL: " + msg);
    process.exit(1);
  }
}

function zoomTo(factor) {
  const span = META.baseSpan / factor;
  gd.layout.xaxis.range = [-span / 2, span / 2];
  handlers["plotly_relayout"]({});
}

// ---- 1. zoomed out: no sub-intent labels, other types keep theirs -------------
assert(handlers["plotly_relayout"], "no relayout handler registered");
assert(handlers["plotly_click"], "no click handler registered");

let subs = lastText(subTrace.trace);
let uis = lastText(uiTrace.trace);
assert(subs !== null, "sub-intent labels never set on init");
assert(shown(subs) === 0, `zoomed out should hide all sub-intent labels, got ${shown(subs)}`);
assert(
  shown(uis) === uiTrace.ids.length,
  `unified intents should stay labelled, got ${shown(uis)}/${uiTrace.ids.length}`
);
console.log(`zoomed out (1x): sub-intent labels ${shown(subs)}/${subTrace.ids.length}`);

// ---- 2. just below the threshold: still hidden -------------------------------
zoomTo(META.labelZoom - 0.3);
subs = lastText(subTrace.trace);
assert(shown(subs) === 0, "labels appeared before the threshold");
console.log(`at ${(META.labelZoom - 0.3).toFixed(1)}x: still hidden`);

// ---- 3. past the threshold: labels appear -----------------------------------
zoomTo(META.labelZoom + 0.5);
subs = lastText(subTrace.trace);
assert(
  shown(subs) === subTrace.ids.length,
  `zoomed in should reveal all sub-intent labels, got ${shown(subs)}`
);
console.log(`at ${(META.labelZoom + 0.5).toFixed(1)}x: ${shown(subs)} labels revealed`);

// ---- 4. zooming back out hides them again -----------------------------------
zoomTo(1);
subs = lastText(subTrace.trace);
assert(shown(subs) === 0, "labels did not hide again on zoom out");
console.log("back to 1x: hidden again");

// ---- 5. clicking a node focuses it, and labels its neighbourhood even when
//         zoomed out, because only a handful of nodes remain ------------------
const target = uiTrace.ids[0];
handlers["plotly_click"]({ points: [{ customdata: [target] }] });

const neighbours = META.adjacency[target];
subs = lastText(subTrace.trace);
const focusedSubs = neighbours.filter((n) => subTrace.ids.includes(n)).length;
assert(
  shown(subs) === focusedSubs,
  `focus should label its ${focusedSubs} sub-intents, got ${shown(subs)}`
);

const op = lastOpacity(subTrace.trace);
const bright = op.filter((o) => o === 1).length;
assert(bright === focusedSubs, `focus should light ${focusedSubs} sub-intents, got ${bright}`);
assert(op.some((o) => o === META.dimNode), "nothing was dimmed");
console.log(
  `click '${target}': ${focusedSubs} sub-intents lit and labelled while zoomed out`
);

// ---- 6. clicking the same node again clears ---------------------------------
handlers["plotly_click"]({ points: [{ customdata: [target] }] });
assert(
  lastOpacity(subTrace.trace).every((o) => o === 1),
  "clicking twice did not restore full opacity"
);
assert(shown(lastText(subTrace.trace)) === 0, "clearing focus left labels on at 1x");
console.log("click again: focus cleared, labels back to zoom rules");

// ---- 7. the manual override works both ways ---------------------------------
element("label-mode").onclick(); // auto -> always
assert(
  shown(lastText(subTrace.trace)) === subTrace.ids.length,
  "'always' did not force labels on at 1x"
);
element("label-mode").onclick(); // always -> off
zoomTo(META.labelZoom + 2);
assert(shown(lastText(subTrace.trace)) === 0, "'off' still showed labels when zoomed in");
element("label-mode").onclick(); // off -> auto
assert(
  shown(lastText(subTrace.trace)) === subTrace.ids.length,
  "back to auto did not restore zoom behaviour"
);
console.log("label mode: always / off / auto all behave");

// ---- 8. clicks on edges are ignored -----------------------------------------
calls.length = 0;
handlers["plotly_click"]({ points: [{}] });
assert(calls.length === 0, "a click without customdata should be ignored");
console.log("edge clicks ignored");

console.log("\nJS TESTS PASSED");

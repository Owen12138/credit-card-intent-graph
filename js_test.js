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

const listeners = {};
const gd = {
  layout: { xaxis: { range: META.baseX.slice() }, yaxis: { range: META.baseY.slice() } },
  _fullLayout: {
    xaxis: { range: META.baseX.slice() },
    yaxis: { range: META.baseY.slice() },
    _size: { l: 80, t: 40, w: 900, h: 600 },
  },
  _transitionData: { _frames: [] },
  on: (ev, fn) => (handlers[ev] = fn),
  addEventListener: (ev, fn) => (listeners[ev] = fn),
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1060, height: 700 }),
};

const Plotly = {
  restyle: (_g, update, idx) => calls.push({ kind: "restyle", update, idx }),
  update: (_g, tr, lay, idx) => {
    calls.push({ kind: "update", update: tr, layout: lay, idx });
    // mirror what Plotly would do, so the next read sees the new ranges
    if (lay["xaxis.range"]) {
      gd._fullLayout.xaxis.range = lay["xaxis.range"].slice();
      gd.layout.xaxis.range = lay["xaxis.range"].slice();
    }
    if (lay["yaxis.range"]) {
      gd._fullLayout.yaxis.range = lay["yaxis.range"].slice();
      gd.layout.yaxis.range = lay["yaxis.range"].slice();
    }
  },
};

const elements = {};
const element = (id) =>
  (elements[id] = elements[id] || { id, innerHTML: "", textContent: "", onclick: null });

const document = {
  getElementById: (id) => (id === "intent-graph" ? gd : element(id)),
};

// window listeners drive the drag. rAF runs inline but advances a clock, so the
// spring-back easing progresses and terminates instead of looping on one instant.
const winListeners = {};
const window = { addEventListener: (ev, fn) => (winListeners[ev] = fn) };
let clock = 0;
const requestAnimationFrame = (fn) => {
  clock += 16;
  fn(clock);
};

vm.runInContext(
  src,
  vm.createContext({
    Plotly,
    document,
    window,
    requestAnimationFrame,
    Math,
    JSON,
    Object,
    Array,
    Infinity,
    console,
  })
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

function lastSize(traceIndex) {
  for (let i = calls.length - 1; i >= 0; i--) {
    const c = calls[i];
    if (!c.update["marker.size"]) continue;
    const at = c.idx.indexOf(traceIndex);
    if (at !== -1) return c.update["marker.size"][at];
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

function nodeIndexOf(id) {
  for (const t of META.nodeTraces) {
    const i = t.ids.indexOf(id);
    if (i !== -1) return { trace: t.trace, i, ord: META.nodeTraces.indexOf(t) };
  }
  throw new Error("unknown node " + id);
}

const clearFocusIfAny = () => document.getElementById("focus-clear-top").onclick();

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL: " + msg);
    process.exit(1);
  }
}

// Drive real wheel events at the centre of the plot, exactly as a user would.
function wheel(times, dir) {
  for (let i = 0; i < times; i++) {
    listeners["wheel"]({
      deltaY: dir === "in" ? -100 : 100,
      clientX: 80 + 900 / 2,
      clientY: 40 + 600 / 2,
      preventDefault() {},
    });
  }
}

const currentZoom = () => {
  const r = gd._fullLayout.xaxis.range;
  return (META.baseX[1] - META.baseX[0]) / (r[1] - r[0]);
};

function zoomTo(factor) {
  document.getElementById("zoom-reset").onclick();
  const step = Math.log(factor) / Math.log(META.zoomStep);
  wheel(Math.round(Math.abs(step)), step >= 0 ? "in" : "out");
}

// ---- 1. zoomed out: no sub-intent labels, other types keep theirs -------------
assert(listeners["wheel"], "no wheel handler registered - zoom is not owned by the page");
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

// ---- 6b. focusing a life event keeps its edge weight ------------------------
// Life-event edge width encodes the event's occurrence count. The focus overlay
// redraws those edges, so if it used one fixed width the encoding would vanish
// on the click that examines it most closely.
function lastFocusWidth() {
  for (let i = calls.length - 1; i >= 0; i--) {
    const c = calls[i];
    if (c.kind !== "restyle" || c.update["line.width"] === undefined) continue;
    if (c.idx.indexOf(META.focusTrace) !== -1) return c.update["line.width"];
  }
  return null;
}

const lifeIds = Object.keys(META.lifeEdgeWidth);
assert(lifeIds.length > 0, "no life events in META");
const byWidth = (pick) =>
  lifeIds.reduce((a, b) => (pick(META.lifeEdgeWidth[a], META.lifeEdgeWidth[b]) ? a : b));
const heaviest = byWidth((a, b) => a >= b);
const lightest = byWidth((a, b) => a <= b);
assert(
  META.lifeEdgeWidth[heaviest] > META.lifeEdgeWidth[lightest],
  "every life event has the same width - this test proves nothing"
);

handlers["plotly_click"]({ points: [{ customdata: [heaviest] }] });
assert(
  lastFocusWidth() === Math.max(META.lifeEdgeWidth[heaviest], META.focusWidth),
  `focusing '${heaviest}' drew the overlay at ${lastFocusWidth()}, ` +
    `not its own ${META.lifeEdgeWidth[heaviest]}`
);
clearFocusIfAny();

// the rarest event is a hairline, so the overlay lifts it to the floor
handlers["plotly_click"]({ points: [{ customdata: [lightest] }] });
assert(
  lastFocusWidth() === META.focusWidth,
  `a ${META.lifeEdgeWidth[lightest]}px edge should be floored at ${META.focusWidth}`
);
clearFocusIfAny();

// any other node mixes widths, so it falls back to the default
handlers["plotly_click"]({ points: [{ customdata: [subTrace.ids[0]] }] });
assert(
  lastFocusWidth() === META.focusWidth,
  `a sub-intent should use the default overlay width, got ${lastFocusWidth()}`
);
clearFocusIfAny();
console.log(
  `focus overlay: '${heaviest}' keeps ${META.lifeEdgeWidth[heaviest]}px, ` +
    `'${lightest}' floored to ${META.focusWidth}px`
);

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

// ---- 8. circles are drawn ON the graph: they shrink as you zoom out, so the
//         gaps between nodes survive and they never pile up ------------------
const base = META.frameSizes[0][META.nodeTraces.indexOf(subTrace)];
const expected = (z) => base.map((s) => Math.max(META.minMarkerPx, s * z));

document.getElementById("zoom-reset").onclick();
let sizes = lastSize(subTrace.trace);
assert(
  sizes.every((s, i) => Math.abs(s - expected(1)[i]) < 1e-6),
  "at the fitted view markers should be exactly their designed size"
);

wheel(4, "out");
let z = currentZoom();
assert(z < 1, `zooming out should reduce the zoom factor, got ${z}`);
sizes = lastSize(subTrace.trace);
assert(
  sizes.every((s, i) => Math.abs(s - expected(z)[i]) < 1e-6),
  "markers did not shrink with the view when zooming out"
);
console.log(`4 notches out -> zoom ${z.toFixed(3)}, markers scaled to match`);

// THE requirement: a node's size relative to the drawing never changes, so the
// space between nodes is preserved at every zoom and they cannot overlap more
// than they do at the fitted view.
// The plot area is a fixed number of pixels, so a marker of P pixels covers a
// data width of P * span / areaPixels. Holding a node's size fixed ON THE GRAPH
// therefore means P * span must be constant - P alone shrinking is the point.
// Measured on the largest node, which never reaches the minimum-pixel floor.
const spanNow = () => gd._fullLayout.xaxis.range[1] - gd._fullLayout.xaxis.range[0];
const biggest = base.indexOf(Math.max.apply(null, base));
const ratioAt = () => lastSize(subTrace.trace)[biggest] * spanNow();

document.getElementById("zoom-reset").onclick();
const want = ratioAt();
for (const n of [1, 3, 6, 10]) {
  document.getElementById("zoom-reset").onclick();
  wheel(n, "out");
  assert(
    Math.abs(ratioAt() / want - 1) < 1e-6,
    `size-to-span ratio drifted after ${n} notches out`
  );
  document.getElementById("zoom-reset").onclick();
  wheel(n, "in");
  assert(
    Math.abs(ratioAt() / want - 1) < 1e-6,
    `size-to-span ratio drifted after ${n} notches in`
  );
}
console.log("size-to-span ratio identical at every zoom: spacing is preserved");

// ---- 9. no repaint ever moves the range without also resizing ---------------
// This is what made the old build snap: Plotly painted the new range first and
// the sizes were corrected a beat later, so each notch rendered twice.
calls.length = 0;
document.getElementById("zoom-reset").onclick();
wheel(5, "out");
wheel(8, "in");

const ranged = calls.filter((c) => c.layout && c.layout["xaxis.range"]);
assert(ranged.length > 0, "zooming produced no range changes at all");
ranged.forEach((c) => {
  assert(c.kind === "update", "a range change was not part of a combined update");
  assert(c.update["marker.size"], "a range moved without resizing the markers");
  assert(c.update.text, "a range moved without settling the labels");
});
assert(
  calls.every((c) => !(c.kind === "restyle" && c.update["marker.size"])),
  "markers were resized in a separate repaint - that is the snap"
);
console.log(
  `${ranged.length} zoom steps, every one a single update carrying range + size + labels`
);

document.getElementById("zoom-reset").onclick();
assert(Math.abs(currentZoom() - 1) < 1e-9, "reset did not return to the fitted view");

// zoom limits hold
document.getElementById("zoom-reset").onclick();
wheel(200, "out");
assert(Math.abs(currentZoom() - META.zoomMin) < 1e-6, `zoom-out ran past the limit`);
document.getElementById("zoom-reset").onclick();
wheel(200, "in");
assert(Math.abs(currentZoom() - META.zoomMax) < 1e-6, `zoom-in ran past the limit`);
console.log(`zoom clamped to ${META.zoomMin}x - ${META.zoomMax}x`);
document.getElementById("zoom-reset").onclick();

// ---- 10. nodes drag, everything attached follows, and they spring back -----
function lastXY(traceIndex) {
  for (let i = calls.length - 1; i >= 0; i--) {
    const c = calls[i];
    if (!c.update.x) continue;
    const at = c.idx.indexOf(traceIndex);
    if (at !== -1) return [c.update.x[at], c.update.y[at]];
  }
  return null;
}

// pixel position of a node under the current view, mirroring the page's maths
function pixelOf(id) {
  const s = gd._fullLayout._size;
  const xr = gd._fullLayout.xaxis.range;
  const yr = gd._fullLayout.yaxis.range;
  const p = META.pos[id];
  return [
    ((p[0] - xr[0]) / (xr[1] - xr[0])) * s.w + s.l,
    ((yr[1] - p[1]) / (yr[1] - yr[0])) * s.h + s.t,
  ];
}

document.getElementById("zoom-reset").onclick();
clearFocusIfAny();

const dragTarget = uiTrace.ids[0];
const dragAt = nodeIndexOf(dragTarget);
const dragFrom = pixelOf(dragTarget);
const home = META.pos[dragTarget];

// --- while held, the node follows the cursor ---
calls.length = 0;
listeners["mousedown"]({
  clientX: dragFrom[0],
  clientY: dragFrom[1],
  preventDefault() {},
  stopPropagation() {},
});
winListeners["mousemove"]({ clientX: dragFrom[0] + 120, clientY: dragFrom[1] - 90 });

const held = lastXY(dragAt.trace);
assert(held, "dragging produced no position update");
const at = [held[0][dragAt.i], held[1][dragAt.i]];
assert(
  Math.abs(at[0] - home[0]) > 1e-6 || Math.abs(at[1] - home[1]) > 1e-6,
  "the dragged node did not follow the cursor"
);
console.log(
  `held '${dragTarget}': (${home[0].toFixed(2)}, ${home[1].toFixed(2)}) -> ` +
    `(${at[0].toFixed(2)}, ${at[1].toFixed(2)})`
);

// neighbours in the same trace stayed put
assert(
  uiTrace.ids.every((id, i) =>
    i === dragAt.i ? true : Math.abs(held[0][i] - META.pos[id][0]) < 1e-9
  ),
  "dragging one node moved others"
);

// every edge touching it was redrawn to the held position, across all traces
let checked = 0;
META.edgePairs.forEach((e) => {
  const xy = lastXY(e.trace);
  e.pairs.forEach((p, k) => {
    const isEnd0 = p[0] === dragTarget;
    if (!isEnd0 && p[1] !== dragTarget) return;
    assert(xy, `edge trace ${e.trace} was not redrawn`);
    const gx = isEnd0 ? xy[0][k * 3] : xy[0][k * 3 + 1];
    const gy = isEnd0 ? xy[1][k * 3] : xy[1][k * 3 + 1];
    assert(
      Math.abs(gx - at[0]) < 1e-9 && Math.abs(gy - at[1]) < 1e-9,
      `an edge still points at the old position of ${dragTarget}`
    );
    checked++;
  });
});
const degree = META.adjacency[dragTarget].length;
assert(checked === degree, `only ${checked} of ${degree} attached edges were redrawn`);
console.log(`all ${checked} edges follow it while held`);

// --- released, it eases back to where the layout put it ---
calls.length = 0;
winListeners["mouseup"]({});

const landed = lastXY(dragAt.trace);
assert(landed, "releasing produced no update");
assert(
  Math.abs(landed[0][dragAt.i] - home[0]) < 1e-9 &&
    Math.abs(landed[1][dragAt.i] - home[1]) < 1e-9,
  "the node did not return to its layout position"
);

// it animated rather than teleporting, and the motion was monotonic homeward
const frames = calls.filter((c) => c.update.x && c.idx.indexOf(dragAt.trace) !== -1);
assert(frames.length > 3, `sprang home in ${frames.length} frames - not animated`);
let prev = Infinity;
frames.forEach((c) => {
  const k = c.idx.indexOf(dragAt.trace);
  const d = Math.abs(c.update.x[k][dragAt.i] - home[0]);
  assert(d <= prev + 1e-9, "the spring overshot or reversed");
  prev = d;
});
console.log(`released: eased home over ${frames.length} frames, no overshoot`);

// the edges came home with it
META.edgePairs.forEach((e) => {
  const xy = lastXY(e.trace);
  e.pairs.forEach((p, k) => {
    const isEnd0 = p[0] === dragTarget;
    if (!isEnd0 && p[1] !== dragTarget) return;
    const gx = isEnd0 ? xy[0][k * 3] : xy[0][k * 3 + 1];
    assert(Math.abs(gx - home[0]) < 1e-9, "an edge stayed behind after the spring");
  });
});

// grabbing the node again mid-spring must cancel it, not fight it
listeners["mousedown"]({
  clientX: dragFrom[0],
  clientY: dragFrom[1],
  preventDefault() {},
  stopPropagation() {},
});
winListeners["mousemove"]({ clientX: dragFrom[0] + 60, clientY: dragFrom[1] });
const regrab = lastXY(dragAt.trace);
assert(
  Math.abs(regrab[0][dragAt.i] - home[0]) > 1e-6,
  "a re-grab was overridden by the in-flight spring"
);
winListeners["mouseup"]({});
console.log("re-grabbing cancels an in-flight spring");

// a press that does not travel is still a click, so focus survives dragging
calls.length = 0;
listeners["mousedown"]({
  clientX: dragFrom[0],
  clientY: dragFrom[1],
  preventDefault() {},
  stopPropagation() {},
});
winListeners["mouseup"]({});
assert(
  lastOpacity(subTrace.trace).some((o) => o === META.dimNode),
  "a click on a node no longer focuses it"
);
console.log("a press that does not travel still focuses, not drags");

clearFocusIfAny();

// ---- 11. the edge-hover targets ride along with a drag ----------------------
// They sit at edge midpoints, so a dragged node has to carry them - otherwise
// the number stays behind, hovering empty space where the edge used to be.
document.getElementById("zoom-reset").onclick();
clearFocusIfAny();

const lifeNode = META.edgeHover.pairs[0][0];
const lifeAt = nodeIndexOf(lifeNode);
const lifeFrom = pixelOf(lifeNode);

calls.length = 0;
listeners["mousedown"]({
  clientX: lifeFrom[0],
  clientY: lifeFrom[1],
  preventDefault() {},
  stopPropagation() {},
});
winListeners["mousemove"]({ clientX: lifeFrom[0] + 140, clientY: lifeFrom[1] + 100 });

const heldLife = lastXY(lifeAt.trace);
assert(heldLife, "dragging the life event produced no update");
const lifeTo = [heldLife[0][lifeAt.i], heldLife[1][lifeAt.i]];
assert(
  Math.abs(lifeTo[0] - META.pos[lifeNode][0]) > 1e-6,
  `'${lifeNode}' did not move`
);

const hoverXY = lastXY(META.edgeHover.trace);
assert(hoverXY, "the hover targets were not redrawn");

let tracked = 0;
META.edgeHover.pairs.forEach((p, k) => {
  const touched = p[0] === lifeNode || p[1] === lifeNode;
  const other = p[0] === lifeNode ? p[1] : p[0];
  const from = touched ? lifeTo : META.pos[p[0]];
  const mx = touched
    ? (from[0] + META.pos[other][0]) / 2
    : (META.pos[p[0]][0] + META.pos[p[1]][0]) / 2;
  const my = touched
    ? (from[1] + META.pos[other][1]) / 2
    : (META.pos[p[0]][1] + META.pos[p[1]][1]) / 2;
  assert(
    Math.abs(hoverXY[0][k] - mx) < 1e-9 && Math.abs(hoverXY[1][k] - my) < 1e-9,
    touched
      ? "a hover target stayed behind where the edge used to be"
      : "an unrelated hover target moved"
  );
  if (touched) tracked++;
});
assert(tracked > 0, `'${lifeNode}' has no hover targets - this test proves nothing`);
winListeners["mouseup"]({});
console.log(`drag '${lifeNode}': ${tracked} hover targets tracked their midpoints`);

clearFocusIfAny();

// ---- 12. clicks on edges are ignored ----------------------------------------
calls.length = 0;
handlers["plotly_click"]({ points: [{}] });
assert(calls.length === 0, "a click without customdata should be ignored");
console.log("edge clicks ignored");

console.log("\nJS TESTS PASSED");

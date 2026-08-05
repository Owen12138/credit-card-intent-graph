"""Export the graph to a self-contained HTML page for GitHub Pages.

GitHub Pages serves static files only, so the Streamlit app itself cannot run
there. This writes the same interactive page the app embeds - Plotly animation
frames for the timeline plus a click handler for focus - as one standalone file.

    python export_static.py [--out docs/index.html] [--label-min N]

`--label-min` hides sub-intent labels below that all-time volume, the static
equivalent of the app's label threshold slider. The default shows every label,
matching the app.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import graph_builder as gb
from interactive_html import render_page

LAYOUT = "Spring (force-directed)"
SCALE = gb.SCALE_LOG
EMPHASIS = 1.8
HEIGHT = 780


def build_html(label_min: int = 0) -> str:
    g = gb.build_graph()
    pos = gb.compute_layout(g, LAYOUT)

    labelled = {
        n
        for n, d in g.nodes(data=True)
        if d["node_type"] != gb.SUB_INTENT or d["volume"] >= label_min
    }

    return render_page(
        g,
        pos,
        labelled,
        scale=SCALE,
        emphasis=EMPHASIS,
        height=HEIGHT,
        include_plotlyjs=True,  # inline, so it works offline and behind proxies
        chrome=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument(
        "--label-min",
        type=int,
        default=0,
        help="hide sub-intent labels below this all-time volume (0 = show all)",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(args.label_min), encoding="utf-8")

    # Stops GitHub Pages running the file through Jekyll.
    (out.parent / ".nojekyll").write_text("", encoding="utf-8")

    print(f"wrote {out} ({out.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()

"""Conversation volumes per intent, over time.

These are synthetic but deterministic: the same seed always produces the same
numbers, so node sizes stay stable across reruns and between sessions. Swap
`generate()` for a real load (CSV / warehouse query) when actual conversation
counts are available - everything downstream only needs the dicts returned by
it, each mapping an intent to one volume per period.

Model
-----
Each unified intent gets a baseline volume drawn log-uniformly across the
requested range, split across its 8 sub-intents with a skewed (lognormal)
distribution so a couple of sub-intents dominate and the tail is small - which
is how real intent traffic behaves.

That baseline is then pushed through a trend over the 5 periods. Trends are
assigned per unified intent so a whole service visibly grows, shrinks or spikes
as a block, which is what makes movement legible on the graph. Individual
sub-intents wobble around their parent's trend with a little noise.

A unified intent's volume in any period is the exact sum of its sub-intents in
that period, so the hierarchy adds up at every point on the timeline.
"""

from __future__ import annotations

import math
import random

import taxonomy

SEED = 20260805

# --- timeline ----------------------------------------------------------------
PERIODS = ["Apr 2026", "May 2026", "Jun 2026", "Jul 2026", "Aug 2026"]
N_PERIODS = len(PERIODS)

# Trend shapes across the 5 periods, as multipliers on the baseline.
TREND_PATTERNS = {
    "steady": [1.00, 1.03, 0.99, 1.02, 1.00],
    "growth": [0.55, 0.72, 0.95, 1.25, 1.60],
    "decline": [1.60, 1.30, 1.00, 0.78, 0.55],
    "seasonal": [1.35, 0.95, 0.70, 0.95, 1.40],
    "spike": None,  # built per intent so the peak lands on a different period
}

TREND_NAMES = list(TREND_PATTERNS)
TREND_WEIGHTS = [0.30, 0.25, 0.20, 0.10, 0.15]

SPIKE_PEAK = 2.4

# --- volume ranges ------------------------------------------------------------
# No sub-intent is reported as completely dead.
MIN_SUB_VOLUME = 100

# Requested range for the headline (unified intent) volumes. The floor is the
# smallest total a unified intent can actually represent - 8 sub-intents that
# have each bottomed out at MIN_SUB_VOLUME. Drawing below it would just clamp a
# batch of services to the identical value and flatten their relative sizes.
SUB_INTENTS_PER_UNIFIED = 8
MIN_UNIFIED_VOLUME = MIN_SUB_VOLUME * SUB_INTENTS_PER_UNIFIED
MAX_UNIFIED_VOLUME = 500_000

# Higher = more lopsided split across the 8 sub-intents of one unified intent.
SPLIT_SKEW = 0.9

# How much each sub-intent is allowed to drift from its parent's trend.
NOISE = 0.12


def _trend_for(name: str, rng: random.Random) -> list[float]:
    if name != "spike":
        return list(TREND_PATTERNS[name])
    peak = rng.randrange(N_PERIODS)
    return [
        SPIKE_PEAK if i == peak else rng.uniform(0.80, 0.95) for i in range(N_PERIODS)
    ]


def generate(
    seed: int = SEED,
    min_volume: int = MIN_UNIFIED_VOLUME,
    max_volume: int = MAX_UNIFIED_VOLUME,
) -> tuple[dict[str, list[int]], dict[tuple[str, str], list[int]], dict[str, str]]:
    """Return (unified series, sub-intent series, trend name per unified intent).

    Each series is one conversation count per period, in `PERIODS` order.
    """
    rng = random.Random(seed)

    log_min, log_max = math.log10(min_volume), math.log10(max_volume)

    baselines: dict[str, float] = {}
    weights: dict[str, list[float]] = {}
    trends: dict[str, str] = {}
    trend_curves: dict[str, list[float]] = {}

    for ui, subs in taxonomy.UNIFIED_INTENTS.items():
        baselines[ui] = 10 ** rng.uniform(log_min, log_max)
        weights[ui] = [rng.lognormvariate(0.0, SPLIT_SKEW) for _ in subs]
        trends[ui] = rng.choices(TREND_NAMES, weights=TREND_WEIGHTS, k=1)[0]
        trend_curves[ui] = _trend_for(trends[ui], rng)

    # Raw (unanchored) per-period shares for every sub-intent.
    raw: dict[tuple[str, str], list[float]] = {}
    for ui, subs in taxonomy.UNIFIED_INTENTS.items():
        total_weight = sum(weights[ui])
        for sub, weight in zip(subs, weights[ui]):
            share = baselines[ui] * weight / total_weight
            raw[(ui, sub)] = [
                share * trend_curves[ui][t] * rng.uniform(1 - NOISE, 1 + NOISE)
                for t in range(N_PERIODS)
            ]

    # Stretch everything so the busiest service in its busiest period lands on
    # the top of the requested range. With only 31 samples the raw maximum falls
    # well short of it, which would make the configured ceiling meaningless.
    peak = max(
        sum(raw[(ui, sub)][t] for sub in subs)
        for ui, subs in taxonomy.UNIFIED_INTENTS.items()
        for t in range(N_PERIODS)
    )
    anchor = max_volume / peak

    sub_series: dict[tuple[str, str], list[int]] = {
        key: [max(MIN_SUB_VOLUME, round(v * anchor)) for v in vals]
        for key, vals in raw.items()
    }

    unified_series: dict[str, list[int]] = {
        ui: [sum(sub_series[(ui, sub)][t] for sub in subs) for t in range(N_PERIODS)]
        for ui, subs in taxonomy.UNIFIED_INTENTS.items()
    }

    return unified_series, sub_series, trends


UNIFIED_SERIES, SUB_SERIES, TRENDS = generate()

PRODUCT_SERIES = [
    sum(series[t] for series in UNIFIED_SERIES.values()) for t in range(N_PERIODS)
]

# All-time totals, used when the timeline is set to show every period at once.
UNIFIED_TOTALS = {ui: sum(s) for ui, s in UNIFIED_SERIES.items()}
SUB_TOTALS = {key: sum(s) for key, s in SUB_SERIES.items()}
PRODUCT_TOTAL = sum(PRODUCT_SERIES)


# =============================================================================
# Life event occurrences
# =============================================================================
# A life event carries a metric of its own: how many times it was discovered.
# This is NOT conversation volume - the node's `volume` is still the traffic of
# the sub-intents it touches, which is a different number measuring a different
# thing. Occurrences are a single all-time count with no per-period series, so
# life-event edge widths hold still while the timeline runs.
MIN_LIFE_OCCURRENCES = 10
MAX_LIFE_OCCURRENCES = 100_000
LIFE_SEED = SEED + 1


def generate_life_occurrences(
    seed: int = LIFE_SEED,
    min_occurrences: int = MIN_LIFE_OCCURRENCES,
    max_occurrences: int = MAX_LIFE_OCCURRENCES,
) -> dict[str, int]:
    """One occurrence count per life event, spanning the full range.

    Drawn log-uniformly, then stretched so the quietest event lands exactly on
    the floor and the busiest exactly on the ceiling. With only 10 samples the
    raw draw covers maybe half of four decades, which would leave the configured
    range meaningless and the thickest edge barely thicker than the thinnest.
    """
    rng = random.Random(seed)
    log_min, log_max = math.log10(min_occurrences), math.log10(max_occurrences)

    events = list(taxonomy.LIFE_EVENTS)
    step = (log_max - log_min) / len(events)

    # One draw per band rather than ten free draws across the whole range. A
    # plain uniform draw of ten samples clumps: the first attempt put six of the
    # ten within a single decade of each other, which the width scale then drew
    # as six near-identical lines. Stratifying spreads them, and the events are
    # shuffled afterwards so the order in the taxonomy carries no signal.
    draws = [log_min + (i + rng.random()) * step for i in range(len(events))]
    rng.shuffle(draws)
    raw = dict(zip(events, draws))

    lo, hi = min(raw.values()), max(raw.values())
    span = hi - lo

    if span <= 0:  # one event, or a freak draw - nothing to stretch
        return {event: min_occurrences for event in raw}

    return {
        event: round(10 ** (log_min + (v - lo) * (log_max - log_min) / span))
        for event, v in raw.items()
    }


LIFE_OCCURRENCES = generate_life_occurrences()
LIFE_OCCURRENCE_RANGE = (
    min(LIFE_OCCURRENCES.values()),
    max(LIFE_OCCURRENCES.values()),
)
LIFE_OCCURRENCE_TOTAL = sum(LIFE_OCCURRENCES.values())


def fmt(value: int | float) -> str:
    """Thousands-separated volume for display."""
    return f"{round(value):,}"


def delta(series: list[int], period: int) -> int | None:
    """Change versus the previous period, or None for the first one."""
    if period <= 0:
        return None
    return series[period] - series[period - 1]

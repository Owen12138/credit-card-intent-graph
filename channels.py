"""Per-channel intent data: generation, files, loading and validation.

Three source channels each own two JSON files - one for unified intents, one for
sub-intents:

    data/virtual-assistant.json        data/virtual-assistant-sub.json
    data/agent-assistant.json          data/agent-assistant-sub.json
    data/ai-voice-assistant.json       data/ai-voice-assistant-sub.json

Each file holds only that channel's data. `load()` reads all six and `records()`
combines them for a single intent, which is what the detail view renders.

Schema
------
A unified intent is keyed by its name:

    {"Fee Inquiry": {
        "description": str,
        "sampleConversation": {"conversationText": str},
        "channelIntent": [str, ...],
        "parentIntent": None,
        "subIntent": [str, ...],
        "numberOfConversations": int}}

A sub-intent is the same, except `parentIntent` names its unified intent and
there is no `subIntent` list.

How the numbers relate to the rest of the app
---------------------------------------------
`numberOfConversations` is an all-time total, as the schema has one integer per
intent with no time dimension - the five-period timeline is a separate axis.
The channels PARTITION the volumes in `volumes.py`, so a sub-intent's three
channel counts add up to the total the graph draws it at, and every number on
the detail view reconciles with every number on the canvas.

A channel does not have to carry every intent: voice handles a narrower range
than chat, so some sub-intents are missing from ai-voice-assistant. Volume is
split only across the channels that carry an intent, so the totals still add up.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import taxonomy
import volumes

SEED = 5150
DATA_DIR = Path(__file__).parent / "data"

# Share of sub-intents that voice does not handle at all.
VOICE_GAP = 0.12


class Channel:
    def __init__(self, key: str, label: str, blurb: str):
        self.key = key
        self.label = label
        self.blurb = blurb

    @property
    def unified_file(self) -> str:
        return f"{self.key}.json"

    @property
    def sub_file(self) -> str:
        return f"{self.key}-sub.json"


CHANNELS = [
    Channel(
        "virtual-assistant",
        "Virtual Assistant",
        "Self-service chat in the app and on the website.",
    ),
    Channel(
        "agent-assistant",
        "Agent Assistant",
        "Suggestions surfaced to a human agent mid-conversation.",
    ),
    Channel(
        "ai-voice-assistant",
        "AI Voice Assistant",
        "Spoken IVR handling calls before they reach an agent.",
    ),
]

CHANNELS_BY_KEY = {c.key: c for c in CHANNELS}


# --- naming ------------------------------------------------------------------
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _abbrev(text: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]
    if len(words) >= 3:
        return "".join(w[0] for w in words).upper()
    # Two-word names need more than the first six letters: "Balance Inquiry" and
    # "Balance Transfer" both begin "BALANC".
    return "".join(w[:3] for w in words).upper()


STOPWORDS = {"a", "an", "the", "of", "for", "to", "on", "in", "and", "or",
             "my", "your", "with", "at", "from", "this", "that", "it", "as"}


def _keywords(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z0-9]+", text.lower())
            if w and w not in STOPWORDS]


def _tail(text: str, n: int = 3) -> str:
    """The distinctive end of a name, e.g. 'late fee waiver' from a longer one."""
    words = _keywords(text)
    return "_".join(words[-n:]) if words else "intent"


def _channel_intents(channel: str, name: str, parent: str | None) -> list[str]:
    """Channel-specific intent names, in each channel's own house style.

    The second entry is a differently shaped phrasing rather than the first with
    a suffix bolted on, which would produce things like
    'request_one_time_late_fee_waiver_request'.
    """
    slug, tail = _slug(name), _tail(name)

    if channel == "virtual-assistant":          # chatbot NLU intents
        if parent is None:
            return [slug, f"ask_about_{tail}"]
        return [slug, f"{tail}_request"]

    if channel == "agent-assistant":            # case-management codes
        code = _abbrev(name)
        if parent is None:
            return [f"{code}_MAIN", f"{code}_ASSIST"]
        return [f"{_abbrev(parent)}_{code}", f"{_abbrev(parent)}_{code}_ASSIST"]

    if parent is None:                          # voice: menu and utterances
        return [f"utt_{tail}", f"utt_{tail}_menu"]
    return [f"utt_{slug}", f"utt_{tail}_confirm"]


def _description(name: str, parent: str | None, subs: list[str]) -> str:
    # Unified intent names are noun phrases ("Late Fee Waiver") while sub-intent
    # names are verb phrases ("Request one-time late fee waiver"), so the two
    # levels need different sentence frames to read as English.
    if parent is None:
        head = f"Customer conversations handled under {name}."
        if subs:
            head += f" Covers {len(subs)} sub-intents, such as {subs[0].lower()}."
        return head
    lower = name[0].lower() + name[1:]
    return f"Customers wanting to {lower}, handled under {parent}."


def _sample(channel: str, name: str, parent: str | None) -> str:
    if parent is None:
        if channel == "virtual-assistant":
            return f"Hi, I have a question about {name.lower()}."
        if channel == "agent-assistant":
            return (
                f"Customer has verified their identity and is asking about "
                f"{name.lower()}. Suggested next step surfaced to the agent."
            )
        return f"I'm calling about {name.lower()}."

    lower = name[0].lower() + name[1:]
    if channel == "virtual-assistant":
        return f"Hi, I need to {lower} - can you help me with that?"
    if channel == "agent-assistant":
        return (
            f"Customer verified. They want to {lower}. "
            "Suggested next step surfaced to the agent."
        )
    return f"I want to {lower}, please."


# --- generation --------------------------------------------------------------
def generate(seed: int = SEED) -> dict[str, dict[str, dict]]:
    """Build every channel's unified and sub-intent records.

    Returns {channel_key: {"unified": {...}, "sub": {...}}}.
    """
    rng = random.Random(seed)
    keys = [c.key for c in CHANNELS]

    # Which channels carry each sub-intent, and how its volume splits between
    # them. Splitting only across the carriers is what keeps a sub-intent's
    # channel counts adding up to the total the graph draws.
    carriers: dict[tuple[str, str], list[str]] = {}
    split: dict[tuple[str, str], dict[str, int]] = {}

    for ui, subs in taxonomy.UNIFIED_INTENTS.items():
        for sub in subs:
            here = list(keys)
            if rng.random() < VOICE_GAP:
                here.remove("ai-voice-assistant")
            carriers[(ui, sub)] = here

            weights = [rng.uniform(0.6, 1.8) for _ in here]
            total_w = sum(weights)
            total_v = volumes.SUB_TOTALS[(ui, sub)]

            counts, running = {}, 0
            for i, key in enumerate(here):
                if i == len(here) - 1:
                    counts[key] = total_v - running       # last takes the remainder
                else:
                    counts[key] = max(1, round(total_v * weights[i] / total_w))
                    running += counts[key]
            split[(ui, sub)] = counts

    out: dict[str, dict[str, dict]] = {c.key: {"unified": {}, "sub": {}} for c in CHANNELS}
    # A channel intent must name exactly one intent, or the mapping is
    # ambiguous. Shortened forms can collide - "Check minimum amount due" and
    # "Pay minimum amount due" share a tail - so collisions are resolved here.
    used: dict[str, dict[str, str]] = {c.key: {} for c in CHANNELS}

    def unique(key: str, name: str, candidates: list[str]) -> list[str]:
        taken = used[key]
        result = []
        for cand in candidates:
            if taken.get(cand, name) != name:
                cand = f"{cand}_{_abbrev(name).lower()}"
                suffix = 2
                while taken.get(cand, name) != name:
                    cand = f"{cand}_{suffix}"
                    suffix += 1
            taken[cand] = name
            result.append(cand)
        return result

    for ui, subs in taxonomy.UNIFIED_INTENTS.items():
        for key in keys:
            carried = [s for s in subs if key in carriers[(ui, s)]]
            if not carried:
                continue

            for sub in carried:
                out[key]["sub"][sub] = {
                    "description": _description(sub, ui, []),
                    "sampleConversation": {"conversationText": _sample(key, sub, ui)},
                    "channelIntent": unique(key, sub, _channel_intents(key, sub, ui)),
                    "parentIntent": ui,
                    "numberOfConversations": split[(ui, sub)][key],
                }

            out[key]["unified"][ui] = {
                "description": _description(ui, None, subs),
                "sampleConversation": {"conversationText": _sample(key, ui, None)},
                "channelIntent": unique(key, ui, _channel_intents(key, ui, None)),
                "parentIntent": None,
                "subIntent": carried,
                "numberOfConversations": sum(split[(ui, s)][key] for s in carried),
            }

    return out


def write(directory: Path = DATA_DIR, seed: int = SEED) -> list[Path]:
    """Write all six channel files. Returns the paths written."""
    directory.mkdir(parents=True, exist_ok=True)
    data = generate(seed)
    written = []
    for channel in CHANNELS:
        for kind, filename in (
            ("unified", channel.unified_file),
            ("sub", channel.sub_file),
        ):
            path = directory / filename
            path.write_text(
                json.dumps(data[channel.key][kind], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written.append(path)
    return written


# --- loading -----------------------------------------------------------------
def load(directory: Path = DATA_DIR) -> dict[str, dict[str, dict]]:
    """Read all six files. Raises if any are missing or malformed."""
    data: dict[str, dict[str, dict]] = {}
    for channel in CHANNELS:
        entry = {}
        for kind, filename in (
            ("unified", channel.unified_file),
            ("sub", channel.sub_file),
        ):
            path = directory / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} is missing - run `python channels.py` to generate it"
                )
            entry[kind] = json.loads(path.read_text(encoding="utf-8"))
        data[channel.key] = entry
    validate(data)
    return data


def validate(data: dict[str, dict[str, dict]]) -> None:
    """Fail loudly on anything the detail view would render wrongly."""
    for channel in CHANNELS:
        entry = data.get(channel.key)
        if entry is None:
            raise ValueError(f"no data for channel {channel.key}")

        for name, rec in entry["unified"].items():
            _require(rec, name, channel.key, ("subIntent",))
            if rec["parentIntent"] is not None:
                raise ValueError(f"{channel.key}: unified '{name}' has a parentIntent")
            if not isinstance(rec["subIntent"], list):
                raise ValueError(f"{channel.key}: '{name}' subIntent is not a list")
            for sub in rec["subIntent"]:
                if sub not in entry["sub"]:
                    raise ValueError(
                        f"{channel.key}: '{name}' lists sub-intent '{sub}', "
                        "which the sub-intent file does not contain"
                    )

        for name, rec in entry["sub"].items():
            _require(rec, name, channel.key, ())
            if "subIntent" in rec:
                raise ValueError(f"{channel.key}: sub-intent '{name}' has a subIntent list")
            parent = rec["parentIntent"]
            if not isinstance(parent, str):
                raise ValueError(f"{channel.key}: sub-intent '{name}' has no parentIntent")
            if parent not in entry["unified"]:
                raise ValueError(
                    f"{channel.key}: '{name}' points at unknown parent '{parent}'"
                )
            if name not in entry["unified"][parent]["subIntent"]:
                raise ValueError(
                    f"{channel.key}: '{name}' claims parent '{parent}', "
                    "which does not list it"
                )


def _require(rec: dict, name: str, channel: str, extra: tuple[str, ...]) -> None:
    for field in ("description", "sampleConversation", "channelIntent",
                  "parentIntent", "numberOfConversations") + extra:
        if field not in rec:
            raise ValueError(f"{channel}: '{name}' is missing '{field}'")
    if not isinstance(rec["description"], str) or not rec["description"]:
        raise ValueError(f"{channel}: '{name}' has an empty description")
    if not isinstance(rec["sampleConversation"], dict):
        raise ValueError(f"{channel}: '{name}' sampleConversation is not an object")
    if "conversationText" not in rec["sampleConversation"]:
        raise ValueError(f"{channel}: '{name}' has no conversationText")
    if not isinstance(rec["channelIntent"], list) or not rec["channelIntent"]:
        raise ValueError(f"{channel}: '{name}' has no channelIntent entries")
    if not isinstance(rec["numberOfConversations"], int):
        raise ValueError(f"{channel}: '{name}' numberOfConversations is not an integer")


# --- combining for the frontend ----------------------------------------------
def records(
    data: dict[str, dict[str, dict]], name: str, kind: str
) -> list[tuple[Channel, dict | None]]:
    """One (channel, record) pair per channel, in display order.

    The record is None where that channel does not carry the intent, which the
    detail view renders as an empty card rather than hiding it - three cards
    always, so the comparison between channels stays fixed.
    """
    return [(c, data[c.key][kind].get(name)) for c in CHANNELS]


def total(data: dict[str, dict[str, dict]], name: str, kind: str) -> int:
    return sum(
        rec["numberOfConversations"] for _, rec in records(data, name, kind) if rec
    )


if __name__ == "__main__":
    paths = write()
    loaded = load()
    print(f"wrote {len(paths)} files to {DATA_DIR}")
    for channel in CHANNELS:
        u = loaded[channel.key]["unified"]
        s = loaded[channel.key]["sub"]
        conv = sum(r["numberOfConversations"] for r in s.values())
        print(f"  {channel.label:<20} {len(u):>3} unified  {len(s):>4} sub  "
              f"{conv:>10,} conversations")

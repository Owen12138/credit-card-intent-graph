"""Checks the channel JSON files against the schema and against the graph.

Run: python channels_test.py
"""

import json

import channels
import taxonomy
import volumes

data = channels.load()

# =============================================================================
# Schema, exactly as specified
# =============================================================================
UNIFIED_FIELDS = {
    "description",
    "sampleConversation",
    "channelIntent",
    "parentIntent",
    "subIntent",
    "numberOfConversations",
}
SUB_FIELDS = UNIFIED_FIELDS - {"subIntent"}

for channel in channels.CHANNELS:
    unified = data[channel.key]["unified"]
    sub = data[channel.key]["sub"]

    for name, rec in unified.items():
        assert set(rec) == UNIFIED_FIELDS, (channel.key, name, sorted(rec))
        assert rec["parentIntent"] is None, (channel.key, name)
        assert set(rec["sampleConversation"]) == {"conversationText"}, name
        assert isinstance(rec["numberOfConversations"], int)
        assert rec["channelIntent"], name

    for name, rec in sub.items():
        assert set(rec) == SUB_FIELDS, (channel.key, name, sorted(rec))
        assert isinstance(rec["parentIntent"], str), (channel.key, name)
        assert "subIntent" not in rec, (channel.key, name)
        assert set(rec["sampleConversation"]) == {"conversationText"}, name

print("schema ok: unified and sub records carry exactly the specified fields")

# =============================================================================
# The taxonomy is representable in this schema at all
# =============================================================================
# Sub-intents are keyed by name alone, so the names have to be globally unique.
# They were not: 'Understand impact on credit score' sat under both Decrease
# Credit Limit and Close Account, and one record silently overwrote the other.
all_subs = [s for subs in taxonomy.UNIFIED_INTENTS.values() for s in subs]
assert len(all_subs) == len(set(all_subs)), "sub-intent names are not unique"
assert not (set(all_subs) & set(taxonomy.UNIFIED_INTENTS)), "a name is used at both levels"
print(f"names ok: {len(all_subs)} sub-intents, all distinct, none clashing with a service")

# =============================================================================
# Cross-references hold within each channel
# =============================================================================
for channel in channels.CHANNELS:
    unified = data[channel.key]["unified"]
    sub = data[channel.key]["sub"]

    assert set(unified) == set(taxonomy.UNIFIED_INTENTS), channel.key

    for name, rec in unified.items():
        # a unified intent may only list sub-intents this channel actually has
        assert set(rec["subIntent"]) <= set(sub), (channel.key, name)
        assert set(rec["subIntent"]) <= set(taxonomy.UNIFIED_INTENTS[name]), name
        # and every one of them points back
        for s in rec["subIntent"]:
            assert sub[s]["parentIntent"] == name, (channel.key, s)

    for name, rec in sub.items():
        parent = rec["parentIntent"]
        assert parent in unified, (channel.key, name, parent)
        assert name in unified[parent]["subIntent"], (channel.key, name)
        assert name in taxonomy.UNIFIED_INTENTS[parent], (channel.key, name)

print("cross-references ok: every parent lists its children and every child names its parent")

# =============================================================================
# A channel intent maps to exactly one intent
# =============================================================================
# Shortened forms collide easily: "Check minimum amount due" and "Pay minimum
# amount due" share a tail, and "Balance Inquiry"/"Balance Transfer" share their
# first six letters. A channel intent claimed by two intents makes the mapping
# ambiguous, so generation resolves collisions rather than letting them stand.
for channel in channels.CHANNELS:
    owner: dict[str, str] = {}
    for kind in ("unified", "sub"):
        for name, rec in data[channel.key][kind].items():
            for ci in rec["channelIntent"]:
                assert owner.get(ci, name) == name, (
                    f"{channel.key}: channel intent '{ci}' is claimed by both "
                    f"'{owner.get(ci)}' and '{name}'"
                )
                owner[ci] = name
    print(f"  {channel.label:<20} {len(owner):>4} channel intents, each mapping to one intent")

# =============================================================================
# The numbers reconcile with the graph
# =============================================================================
# Within a channel, a unified intent is the sum of the sub-intents that channel
# carries.
for channel in channels.CHANNELS:
    for name, rec in data[channel.key]["unified"].items():
        rolled = sum(
            data[channel.key]["sub"][s]["numberOfConversations"]
            for s in rec["subIntent"]
        )
        assert rec["numberOfConversations"] == rolled, (channel.key, name)

# Across channels, a sub-intent's counts add up to the total the graph draws it
# at - so no number in the detail view contradicts the canvas.
for ui, subs in taxonomy.UNIFIED_INTENTS.items():
    for s in subs:
        across = channels.total(data, s, "sub")
        assert across == volumes.SUB_TOTALS[(ui, s)], (s, across, volumes.SUB_TOTALS[(ui, s)])

grand = sum(
    rec["numberOfConversations"]
    for channel in channels.CHANNELS
    for rec in data[channel.key]["sub"].values()
)
assert grand == volumes.PRODUCT_TOTAL, (grand, volumes.PRODUCT_TOTAL)
print(f"totals ok: {grand:,} conversations, matching the graph exactly")

# =============================================================================
# Coverage: three cards always, but a channel need not carry everything
# =============================================================================
for ui in taxonomy.UNIFIED_INTENTS:
    rows = channels.records(data, ui, "unified")
    assert len(rows) == 3, ui
    assert all(rec for _, rec in rows), f"every channel should carry unified '{ui}'"

missing = {
    c.key: sorted(set(all_subs) - set(data[c.key]["sub"])) for c in channels.CHANNELS
}
for key, gone in missing.items():
    print(f"  {key:<20} carries {len(all_subs) - len(gone):>3}/{len(all_subs)} sub-intents")

assert missing["ai-voice-assistant"], "voice should not carry everything - the empty card is untested"
assert not missing["virtual-assistant"], "chat should carry every sub-intent"

# a sub-intent absent from a channel still resolves to a card, just an empty one
sample = missing["ai-voice-assistant"][0]
rows = channels.records(data, sample, "sub")
assert len(rows) == 3
assert any(rec is None for _, rec in rows), sample
assert channels.total(data, sample, "sub") == volumes.SUB_TOTALS[
    (data["virtual-assistant"]["sub"][sample]["parentIntent"], sample)
]
print(f"coverage ok: '{sample}' is absent from voice and still renders three cards")

# =============================================================================
# Files are real, valid JSON, one per channel per level
# =============================================================================
for channel in channels.CHANNELS:
    for filename in (channel.unified_file, channel.sub_file):
        path = channels.DATA_DIR / filename
        assert path.exists(), path
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed, filename
        # keyed by intent name, as specified
        assert all(isinstance(k, str) for k in parsed), filename

# regeneration is deterministic
assert channels.generate() == channels.generate(), "generation is not deterministic"

# validation actually rejects a broken record
broken = channels.generate()
first = next(iter(broken["virtual-assistant"]["sub"]))
broken["virtual-assistant"]["sub"][first]["parentIntent"] = "Nope"
try:
    channels.validate(broken)
    raise AssertionError("validate() accepted an orphaned sub-intent")
except ValueError:
    pass
print("files ok: 6 files, deterministic, and validation rejects a bad parent link")

print("\nCHANNEL TESTS PASSED")

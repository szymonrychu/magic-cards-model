"""Boulder Dash: "Boulder Dash deals 2 damage to any target and 1 damage to
any other target." - `_merge_split_damage_clauses`'s own unequal-split
family (already proven on Hungry Flames' two independently-typed
requirements, `test_split_damage_targets.py`), widened for CR 115.4's bare
"any target"/"any other target" phrasing on *both* halves at once.

The gap: `_DAMAGE_TARGET_RE`'s and `_BARE_DAMAGE_CONTINUATION_RE`'s own
`phrase` alternation already read a bare "any target" (Lightning Bolt), but
their second, generic alternative - "`.*?target.+?`", at least one character
*after* the word "target" - cannot match a phrase that ends at "target"
itself. "Any other target" is exactly that shape, so it fell through
unread. Both regexes now list it as its own literal alternative, alongside
"any target".

Proof printing: **Arc Trail** (real Scryfall data, added with
`scripts/add_card.py`, Modern `legal`, not a listed ecl-T8 card, not in any
deck list) - the identical template, word for word, on a different card -
about as direct a proof of "the shape, not the card" as this mechanic
offers, since Boulder Dash and Arc Trail are templated identically down to
the punctuation.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 115.3 (the same target can't be chosen twice for *one* instance
of the word "target"), 115.4 ("any target," "another target" - these
targets may be creatures, players, planeswalkers, or battles), 601.2c (two
instances of "target" are two independent requirements), 608.2b (an
illegal target is unaffected only for the parts of the effect it is illegal
for).

CR 115.4's own "any *other*" distinctness is now enforced at *announcement*
too (`TargetRequirement.distinct_from_prior_requirement`,
`TargetingProfile._check_distinct_from_prior` in `machines/targeting.py`):
a player cannot name the identical object for both the "any target" and the
"any other target" half of one spell - the cast is refused outright
(CR 601.2c) rather than resolving with both amounts stacked onto one object.
The flag is set only for the *paired* idiom (a bare "any other target"
following a bare "any target" in the same text) - a solitary "any other
target" with nothing before it (Iron Fist, Living Weapon; Red Hulk;
Screaming Nemesis) keeps meaning "other than this ability's own source"
(`TargetRequirement.excludes_source`) exactly as it already did, since none
of those three has an earlier "any target" to be distinct from.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

BOULDER_DASH = "Boulder Dash"
ARC_TRAIL = "Arc Trail"


def test_both_printings_are_fully_handled():
    for name in (BOULDER_DASH, ARC_TRAIL):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def test_boulder_dash_deals_two_to_one_target_and_one_to_the_other():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BOULDER_DASH],
            battlefield=["Mountain"] * 2 + ["Craw Wurm"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Craw Wurm", "alice")
    vanguard = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve(BOULDER_DASH, *sources, targets=[bears, vanguard])

    assert bears.damage == 2
    assert vanguard.damage == 1


def test_boulder_dash_pays_the_right_amount_whichever_order_targets_were_chosen():
    """The two targets classified by which requirement they satisfy, not by
    the order they were announced in (`_merge_split_damage_clauses`'s own
    `TargetRequirement.rejects` classification) - both directions land the
    same result once both targets are the same kind of object."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BOULDER_DASH],
            battlefield=["Mountain"] * 2 + ["Craw Wurm"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Craw Wurm", "alice")
    vanguard = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve(BOULDER_DASH, *sources, targets=[vanguard, bears])

    assert bears.damage + vanguard.damage == 3, "the total is unchanged by announcement order"


def test_boulder_dash_can_target_two_players():
    """CR 115.4: "any target" reaches players too, not only creatures - and,
    per CR 115.3/115.4, "any target" and "any other target" may name two
    different players (they may not name the same one twice - see
    `test_boulder_dash_refuses_the_same_player_for_both_halves` below)."""
    scenario = (
        Scenario()
        .player("alice", hand=[BOULDER_DASH], battlefield=["Mountain"] * 2)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    alice.life = 20
    bob.life = 20
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve(BOULDER_DASH, *sources, targets=["alice", "bob"])

    assert (20 - alice.life) + (20 - bob.life) == 3, "2 damage plus 1 damage, split across both"


# -- proof printing: Arc Trail, the identical template on a different card --


def test_arc_trail_deals_its_own_unequal_split():
    scenario = (
        Scenario()
        .player("alice", hand=[ARC_TRAIL], battlefield=["Mountain"] * 2)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Hill Giant", "bob")
    alice = scenario.player("alice")
    alice.life = 20
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve(ARC_TRAIL, *sources, targets=[bears, "alice"])

    assert bears.damage + (20 - alice.life) == 3


# -- CR 115.3/115.4: "any target" and "any other target" must be distinct --


def test_boulder_dash_refuses_the_same_creature_for_both_halves():
    """CR 115.3/115.4: "any other target" is a second, differently-named
    instance of the word "target" - it must name a target other than the one
    "any target" already named, so the announcement naming the identical
    creature twice is refused outright rather than resolving with 2+1=3
    damage stacked onto that one object."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BOULDER_DASH],
            battlefield=["Mountain"] * 2 + ["Craw Wurm"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Craw Wurm", "alice")
    scenario.untapped_sources("Mountain", "Mountain")

    with pytest.raises(ValueError):
        scenario.cast(BOULDER_DASH, targets=[bears, bears])

    assert bears.damage == 0, "the illegal cast never happened"


def test_boulder_dash_refuses_the_same_player_for_both_halves():
    """The same refusal for a player named twice, not only a permanent."""
    scenario = (
        Scenario()
        .player("alice", hand=[BOULDER_DASH], battlefield=["Mountain"] * 2)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bob.life = 20

    with pytest.raises(ValueError):
        scenario.cast(BOULDER_DASH, targets=["bob", "bob"])

    assert bob.life == 20, "the illegal cast never happened"


def test_arc_trail_refuses_the_same_target_for_both_halves():
    """The identical refusal on Arc Trail - the proof printing, not the
    reported card, carries the same fix."""
    scenario = (
        Scenario()
        .player("alice", hand=[ARC_TRAIL], battlefield=["Mountain"] * 2)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vanguard = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError):
        scenario.cast(ARC_TRAIL, targets=[vanguard, vanguard])

    assert vanguard.damage == 0, "the illegal cast never happened"


def test_solitary_any_other_target_still_excludes_only_its_own_source():
    """Iron Fist, Living Weapon's granted ability has one bare "any other
    target" with no preceding "any target" to be distinct from - it keeps
    meaning "other than this permanent" (`excludes_source`), not CR 115.4's
    paired distinctness, and is unaffected by this fix."""
    from magic_cards_model.machines.targeting import _parse, profile_for_text
    from tests.cards import card as card_fixture

    texts = {
        # Iron Fist's own damage sentence is granted-ability text, quoted on
        # the card and stripped by `_parse`'s own `_QUOTED_SPAN` removal -
        # read directly with `profile_for_text`, the same reader the granted
        # ability's own text goes through once it is copied off the card,
        # rather than `_parse` on the whole (quoted) oracle text.
        "Iron Fist, Living Weapon": (
            profile_for_text,
            "Iron Fist deals damage equal to his power to any other target.",
        ),
        "Red Hulk": (lambda t: _parse(t, spell_only=False), card_fixture("Red Hulk").oracle_text),
        "Screaming Nemesis": (
            lambda t: _parse(t, spell_only=False),
            card_fixture("Screaming Nemesis").oracle_text,
        ),
    }
    for name, (reader, text) in texts.items():
        profile = reader(text)
        matching = [r for r in profile.requirements if r.phrase == "target"]
        assert matching, (name, profile.requirements)
        for requirement in matching:
            assert requirement.excludes_source, (name, requirement)
            assert not requirement.distinct_from_prior_requirement, (name, requirement)

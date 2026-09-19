"""Scenario: a CAST_SPELL trigger condition that names what the spell targets.

Danitha, Spear of Agony: "Whenever you cast a spell that targets an opponent
or a creature an opponent controls, put a +1/+1 counter on Danitha." Danitha,
Sword of Hope: "Whenever you cast an Equipment spell or a spell that targets
a creature you control, draw a card."

Before this fix, `machines/triggers.condition_matches`'s CAST_SPELL branch
read a condition's colour/type/subtype words (CR 105.2, CR 202.3) but nothing
about CR 601.2c's own targets - a "spell that targets `<restriction>`" tail
was silently ignored, so neither Danitha's trigger ever fired: their own
"opponent"/"creature you control" text was checked against the *cast
spell's own* characteristics ("is the spell a creature spell") rather than
against what CR 601.2c's announcement actually put in `CardState.targets`.

The fix reads the tail with `machines/targeting._read_phrase` - the identical
grammar an ordinary "target `<description>`" phrase on a spell's own text
already uses - so "an opponent", "a creature an opponent controls" and "a
creature you control" are read the same way regardless of which side of the
word "target" they sit on. Danitha, Sword of Hope's own condition also names
*two* alternative descriptions of the cast spell ("an Equipment spell or a
spell that targets a creature you control") joined by an ordinary English
"or" - `machines/triggers._cast_spell_alternatives` splits the condition into
its two independent clauses (each re-prefixed with the shared "you cast" lead
so `_controller_clause_holds` still reads correctly) and the trigger fires
when *either* is satisfied, rather than ANDing both restrictions' words
together the way a single, unsplit condition would.

Stirring Hopesinger - not in the printings pool used to design this fix -
proves it generalises: "Whenever you cast an instant or sorcery spell that
targets a creature, put a +1/+1 counter on each creature you control." used
to have its own "creature" clause misread as "cast a creature spell" (CR
202.3, a fact about the cast spell's own printed type), so casting a
noncreature spell at a player fired it wrongly and casting an actual creature
spell (which is never announced with any target at all) risked firing it for
the wrong reason too. The fixed condition now correctly reads both halves at
once: an instant or sorcery, that ALSO targets a creature.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers."
- **CR 601.2c** - a spell's targets are announced and become part of it as
  part of casting it.
- **CR 105.2** - what makes a permanent's controller an "opponent" of
  another player.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_danitha_spear_of_agony_grows_when_a_spell_targets_an_opponent():
    """CR 601.2c's "an opponent" half - Lightning Bolt aimed at Bob's face."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Danitha, Spear of Agony", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    danitha = scenario.creature("Danitha, Spear of Agony", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert danitha.counters["+1/+1"] == 1


def test_danitha_spear_of_agony_grows_when_a_spell_targets_an_opponents_creature():
    """CR 601.2c's "a creature an opponent controls" half."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Danitha, Spear of Agony", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    danitha = scenario.creature("Danitha, Spear of Agony", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bob_bears])

    assert danitha.counters["+1/+1"] == 1


def test_danitha_spear_of_agony_does_not_grow_targeting_your_own_creature():
    """Neither half names "a creature you control" - Giant Growth on Alice's
    own Grizzly Bears satisfies neither "an opponent" nor "a creature an
    opponent controls", so the trigger must not fire."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Danitha, Spear of Agony", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    danitha = scenario.creature("Danitha, Spear of Agony", "alice")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Giant Growth", forest, targets=[alice_bears])

    assert danitha.counters["+1/+1"] == 0


def test_danitha_sword_of_hope_draws_a_card_for_an_equipment_spell():
    """The first alternative clause, "an Equipment spell" (CR 205.3h) - no
    target at all, so only `_cast_spell_alternatives`' split (not the
    "that targets" reader) is exercised here."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bonesplitter"],
            library=["Grizzly Bears"],
            battlefield=["Danitha, Sword of Hope", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Bonesplitter", plains)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert [card.name for card in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_danitha_sword_of_hope_draws_a_card_for_a_spell_targeting_your_creature():
    """The second alternative clause, "a spell that targets a creature you
    control" - Giant Growth on Alice's own Grizzly Bears."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            library=["Opt"],
            battlefield=["Danitha, Sword of Hope", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Giant Growth", forest, targets=[alice_bears])
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert [card.name for card in scenario.player("alice").hand] == ["Opt"]


def test_danitha_sword_of_hope_does_not_trigger_on_an_opponents_creature():
    """Neither alternative clause names "a creature an opponent controls" -
    Lightning Bolt aimed at Bob's Grizzly Bears is not an Equipment spell and
    does not target a creature Alice controls, so nothing should draw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            library=["Opt"],
            battlefield=["Danitha, Sword of Hope", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("alice").hand)
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bob_bears])

    assert len(scenario.player("alice").hand) == hand_before - 1  # only the Bolt left, no draw


def test_stirring_hopesinger_fires_for_an_instant_that_targets_a_creature():
    """The off-set proof: a card outside this fix's own design pool. Both
    halves of its condition - "an instant or sorcery spell" (CR 202.3) *and*
    "that targets a creature" (CR 601.2c) - must hold together."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Stirring Hopesinger", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hopesinger = scenario.creature("Stirring Hopesinger", "alice")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[alice_bears])

    assert hopesinger.counters["+1/+1"] == 1
    assert alice_bears.counters["+1/+1"] == 1


def test_stirring_hopesinger_does_not_fire_targeting_a_player():
    """The instant/sorcery half holds, but nothing about the target does -
    Lightning Bolt aimed at Bob's face targets no creature at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Stirring Hopesinger", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hopesinger = scenario.creature("Stirring Hopesinger", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert hopesinger.counters["+1/+1"] == 0

"""Scenario: protection (CR 702.16), through Emrakul's "protection from instants".

CR 702.16a: "Protection is a static ability, written 'Protection from
[quality].'" What it actually does is six separate things, and this file is
organised around which of them this engine can express:

- **CR 702.16b**, can't be *targeted* by spells with the quality or by
  abilities from a source with it - enforced at **announcement** (CR 601.2c:
  "the player announces their choice of an appropriate object or player for
  each target the spell requires"), so the cast is refused outright rather than
  proposed and then fizzled. `machines/targeting.py`'s `TargetingProfile.check`
  asks `Game.protection_refusal` the same question `Game.legal_target` asks on
  resolution, so the two can never disagree; the CR 608.2b recheck is still
  there as the backstop for protection *gained* after the spell is already on
  the stack, which is the only way a legally announced target can become a
  protected one.
- **CR 702.16c**, can't be *enchanted* by Auras with the quality - not
  expressible: `CardState` has no attachments.
- **CR 702.16d**, can't be *equipped* by Equipment with the quality - the same.
- **CR 702.16e**, *damage* from sources with the quality is prevented -
  enforced end to end: `Game.deal_damage` carries a source, and both combat
  (`machines/combat._deal_combat_damage`) and spell damage
  (`machines/effects.py`) name theirs. The one test below that still xfails
  calls `deal_damage` with no source at all, on purpose, which is a different
  thing from the engine being unable to name one - see its own docstring, and
  `scenarios/test_prevention_effects.py`/`scenarios/test_protection_grants.py`
  for the cases with a real source.
- **CR 702.16f**, an attacking creature with it can't be *blocked* by creatures
  with the quality - vacuous for "from instants", and unenforced in general.
- **CR 702.16m**, multiple instances of one quality are redundant - Emrakul's
  own printed protection can never have two instances of the same quality on
  itself, and nothing in the pool grants Emrakul *more* protection from
  instants specifically, so this file still cannot exercise the redundancy.
  Protection can be granted now (Akroma's Memorial - CR 613.1f, see
  `scenarios/test_protection_grants.py`), so "nothing grants protection" is no
  longer true in general, just for this file's own board.

CR 702.16a also carries the rule that makes "protection from instants" work at
all: "If the quality is a card type, subtype, or supertype, the ability applies
to sources that are permanents with that card type ... and to any sources not on
the battlefield that are of that card type, subtype, or supertype. This is an
exception to rule 109.2." An instant is never a permanent, so it is always the
second half that bites.

The quality is read off the oracle text, not off Scryfall's `keywords`, which
says only "Protection" and never from what.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import protection_qualities
from tests.cards import card

from .harness import Scenario


def emrakul_on_bobs_board() -> Scenario:
    """Bob resolved Emrakul; alice has a Plains and a Mountain and some removal."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Swords to Plowshares"],
            battlefield=["Mountain", "Plains"],
        )
        .player(
            "bob",
            library=["Island"],
            battlefield=["Emrakul, the Promised End", "Grizzly Bears"],
        )
    )


# -- reading the quality (CR 702.16a) --------------------------------------


def test_the_quality_is_read_off_the_oracle_text():
    assert protection_qualities(card("Emrakul, the Promised End")) == ["instants"]


def test_scryfall_says_only_that_there_is_protection_never_from_what():
    """Which is why the parser reads the text: the keyword list is not enough."""
    keywords = [keyword.lower() for keyword in card("Emrakul, the Promised End").keywords]
    assert "protection" in keywords
    assert not any("instant" in keyword for keyword in keywords)


def test_a_card_without_protection_has_no_qualities():
    assert protection_qualities(card("Grizzly Bears")) == []


# -- CR 702.16b: targeting -------------------------------------------------


def test_an_instant_that_targets_it_is_not_a_legal_target():
    """CR 601.2c: an inappropriate target is not announced, so the cast stops."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    with pytest.raises(ValueError, match="protection from instants"):
        scenario.cast("Lightning Bolt", username="alice", targets=[emrakul])


def test_the_instant_never_leaves_the_hand_and_nothing_is_dealt():
    """The refused cast is undone whole: no mana spent, no damage, no spell.

    CR 601.2c is where the announcement fails, which is before CR 601.2g's
    mana abilities and CR 601.2h's payment - so the Mountain is still untapped
    and the Bolt is still in hand.
    """
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError, match="protection from instants"):
        scenario.cast("Lightning Bolt", username="alice", targets=[emrakul])

    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND
    assert mountain.tapped is False
    assert emrakul.zone is Zone.BATTLEFIELD
    assert emrakul.damage == 0, "no damage was dealt at all"


def test_an_exile_instant_fares_no_better():
    """Swords to Plowshares does not destroy or damage - it still has to target."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    with pytest.raises(ValueError, match="protection from instants"):
        scenario.cast("Swords to Plowshares", username="alice", targets=[emrakul])

    assert emrakul.zone is Zone.BATTLEFIELD


def test_the_resolution_recheck_still_answers_the_same_way():
    """CR 608.2b is the backstop for protection gained after announcement.

    Nothing in this file's pool can grant protection from instants mid-stack,
    so the recheck is asserted against the question it would ask rather than
    through a board that cannot be built: `Game.why_cannot_target` is what
    `Game.legal_target` consults on resolution, and it refuses this pairing
    exactly as the announcement did.
    """
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    assert scenario.game.why_cannot_target(bolt, emrakul) is not None


def test_the_refusal_names_the_rule_and_the_quality():
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    refusal = scenario.game.protection_refusal(emrakul, card("Lightning Bolt"))

    assert refusal is not None
    assert "protection from instants" in refusal
    assert "CR 702.16b" in refusal


def test_a_sorcery_is_not_an_instant():
    """The quality is one card type, and only that one."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    assert scenario.game.protection_refusal(emrakul, card("Bone Splinters")) is None
    assert scenario.game.protection_refusal(emrakul, card("Lava Spike")) is None


def test_protection_shields_only_the_permanent_that_has_it():
    """The Bears standing next to Emrakul have none of it."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])

    assert not scenario.game.spell_fizzles(bolt)

    scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD, "3 damage on a 2/2 (CR 704.5g)"


def test_an_instant_may_still_target_a_player():
    """Emrakul gives its controller nothing; only the permanent is protected."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.player("bob").life == 17


# -- CR 702.16f: blocking --------------------------------------------------


def test_protection_from_instants_can_never_refuse_a_block():
    """CR 702.16f refuses blockers "that have the stated quality", and no
    creature is ever an instant, so this protection is inert in combat.

    The block below is legal for that reason, not because the engine checked:
    `machines/combat.py` does not read protection at all. See
    `docs/engine-coverage.md`.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", library=["Island"], battlefield=["Emrakul, the Promised End"])
        .player("alice", library=["Plains"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")
    angel = scenario.creature("Serra Angel", "alice")
    emrakul.summoning_sick = False

    scenario.attack_with(emrakul, defending="alice")
    scenario.advance()

    assert scenario.game.can_block(angel, emrakul), "flying answers flying (CR 702.9b)"


# -- what protection still cannot do here ----------------------------------


def test_announcing_a_protected_target_is_refused_as_the_spell_is_cast():
    """CR 601.2c: an illegal target is refused then, not left to fizzle later."""
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Lightning Bolt", username="alice", targets=[emrakul])


@pytest.mark.xfail(
    reason="CR 702.16e is implemented end to end now, not just possible: "
    "`Game.deal_damage` takes a `source`, `Game.protection_from_damage` reads "
    "the target's protection against it, and real callers actually pass one - "
    "`machines/combat._deal_combat_damage` names the attacker or blocker, and "
    "the damage entries in `machines/effects.py` name the spell or ability - "
    "covered end to end in scenarios/test_prevention_effects.py and "
    "scenarios/test_protection_grants.py. This test's own call below deals its "
    "damage anonymously (`deal_damage(emrakul, 3)`, no `source=`), which is a "
    "choice this test makes, not an engine gap: an anonymous source has no "
    "quality for protection to check against, so this specific call is "
    "correctly never prevented",
    strict=True,
)
def test_damage_from_an_instant_source_is_prevented():
    """CR 702.16e: even damage that never targeted is prevented.

    An *anonymous* call, on purpose - `deal_damage(emrakul, 3)` names no
    source, so there is nothing here for protection to check a quality
    against. `scenarios/test_protection_grants.py`'s Lightning Bolt and
    combat tests are the ones that show a real, named source actually being
    prevented; this one stays xfail to keep that distinction visible rather
    than deleting the case that first exposed the gap.
    """
    scenario = emrakul_on_bobs_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    scenario.game.deal_damage(emrakul, 3)

    assert emrakul.damage == 0


def test_a_player_can_have_protection_too():
    """CR 702.16b covers "a permanent *or player* with protection".

    Runed Halo is **cast** rather than staged onto the battlefield, and that is
    load-bearing: "As this enchantment enters, choose a card name" is a
    CR 614.12a replacement effect, and CR 614.12a puts the choice *before* the
    permanent enters. The scenario harness's staged battlefield skips
    `Game.enter_the_battlefield`, so a staged Halo is a Halo that was never
    asked, and it names nothing to have protection from.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Runed Halo"], battlefield=["Plains", "Plains"])
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", username="bob")
    scenario.will_choose("Lightning Bolt", username="bob", source="Runed Halo")
    scenario.cast_and_resolve("Runed Halo", *sources, username="bob")

    assert (
        scenario.game.protection_refusal(scenario.player("bob"), card("Lightning Bolt")) is not None
    )
    assert scenario.game.protection_refusal(scenario.player("bob"), card("Shock")) is None, (
        "the chosen name is one name, not every red spell (CR 702.16a)"
    )

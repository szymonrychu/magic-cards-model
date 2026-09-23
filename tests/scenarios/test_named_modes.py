"""Scenario: named modes - a flavor word in front of a mode's effect.

Scout the City prints the mode "Destroy target creature with flying." behind
the label "Bring Down" and an em dash. The words before the dash are a flavor
word (CR 207.2d: "Flavor words provide a flavorful description of abilities,
but they have no special rules meaning"), so the mode's instruction is only
the text after the dash.
`machines/modes.mode_effect_text` now strips the label once, in the one
place every mode reader goes through - the resolution parser
(`parse_mode_effect`) and the targeting profile (`mode_rules_text`) - rather
than each reader stepping over it on its own (the select-from-the-top reader
used to, which is why Look Around read and Bring Down did not).

Proof printings: School Daze (Standard/Pioneer/Modern) and You Find the
Villains' Lair (Pioneer/Modern), both "Choose one" with every mode named,
neither in the deck pool - a draw mode, a counter mode, and a two-sentence
counter-then-draw mode, so the stripped label feeds three different readers.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 207.2d** - flavor words carry no rules meaning.
- **CR 700.2** - a modal spell's options are its bulleted modes.
- **CR 700.2h** - a mode with a cost printed before its effect (Tiered's
  "Fire", then "{0}", then the effect): the label-then-cost shape is still read as a cost.
- **CR 701.8a** - destroy moves a permanent to its owner's graveyard.
- **CR 608.2b** - an illegal target on resolution is not affected.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.modes import modal_profile, mode_effect_text, mode_rules_text
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# -- Parsing: the label comes off, and only the label ----------------------


def test_a_named_mode_hands_its_reader_only_the_instruction():
    profile = modal_profile(card("Scout the City"))
    assert profile is not None and profile.understood
    look_around, bring_down = profile.modes
    assert mode_effect_text(bring_down) == "Destroy target creature with flying."
    assert mode_effect_text(look_around).startswith("Mill three cards.")
    # The printed text itself is kept whole, for a player pointing at it.
    assert bring_down.text.startswith("Bring Down")


def test_the_named_mode_targets_exactly_one_creature_with_flying():
    profile = modal_profile(card("Scout the City"))
    assert profile is not None
    targeting = profile_for_text(mode_rules_text(profile.modes[1]))
    assert targeting.understood
    (requirement,) = targeting.requirements
    assert (requirement.minimum, requirement.maximum) == (1, 1)


def test_a_mode_with_no_label_is_left_alone():
    """Thraben Charm's first mode opens with the card's own name and has no
    dash at all - nothing to strip."""
    profile = modal_profile(card("Thraben Charm"))
    assert profile is not None
    assert mode_effect_text(profile.modes[0]).startswith("Thraben Charm deals damage")


def test_a_tiered_label_and_cost_still_read_as_a_cost():
    """CR 700.2h: Fire Magic's "Fire" label is followed by a cost "{0}"; the cost is
    still read, and the effect handed on is the text after both."""
    profile = modal_profile(card("Fire Magic"))
    assert profile is not None
    assert [mode.cost for mode in profile.modes] == ["{0}", "{2}", "{5}"]
    assert mode_effect_text(profile.modes[0]) == "Fire Magic deals 1 damage to each creature."


def test_multi_word_labels_are_stripped_whole():
    """ "Learn Their Secrets" is three words; "Foil Their Scheme" three too."""
    profile = modal_profile(card("You Find the Villains' Lair"))
    assert profile is not None
    assert [mode_effect_text(mode) for mode in profile.modes] == [
        "Counter target spell.",
        "Draw two cards, then discard two cards.",
    ]


# -- Scout the City: both modes resolve ------------------------------------


def _scout_board(bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Scout the City"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Grizzly Bears", "Lightning Bolt", "Island"],
        )
        .player("bob", battlefield=bob_battlefield)
    )


def test_bring_down_destroys_a_creature_with_flying():
    scenario = _scout_board(["Serra Angel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast("Scout the City")
    casting.choose_modes([2])
    casting.choose_targets([angel])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    assert angel.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices


def test_bring_down_refuses_a_creature_without_flying():
    scenario = _scout_board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Scout the City")
    casting.choose_modes([2])
    with pytest.raises(ValueError):
        casting.choose_targets([bears])


def test_bring_down_does_nothing_to_a_flier_that_lost_flying_before_resolution():
    """CR 608.2b: the target is rechecked on resolution. Birds of Paradise
    is a flier when targeted; if it is gone from the battlefield by then,
    the mode does nothing and the spell still leaves the stack."""
    scenario = _scout_board(["Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")

    casting = scenario.cast("Scout the City")
    casting.choose_modes([2])
    casting.choose_targets([birds])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    spell = scenario.put_on_stack(casting)
    scenario.game.return_to_hand(birds)
    _resolve_all(scenario)

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.find("Birds of Paradise", Zone.HAND, "bob") is not None
    assert not scenario.game.mode_notices


def test_look_around_still_mills_three_and_keeps_a_permanent_card():
    scenario = _scout_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.player("alice").library[1]
    scenario.will_choose_cards(bears, source="Scout the City")

    casting = scenario.cast("Scout the City")
    casting.choose_modes([1])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    assert bears.zone is Zone.HAND
    assert scenario.player("alice").life == 23
    assert [c.name for c in scenario.player("alice").library] == ["Island"]
    assert not scenario.game.mode_notices


# -- School Daze: a second printing, Standard-legal ------------------------


def test_do_homework_draws_three():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["School Daze"],
            battlefield=["Island"] * 5,
            library=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("School Daze")
    casting.choose_modes([1])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Island"] * 5)))
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    alice = scenario.player("alice")
    assert [c.name for c in alice.hand] == ["Forest"] * 3
    assert len(alice.library) == 1
    assert not scenario.game.mode_notices


def _bolt_on_the_stack(alice_hand: list[str], islands: int) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player(
            "alice",
            hand=alice_hand,
            battlefield=["Island"] * islands,
            library=["Forest"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    return scenario, bolt


def test_fight_crime_counters_the_spell_and_draws_a_card():
    """Two sentences after the label - both run (CR 608.2c)."""
    scenario, bolt = _bolt_on_the_stack(["School Daze"], 5)

    casting = scenario.cast("School Daze", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([bolt])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*(["Island"] * 5), username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert alice.life == 20, "the countered Bolt never resolved"
    assert [c.name for c in alice.hand] == ["Forest"]
    assert not scenario.game.mode_notices


# -- You Find the Villains' Lair: a third printing -------------------------


def test_foil_their_scheme_counters_target_spell():
    scenario, bolt = _bolt_on_the_stack(["You Find the Villains' Lair"], 3)

    casting = scenario.cast("You Find the Villains' Lair", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bolt])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*(["Island"] * 3), username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20
    assert not scenario.game.mode_notices


def test_learn_their_secrets_draws_two_then_discards_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["You Find the Villains' Lair", "Mountain"],
            battlefield=["Island"] * 3,
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    alice = scenario.player("alice")
    first, second = alice.library[0], alice.library[1]
    scenario.will_choose_cards(mountain, first, source="You Find the Villains' Lair")

    casting = scenario.cast("You Find the Villains' Lair")
    casting.choose_modes([2])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Island"] * 3)))
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    assert [c.id for c in alice.hand] == [second.id]
    assert mountain.zone is Zone.GRAVEYARD
    assert first.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices

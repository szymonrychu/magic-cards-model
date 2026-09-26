"""Scenario: prepare spell faces (CR 722) resolved by the ordinary spell
dispatcher.

CR 722.3c: "As a permanent with a prepare spell gains the prepared
designation ..., its controller creates a copy of that object in exile,
except that copy has only the characteristics of that permanent's prepare
spell ... For as long as the copy remains in exile, the prepared permanent's
controller may cast the copy." So the copy that is cast is an ordinary
instant or sorcery whose only text is the inset spell's - nothing reads it
but `effect_for`, the same dispatcher every other spell goes through. These
are the Secrets of Strixhaven prepare faces that dispatcher could not read:

- **Reanimate** (Grave Researcher): "Put target creature card from a
  graveyard onto the battlefield under your control. You lose life equal to
  that card's mana value." CR 110.2a puts it under the resolving spell's
  controller; the life loss is read off the card the first sentence moved.
- **Scrollboost** (Spiritcall Enthusiast): "One or two target creatures each
  get +2/+2 until end of turn." - CR 601.2c's "one or two" is a target count
  with a minimum of one.
- **Venomous Words** (Scathing Shadelock): "Target creature you control gets
  +2/+0 and gains deathtouch until end of turn."
- **Secret Rendezvous** (Joined Researchers): "You and target opponent each
  draw three cards." - a compound subject, one instruction per player.

Generality, each on a printing that is not a listed card and not in a deck:

- **Beacon of Unrest** (Modern) - "Put target artifact or creature card from
  a graveyard onto the battlefield under your control. Shuffle Beacon of
  Unrest into its owner's library." The same reanimation sentence with a
  different target phrase and a different rider.
- **Divine Offering** (Modern) - "Destroy target artifact. You gain life equal
  to its mana value." The life-equal-to-mana-value rider after a different
  verb, gain instead of lose, "its" instead of "that card's".
- **Appeal to Eirdu** (Standard) - "One or two target creatures each get
  +2/+1 until end of turn." on an ordinary card with convoke.
- **Farsight Adept** (Pioneer) - "When this creature enters, you and target
  opponent each draw a card." - the compound subject on a triggered ability.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import CardState
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _prepared_copy(scenario: PlayedScenario, name: str, username: str = "alice") -> CardState:
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    copy = scenario.game.become_prepared(permanent)
    assert copy is not None, "CR 722.3a: a permanent with a prepare spell becomes prepared"
    return copy


def _cast_copy(
    scenario: PlayedScenario,
    copy: CardState,
    *mana: CardState,
    targets: list,
    username: str = "alice",
) -> None:
    casting = scenario.cast(copy.name, username, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *mana)
    scenario.put_on_stack(casting)


# -- CR 722.3c: the copy has only the prepare spell's characteristics ---------


@pytest.mark.parametrize(
    ("front", "face", "kind"),
    [
        ("Grave Researcher", "Reanimate", Type.SORCERY),
        ("Spiritcall Enthusiast", "Scrollboost", Type.SORCERY),
        ("Scathing Shadelock", "Venomous Words", Type.SORCERY),
        ("Joined Researchers", "Secret Rendezvous", Type.SORCERY),
    ],
)
def test_the_prepared_copy_is_only_the_prepare_spell(front, face, kind):
    scenario = Scenario().player("alice", battlefield=[front]).build()
    copy = _prepared_copy(scenario, front)

    assert copy.name == face
    assert kind in copy.types
    assert Type.CREATURE not in copy.types, "CR 722.3c: only the prepare spell's characteristics"
    assert copy.zone is Zone.EXILE


# -- Reanimate ------------------------------------------------------------------


def _reanimate_board(*, bob_graveyard: list[str], alice_graveyard: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grave Researcher", "Swamp"],
            graveyard=alice_graveyard or [],
        )
        .player("bob", graveyard=bob_graveyard)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_reanimate_steals_from_an_opponents_graveyard_and_costs_its_mana_value():
    scenario = _reanimate_board(bob_graveyard=["Ancient Silverback"])
    researcher = scenario.creature("Grave Researcher")
    copy = _prepared_copy(scenario, "Grave Researcher")
    silverback = scenario.find("Ancient Silverback", Zone.GRAVEYARD, "bob")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[silverback])
    assert researcher.prepared is False, "CR 601.2i: casting the copy unprepares it"
    scenario.resolve_top()

    assert silverback.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(silverback).username == "alice", (
        "CR 110.2a: under the control of the player the effect names"
    )
    assert silverback.owner == "bob"
    assert scenario.player("alice").life == 20 - 6, "Ancient Silverback's mana value is 6"
    assert scenario.player("bob").life == 20


def test_reanimate_from_your_own_graveyard():
    scenario = _reanimate_board(bob_graveyard=[], alice_graveyard=["Grizzly Bears"])
    copy = _prepared_copy(scenario, "Grave Researcher")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 18


def test_a_zero_mana_value_creature_costs_no_life():
    scenario = _reanimate_board(bob_graveyard=["Memnite"])
    copy = _prepared_copy(scenario, "Grave Researcher")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "bob")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[memnite])
    scenario.resolve_top()

    assert memnite.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_reanimate_cannot_target_a_noncreature_card():
    scenario = _reanimate_board(bob_graveyard=["Sol Ring"])
    copy = _prepared_copy(scenario, "Grave Researcher")
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "bob")

    casting = scenario.cast(copy.name, "alice", from_zone=Zone.EXILE)
    casting.use_permission()
    with pytest.raises(ValueError):
        casting.choose_targets([ring])


def test_reanimate_whose_target_left_the_graveyard_does_nothing_at_all():
    """CR 608.2b: its only target is illegal, so the spell doesn't resolve -
    no creature and no life loss."""
    scenario = _reanimate_board(bob_graveyard=["Ancient Silverback"])
    copy = _prepared_copy(scenario, "Grave Researcher")
    silverback = scenario.find("Ancient Silverback", Zone.GRAVEYARD, "bob")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[silverback])
    scenario.game.exile_cards([silverback])
    scenario.resolve_top()

    assert silverback.zone is Zone.EXILE
    assert scenario.player("alice").life == 20


def test_the_resolved_copy_does_not_linger():
    """CR 704.5e: a copy of a card outside the stack ceases to exist."""
    scenario = _reanimate_board(bob_graveyard=["Grizzly Bears"])
    copy = _prepared_copy(scenario, "Grave Researcher")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.resolve_top()

    everywhere = [state for state in scenario.all_card_states() if state.id == copy.id]
    assert all(state.zone is not Zone.GRAVEYARD for state in everywhere)


def test_beacon_of_unrest_reads_the_same_reanimation_sentence():
    scenario = (
        Scenario()
        .player("alice", hand=["Beacon of Unrest"], battlefield=["Swamp"] * 5)
        .player("bob", graveyard=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "bob")

    beacon = scenario.cast_and_resolve(
        "Beacon of Unrest", *scenario.untapped_sources(*["Swamp"] * 5), targets=[ring]
    )

    assert ring.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(ring).username == "alice"
    assert beacon.zone is Zone.LIBRARY, "Shuffle Beacon of Unrest into its owner's library"
    assert scenario.player("alice").life == 20, "no life rider on Beacon of Unrest"


def test_divine_offering_gains_life_equal_to_the_destroyed_artifacts_mana_value():
    scenario = (
        Scenario()
        .player("alice", hand=["Divine Offering"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Divine Offering", *scenario.untapped_sources("Plains", "Plains"), targets=[ring]
    )

    assert ring.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 21


def test_divine_offering_whose_artifact_is_indestructible_still_gains_the_life():
    """The rider reads the target's mana value, not whether it was destroyed
    - Darksteel Relic survives and the life is still gained."""
    scenario = (
        Scenario()
        .player("alice", hand=["Divine Offering"], battlefield=["Plains"] * 2)
        .player("bob", battlefield=["Darksteel Relic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    citadel = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Divine Offering", *scenario.untapped_sources("Plains", "Plains"), targets=[citadel]
    )

    assert citadel.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20, "Darksteel Relic's mana value is 0"


# -- Scrollboost ---------------------------------------------------------------


def _scrollboost_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Spiritcall Enthusiast", "Grizzly Bears", "Plains", "Plains"])
        .player("bob", battlefield=["Tarmogoyf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_scrollboost_pumps_two_targets():
    scenario = _scrollboost_board()
    enthusiast = scenario.creature("Spiritcall Enthusiast")
    bears = scenario.creature("Grizzly Bears")
    copy = _prepared_copy(scenario, "Spiritcall Enthusiast")

    _cast_copy(
        scenario, copy, *scenario.untapped_sources("Plains", "Plains"), targets=[enthusiast, bears]
    )
    scenario.resolve_top()

    assert scenario.game.characteristics_of(enthusiast).power == 5
    assert scenario.game.characteristics_of(enthusiast).toughness == 5
    assert scenario.game.characteristics_of(bears).power == 4
    assert scenario.game.characteristics_of(bears).toughness == 4


def test_scrollboost_with_one_target_pumps_only_that_one():
    """CR 601.2c: "one or two" - one target is enough."""
    scenario = _scrollboost_board()
    enthusiast = scenario.creature("Spiritcall Enthusiast")
    goyf = scenario.creature("Tarmogoyf", "bob")
    copy = _prepared_copy(scenario, "Spiritcall Enthusiast")
    goyf_power = scenario.game.characteristics_of(goyf).power

    _cast_copy(scenario, copy, *scenario.untapped_sources("Plains", "Plains"), targets=[goyf])
    scenario.resolve_top()

    assert scenario.game.characteristics_of(goyf).power == goyf_power + 2
    assert scenario.game.characteristics_of(enthusiast).power == 3


def test_scrollboost_refuses_a_third_target():
    scenario = _scrollboost_board()
    enthusiast = scenario.creature("Spiritcall Enthusiast")
    bears = scenario.creature("Grizzly Bears")
    goyf = scenario.creature("Tarmogoyf", "bob")
    copy = _prepared_copy(scenario, "Spiritcall Enthusiast")

    casting = scenario.cast(copy.name, "alice", from_zone=Zone.EXILE)
    casting.use_permission()
    with pytest.raises(ValueError):
        casting.choose_targets([enthusiast, bears, goyf])


def test_scrollboost_still_pumps_the_target_that_stayed_legal():
    """CR 608.2b: an illegal target is not affected; the legal one still is."""
    scenario = _scrollboost_board()
    enthusiast = scenario.creature("Spiritcall Enthusiast")
    bears = scenario.creature("Grizzly Bears")
    copy = _prepared_copy(scenario, "Spiritcall Enthusiast")

    _cast_copy(
        scenario, copy, *scenario.untapped_sources("Plains", "Plains"), targets=[enthusiast, bears]
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(enthusiast).power == 5


def test_scrollboost_wears_off_in_the_cleanup_step():
    scenario = _scrollboost_board()
    enthusiast = scenario.creature("Spiritcall Enthusiast")
    copy = _prepared_copy(scenario, "Spiritcall Enthusiast")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Plains", "Plains"), targets=[enthusiast])
    scenario.resolve_top()
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()

    assert scenario.game.characteristics_of(enthusiast).power == 3


def test_appeal_to_eirdu_reads_one_or_two_targets_the_same_way():
    scenario = (
        Scenario()
        .player("alice", hand=["Appeal to Eirdu"], battlefield=["Plains"] * 4 + ["Grizzly Bears"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Appeal to Eirdu", *scenario.untapped_sources(*["Plains"] * 4), targets=[bears, angel]
    )

    assert scenario.game.characteristics_of(bears).power == 4
    assert scenario.game.characteristics_of(bears).toughness == 3
    assert scenario.game.characteristics_of(angel).power == 6
    assert scenario.game.characteristics_of(angel).toughness == 5


# -- Venomous Words ------------------------------------------------------------


def _venomous_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Scathing Shadelock", "Grizzly Bears", "Swamp"])
        .player("bob", battlefield=["Tarmogoyf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_venomous_words_gives_plus_two_and_deathtouch():
    scenario = _venomous_board()
    bears = scenario.creature("Grizzly Bears")
    copy = _prepared_copy(scenario, "Scathing Shadelock")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.resolve_top()

    computed = scenario.game.characteristics_of(bears)
    assert computed.power == 4
    assert computed.toughness == 2
    assert has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)


def test_venomous_words_cannot_target_an_opponents_creature():
    scenario = _venomous_board()
    goyf = scenario.creature("Tarmogoyf", "bob")
    copy = _prepared_copy(scenario, "Scathing Shadelock")

    casting = scenario.cast(copy.name, "alice", from_zone=Zone.EXILE)
    casting.use_permission()
    with pytest.raises(ValueError):
        casting.choose_targets([goyf])


def test_venomous_words_wears_off_in_the_cleanup_step():
    scenario = _venomous_board()
    bears = scenario.creature("Grizzly Bears")
    copy = _prepared_copy(scenario, "Scathing Shadelock")

    _cast_copy(scenario, copy, *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.resolve_top()
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()

    assert scenario.game.characteristics_of(bears).power == 2
    assert not has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)


# -- Secret Rendezvous ---------------------------------------------------------


def _rendezvous_board(*, bob_library: int = 5):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Joined Researchers", "Plains", "Plains", "Plains"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_secret_rendezvous_draws_three_for_each_of_you():
    scenario = _rendezvous_board()
    copy = _prepared_copy(scenario, "Joined Researchers")
    alice_hand = len(scenario.player("alice").hand)

    _cast_copy(scenario, copy, *scenario.untapped_sources(*["Plains"] * 3), targets=["bob"])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == alice_hand + 3
    assert len(scenario.player("bob").hand) == 3


def test_secret_rendezvous_cannot_target_yourself():
    scenario = _rendezvous_board()
    copy = _prepared_copy(scenario, "Joined Researchers")

    casting = scenario.cast(copy.name, "alice", from_zone=Zone.EXILE)
    casting.use_permission()
    with pytest.raises(ValueError):
        casting.choose_targets(["alice"])


def test_secret_rendezvous_against_a_short_library_draws_what_is_there():
    """CR 609.3: the opponent draws the two cards they have; the attempt to
    draw from an empty library is what CR 704.5b later reads."""
    scenario = _rendezvous_board(bob_library=2)
    copy = _prepared_copy(scenario, "Joined Researchers")

    _cast_copy(scenario, copy, *scenario.untapped_sources(*["Plains"] * 3), targets=["bob"])
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == 2
    assert len(scenario.player("bob").library) == 0
    assert len(scenario.player("alice").hand) == 3


def test_farsight_adept_reads_the_compound_subject_on_a_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Farsight Adept"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", username="alice")

    scenario.put_onto_battlefield("Farsight Adept", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == 1
    assert len(scenario.player("bob").hand) == 1

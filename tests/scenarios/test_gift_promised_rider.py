"""Scenario: a gift spell's "If the gift was promised, <more>" sentence - the
extra only happens when the caster promised the gift.

- **CR 702.174k** - a spell's gift was promised if its controller declared
  the intention to pay its gift cost; that is the condition, read off the
  resolving spell's own cast record, not guessed from the board.
- **CR 702.174j** - for an instant or sorcery the gift effect happens before
  any other spell ability of the card.
- **CR 608.2c** - "that creature" is the object the first sentence acted on.
- **CR 613.1f** - the rider's keyword is a layer 6 grant; **CR 613.4c** - the
  +2/+2 is sublayer 7c.
- **CR 702.12b** - indestructible: a permanent with it can't be destroyed.
- **CR 608.2b** - with its only target illegal the spell does not resolve, so
  neither the gift nor the rider happens.

Crumb and Get It is the reported card (a targeted pump and an anaphoric
"that creature also gains indestructible"). Dawn's Truce is the second
printing: a different gift (a card), a group rather than an anaphor
("permanents you control also gain indestructible"), and a first sentence
that grants the player hexproof too.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario: Scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _crumb(**bob) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=["Crumb and Get It"],
            battlefield=["Plains", "Grizzly Bears", "Memnite"],
        )
        .player("bob", library=["Plains"], **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_crumb(scenario: Scenario, *, gift: str | None):
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = scenario.find("Crumb and Get It", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.game.cast(spell, "alice", targets=[bears], mana_sources=[plains], gift=gift)
    scenario.pass_until_resolved()
    return bears


def test_without_the_gift_only_the_pump():
    scenario = _crumb()
    bears = _cast_crumb(scenario, gift=None)

    assert computed(scenario).of(bears).power_toughness == (4, 4)
    assert not is_indestructible(bears, scenario.game)
    assert "Food Token" not in scenario.battlefield_names()
    assert notices(scenario) == []


def test_with_the_gift_that_creature_also_gains_indestructible():
    scenario = _crumb()
    bears = _cast_crumb(scenario, gift="bob")

    assert computed(scenario).of(bears).power_toughness == (4, 4)
    assert is_indestructible(bears, scenario.game)
    food = [state for state in scenario.game.battlefield if state.name == "Food Token"]
    assert [token.controller for token in food] == ["bob"]
    assert notices(scenario) == []


def test_the_rider_is_bound_to_the_target_only():
    scenario = _crumb()
    _cast_crumb(scenario, gift="bob")
    memnite = scenario.creature("Memnite", "alice")

    assert not is_indestructible(memnite, scenario.game)
    assert computed(scenario).of(memnite).power_toughness == (1, 1)


def test_the_granted_indestructible_survives_a_destroy_spell():
    """CR 702.12b on a real opponent's Prophesied End."""
    scenario = _crumb(hand=["Prophesied End"], battlefield=["Plains", "Plains"])
    bears = _cast_crumb(scenario, gift="bob")

    plains = scenario.untapped_sources("Plains", "Plains", username="bob")
    scenario.game.pass_priority("alice")  # hand priority to bob in alice's main phase
    scenario.cast_onto_stack("Prophesied End", *plains, username="bob", targets=[bears])
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD


def test_without_the_gift_the_destroy_spell_kills_it():
    scenario = _crumb(hand=["Prophesied End"], battlefield=["Plains", "Plains"])
    bears = _cast_crumb(scenario, gift=None)

    plains = scenario.untapped_sources("Plains", "Plains", username="bob")
    scenario.game.pass_priority("alice")
    scenario.cast_onto_stack("Prophesied End", *plains, username="bob", targets=[bears])
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD


def test_indestructible_ends_with_the_pump_in_the_cleanup_step():
    scenario = _crumb()
    bears = _cast_crumb(scenario, gift="bob")

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not is_indestructible(bears, scenario.game)
    assert computed(scenario).of(bears).power_toughness == (2, 2)


def test_an_illegal_target_means_no_gift_and_no_rider():
    """CR 608.2b / CR 702.174j: the spell does not resolve, so the gift effect
    does not happen either."""
    scenario = _crumb()
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = scenario.find("Crumb and Get It", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.game.cast(spell, "alice", targets=[bears], mana_sources=[plains], gift="bob")
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert "Food Token" not in scenario.battlefield_names()
    assert scenario.game.continuous_effects.effects == []


# -- second printing: Dawn's Truce -----------------------------------------


def _truce(*, gift: str | None) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=["Dawn's Truce"],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", library=["Plains"], hand=[], battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Dawn's Truce", Zone.HAND, "alice")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.game.cast(spell, "alice", mana_sources=plains, gift=gift)
    scenario.pass_until_resolved()
    return scenario


def test_dawns_truce_without_the_gift_is_hexproof_only():
    scenario = _truce(gift=None)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert computed(scenario).of(bears).has_ability("Hexproof")
    assert not is_indestructible(bears, scenario.game)
    assert len(scenario.player("bob").hand) == 0
    assert notices(scenario) == []


def test_dawns_truce_with_the_gift_makes_your_permanents_indestructible_too():
    scenario = _truce(gift="bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    (land, _) = scenario.creatures("Plains", "Plains", username="alice")

    assert computed(scenario).of(bears).has_ability("Hexproof")
    assert is_indestructible(bears, scenario.game)
    assert is_indestructible(land, scenario.game), "permanents, not only creatures"
    assert len(scenario.player("bob").hand) == 1, "Gift a card: bob drew"
    assert notices(scenario) == []


def test_dawns_truce_gift_does_not_reach_the_opponents_permanents():
    scenario = _truce(gift="bob")
    memnite = scenario.creature("Memnite", "bob")

    assert not is_indestructible(memnite, scenario.game)

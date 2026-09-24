"""A permanent's static permission to cast a spell from its controller's
graveyard once during each of that player's turns.

- **Rivaz of the Claw** - "Once during each of your turns, you may cast a
  Dragon creature spell from your graveyard."
- **Gisa and Geralf** (second printing - Modern and Pioneer legal on
  Scryfall, in no deck list) - "... you may cast a Zombie creature spell from
  your graveyard." A different subtype and no exile rider.
- **Kess, Dissident Mage** (third printing - Modern legal, in no deck list) -
  "Once during each of your turns, you may cast an instant or sorcery spell
  from your graveyard. If a spell cast this way would be put into your
  graveyard, exile it instead." Card types rather than a subtype, with the
  exile rider.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 601.3** - a spell can be cast only if a rule or effect allows it; the
  permission is the static ability's (CR 611.3a: it applies at any moment to
  whatever its text indicates, and only while the permanent is on the
  battlefield, CR 611.3b).
- **CR 400.7** - a permanent that leaves and comes back is a new object, so
  the "once" it had already spent does not follow it.
- **CR 614.1a** - Kess's "instead" is a replacement effect.
- **CR 304.1** / **CR 307.1** - the permission changes where a spell is cast
  from, not when: a creature or sorcery still waits for its controller's
  main phase.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    Casting,
    granted_cast_options,
    why_cannot_cast_from,
)
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_from_graveyard(scenario, card, caster="alice", *, targets=()):
    casting = Casting(spell=card, caster=caster, origin_zone=Zone.GRAVEYARD, game=scenario.game)
    casting.use_keyword(CAST_PERMISSION)
    if targets:
        casting.choose_targets(list(targets))
    scenario.auto_pay(casting.begin_paying(), username=caster)
    return scenario.put_on_stack(casting)


def _rivaz(*, graveyard=("Slumbering Dragon", "Slumbering Dragon", "Grizzly Bears")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rivaz of the Claw"] + ["Mountain"] * 4 + ["Forest"] * 2,
            graveyard=list(graveyard),
            library=["Mountain"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_dragon_creature_card_can_be_cast_from_the_graveyard():
    scenario = _rivaz()
    dragon = scenario.find("Slumbering Dragon", Zone.GRAVEYARD, "alice")
    dragon = _cast_from_graveyard(scenario, dragon)
    _resolve_everything(scenario)
    assert dragon.zone is Zone.BATTLEFIELD


def test_only_once_during_the_turn():
    scenario = _rivaz()
    first, second = [
        card for card in scenario.player("alice").graveyard if card.name == "Slumbering Dragon"
    ]
    _cast_from_graveyard(scenario, first)
    _resolve_everything(scenario)

    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, second)
    assert second.zone is Zone.GRAVEYARD


def test_legal_actions_stop_offering_the_second_cast():
    scenario = _rivaz()
    first, second = [
        card for card in scenario.player("alice").graveyard if card.name == "Slumbering Dragon"
    ]

    def offered(card):
        return any(
            getattr(action, "card_id", None) == card.id
            for action in legal_actions(scenario.game, "alice")
        )

    assert offered(first) and offered(second)
    _cast_from_graveyard(scenario, first)
    _resolve_everything(scenario)
    assert not offered(second)


def test_a_non_dragon_creature_card_is_not_covered():
    scenario = _rivaz()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, bears)


def test_the_permission_comes_back_on_its_controllers_next_turn():
    scenario = _rivaz()
    first, second = [
        card for card in scenario.player("alice").graveyard if card.name == "Slumbering Dragon"
    ]
    _cast_from_graveyard(scenario, first)
    _resolve_everything(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    second = _cast_from_graveyard(scenario, second)
    _resolve_everything(scenario)
    assert second.zone is Zone.BATTLEFIELD


def test_a_rivaz_that_left_and_returned_is_a_new_object_with_its_own_once():
    """CR 400.7: the flickered Rivaz has spent nothing this turn."""
    scenario = _rivaz()
    first, second = [
        card for card in scenario.player("alice").graveyard if card.name == "Slumbering Dragon"
    ]
    _cast_from_graveyard(scenario, first)
    _resolve_everything(scenario)
    rivaz = scenario.find("Rivaz of the Claw", Zone.BATTLEFIELD, "alice")
    exiled = scenario.game.exile_permanent(rivaz)
    scenario.game.put_onto_battlefield(exiled, "alice")

    second = _cast_from_graveyard(scenario, second)
    _resolve_everything(scenario)
    assert second.zone is Zone.BATTLEFIELD


def test_without_rivaz_the_graveyard_is_closed():
    scenario = _rivaz()
    rivaz = scenario.find("Rivaz of the Claw", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(rivaz)
    dragon = scenario.find("Slumbering Dragon", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, dragon)


# -- Gisa and Geralf: a Zombie, no rider -----------------------------------


def test_gisa_and_geralf_cast_a_zombie_once_and_it_dies_to_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gisa and Geralf", "Swamp", "Swamp"],
            graveyard=["Carrion Feeder", "Carrion Feeder"],
            library=["Swamp"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.player("alice").graveyard
    first = _cast_from_graveyard(scenario, first)
    _resolve_everything(scenario)
    assert first.zone is Zone.BATTLEFIELD

    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, second)

    scenario.game.destroy(first)
    assert first.zone is Zone.GRAVEYARD


# -- Kess, Dissident Mage: instants and sorceries, exiled after -----------


def _kess(graveyard=("Lightning Bolt", "Shock")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kess, Dissident Mage", "Mountain", "Mountain"],
            graveyard=list(graveyard),
            library=["Mountain"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_kess_casts_an_instant_from_the_graveyard_and_exiles_it():
    scenario = _kess()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    bolt = _cast_from_graveyard(scenario, bolt, targets=[scenario.player("bob")])
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE


def test_kess_allows_only_one_per_turn():
    scenario = _kess()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    shock = scenario.find("Shock", Zone.GRAVEYARD, "alice")
    _cast_from_graveyard(scenario, bolt, targets=[scenario.player("bob")])
    _resolve_everything(scenario)
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, shock, targets=[scenario.player("bob")])


def test_kess_does_nothing_during_an_opponents_turn():
    """ "During each of your turns": an instant from the graveyard on bob's
    turn is refused even though an instant could otherwise be cast then."""
    scenario = _kess()
    scenario.game.automatic_turn_based_actions = True
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    scenario.start_at(Step.UPKEEP)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert granted_cast_options(scenario.game, bolt, "alice", Zone.GRAVEYARD) == []
    assert why_cannot_cast_from(bolt, "alice", Zone.GRAVEYARD, scenario.game) is not None

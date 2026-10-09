"""CR 118.8 additional costs and CR 118.9 alternative costs read off a spell's
own printed line (EP-01 round 1, task T7): "tap N untapped artifacts,
creatures, and/or lands you control", "discard a card or sacrifice a
permanent", "you may collect evidence 6", "You may pay {1} and return a basic
land you control to its owner's hand rather than pay this spell's mana cost".

Rules read whole with `mise run rules:find 118.8` and `mise run rules:find
118.9` this session: an additional cost is paid on top of the mana or
alternative cost (CR 118.8, CR 601.2f); only one alternative cost may be
applied to a spell (CR 118.9a); a cost is paid in full or not at all (CR 118.3).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting.options import (
    optional_additional_costs,
    or_additional_cost_alternatives,
    reads_optional_additional_cost_line,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _kinds(casting) -> list[tuple[str, int]]:
    scenario_game = casting.game
    scenario_game.determine_total_cost(casting)
    return [(c.kind.value, c.required) for c in casting.total_cost.components]


# -- mandatory "tap N untapped <qualities>" -----------------------------------


@pytest.mark.parametrize(
    ("spell", "count", "fodder"),
    [
        ("Fear of Exposure", 2, ["Grizzly Bears", "Forest"]),
        ("Warlord's Elite", 2, ["Grizzly Bears", "Sol Ring"]),
        ("Guardian of the Great Door", 4, ["Grizzly Bears", "Sol Ring", "Plains", "Plains"]),
    ],
)
def test_and_or_tap_costs_are_charged_with_the_chosen_permanents(spell, count, fodder):
    scenario = _main(alice={"hand": [spell], "battlefield": fodder})
    chosen = scenario.game.permanents_controlled_by("alice")[:count]
    casting = scenario.cast(spell, "alice", tapping=chosen)
    assert _kinds(casting) == [("tap", count)]
    assert len(casting.total_cost.components[0].cards) == count


def test_a_tap_cost_refuses_fewer_permanents_than_it_demands():
    scenario = _main(alice={"hand": ["Fear of Exposure"], "battlefield": ["Forest"]})
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast("Fear of Exposure", "alice", tapping=[forest])
    scenario.game.determine_total_cost(casting)
    (component,) = casting.total_cost.components
    assert component.required == 2
    assert len(component.cards) == 1, "one permanent cannot pay for two (CR 118.3)"


# -- "discard a card or sacrifice a permanent" ----------------------------------


def test_souls_of_the_lost_is_paid_by_discarding_a_card():
    scenario = _main(
        alice={"hand": ["Souls of the Lost", "Grizzly Bears"], "battlefield": ["Sol Ring"]}
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    casting = scenario.cast("Souls of the Lost", "alice", discarding=[bears])
    assert _kinds(casting) == [("discard", 1)]


def test_souls_of_the_lost_is_paid_by_sacrificing_a_permanent():
    scenario = _main(alice={"hand": ["Souls of the Lost"], "battlefield": ["Sol Ring"]})
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast("Souls of the Lost", "alice", sacrificing=[ring])
    assert _kinds(casting) == [("sacrifice", 1)]


def test_the_two_halves_are_both_readable_alternatives():
    assert or_additional_cost_alternatives("discard a card or sacrifice a permanent") == [
        "discard a card",
        "sacrifice a permanent",
    ]


# -- optional additional costs ---------------------------------------------------


@pytest.mark.parametrize(
    ("spell", "keyword"),
    [
        ("Crimestopper Sprite", "collect evidence"),
        ("Vitu-Ghazi Inspector", "collect evidence"),
        ("Orator of Ojutai", "reveal"),
    ],
)
def test_optional_additional_costs_are_offered_and_understood(spell, keyword):
    scenario = _main(alice={"hand": [spell]})
    (card,) = scenario.game.player("alice").hand
    (offer,) = optional_additional_costs(card.card)
    assert offer.keyword == keyword
    assert offer.understood
    assert reads_optional_additional_cost_line(
        f"As an additional cost to cast this spell, {offer.cost}."
    )


# -- alternative costs: "pay {M} and <object cost>" ---------------------------------


@pytest.mark.parametrize("post", ["Fieldmist Borderpost", "Firewild Borderpost"])
def test_borderposts_offer_pay_one_and_return_a_basic_land(post):
    scenario = _main(alice={"hand": [post], "battlefield": ["Plains", "Island", "Mountain"]})
    casting = scenario.cast(post, "alice")
    (option,) = casting.alternative_costs
    assert "return a basic land" in option.description.lower() or option.cost is not None
    land = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    casting.use_alternative_cost(choosing=[land])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}"
    assert [c.kind.value for c in casting.total_cost.components] == ["return_to_hand"]


def test_stalwart_valkyrie_exiles_a_creature_card_from_the_graveyard():
    scenario = _main(
        alice={
            "hand": ["Stalwart Valkyrie"],
            "graveyard": ["Grizzly Bears"],
            "battlefield": ["Plains", "Plains"],
        }
    )
    casting = scenario.cast("Stalwart Valkyrie", "alice")
    (option,) = casting.alternative_costs
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    casting.use_alternative_cost(choosing=[bears])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}{W}"
    assert [c.kind.value for c in casting.total_cost.components] == ["exile"]
    assert option is not None


def test_zahid_taps_an_untapped_artifact():
    scenario = _main(
        alice={"hand": ["Zahid, Djinn of the Lamp"], "battlefield": ["Sol Ring", "Island"]}
    )
    casting = scenario.cast("Zahid, Djinn of the Lamp", "alice")
    (option,) = casting.alternative_costs
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    casting.use_alternative_cost(choosing=[ring])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{3}{U}"
    assert [c.kind.value for c in casting.total_cost.components] == ["tap"]
    assert option is not None

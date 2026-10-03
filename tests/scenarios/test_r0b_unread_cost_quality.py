"""A sacrifice/discard cost whose quality words are unread is never free.

`Game._choice_cost` used to fall back to an unrestricted sacrifice or discard
when `cost_component_for_phrase` could not read the phrase, so a quality word
nobody taught the reader (Fountainport's "token" was the first) went unenforced
(CR 118.3, CR 602.2). Now an unread phrase is refused (CR 602.5), a
"discard-or-sacrifice" choice (CR 118.1) is read as two options, and a discard
cost that only names its own mana value (Kozilek) is read as "a card".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _bullseye_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Bullseye, Death Dealer", "Sol Ring", "Forest", "Forest", "Forest"],
            hand=["Lightning Bolt", "Forest"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
    )


def _ready_bullseye(scenario):
    bullseye = scenario.find("Bullseye, Death Dealer", Zone.BATTLEFIELD, "alice")
    bullseye.summoning_sick = False
    return bullseye


def _pay(scenario):
    return scenario.untapped_sources("Forest", "Forest", "Forest")


def test_bullseye_sacrifices_an_artifact_for_its_cost():
    scenario = _bullseye_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bullseye = _ready_bullseye(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        bullseye,
        *_pay(scenario),
        index=0,
        sacrificing=[ring],
        targets=[scenario.player("bob")],
    )
    assert ring.zone is not Zone.BATTLEFIELD


def test_bullseye_discards_a_nonland_card_for_its_cost():
    scenario = _bullseye_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bullseye = _ready_bullseye(scenario)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.activate(
        bullseye,
        *_pay(scenario),
        index=0,
        discarding=[bolt],
        targets=[scenario.player("bob")],
    )
    assert bolt.zone is Zone.GRAVEYARD


def test_bullseye_refuses_a_land_discard():
    scenario = _bullseye_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bullseye = _ready_bullseye(scenario)
    forest = scenario.find("Forest", Zone.HAND, "alice")
    with pytest.raises(ValueError):
        scenario.activate(
            bullseye,
            *_pay(scenario),
            index=0,
            discarding=[forest],
            targets=[scenario.player("bob")],
        )
    assert forest.zone is Zone.HAND


def test_bullseye_refuses_a_nonartifact_sacrifice():
    scenario = _bullseye_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bullseye = _ready_bullseye(scenario)
    with pytest.raises(ValueError):
        scenario.activate(
            bullseye,
            *_pay(scenario),
            index=0,
            sacrificing=[bullseye],
            targets=[scenario.player("bob")],
        )
    assert bullseye.zone is Zone.BATTLEFIELD


def test_bullseye_refuses_when_neither_option_is_offered():
    scenario = _bullseye_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bullseye = _ready_bullseye(scenario)
    with pytest.raises(ValueError):
        scenario.activate(bullseye, *_pay(scenario), index=0, targets=[scenario.player("bob")])


def test_kozilek_discard_cost_takes_any_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kozilek, the Great Distortion"],
            hand=["Lightning Bolt"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kozilek = scenario.find("Kozilek, the Great Distortion", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    index = next(
        i
        for i, ability in enumerate(scenario.game.activated_abilities(kozilek))
        if "Discard a card" in ability.text
    )
    cost = scenario.game.activation_cost(kozilek, index, discarding=[bolt])
    (discard,) = [c for c in cost.components if c.cards]
    assert discard.cards == [bolt]


def test_an_unread_quality_word_is_refused_not_ignored():
    scenario = _bullseye_board().build()
    bullseye = _ready_bullseye(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    from magic_cards_model.machines.cost import sacrifice_cost

    with pytest.raises(ValueError):
        scenario.game._choice_cost(
            "Sacrifice a creature with flying", bullseye, [ring], "alice", sacrifice_cost
        )


def _kozilek_against_a_bolt():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kozilek, the Great Distortion"],
            hand=["Island", "Lightning Bolt"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Forest"] * 3, hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    spell = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )
    kozilek = scenario.find("Kozilek, the Great Distortion", Zone.BATTLEFIELD, "alice")
    index = next(
        i
        for i, ability in enumerate(scenario.game.activated_abilities(kozilek))
        if "Discard a card" in ability.text
    )
    return scenario, kozilek, index, spell


def test_kozilek_discard_must_match_the_target_spells_mana_value():
    """CR 107.3: X is one value - the discarded card's mana value is the
    target spell's, so an Island (0) cannot counter a Bolt (1)."""
    scenario, kozilek, index, spell = _kozilek_against_a_bolt()
    island = scenario.find("Island", Zone.HAND, "alice")
    cost = scenario.game.activation_cost(
        kozilek, index, "alice", discarding=[island], targets=[spell]
    )
    (discard,) = [c for c in cost.components if c.cards]
    assert discard.requirement.why_not(island, scenario.game, "alice") is not None


def test_kozilek_discard_of_a_matching_mana_value_is_accepted():
    scenario, kozilek, index, spell = _kozilek_against_a_bolt()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    cost = scenario.game.activation_cost(
        kozilek, index, "alice", discarding=[bolt], targets=[spell]
    )
    (discard,) = [c for c in cost.components if c.cards]
    assert discard.requirement.why_not(bolt, scenario.game, "alice") is None

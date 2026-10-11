"""Statics about the abilities of cards in graveyards (EP-01 round 2, T8).

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 113.6b** - an ability that states which zones it functions in functions
  only from those zones.
- **CR 702.34a** - the graveyard half of flashback is a static ability that
  functions while the card is in a graveyard.
- **CR 702.84a** - unearth is an activated ability that functions in a graveyard.
- **CR 702.52a** - dredge is a static ability that functions in a graveyard.
- **CR 613.1f** - layer 6 adds and removes abilities.

Yixlid Jailer ("Cards in graveyards lose all abilities.") takes away every one
of those. Mishra, Tamer of Mak Fawa gives each artifact card in its controller's
graveyard unearth {1}{B}{R}.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_from
from magic_cards_model.machines.keywords import (
    off_zone_abilities,
    off_zone_activation,
    unearth_activation,
    why_cannot_dredge,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def _board(*, alice=None, bob=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **(alice or {}))
        .player("bob", **(bob or {}))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _unearth(scenario, card, *sources):
    activation = unearth_activation(scenario.game, card, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation.resolve()


# ---- Yixlid Jailer ---------------------------------------------------------


def test_flashback_casts_from_the_graveyard_without_a_jailer():
    scenario = _board(
        alice={"graveyard": ["Faithless Looting"], "battlefield": ["Mountain"] * 3},
    )
    looting = scenario.find("Faithless Looting", Zone.GRAVEYARD, "alice")
    assert why_cannot_cast_from(looting, "alice", Zone.GRAVEYARD, scenario.game) is None


def test_flashback_is_lost_under_a_jailer_of_either_player():
    scenario = _board(
        alice={"graveyard": ["Faithless Looting"], "battlefield": ["Mountain"] * 3},
        bob={"battlefield": ["Yixlid Jailer"]},
    )
    looting = scenario.find("Faithless Looting", Zone.GRAVEYARD, "alice")
    reason = why_cannot_cast_from(looting, "alice", Zone.GRAVEYARD, scenario.game)
    assert reason is not None and "Yixlid Jailer" in reason


def test_unearth_is_offered_without_a_jailer_and_lost_with_one():
    free = _board(alice={"graveyard": ["Anathemancer"]})
    leveler = free.find("Anathemancer", Zone.GRAVEYARD, "alice")
    assert [e.family for e in off_zone_abilities(leveler.card, state=leveler, game=free.game)] == [
        "unearth"
    ]

    jailed = _board(alice={"graveyard": ["Anathemancer"], "battlefield": ["Yixlid Jailer"]})
    leveler = jailed.find("Anathemancer", Zone.GRAVEYARD, "alice")
    assert off_zone_abilities(leveler.card, state=leveler, game=jailed.game) == []
    with pytest.raises(ValueError, match="Yixlid Jailer"):
        unearth_activation(jailed.game, leveler, "alice")
    with pytest.raises(ValueError, match="no activated ability"):
        off_zone_activation(jailed.game, leveler, "alice", 0)


def test_dredge_is_lost_under_a_jailer():
    free = _board(alice={"graveyard": ["Golgari Thug"], "library": ["Forest"] * 6})
    thug = free.find("Golgari Thug", Zone.GRAVEYARD, "alice")
    assert why_cannot_dredge(free.game, thug, "alice") is None

    jailed = _board(
        alice={
            "graveyard": ["Golgari Thug"],
            "library": ["Forest"] * 6,
            "battlefield": ["Yixlid Jailer"],
        }
    )
    thug = jailed.find("Golgari Thug", Zone.GRAVEYARD, "alice")
    reason = why_cannot_dredge(jailed.game, thug, "alice")
    assert reason is not None and "Yixlid Jailer" in reason


# ---- Mishra, Tamer of Mak Fawa: unearth for artifact cards -----------------


def test_an_artifact_card_in_the_graveyard_unearths_for_one_black_red():
    scenario = _board(
        alice={
            "graveyard": ["Sol Ring"],
            "battlefield": ["Mishra, Tamer of Mak Fawa", "Swamp", "Mountain", "Mountain"],
        }
    )
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    entries = off_zone_abilities(ring.card, state=ring, game=scenario.game)
    assert [entry.family for entry in entries] == ["unearth"]
    sources = scenario.untapped_sources("Swamp", "Mountain", "Mountain")
    entered = _unearth(scenario, ring, *sources)
    assert entered.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(entered).abilities


def test_a_non_artifact_card_gets_no_unearth():
    scenario = _board(
        alice={
            "graveyard": ["Grizzly Bears"],
            "battlefield": ["Mishra, Tamer of Mak Fawa"],
        }
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert off_zone_abilities(bears.card, state=bears, game=scenario.game) == []


def test_the_opponents_graveyard_gets_no_unearth():
    scenario = _board(
        alice={"battlefield": ["Mishra, Tamer of Mak Fawa"]},
        bob={"graveyard": ["Sol Ring"]},
    )
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "bob")
    assert off_zone_abilities(ring.card, state=ring, game=scenario.game) == []


def test_the_grant_needs_mishra_on_the_battlefield():
    scenario = _board(alice={"graveyard": ["Sol Ring"]})
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    assert off_zone_abilities(ring.card, state=ring, game=scenario.game) == []


def test_a_jailer_takes_the_granted_unearth_away_too():
    scenario = _board(
        alice={
            "graveyard": ["Sol Ring"],
            "battlefield": ["Mishra, Tamer of Mak Fawa"],
        },
        bob={"battlefield": ["Yixlid Jailer"]},
    )
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    assert off_zone_abilities(ring.card, state=ring, game=scenario.game) == []


# ---- Mishra's other line: Ward-Sacrifice a permanent on every permanent ----


def _bolt_at_mishras_bears(*, extra=()):
    """Alice (the opponent) bolts Bob's Grizzly Bears; Bob controls Mishra."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", *extra],
        )
        .player("bob", battlefield=["Mishra, Tamer of Mak Fawa", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])
    return scenario, bears, bolt


def test_targeting_a_permanent_mishra_protects_triggers_ward_and_paying_lets_it_through():
    scenario, bears, bolt = _bolt_at_mishras_bears(extra=["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, username="alice", source="Grizzly Bears")
    scenario.will_choose_cards(forest, username="alice", source="Grizzly Bears")

    scenario.resolve_top()  # the ward trigger

    assert forest.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.STACK
    scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD  # the Bolt resolved and killed it


def test_declining_the_sacrifice_counters_the_spell():
    scenario, bears, bolt = _bolt_at_mishras_bears(extra=["Forest"])
    scenario.will_take_the_may(False, username="alice", source="Grizzly Bears")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


# ---- Retriever Phoenix: a learn replacement that functions in the graveyard --
#
# CR 614.1a (replacement of "would"), CR 113.6b (zones an ability functions in),
# CR 701.48a (learn).


def _learner(*, alice_graveyard=(), alice_hand=("Island",), bob_battlefield=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=list(alice_graveyard),
            hand=list(alice_hand),
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _learn(scenario, who="alice"):
    from magic_cards_model.machines.effects.library import learn

    learn(scenario.game, scenario.game.player(who), "Divide by Zero", source_id=None)


def test_phoenix_in_the_graveyard_returns_instead_of_learning():
    scenario = _learner(alice_graveyard=["Retriever Phoenix"])
    scenario.will_take_the_may(True, username="alice", source="Retriever Phoenix")

    _learn(scenario)

    phoenix = scenario.find("Retriever Phoenix", Zone.BATTLEFIELD, "alice")
    assert phoenix.zone is Zone.BATTLEFIELD
    # Learn never happened: the Island is still in hand, nothing was drawn.
    assert [c.name for c in scenario.player("alice").hand] == ["Island"]
    assert len(scenario.player("alice").library) == 5


def test_declining_the_replacement_lets_learn_happen():
    scenario = _learner(alice_graveyard=["Retriever Phoenix"])
    scenario.will_take_the_may(False, username="alice", source="Retriever Phoenix")
    scenario.will_take_the_may(True, username="alice", source="Divide by Zero")
    scenario.will_discard(scenario.find("Island", Zone.HAND, "alice"), username="alice")

    _learn(scenario)

    assert scenario.find("Retriever Phoenix", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 4  # discarded the Island, drew a Forest


def test_phoenix_outside_the_graveyard_does_not_replace_learn():
    scenario = _learner(alice_graveyard=[], alice_hand=("Retriever Phoenix",))
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")

    _learn(scenario)

    questions = [q.source for q in scenario.questions_asked()]
    assert "Retriever Phoenix" not in questions


def test_an_opponents_phoenix_does_not_replace_my_learn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Island"], library=["Forest"] * 5)
        .player("bob", graveyard=["Retriever Phoenix"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")

    _learn(scenario)

    assert "Retriever Phoenix" not in [q.source for q in scenario.questions_asked()]
    assert scenario.find("Retriever Phoenix", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


def test_a_jailer_takes_the_phoenix_replacement_away():
    scenario = _learner(alice_graveyard=["Retriever Phoenix"], bob_battlefield=["Yixlid Jailer"])
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")

    _learn(scenario)

    assert "Retriever Phoenix" not in [q.source for q in scenario.questions_asked()]

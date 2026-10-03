"""R0b proofs: CR 601.2b's "[cost] or [cost]" mandatory additional costs.

Bitter Triumph ("discard a card or pay 3 life"), Deadly Precision ("pay {4} or
sacrifice an artifact or creature"), Stir Up Trouble ("sacrifice an artifact
or creature or pay {4}") and Dusk Rose Reliquary (a plain mandatory sacrifice
with ward {2} and an exile-until-leaves enters trigger). Bitter Triumph and
Deadly Precision were `handled` by the sweep yet uncastable: the "or" reader
only knew "[cost] or pay [mana]". `or_additional_cost_halves` now reads the
mana-first and life-fallback spellings too, and Dusk Mangler's three-way "A,
B, or pay 4 life" (also uncastable before) goes through the same reader.

Every CR number below was looked up with `mise run rules:find`:

- **CR 601.2b** - the caster announces which costs, and with what, as the spell
  is cast.
- **CR 601.2f / 601.2h** - the total cost is determined, then paid.
- **CR 118.3** - a cost can't be paid without the resources for it.
- **CR 119.4** - life may be paid only with a life total at least that high.
- **CR 118.8a** - an additional cost is paid on top of the mana cost.
- **CR 702.21a** - ward: counter the spell unless its controller pays the cost.
- **CR 610.3** - an effect that exiles "until" a permanent leaves returns it.
"""

import pytest

from magic_cards_model.machines import Step, legal_actions
from magic_cards_model.models import ActionKind, Affordability, Zone
from tests.scenarios.harness import Scenario


def _start(scenario: Scenario):
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def _cast_row(scenario, name):
    card = scenario.find(name, Zone.HAND, "alice")
    (row,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == card.id and action.kind is ActionKind.CAST
    ]
    return row


# -- Bitter Triumph: discard a card OR pay 3 life ------------------------------------


def _triumph_board(hand=(), *, bob=("Grizzly Bears",)):
    return _start(
        Scenario()
        .player(
            "alice",
            hand=["Bitter Triumph", *hand],
            battlefield=["Swamp", "Swamp"],
        )
        .player("bob", battlefield=list(bob))
    )


def test_bitter_triumph_discarding_a_card_pays_no_life():
    scenario = _triumph_board(["Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    island = scenario.find("Island", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[bears], discarding=[island])

    assert island.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20
    assert bears.zone is Zone.GRAVEYARD


def test_bitter_triumph_paying_three_life_keeps_the_hand():
    scenario = _triumph_board(["Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    island = scenario.find("Island", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[bears])

    assert island.zone is Zone.HAND
    assert scenario.player("alice").life == 17
    assert bears.zone is Zone.GRAVEYARD


def test_bitter_triumph_destroys_a_planeswalker_too():
    scenario = _triumph_board(bob=["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[liliana])

    assert liliana.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17


def test_bitter_triumph_with_no_other_card_and_two_life_cannot_be_paid():
    """CR 118.3 / CR 119.4: the spell is on the stack by CR 601.2a, so the hand
    is empty, and 2 life is less than 3. Neither half is payable."""
    scenario = _triumph_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.player("alice").life = 2
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 2


def test_bitter_triumph_at_two_life_can_still_discard():
    scenario = _triumph_board(["Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    island = scenario.find("Island", Zone.HAND, "alice")
    scenario.player("alice").life = 2
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[bears], discarding=[island])

    assert island.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 2
    assert bears.zone is Zone.GRAVEYARD


def test_bitter_triumph_with_four_life_pays_down_to_one():
    scenario = _triumph_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.player("alice").life = 4
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Bitter Triumph", *sources, targets=[bears])

    assert scenario.player("alice").life == 1
    assert bears.zone is Zone.GRAVEYARD


def test_bitter_triumph_affordability_counts_either_half():
    """`legal_actions` tells the seat the cast is payable when the life half
    is, or when only the discard half is - and not when neither is."""
    rich = _triumph_board()
    assert _cast_row(rich, "Bitter Triumph").affordable is Affordability.YES

    discard_only = _triumph_board(["Island"])
    discard_only.player("alice").life = 2
    assert _cast_row(discard_only, "Bitter Triumph").affordable is Affordability.YES

    neither = _triumph_board()
    neither.player("alice").life = 2
    assert _cast_row(neither, "Bitter Triumph").affordable is Affordability.NO


# -- Deadly Precision: pay {4} OR sacrifice an artifact or creature -------------------


def _precision_board(*, battlefield, hand=("Deadly Precision",)):
    return _start(
        Scenario()
        .player("alice", hand=list(hand), battlefield=battlefield)
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_deadly_precision_paying_four_more_sacrifices_nothing():
    scenario = _precision_board(battlefield=["Swamp"] * 5 + ["Memnite"])
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "alice")
    sources = scenario.untapped_sources(*(["Swamp"] * 5), username="alice")

    scenario.cast_and_resolve("Deadly Precision", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.BATTLEFIELD
    assert all(source.tapped for source in sources)


def test_deadly_precision_sacrificing_a_creature_costs_only_the_black():
    scenario = _precision_board(battlefield=["Swamp", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "alice")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.cast_and_resolve("Deadly Precision", swamp, targets=[bears], sacrificing=[memnite])

    assert memnite.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_deadly_precision_sacrificing_a_noncreature_artifact_also_works():
    scenario = _precision_board(battlefield=["Swamp", "Mind Stone"])
    bears = scenario.creature("Grizzly Bears", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.cast_and_resolve("Deadly Precision", swamp, targets=[bears], sacrificing=[stone])

    assert stone.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_deadly_precision_cannot_sacrifice_a_land():
    scenario = _precision_board(battlefield=["Swamp", "Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Deadly Precision", swamp, targets=[bears], sacrificing=[island])

    assert island.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD


def test_deadly_precision_with_neither_four_extra_mana_nor_a_sacrifice_is_refused():
    scenario = _precision_board(battlefield=["Swamp"])
    bears = scenario.creature("Grizzly Bears", "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Deadly Precision", swamp, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD


def test_deadly_precision_is_affordable_by_either_half():
    sacrifice_only = _precision_board(battlefield=["Swamp", "Memnite"])
    assert _cast_row(sacrifice_only, "Deadly Precision").affordable is Affordability.YES

    mana_only = _precision_board(battlefield=["Swamp"] * 5)
    assert _cast_row(mana_only, "Deadly Precision").affordable is Affordability.YES

    neither = _precision_board(battlefield=["Swamp"])
    assert _cast_row(neither, "Deadly Precision").affordable is not Affordability.YES


# -- Stir Up Trouble: sacrifice an artifact or creature OR pay {4} --------------------


def test_stir_up_trouble_sacrificing_an_artifact_costs_only_the_black():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Stir Up Trouble"], battlefield=["Swamp", "Mind Stone"])
        .player("bob", battlefield=["Grizzly Bears"])
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.cast_and_resolve("Stir Up Trouble", swamp, targets=[bears], sacrificing=[stone])

    assert stone.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_stir_up_trouble_paying_four_more_with_nothing_to_sacrifice():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Stir Up Trouble"], battlefield=["Swamp"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 5), username="alice")

    scenario.cast_and_resolve("Stir Up Trouble", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_stir_up_trouble_cannot_destroy_a_noncreature_target():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Stir Up Trouble"], battlefield=["Swamp"] * 5)
        .player("bob", battlefield=["Mind Stone"])
    )
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError):
        scenario.cast("Stir Up Trouble", targets=[stone])


# -- Dusk Rose Reliquary -------------------------------------------------------------


def _reliquary_board(*, alice, bob=("Grizzly Bears",), bob_hand=()):
    return _start(
        Scenario()
        .player("alice", hand=["Dusk Rose Reliquary"], battlefield=["Plains", *alice])
        .player("bob", hand=list(bob_hand), battlefield=list(bob))
    )


def _land_reliquary(scenario, sacrificed, target):
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.choose_trigger_targets("Dusk Rose Reliquary", [target])
    reliquary = scenario.cast_and_resolve("Dusk Rose Reliquary", plains, sacrificing=[sacrificed])
    scenario.pass_until_resolved()  # the enters trigger
    return reliquary


def test_reliquary_sacrifices_a_creature_and_exiles_their_creature():
    scenario = _reliquary_board(alice=["Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    reliquary = _land_reliquary(scenario, memnite, bears)

    assert memnite.zone is Zone.GRAVEYARD
    assert reliquary.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.EXILE


def test_reliquary_can_sacrifice_an_artifact_and_exile_their_artifact():
    scenario = _reliquary_board(alice=["Mind Stone"], bob=["Sol Ring"])
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _land_reliquary(scenario, stone, ring)

    assert stone.zone is Zone.GRAVEYARD
    assert ring.zone is Zone.EXILE


def test_reliquary_cannot_be_cast_without_a_sacrifice():
    """CR 118.3: the sacrifice is mandatory, so with nothing nominated the cast
    is illegal and the card stays in hand."""
    scenario = _reliquary_board(alice=["Memnite"])
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Dusk Rose Reliquary", plains)

    assert scenario.creature("Memnite", "alice").zone is Zone.BATTLEFIELD


def test_reliquary_cannot_sacrifice_a_land():
    scenario = _reliquary_board(alice=["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Dusk Rose Reliquary", plains, sacrificing=[forest])

    assert forest.zone is Zone.BATTLEFIELD


def test_reliquary_leaving_the_battlefield_returns_the_exiled_permanent():
    """CR 610.3: the exile lasts only until the Reliquary leaves."""
    scenario = _reliquary_board(alice=["Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    reliquary = _land_reliquary(scenario, memnite, bears)
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(reliquary)
    scenario.pass_until_resolved()

    assert reliquary.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "bob"


def test_reliquary_has_ward_two_so_an_unpaid_ward_counters_the_spell():
    """CR 702.21a: bob's Smash to Smithereens targeting the Reliquary is
    countered unless he pays {2}; with nothing left to pay it, it is."""
    scenario = _reliquary_board(
        alice=["Memnite"],
        bob=["Grizzly Bears", "Mountain", "Mountain"],
        bob_hand=["Smash to Smithereens"],
    )
    memnite = scenario.creature("Memnite", "alice")
    reliquary = _land_reliquary(scenario, memnite, scenario.creature("Grizzly Bears", "bob"))
    scenario.pass_priority("alice")
    scenario.will_pay_the_mana_cost(False, username="bob")

    smash = scenario.cast_onto_stack(
        "Smash to Smithereens",
        *scenario.untapped_sources("Mountain", "Mountain", username="bob"),
        username="bob",
        targets=[reliquary],
    )
    assert scenario.stack_names()[-1] == "Dusk Rose Reliquary's triggered ability"
    scenario.resolve_top()  # the ward trigger

    assert smash.zone is Zone.GRAVEYARD
    assert reliquary.zone is Zone.BATTLEFIELD


# -- Second printings: the same readers on cards that are in no deck -------------------
#
# Annihilating Glare ("pay {4} or sacrifice an artifact or creature.") is
# Deadly Precision's spelling; Dusk Mangler ("sacrifice a creature, discard a
# card, or pay 4 life.") is Bitter Triumph's life fallback with three ways to
# pay instead of two. Both are legal in Modern and Pioneer.


def test_annihilating_glare_sacrificing_costs_only_the_black_and_hits_a_planeswalker():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Annihilating Glare"], battlefield=["Swamp", "Memnite"])
        .player("bob", battlefield=["Liliana of the Veil"])
    )
    memnite = scenario.creature("Memnite", "alice")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.cast_and_resolve("Annihilating Glare", swamp, targets=[liliana], sacrificing=[memnite])

    assert memnite.zone is Zone.GRAVEYARD
    assert liliana.zone is Zone.GRAVEYARD


def test_annihilating_glare_paying_four_more_sacrifices_nothing():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Annihilating Glare"], battlefield=["Swamp"] * 5 + ["Memnite"])
        .player("bob", battlefield=["Grizzly Bears"])
    )
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 5), username="alice")

    scenario.cast_and_resolve("Annihilating Glare", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.BATTLEFIELD


def _mangler_board(*, hand=(), battlefield=()):
    return _start(
        Scenario()
        .player(
            "alice",
            hand=["Dusk Mangler", *hand],
            battlefield=["Swamp"] * 7 + list(battlefield),
        )
        .player("bob", hand=["Island"], battlefield=["Grizzly Bears"])
    )


def _mangler_sources(scenario):
    return scenario.untapped_sources(*(["Swamp"] * 7), username="alice")


def test_dusk_mangler_defaults_to_paying_four_life():
    scenario = _mangler_board(hand=["Island"], battlefield=["Memnite"])
    sources = _mangler_sources(scenario)

    mangler = scenario.cast_and_resolve("Dusk Mangler", *sources)

    assert scenario.player("alice").life == 16
    assert scenario.find("Island", Zone.HAND, "alice").zone is Zone.HAND
    assert scenario.creature("Memnite", "alice").zone is Zone.BATTLEFIELD
    assert mangler.zone is Zone.BATTLEFIELD


def test_dusk_mangler_sacrificing_a_creature_pays_no_life():
    scenario = _mangler_board(battlefield=["Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    sources = _mangler_sources(scenario)

    scenario.cast_and_resolve("Dusk Mangler", *sources, sacrificing=[memnite])

    assert memnite.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_dusk_mangler_discarding_a_card_pays_no_life():
    scenario = _mangler_board(hand=["Island"])
    island = scenario.find("Island", Zone.HAND, "alice")
    sources = _mangler_sources(scenario)

    scenario.cast_and_resolve("Dusk Mangler", *sources, discarding=[island])

    assert island.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_dusk_mangler_enters_trigger_hits_the_opponent():
    scenario = _mangler_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    island = scenario.find("Island", Zone.HAND, "bob")
    sources = _mangler_sources(scenario)

    scenario.cast_and_resolve("Dusk Mangler", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert island.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16


def test_dusk_mangler_with_too_little_life_and_nothing_else_cannot_be_cast():
    scenario = _mangler_board()
    scenario.player("alice").life = 3
    sources = _mangler_sources(scenario)

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Dusk Mangler", *sources)

    assert scenario.player("alice").life == 3


def test_the_or_cost_reader_splits_every_printed_spelling_into_its_halves():
    from magic_cards_model.machines.casting import (
        or_additional_cost_alternatives,
        or_additional_cost_halves,
    )

    # "[cost] or pay [mana]": the mana is the default half.
    assert or_additional_cost_halves("sacrifice an artifact or creature or pay {4}") == (
        "sacrifice an artifact or creature",
        "{4}",
    )
    # "pay [mana] or [cost]": same halves, mana written first.
    assert or_additional_cost_halves("pay {4} or sacrifice an artifact or creature") == (
        "sacrifice an artifact or creature",
        "{4}",
    )
    # "[cost] or pay N life": the life is the default half.
    assert or_additional_cost_halves("discard a card or pay 3 life") == (
        "discard a card",
        "pay 3 life",
    )
    # A comma list inside the non-default half is several alternatives.
    assert or_additional_cost_alternatives(
        "sacrifice a creature, discard a card, or pay 4 life"
    ) == [
        "sacrifice a creature",
        "discard a card",
        "pay 4 life",
    ]
    # A plain cost is not an "or" cost, and neither is an "or" inside one noun.
    assert or_additional_cost_halves("sacrifice a creature") is None
    assert or_additional_cost_halves("sacrifice an artifact or creature") is None

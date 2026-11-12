"""Scenario: "Choose target `<spell>`. That player may exile it. If they don't,
`<otherwise>`." (T-136 b1) - Brazen Bluff.

The player who gets the choice is the *controller of the target* ("that
player", CR 608.2d), not the controller of the resolving spell: the opponent
of the Bluff's caster decides whether to give up their spell or let the caster
cast a free noncreature spell from hand. `merges._merge_choose_target_then_
controller_may_exile_it_else_clauses` reads the three sentences as one
instruction; "exile it" is the ordinary "exile target `<X>`" clause (a spell
leaves the stack by `Game.exile_from_stack`, CR 701.13a, never countered) and
the otherwise branch is whatever clause reader reads it.

No other printing has this shape (Scryfall checked 2026-11-12, see MEMORY.md),
so the generality shown here is in the board: the target spell's type, the free
spell's type and what the caster holds, who declines, and the target leaving.

Every CR number was looked up with `mise run rules:find`:

- **CR 608.2d** - an optional choice is made by the player the text names.
- **CR 608.2b** - a target that is no longer legal is not acted on.
- **CR 701.13a** - to exile an object is to put it into the exile zone.
- **CR 118.9** - casting without paying the mana cost is an alternative cost.
- **CR 608.2g** - a spell cast during resolution is cast as the effect says.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone

from .harness import PlayedScenario, Scenario

_ALICE_LANDS = ["Mountain", "Island", "Island", "Forest", "Forest"]


def _bluff_board(bob_hand: list[str]) -> PlayedScenario:
    """Alice (active) holds a Bolt, a Divination and Bears; Bob holds Brazen
    Bluff and `bob_hand`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Divination", "Grizzly Bears"],
            battlefield=_ALICE_LANDS,
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            hand=["Brazen Bluff", *bob_hand],
            battlefield=["Mountain", "Mountain"],
            library=["Island"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


_PAYMENT = {
    "Lightning Bolt": ("Mountain",),
    "Divination": ("Island", "Island", "Forest"),
    "Grizzly Bears": ("Forest", "Forest"),
}


def _alice_casts(scenario: PlayedScenario, name: str) -> CardState:
    sources = scenario.untapped_sources(*_PAYMENT[name], username="alice")
    targets = ["bob"] if name == "Lightning Bolt" else []
    return scenario.cast_onto_stack(name, *sources, username="alice", targets=targets)


def _bob_bluffs(scenario: PlayedScenario, spell: CardState) -> CardState:
    scenario.pass_priority("alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    return scenario.cast_onto_stack("Brazen Bluff", *sources, username="bob", targets=[spell])


def _bolt_then_bluff(scenario: PlayedScenario) -> CardState:
    bolt = _alice_casts(scenario, "Lightning Bolt")
    _bob_bluffs(scenario, bolt)
    return bolt


def _resolve_all(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_the_opponent_exiles_the_spell_and_the_caster_casts_nothing():
    scenario = _bluff_board(["Divination"])
    bolt = _bolt_then_bluff(scenario)
    scenario.will_take_the_may(True, username="alice", source="Brazen Bluff")

    scenario.resolve_top()  # Brazen Bluff

    assert bolt.zone is Zone.EXILE
    assert scenario.find("Divination", Zone.HAND, "bob").zone is Zone.HAND
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20  # the Bolt never resolved


def test_the_opponent_keeps_the_spell_and_the_caster_casts_a_free_noncreature_spell():
    scenario = _bluff_board(["Divination", "Grizzly Bears"])
    bolt = _bolt_then_bluff(scenario)
    scenario.will_take_the_may(False, username="alice", source="Brazen Bluff")
    scenario.will_take_the_may(True, username="bob", source="Brazen Bluff")
    divination = scenario.find("Divination", Zone.HAND, "bob")

    scenario.resolve_top()  # Brazen Bluff

    assert bolt.zone is Zone.STACK  # not exiled
    assert divination.zone is Zone.STACK  # cast free, above the Bolt
    _resolve_all(scenario)
    assert divination.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 1 + 2  # Bears, plus two drawn
    assert scenario.player("bob").life == 17  # the Bolt resolved


def test_only_a_noncreature_spell_may_be_cast_free():
    """Bob holds only a creature card: the free cast has nothing legal to
    offer, so nothing is cast and no free-cast question is asked of Bob."""
    scenario = _bluff_board(["Grizzly Bears"])
    _bolt_then_bluff(scenario)
    scenario.will_take_the_may(False, username="alice", source="Brazen Bluff")

    scenario.resolve_top()

    assert scenario.find("Grizzly Bears", Zone.HAND, "bob").zone is Zone.HAND
    asked = [q for q in scenario.questions_asked() if q.source == "Brazen Bluff"]
    assert [q.player for q in asked] == ["alice"]


def test_the_caster_may_decline_the_free_spell():
    scenario = _bluff_board(["Divination"])
    bolt = _bolt_then_bluff(scenario)
    scenario.will_take_the_may(False, username="alice", source="Brazen Bluff")
    scenario.will_take_the_may(False, username="bob", source="Brazen Bluff")

    scenario.resolve_top()

    assert bolt.zone is Zone.STACK
    assert scenario.find("Divination", Zone.HAND, "bob").zone is Zone.HAND


def test_the_choice_is_put_to_the_targets_controller_not_the_bluffs():
    scenario = _bluff_board(["Divination"])
    _bolt_then_bluff(scenario)
    scenario.will_take_the_may(True, username="alice", source="Brazen Bluff")

    scenario.resolve_top()

    asked = [q for q in scenario.questions_asked() if q.source == "Brazen Bluff"]
    assert [q.player for q in asked] == ["alice"]


def test_a_sorcery_is_a_legal_target_and_is_exiled_too():
    scenario = _bluff_board(["Divination"])
    divination = _alice_casts(scenario, "Divination")
    _bob_bluffs(scenario, divination)
    scenario.will_take_the_may(True, username="alice", source="Brazen Bluff")

    scenario.resolve_top()
    _resolve_all(scenario)

    assert divination.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == 2  # nothing was drawn


def test_a_creature_spell_is_not_a_legal_target():
    scenario = _bluff_board([])
    bears = _alice_casts(scenario, "Grizzly Bears")
    scenario.pass_priority("alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Brazen Bluff", *sources, username="bob", targets=[bears])


def test_a_spell_its_own_caster_controls_is_not_a_legal_target():
    """ "an opponent controls": Bob may not aim the Bluff at his own spell."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"])
        .player("bob", hand=["Brazen Bluff", "Lightning Bolt"], battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")  # Bob is not the active player; the Bolt is an instant
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob")[:1],
        username="bob",
        targets=["alice"],
    )
    sources = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Brazen Bluff", *sources, username="bob", targets=[bolt])


def test_a_target_that_is_gone_asks_nobody_and_casts_nothing():
    """CR 608.2b: the Bolt is countered first, so the Bluff's only target is
    illegal and the whole spell does nothing - not even the free cast the "if
    they don't" branch would have given."""
    scenario = _bluff_board(["Divination"])
    bolt = _bolt_then_bluff(scenario)
    scenario.game.counter(bolt)

    scenario.resolve_top()

    assert scenario.find("Divination", Zone.HAND, "bob").zone is Zone.HAND
    assert [q for q in scenario.questions_asked() if q.source == "Brazen Bluff"] == []

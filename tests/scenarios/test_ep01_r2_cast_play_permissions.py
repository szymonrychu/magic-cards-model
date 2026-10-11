"""EP-01 round 2, task T7: static cast and play permissions and prohibitions
(CR 305.2, 305.1, 601.3, 611.3d, 701.20).

    Ghirapur Orrery / Rites of Flourishing - Each player may play an additional land.
    Aggressive Mining       - You can't play lands.
    Experimental Frenzy     - You can't play lands or cast spells from your hand.
    Lens of Clarity         - look at the top card and at face-down creatures you don't control.

The pool carries no second printing of any of these four shapes (the two
"each player" lands are the only ones, and the two prohibitions are the only
"you can't play lands" lines), so the listed cards are the proof.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_restriction
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str, containing: str) -> None:
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes, f"{name}: no clause containing {containing!r}"
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _offered(scenario, card_state, kind, username="alice") -> bool:
    return any(
        action.kind is kind and getattr(action, "card_id", None) == card_state.id
        for action in legal_actions(scenario.game, username)
    )


# -- Each player may play an additional land ------------------------------


@pytest.mark.parametrize("source", ["Ghirapur Orrery", "Rites of Flourishing"])
def test_each_player_may_play_an_additional_land(source):
    scenario = _main(
        alice={"hand": ["Forest", "Forest", "Forest"], "battlefield": [source]},
        bob={"library": ["Island"] * 4},
    )
    assert scenario.game.land_allowance("alice") == 2
    assert scenario.game.land_allowance("bob") == 2, (
        "CR 611.3d: each player, not only the controller"
    )
    scenario.play_land("Forest")
    scenario.play_land("Forest")
    with pytest.raises(ValueError, match="already used"):
        scenario.play_land("Forest")


@pytest.mark.parametrize("source", ["Ghirapur Orrery", "Rites of Flourishing"])
def test_an_opponents_each_player_grant_reaches_me_too(source):
    scenario = _main(
        alice={"hand": ["Forest", "Forest"]},
        bob={"battlefield": [source]},
    )
    assert scenario.game.land_allowance("alice") == 2
    scenario.play_land("Forest")
    scenario.play_land("Forest")


def test_without_the_grant_a_second_land_is_refused_and_the_grant_leaves_with_its_source():
    scenario = _main(
        alice={"hand": ["Forest", "Forest"], "battlefield": ["Ghirapur Orrery"]},
        bob={},
    )
    assert scenario.game.land_allowance("alice") == 2
    orrery = scenario.find("Ghirapur Orrery", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(orrery)
    assert scenario.game.land_allowance("alice") == 1
    scenario.play_land("Forest")
    with pytest.raises(ValueError, match="already used"):
        scenario.play_land("Forest")


def test_the_each_player_grants_stack_with_a_personal_one():
    scenario = _main(
        alice={
            "battlefield": ["Ghirapur Orrery", "Rites of Flourishing", "Azusa, Lost but Seeking"]
        },
        bob={},
    )
    assert scenario.game.land_allowance("alice") == 5
    assert scenario.game.land_allowance("bob") == 3


def test_each_player_land_grants_are_credited():
    _handled("Ghirapur Orrery", "Each player may play an additional land")
    _handled("Rites of Flourishing", "Each player may play an additional land")


# -- You can't play lands (Aggressive Mining) -----------------------------


def test_aggressive_mining_refuses_every_land_play_of_its_controller():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Aggressive Mining"]},
        bob={},
    )
    land = scenario.find("Forest", Zone.HAND, "alice")
    reason = scenario.game.why_cannot_play_land("alice")
    assert reason is not None and "Aggressive Mining" in reason
    with pytest.raises(ValueError, match="Aggressive Mining"):
        scenario.play_land("Forest")
    assert land.zone is Zone.HAND
    assert not _offered(scenario, land, ActionKind.PLAY_LAND)


def test_aggressive_mining_does_not_stop_an_opponents_land_play():
    scenario = _main(
        alice={"hand": ["Forest"]},
        bob={"battlefield": ["Aggressive Mining"]},
    )
    assert scenario.game.why_cannot_play_land("alice") is None
    scenario.play_land("Forest")


def test_aggressive_mining_still_lets_a_spell_put_a_land_onto_the_battlefield():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Aggressive Mining"]},
        bob={},
    )
    land = scenario.put_onto_battlefield("Forest")
    assert land.zone is Zone.BATTLEFIELD, (
        "CR 305.4: putting a land onto the battlefield is not playing it"
    )


def test_aggressive_mining_is_credited():
    _handled("Aggressive Mining", "You can't play lands")


# -- Experimental Frenzy: no lands or spells from hand ---------------------


def _frenzy():
    return _main(
        alice={
            "hand": ["Forest", "Lightning Bolt"],
            "battlefield": ["Experimental Frenzy", "Mountain"],
            "library": ["Mountain", "Lightning Bolt"],
        },
        bob={},
    )


def test_frenzy_refuses_a_land_and_a_spell_from_hand():
    scenario = _frenzy()
    land = scenario.find("Forest", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="Experimental Frenzy"):
        scenario.play_land("Forest")
    assert not _offered(scenario, land, ActionKind.PLAY_LAND)
    reason = why_cannot_cast_restriction(bolt, "alice", scenario.game)
    assert reason is not None and "Experimental Frenzy" in reason
    assert not _offered(scenario, bolt, ActionKind.CAST)


def test_frenzy_still_allows_the_top_of_the_library():
    scenario = _frenzy()
    top = scenario.player("alice").library[0]
    assert _offered(scenario, top, ActionKind.PLAY_LAND)
    scenario.play_land("Mountain", from_zone=Zone.LIBRARY)
    assert top.zone is Zone.BATTLEFIELD


def test_frenzy_allows_casting_a_spell_from_the_top_of_the_library():
    scenario = _main(
        alice={
            "hand": ["Lightning Bolt"],
            "battlefield": ["Experimental Frenzy", "Mountain"],
            "library": ["Lightning Bolt", "Mountain"],
        },
        bob={},
    )
    top = scenario.player("alice").library[0]
    assert why_cannot_cast_restriction(top, "alice", scenario.game) is None
    assert _offered(scenario, top, ActionKind.CAST)


def test_frenzy_does_not_bind_an_opponent_and_ends_when_it_leaves():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Experimental Frenzy", "Mountain"]},
        bob={"hand": ["Lightning Bolt"]},
    )
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is None
    frenzy = scenario.find("Experimental Frenzy", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(frenzy)
    scenario.play_land("Forest")


def test_frenzy_can_destroy_itself_for_3r():
    scenario = _main(
        alice={
            "battlefield": ["Experimental Frenzy", "Mountain", "Mountain", "Mountain", "Mountain"]
        },
        bob={},
    )
    frenzy = scenario.find("Experimental Frenzy", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        frenzy, *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"), index=0
    )
    scenario.pass_until_resolved()
    assert frenzy.zone is Zone.GRAVEYARD


def test_frenzy_is_credited():
    _handled("Experimental Frenzy", "You can't play lands or cast spells from your hand")
    _handled("Experimental Frenzy", "Destroy this enchantment")

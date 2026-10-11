"""Static player-action prohibitions (EP-01 round 2, T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 101.2** - "When a rule or effect allows or directs something to happen,
  and another effect states that it can't happen, the 'can't' effect takes
  precedence."
- **CR 701.21a** - sacrificing a permanent; **CR 119.4** - paying life.
- **CR 701.23a** - searching a zone; **CR 701.49a** - venturing into the dungeon.

Printings: Angel of Jubilation (no life, no creature sacrifice to cast or
activate), Karn's Sylex (no life), Mindlock Orb and Leonin Arbiter (no library
searches, the Arbiter with a {2} release), Sigarda, Host of Herons and Tajuru
Preserver (opponents' spells and abilities can't make me sacrifice) and
Keen-Eared Sentry (an opponent ventures once each turn).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.dungeon import venture
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), bob_hand=(), library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=list(library or ["Plains"] * 8),
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# ---- paying life ---------------------------------------------------------------


def test_angel_of_jubilation_stops_a_phyrexian_symbol_being_paid_with_life():
    scenario = _board(["Angel of Jubilation", "Grizzly Bears"], hand=["Mutagenic Growth"])
    with pytest.raises(ValueError, match="CR 101.2"):
        scenario.cast_onto_stack(
            "Mutagenic Growth",
            username="alice",
            targets=[scenario.creature("Grizzly Bears", "alice")],
        )
    assert scenario.game.player("alice").life == 20


def test_mutagenic_growth_is_castable_for_life_without_the_prohibition():
    scenario = _board(["Grizzly Bears"], hand=["Mutagenic Growth"])
    life = scenario.game.player("alice").life
    scenario.cast_onto_stack(
        "Mutagenic Growth", username="alice", targets=[scenario.creature("Grizzly Bears", "alice")]
    )
    assert scenario.game.player("alice").life == life - 2


def test_karns_sylex_stops_paying_life_for_either_player():
    scenario = _board(["Swamp", "Grizzly Bears"], bob=["Karn's Sylex"], hand=["Dismember"])
    with pytest.raises(ValueError, match="CR 101.2"):
        scenario.cast_onto_stack(
            "Dismember",
            *scenario.untapped_sources("Swamp"),
            username="alice",
            targets=[scenario.creature("Grizzly Bears", "alice")],
        )


def test_paying_mana_instead_of_life_is_still_fine_under_karns_sylex():
    scenario = _board(
        ["Swamp", "Swamp", "Swamp", "Grizzly Bears"], bob=["Karn's Sylex"], hand=["Dismember"]
    )
    scenario.cast_onto_stack(
        "Dismember",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        username="alice",
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    assert scenario.game.player("alice").life == 20


# ---- sacrificing creatures as a cost -------------------------------------------


def test_angel_of_jubilation_stops_sacrificing_a_creature_to_activate():
    scenario = _board(["Angel of Jubilation", "Goblin Bombardment", "Grizzly Bears"])
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="CR 101.2"):
        scenario.activate(bombardment, sacrificing=[bears], targets=["bob"])
    assert bears.zone is Zone.BATTLEFIELD


def test_goblin_bombardment_works_without_angel_of_jubilation():
    scenario = _board(["Goblin Bombardment", "Grizzly Bears"])
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(bombardment, sacrificing=[bears], targets=["bob"])
    assert bears.zone is Zone.GRAVEYARD


# ---- searching libraries -------------------------------------------------------


def test_mindlock_orb_stops_a_library_search_and_the_shuffle():
    scenario = _board(
        ["Mindlock Orb", "Swamp", "Swamp"],
        hand=["Demonic Tutor"],
        library=["Dark Ritual", "Plains", "Plains"],
    )
    library_before = [c.id for c in scenario.game.player("alice").library]
    scenario.cast_and_resolve("Demonic Tutor", *scenario.untapped_sources("Swamp", "Swamp"))
    assert [c.id for c in scenario.game.player("alice").library] == library_before
    assert not [c for c in scenario.game.player("alice").hand if c.name == "Dark Ritual"]


def test_demonic_tutor_finds_without_mindlock_orb():
    scenario = _board(
        ["Swamp", "Swamp"], hand=["Demonic Tutor"], library=["Dark Ritual", "Plains", "Plains"]
    )
    scenario.cast_and_resolve("Demonic Tutor", *scenario.untapped_sources("Swamp", "Swamp"))
    assert [c for c in scenario.game.player("alice").hand if c.name == "Dark Ritual"]


def test_leonin_arbiter_lets_the_searcher_pay_two_to_ignore_it_this_turn():
    scenario = _board(
        ["Leonin Arbiter", "Swamp", "Swamp", "Mountain", "Mountain"],
        hand=["Demonic Tutor"],
        library=["Dark Ritual", "Plains", "Plains"],
    )
    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.cast_and_resolve("Demonic Tutor", *scenario.untapped_sources("Swamp", "Swamp"))
    assert [c for c in scenario.game.player("alice").hand if c.name == "Dark Ritual"]
    assert "alice" in scenario.game.turn_facts["ignores_search_prohibition"]


def test_leonin_arbiter_still_blocks_when_nobody_pays():
    scenario = _board(
        ["Leonin Arbiter", "Swamp", "Swamp"],
        hand=["Demonic Tutor"],
        library=["Dark Ritual", "Plains", "Plains"],
    )
    scenario.will_pay_the_mana_cost(False, username="alice")
    scenario.will_pay_the_mana_cost(False, username="bob")
    scenario.cast_and_resolve("Demonic Tutor", *scenario.untapped_sources("Swamp", "Swamp"))
    assert not [c for c in scenario.game.player("alice").hand if c.name == "Dark Ritual"]


# ---- opponents can't cause me to sacrifice -------------------------------------


def _edict(scenario, *, target):
    scenario.cast_and_resolve(
        "Diabolic Edict", *scenario.untapped_sources("Swamp", "Swamp"), targets=[target]
    )


def test_sigarda_stops_an_opponents_edict():
    scenario = _board(
        ["Swamp", "Swamp"],
        hand=["Diabolic Edict"],
        bob=["Sigarda, Host of Herons", "Grizzly Bears"],
    )
    _edict(scenario, target="bob")
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD
    assert scenario.creature("Sigarda, Host of Herons", "bob").zone is Zone.BATTLEFIELD


def test_tajuru_preserver_stops_an_opponents_edict_too():
    scenario = _board(["Swamp", "Swamp"], hand=["Diabolic Edict"], bob=["Tajuru Preserver"])
    _edict(scenario, target="bob")
    assert scenario.creature("Tajuru Preserver", "bob").zone is Zone.BATTLEFIELD


def test_an_edict_still_works_against_a_player_without_the_protection():
    scenario = _board(["Swamp", "Swamp"], hand=["Diabolic Edict"], bob=["Grizzly Bears"])
    _edict(scenario, target="bob")
    assert not [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]


def test_my_own_edict_on_myself_is_not_stopped_by_my_sigarda():
    scenario = _board(
        ["Sigarda, Host of Herons", "Grizzly Bears", "Swamp", "Swamp"], hand=["Diabolic Edict"]
    )
    _edict(scenario, target="alice")
    dead = [
        c
        for c in scenario.game.player("alice").graveyard
        if c.name in ("Grizzly Bears", "Sigarda, Host of Herons")
    ]
    assert len(dead) == 1


# ---- venturing -----------------------------------------------------------------


def test_keen_eared_sentry_limits_an_opponents_second_venture():
    scenario = _board(["Keen-Eared Sentry"])
    scenario.will_choose_mode("Tomb of Annihilation", username="bob")
    venture(scenario.game, "bob", source_name="test")
    room = next(
        c for c in scenario.game.shared_zones[Zone.COMMAND] if c.owner == "bob"
    ).venture_room
    venture(scenario.game, "bob", source_name="test")
    after = next(
        c for c in scenario.game.shared_zones[Zone.COMMAND] if c.owner == "bob"
    ).venture_room
    assert after == room


def test_keen_eared_sentry_does_not_limit_its_controller():
    scenario = _board(["Keen-Eared Sentry"])
    scenario.will_choose_mode("Tomb of Annihilation", username="alice")
    venture(scenario.game, "alice", source_name="test")
    room = next(
        c for c in scenario.game.shared_zones[Zone.COMMAND] if c.owner == "alice"
    ).venture_room
    venture(scenario.game, "alice", source_name="test")
    after = next(
        c for c in scenario.game.shared_zones[Zone.COMMAND] if c.owner == "alice"
    ).venture_room
    assert after != room

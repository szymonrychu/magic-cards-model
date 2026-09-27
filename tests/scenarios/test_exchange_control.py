"""Exchanging control of two creatures from a triggered ability (CR 701.12) -
Kitsune, Dragon's Daughter: "Whenever Kitsune enters or deals combat damage
to a player, you may exchange control of two other target creatures
controlled by different players."

- CR 603.1b: one triggered ability with two trigger conditions - it
  triggers on entering (CR 603.6a) and on combat damage to a player.
- CR 701.12a: "if the entire exchange can't be completed, no part of the
  exchange occurs" - a target gone before resolution stops all of it.
- CR 701.12b: each controller simultaneously gains control of the other's
  permanent; the control change is a layer 2 effect (CR 613.1b) with no
  duration, so it outlasts the turn.
- "other target creatures" excludes Kitsune itself (CR 115.1's own
  targeting restriction); "controlled by different players" is checked on
  announcement and again on resolution (CR 608.2b).
- "You may" (CR 608.2d): declining leaves both creatures where they are.

Off-set proofs (legal, in no deck list):

- Tomebound Lich: "Whenever this creature enters or deals combat damage to
  a player, draw a card, then discard a card." - the same two-condition
  trigger on a different effect: the combat-damage half fires on its own.
- The Trickster-God's Heist: "I - You may exchange control of two target
  creatures." / "II - You may exchange control of two target nonbasic,
  noncreature permanents that share a card type." - the optional exchange
  from a Saga chapter, without "other" and with a card-type restriction.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

KITSUNE = "Kitsune, Dragon's Daughter"
HEIST = "The Trickster-God's Heist"


def _controller(scenario, permanent):
    return scenario.game.controller_of(permanent).username


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _kitsune_enters(scenario, *targets):
    scenario.choose_trigger_targets(KITSUNE, list(targets))
    kitsune = scenario.put_onto_battlefield(KITSUNE, "alice")
    _resolve_everything(scenario)
    return kitsune


def _etb_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player("alice", hand=[KITSUNE], battlefield=list(alice), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_kitsune_entering_exchanges_two_creatures():
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    _kitsune_enters(scenario, bears, giant)

    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, giant) == "alice"


def test_declining_the_may_exchanges_nothing():
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, username="alice")

    _kitsune_enters(scenario, bears, giant)

    assert _controller(scenario, bears) == "alice"
    assert _controller(scenario, giant) == "bob"


def test_the_exchange_outlasts_the_turn():
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _kitsune_enters(scenario, bears, giant)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert _controller(scenario, giant) == "alice"
    assert _controller(scenario, bears) == "bob"


def test_two_creatures_one_player_controls_are_refused_as_targets():
    """ "controlled by different players" restricts the pair (CR 601.2c via
    CR 603.3d)."""
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant", "Craw Wurm"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")

    with pytest.raises(ValueError, match="different players"):
        _kitsune_enters(scenario, giant, wurm)


def test_kitsune_cannot_target_itself():
    """ "two other target creatures": Kitsune is never one of the pair."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[KITSUNE], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kitsune = scenario.creature(KITSUNE, "alice")
    giant = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError, match="cannot target"):
        scenario.choose_trigger_targets(KITSUNE, [kitsune, giant])


def test_a_target_gone_before_resolution_stops_the_whole_exchange():
    """CR 701.12a: no part of the exchange happens."""
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets(KITSUNE, [bears, giant])
    scenario.put_onto_battlefield(KITSUNE, "alice")
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(giant)
    while scenario.game.stack:
        scenario.resolve_top()

    assert giant.zone is Zone.GRAVEYARD
    assert _controller(scenario, bears) == "alice"


def test_combat_damage_to_a_player_triggers_the_exchange():
    """CR 603.1b: the second trigger condition fires on its own."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[KITSUNE, "Grizzly Bears"], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kitsune = scenario.creature(KITSUNE, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets(KITSUNE, [bears, giant])
    scenario.attack_with(kitsune)
    scenario.advance()
    scenario.no_blocks()

    scenario.combat_damage()
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 14
    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, giant) == "alice"


def test_combat_damage_blocked_does_not_trigger():
    """Damage to a creature is not damage to a player."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[KITSUNE, "Grizzly Bears"], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant", "Craw Wurm"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kitsune = scenario.creature(KITSUNE, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.choose_trigger_targets(KITSUNE, [bears, giant])
    scenario.attack_with(kitsune)
    scenario.advance()
    scenario.block(kitsune, wurm)

    scenario.combat_damage()
    _resolve_everything(scenario)

    assert _controller(scenario, bears) == "alice"
    assert _controller(scenario, giant) == "bob"


# -- Tomebound Lich: the same two-condition trigger ---------------------------


def test_tomebound_lich_loots_on_combat_damage_to_a_player():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomebound Lich"],
            hand=["Island"],
            library=["Forest", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    lich = scenario.creature("Tomebound Lich", "alice")
    scenario.attack_with(lich)
    scenario.advance()
    scenario.no_blocks()
    hand_before = len(scenario.player("alice").hand)
    graveyard_before = len(scenario.player("alice").graveyard)

    scenario.combat_damage()
    _resolve_everything(scenario)

    # Drew one, discarded one: same hand size, one more card in the graveyard.
    assert len(scenario.player("alice").hand) == hand_before
    assert len(scenario.player("alice").graveyard) == graveyard_before + 1


# -- The Trickster-God's Heist: an optional exchange from a chapter -----------


def _heist_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[HEIST],
            battlefield=["Island", "Island", "Swamp", "Swamp", *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )


def _cast_heist(scenario, *targets):
    scenario.choose_trigger_targets(HEIST, list(targets))
    scenario.cast_and_resolve(
        HEIST, *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="alice")
    )
    _resolve_everything(scenario)
    return scenario.find(HEIST, Zone.BATTLEFIELD, "alice")


def test_heist_chapter_one_exchanges_two_creatures():
    scenario = _heist_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_heist(scenario, bears, giant)

    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, giant) == "alice"


def test_heist_chapter_one_may_be_declined():
    scenario = _heist_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, username="alice")

    _cast_heist(scenario, bears, giant)

    assert _controller(scenario, bears) == "alice"
    assert _controller(scenario, giant) == "bob"


def test_heist_chapter_two_exchanges_two_artifacts():
    """ "nonbasic, noncreature permanents that share a card type"."""
    scenario = _heist_board(alice=["Grizzly Bears", "Mind Stone"], bob=["Hill Giant", "Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _cast_heist(scenario, bears, giant)

    scenario.choose_trigger_targets(HEIST, [stone, ring])
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)

    assert _controller(scenario, stone) == "bob"
    assert _controller(scenario, ring) == "alice"


def test_unchosen_targets_default_to_a_legal_pair():
    """With nothing scripted, the default answer is one creature from each
    controller (CR 601.2c's "controlled by different players")."""
    scenario = _etb_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.put_onto_battlefield(KITSUNE, "alice")
    _resolve_everything(scenario)

    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, giant) == "alice"


def test_with_only_one_players_creatures_the_trigger_is_removed():
    """CR 603.3d: no legal pair exists, so the ability is removed from the
    stack and nothing changes hands."""
    scenario = _etb_board(alice=["Grizzly Bears", "Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.put_onto_battlefield(KITSUNE, "alice")
    _resolve_everything(scenario)

    assert scenario.game.stack_is_empty
    assert _controller(scenario, bears) == "alice"

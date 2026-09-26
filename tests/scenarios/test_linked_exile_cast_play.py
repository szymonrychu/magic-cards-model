"""Cards exiled by an object's own ability, and cast or played later because
of another ability of that object (CR 607.2a's linked abilities).

- **Krang & Shredder** - "Whenever Krang & Shredder enter or attack, each
  opponent exiles cards from the top of their library until they exile a
  nonland card." and "Disappear - At the beginning of your end step, if a
  permanent left the battlefield under your control this turn, you may cast a
  card exiled with Krang & Shredder without paying its mana cost."
- **Raphael, Most Attitude** - "Alliance - Whenever another creature you
  control enters, you may exile the top card of your library." and "Whenever
  Raphael attacks, until end of turn, you may play a card exiled with
  Raphael."
- **Etali, Primal Conqueror** (second printing of the per-player exile-until,
  Modern and Pioneer legal, in no deck list) - "When Etali enters, each player
  exiles cards from the top of their library until they exile a nonland card.
  You may cast any number of spells from among the nonland cards exiled this
  way without paying their mana costs." Every player rather than every
  opponent, with the free cast in the same ability; its back face's "they get
  that many poison counters" is read too.
- **The Temporal Anchor** (second printing of "play cards exiled with", Modern
  and Pioneer legal, in no deck list) - "During your turn, you may play cards
  exiled with The Temporal Anchor." A static permission rather than a
  triggered one, plural, and only during its controller's turn. No other
  printing says "you may play a card exiled with" (Scryfall, this session).

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 607.2a** - the second ability refers only to cards the first one exiled.
- **CR 400.7** - a permanent that leaves and returns is a new object, with
  none of its earlier self's exiled cards (Raphael's own ruling).
- **CR 603.4** - Disappear's intervening "if".
- **CR 608.2g** - Krang & Shredder's cast happens during the resolution;
  timing restrictions based on the card's types are ignored (its ruling).
- **CR 118.9** - "without paying its mana cost".
- **CR 601.1a** - playing a card is playing it as a land or casting it.
- **CR 305.1** - a land played this way is still the turn's land drop, at
  sorcery timing.
- **CR 122.1f** - poison counters are given to a player.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario: Scenario) -> None:
    """Advance through the game itself, so "at the beginning of your end
    step" triggers as that step begins (CR 603.2b)."""
    while scenario.step is not Step.END_STEP:
        _resolve_everything(scenario)
        scenario.advance()
    _resolve_everything(scenario)


def _exiled_with(scenario, permanent):
    return scenario.game.cards_exiled_with(permanent.id, permanent.zone_change_stamp)


# -- Krang & Shredder --------------------------------------------------------


def _krang(bob_library, *, alice_battlefield=(), carol_library=None):
    builder = Scenario().player(
        "alice",
        battlefield=["Swamp", *alice_battlefield],
        hand=["Krang & Shredder"],
        library=["Swamp"] * 8,
    )
    builder = builder.player("bob", library=list(bob_library))
    if carol_library is not None:
        builder = builder.player("carol", library=list(carol_library))
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    krang = scenario.put_onto_battlefield("Krang & Shredder", "alice")
    _resolve_everything(scenario)
    return scenario, krang


def test_krang_entering_makes_each_opponent_exile_until_a_nonland_card():
    scenario, krang = _krang(["Forest", "Forest", "Grizzly Bears", "Hill Giant"])
    assert [state.name for state in scenario.player("bob").library] == ["Hill Giant"]
    pile = _exiled_with(scenario, krang)
    assert sorted(state.name for state in pile) == ["Forest", "Forest", "Grizzly Bears"]


def test_krang_reaches_every_opponent_not_its_controller():
    scenario, krang = _krang(
        ["Forest", "Grizzly Bears"], carol_library=["Island", "Llanowar Elves", "Island"]
    )
    assert [state.name for state in scenario.player("carol").library] == ["Island"]
    assert len(scenario.player("alice").library) == 8
    assert {state.name for state in _exiled_with(scenario, krang)} == {
        "Forest",
        "Grizzly Bears",
        "Island",
        "Llanowar Elves",
    }


def test_krang_attacking_exiles_again():
    scenario, krang = _krang(["Grizzly Bears", "Forest", "Hill Giant", "Forest"])
    krang.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(krang)
    _resolve_everything(scenario)
    assert {state.name for state in _exiled_with(scenario, krang)} == {
        "Grizzly Bears",
        "Forest",
        "Hill Giant",
    }


def test_disappear_casts_an_exiled_card_free_after_a_permanent_left():
    """A Swamp sacrificed... here, simply destroyed: a permanent left the
    battlefield under alice's control this turn, so at her end step she casts
    bob's Grizzly Bears for nothing, and controls it."""
    scenario, krang = _krang(["Forest", "Grizzly Bears", "Hill Giant"])
    scenario.game.destroy(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"))
    _to_end_step(scenario)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert bears.controller == "alice" and bears.owner == "bob"


def test_disappear_does_not_trigger_when_nothing_left():
    """CR 603.4: the intervening "if" is false, so nothing is cast."""
    scenario, krang = _krang(["Forest", "Grizzly Bears", "Hill Giant"])
    _to_end_step(scenario)
    assert scenario.find("Grizzly Bears", Zone.EXILE).zone is Zone.EXILE


def test_disappear_never_casts_a_land():
    scenario, krang = _krang(["Forest", "Forest"])
    scenario.game.destroy(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"))
    _to_end_step(scenario)
    assert all(state.zone is Zone.EXILE for state in scenario.game.exile)


def test_disappear_may_be_declined():
    scenario, krang = _krang(["Forest", "Grizzly Bears", "Hill Giant"])
    scenario.game.destroy(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"))
    scenario.will_take_the_may(False, username="alice")
    _to_end_step(scenario)
    assert scenario.find("Grizzly Bears", Zone.EXILE).zone is Zone.EXILE


def test_disappear_reads_only_this_krangs_own_pile():
    """CR 607.2a: a card exiled by something else is not "exiled with" Krang."""
    scenario, krang = _krang(["Forest", "Forest"])
    elves = scenario.find("Swamp", Zone.LIBRARY, "alice")
    scenario.game.exile_permanent(elves)
    scenario.game.destroy(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"))
    _to_end_step(scenario)
    assert elves.zone is Zone.EXILE


# -- Raphael, Most Attitude --------------------------------------------------


def _raphael(library, *, lands=("Forest", "Forest")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raphael, Most Attitude", *lands],
            hand=["Llanowar Elves", "Mogg Fanatic"],
            library=list(library),
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    raphael = scenario.find("Raphael, Most Attitude", Zone.BATTLEFIELD, "alice")
    raphael.summoning_sick = False
    return scenario, raphael


def _ally_enters(scenario, name="Llanowar Elves"):
    scenario.put_onto_battlefield(name, "alice")
    _resolve_everything(scenario)


def _attack(scenario, raphael):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raphael)
    _resolve_everything(scenario)
    scenario.start_at(Step.POSTCOMBAT_MAIN)


def test_alliance_exiles_the_top_card_with_raphael():
    scenario, raphael = _raphael(["Grizzly Bears", "Forest"])
    _ally_enters(scenario)
    assert [state.name for state in _exiled_with(scenario, raphael)] == ["Grizzly Bears"]


def test_after_attacking_a_spell_exiled_with_raphael_is_cast_for_its_cost():
    scenario, raphael = _raphael(["Grizzly Bears", "Forest", "Island"])
    _ally_enters(scenario)
    _attack(scenario, raphael)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    scenario.game.cast(bears, "alice", mana_sources=scenario.game.permanents_controlled_by("alice"))
    _resolve_everything(scenario)
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_a_land_exiled_with_raphael_is_played_as_the_land_drop():
    scenario, raphael = _raphael(["Forest", "Island"])
    _ally_enters(scenario)
    _attack(scenario, raphael)
    forest = scenario.find("Forest", Zone.EXILE)
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD


def test_only_one_card_may_be_played():
    """ "a card": after one is played, the other stays in exile."""
    scenario, raphael = _raphael(["Forest", "Grizzly Bears", "Island"])
    _ally_enters(scenario)
    _ally_enters(scenario, "Mogg Fanatic")
    assert len(_exiled_with(scenario, raphael)) == 2
    _attack(scenario, raphael)
    scenario.game.play_land(scenario.find("Forest", Zone.EXILE), "alice")
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )
    assert bears.zone is Zone.EXILE


def test_nothing_is_playable_before_raphael_attacks():
    scenario, raphael = _raphael(["Grizzly Bears", "Island"])
    _ally_enters(scenario)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )


def test_the_permission_ends_with_the_turn():
    scenario, raphael = _raphael(["Grizzly Bears", *["Island"] * 6])
    _ally_enters(scenario)
    _attack(scenario, raphael)
    for player in ("alice", "bob"):
        while scenario.game.turn.active_player == player:
            _resolve_everything(scenario)
            scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )


def test_a_returned_raphael_cannot_play_its_earlier_selfs_cards():
    """CR 400.7 and Raphael's own ruling: a new object has no pile."""
    scenario, raphael = _raphael(["Grizzly Bears", "Island"])
    _ally_enters(scenario)
    exiled = scenario.game.exile_permanent(raphael)
    returned = scenario.game.put_onto_battlefield(exiled, "alice")
    returned.summoning_sick = False
    _attack(scenario, returned)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )


# -- Etali, Primal Conqueror: each player, then free casts ---------------------


def _etali(alice_library, bob_library):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Forest"],
            hand=["Etali, Primal Conqueror"],
            library=list(alice_library),
        )
        .player("bob", library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_etali_makes_every_player_exile_and_casts_the_nonland_cards_free():
    scenario = _etali(
        ["Forest", "Llanowar Elves", "Forest"], ["Island", "Island", "Grizzly Bears", "Island"]
    )
    scenario.will_take_the_may(True, username="alice", times=None)
    scenario.put_onto_battlefield("Etali, Primal Conqueror", "alice")
    _resolve_everything(scenario)
    assert scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").owner == "bob"
    assert {state.name for state in scenario.game.exile} == {"Forest", "Island"}


def test_etali_casts_may_be_declined_and_the_cards_stay_exiled():
    scenario = _etali(["Llanowar Elves", "Forest"], ["Grizzly Bears", "Island"])
    scenario.will_take_the_may(False, username="alice")
    scenario.put_onto_battlefield("Etali, Primal Conqueror", "alice")
    _resolve_everything(scenario)
    assert {state.name for state in scenario.game.exile} == {"Llanowar Elves", "Grizzly Bears"}


def test_etali_back_face_gives_that_many_poison_counters():
    scenario = _etali(["Forest"] * 4, ["Island"] * 4)
    etali = scenario.put_onto_battlefield("Etali, Primal Conqueror", "alice")
    _resolve_everything(scenario)
    etali.transform()
    etali.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(etali)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    dealt = scenario.combat_damage()
    _resolve_everything(scenario)
    amount = next(amount for target, amount in dealt if getattr(target, "username", None) == "bob")
    assert scenario.player("bob").counters[Counter.POISON] == amount


# -- The Temporal Anchor: during your turn, play cards exiled with it --------


def _anchor(library, *, lands=("Forest", "Forest")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["The Temporal Anchor", *lands], library=list(library))
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top, second = scenario.top_of_library(2, username="alice")
    scenario.scry_bottoming(top, second, username="alice")
    scenario.game.scry(scenario.player("alice"), 2)
    _resolve_everything(scenario)
    return scenario


def test_anchor_lets_its_controller_cast_and_play_every_card_exiled_with_it():
    scenario = _anchor(["Grizzly Bears", "Forest", "Island", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    forest = scenario.find("Forest", Zone.EXILE)
    scenario.game.play_land(forest, "alice")
    scenario.game.cast(
        bears,
        "alice",
        keyword="Cast permission",
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    _resolve_everything(scenario)
    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")


def test_anchor_permission_is_only_during_your_turn():
    scenario = _anchor(["Spectral Sailor", "Island", "Island", "Island"], lands=("Island",))
    while scenario.game.turn.active_player == "alice":
        _resolve_everything(scenario)
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")
    sailor = scenario.find("Spectral Sailor", Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.game.cast(
            sailor,
            "alice",
            keyword="Cast permission",
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )


def test_anchor_does_not_reach_cards_exiled_otherwise():
    scenario = _anchor(["Island", "Island", "Grizzly Bears", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.game.exile_permanent(bears)
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears,
            "alice",
            keyword="Cast permission",
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )


def test_anchor_keeps_the_cards_own_timing_a_flash_card_in_your_combat():
    """The permission opens the pile, not the timing: Spectral Sailor has
    flash, so alice casts it in her own combat."""
    scenario = _anchor(["Spectral Sailor", "Island", "Island", "Island"], lands=("Island",))
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    sailor = scenario.find("Spectral Sailor", Zone.EXILE)
    scenario.game.cast(
        sailor,
        "alice",
        keyword="Cast permission",
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    _resolve_everything(scenario)
    assert scenario.find("Spectral Sailor", Zone.BATTLEFIELD, "alice")


def test_legal_actions_offer_the_anchor_pile():
    from magic_cards_model.machines.legal_actions import legal_actions
    from magic_cards_model.models.action import ActionKind

    scenario = _anchor(["Grizzly Bears", "Forest", "Island", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    forest = scenario.find("Forest", Zone.EXILE)
    actions = legal_actions(scenario.game, "alice")
    assert any(a.kind is ActionKind.CAST and a.card_id == bears.id for a in actions)
    assert any(a.kind is ActionKind.PLAY_LAND and a.card_id == forest.id for a in actions)

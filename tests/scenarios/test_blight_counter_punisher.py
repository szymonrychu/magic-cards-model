"""The blight-counter punisher: "Whenever this creature enters or attacks,
put a blight counter on it. Then for each blight counter on it, each
opponent loses N life unless that player sacrifices a `<quality>` [of their
choice] or discards a card." (Rottenmouth Viper).

Two pieces, proved apart:

- **The punisher clause itself** - `effects._parse_each_opponent_loses_
  life_unless_sacrifice_or_discard_clause` - a two-way optional cost CR
  118.12 already gives a "you may ... or ..." sentence, read here as "each
  opponent" instead of "you". Proved general on Perforating Artist (legal
  in Modern, Pioneer and Standard, off the deck pool): a plain Raid trigger,
  no counter scaling at all, sharing only the punisher sentence itself.
- **The blight-counter scaling** - `effects._parse_blight_counter_
  punisher_clause` - CR 122.1's counters on the ability's own source, read
  once as the trigger's own condition rather than recomputed from a fresh
  board fact each time, so a creature with three counters already on it
  from an earlier attack punishes three times over on its next one.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 118.12** / **CR 118.12a** - "[A player] may [do something]. If
  [that player] [does ...], [effect]." and its unless-shaped twin.
- **CR 122.1** - a counter modifies the object it is on until it leaves the
  battlefield or the counter is removed.
- **CR 603.2** - a triggered ability triggers once its condition is met,
  independent of whether anyone chooses to pay attention to it.
- **CR 508.1** - CR 506.4's combat damage step aside, "attacks" triggers as
  a creature is declared an attacker (CR 508.1a).
- **CR 508.1** and **CR 508.1b/CR 508.1i** are read whole in this session
  too, confirming "attacks" is CR 508.1a's own declare-attackers event, not
  a later combat-damage one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_end_step(scenario) -> None:
    """From wherever the turn is, into the end step with its triggers stacked."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    if scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
        scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    scenario.game.put_triggers_on_stack()


# -- the general punisher clause, proved on Perforating Artist --------------


def _artist_board(*, bob_battlefield=None, bob_hand=None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Perforating Artist", "Mountain"],
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            battlefield=bob_battlefield or [],
            hand=bob_hand or [],
            library=["Plains"] * 3,
        )
        .build()
    )


def test_bob_sacrifices_a_nonland_permanent_rather_than_lose_life():
    scenario = _artist_board(bob_battlefield=["Memnite"])
    artist = scenario.creature("Perforating Artist", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(artist)
    _to_end_step(scenario)
    scenario.will_take_the_may(True, source="Perforating Artist", username="bob")
    scenario.will_choose(
        "sacrifice a nonland permanent", source="Perforating Artist", username="bob"
    )

    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.life == 20
    assert scenario.find("Memnite", Zone.GRAVEYARD, "bob") is not None


def test_bob_discards_a_card_rather_than_lose_life():
    scenario = _artist_board(bob_hand=["Lightning Bolt"])
    artist = scenario.creature("Perforating Artist", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(artist)
    _to_end_step(scenario)
    scenario.will_take_the_may(True, source="Perforating Artist", username="bob")
    scenario.will_choose("discard a card", source="Perforating Artist", username="bob")

    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.life == 20
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob") is not None


def test_bob_with_neither_option_loses_the_life_with_no_question_asked():
    """CR 608.2d never offers an impossible choice - an empty hand and no
    permanent leaves only losing the life."""
    scenario = _artist_board()
    artist = scenario.creature("Perforating Artist", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(artist)
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.life == 17


def test_declining_both_loses_the_life():
    scenario = _artist_board(bob_battlefield=["Memnite"])
    artist = scenario.creature("Perforating Artist", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(artist)
    _to_end_step(scenario)
    scenario.will_take_the_may(False, source="Perforating Artist", username="bob")

    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.life == 17
    assert scenario.find("Memnite", Zone.BATTLEFIELD, "bob") is not None


# -- Rottenmouth Viper's own blight-counter scaling --------------------------


def _viper_board(*, bob_battlefield=None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Rottenmouth Viper"],
            battlefield=["Swamp"] * 6,
            library=["Swamp"] * 4,
        )
        .player("bob", battlefield=bob_battlefield or [], library=["Plains"] * 3)
        .build()
    )


def test_entering_puts_one_blight_counter_and_punishes_once():
    scenario = _viper_board(bob_battlefield=["Memnite"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Swamp"] * 6))
    scenario.will_take_the_may(True, source="Rottenmouth Viper", username="bob")
    scenario.will_choose(
        "sacrifice a nonland permanent", source="Rottenmouth Viper", username="bob"
    )

    scenario.cast_and_resolve("Rottenmouth Viper", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    viper = scenario.creature("Rottenmouth Viper", "alice")
    assert viper.counters["blight"] == 1
    bob = scenario.player("bob")
    assert bob.life == 20
    assert scenario.find("Memnite", Zone.GRAVEYARD, "bob") is not None


def test_a_second_blight_counter_from_attacking_punishes_twice_over():
    """The trigger's own "for each blight counter on it" reads the count
    *after* this attack's own counter has already been put on (CR 122.1,
    CR 608.2b: the ability's own instructions run in order), so a viper that
    already carried one counter on it before this attack punishes twice
    this time. Staged straight onto the battlefield (rather than cast) so
    it is free of summoning sickness (CR 302.6) without reaching into a
    turn machine no test elsewhere in this file needs."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Rottenmouth Viper"], library=["Swamp"] * 4)
        .player("bob", battlefield=["Memnite", "Ornithopter"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    viper = scenario.creature("Rottenmouth Viper", "alice")
    scenario.game.add_counters(viper, "blight", 1)
    scenario.will_take_the_may(True, source="Rottenmouth Viper", username="bob", times=None)
    scenario.will_choose(
        "sacrifice a nonland permanent", source="Rottenmouth Viper", username="bob", times=None
    )

    scenario.attack_with(viper)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert viper.counters["blight"] == 2
    bob = scenario.player("bob")
    assert bob.life == 20
    assert scenario.find("Memnite", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Ornithopter", Zone.GRAVEYARD, "bob") is not None

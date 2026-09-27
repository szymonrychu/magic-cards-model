"""Keywords a creature has only while its controller has lost life this turn.

Essence Channeler: "As long as you've lost life this turn, this creature has
flying and vigilance." Its other two clauses - "Whenever you gain life, put a
+1/+1 counter on this creature." and "When this creature dies, put its
counters on target creature you control." - are covered at the end.

No other Modern/Pioneer/Standard printing gates a static ability on "you've
lost life this turn" (searched on Scryfall this session); the gate is the
lost-life twin of the gained-life gate Tenured Concocter reads ("This creature
gets +2/+0 as long as you gained life this turn."), one reader for both, and
Tenured Concocter is played here too to prove the shared reader still works.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 613.1f** - the keywords are added in layer 6.
- **CR 611.3a** - a static ability's effect is not locked in: it applies at
  any moment the condition holds, and stops the moment it does not.
- **CR 119.3** - an effect that makes a player lose life adjusts the life
  total; damage to a player is life loss too.
- **CR 514.2** - "this turn" facts end with the turn.
- **CR 702.20b** - a creature with vigilance does not tap to attack.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*, alice_battlefield=(), bob_hand=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Essence Channeler", *alice_battlefield],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            battlefield=list(bob_battlefield),
            hand=list(bob_hand),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _channeler(scenario):
    return scenario.game.computed_board().of(scenario.creature("Essence Channeler", "alice"))


def test_without_life_lost_it_has_neither_keyword():
    scenario = _board()
    computed = _channeler(scenario)
    assert not computed.has_ability("Flying")
    assert not computed.has_ability("Vigilance")


def test_after_losing_life_it_has_flying_and_vigilance():
    scenario = _board()
    scenario.game.lose_life("alice", 2)
    computed = _channeler(scenario)
    assert computed.has_ability("Flying")
    assert computed.has_ability("Vigilance")


def test_damage_to_its_controller_is_life_lost():
    """CR 119.3: an opponent's Bolt to the face is life loss."""
    scenario = _board(bob_hand=["Lightning Bolt"], bob_battlefield=["Mountain"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 17
    assert _channeler(scenario).has_ability("Flying")


def test_an_opponent_losing_life_does_not_count():
    """ "you've": only the Channeler's controller."""
    scenario = _board()
    scenario.game.lose_life("bob", 3)
    assert not _channeler(scenario).has_ability("Flying")


def test_gaining_the_life_back_does_not_undo_the_loss():
    """The question is whether life was lost this turn, not the net total."""
    scenario = _board()
    scenario.game.lose_life("alice", 2)
    scenario.game.gain_life("alice", 2)
    assert _channeler(scenario).has_ability("Flying")


def test_the_keywords_end_with_the_turn():
    """CR 514.2: next turn nobody has lost life yet."""
    scenario = _board()
    scenario.game.lose_life("alice", 1)
    assert _channeler(scenario).has_ability("Flying")
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert not _channeler(scenario).has_ability("Flying")


def test_with_vigilance_it_attacks_without_tapping():
    """CR 702.20b."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Essence Channeler"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    channeler = scenario.creature("Essence Channeler", "alice")
    scenario.game.lose_life("alice", 1)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(channeler)
    assert not channeler.tapped


def test_gaining_life_puts_a_plus_one_counter_on_it():
    scenario = _board()
    channeler = scenario.creature("Essence Channeler", "alice")
    scenario.game.gain_life("alice", 3)
    scenario.pass_until_resolved()
    assert channeler.counters["+1/+1"] == 1
    assert (scenario.game.power_of(channeler), scenario.game.toughness_of(channeler)) == (3, 2)


def test_when_it_dies_its_counters_move_to_another_creature():
    scenario = _board(alice_battlefield=["Grizzly Bears"])
    channeler = scenario.creature("Essence Channeler", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(channeler, "+1/+1", 2)
    scenario.game.destroy(channeler)
    scenario.state_based_actions()
    if scenario.pending_triggers:
        scenario.choose_trigger_targets("Essence Channeler", [bears])
    scenario.pass_until_resolved()
    assert channeler.zone is Zone.GRAVEYARD
    assert bears.counters["+1/+1"] == 2


def test_essence_channeler_classifies_as_handled():
    clauses = [c for c in classify_clauses(card("Essence Channeler")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}


def test_the_gained_life_twin_of_the_gate_still_reads():
    """Tenured Concocter shares the reader: +2/+0 only after gaining life."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tenured Concocter"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    concocter = scenario.creature("Tenured Concocter", "alice")
    base = scenario.game.power_of(concocter)
    scenario.game.lose_life("alice", 1)
    assert scenario.game.power_of(concocter) == base, "losing life is not gaining it"
    scenario.game.gain_life("alice", 1)
    assert scenario.game.power_of(concocter) == base + 2

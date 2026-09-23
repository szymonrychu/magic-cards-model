"""Scenario: "Tap all creatures target player controls. You may pay any
amount of {E}. If you do, choose up to that many creatures tapped this way.
Put a stun counter on each of them." - Suppression Ray.

Reader under test: `machines/effects._parse_tap_all_pay_energy_counter_
chosen_whole_text`, four sentences read as one instruction because each
later one points back at an earlier one ("that many" at the energy paid,
"tapped this way" at the first sentence's tapped set, "each of them" at the
choice). No second printing carries the energy half (Scryfall
`o:"tapped this way" o:"stun counter"`, 2026-09-23 - Suppression Ray only);
its first sentence is the shared tap-all grammar, proven off-set on Dawnglare
Invoker in `test_tap_all_target_player.py`, and the stun counter itself is
CR 122.1d's existing replacement in `CardState.untap`.

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 107.14** - "To pay {E}, a player removes one energy counter from
  themselves."
- **CR 118.3** - a player can't pay more than they have.
- **CR 608.2d** - the amount and the chosen creatures are choices made while
  the spell resolves.
- **CR 701.26a** - only untapped permanents can be tapped; Suppression Ray's
  own ruling (2024-06-07): "Creatures tapped this way" means creatures that
  became tapped as a result of it, not ones that were already tapped.
- **CR 122.1d** - "If a permanent with a stun counter on it would become
  untapped, instead remove a stun counter from it."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

BOBS_TEAM = ["Grizzly Bears", "Serra Angel", "Tarmogoyf"]


def _board(*, energy: int, bobs=BOBS_TEAM):
    scenario = (
        Scenario()
        .player("alice", hand=["Suppression Ray"], battlefield=["Plains"] * 5 + ["Memnite"])
        .player("bob", battlefield=list(bobs) + ["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if energy:
        scenario.game.add_player_counters("alice", Counter.ENERGY, energy)
    return scenario


def _cast(scenario, target="bob"):
    plains = scenario.untapped_sources(*["Plains"] * 5, username="alice")
    return scenario.cast_and_resolve("Suppression Ray", *plains, targets=[target])


def _stun(card) -> int:
    return card.counter_count(Counter.STUN)


def test_pay_two_and_stun_two_of_the_three_tapped_creatures():
    scenario = _board(energy=3)
    bears, angel, goyf = (scenario.creature(name, "bob") for name in BOBS_TEAM)
    scenario.will_pay_energy_amount(2)
    scenario.will_choose_cards(bears, angel)

    ray = _cast(scenario)

    assert ray.zone is Zone.GRAVEYARD
    assert bears.tapped and angel.tapped and goyf.tapped
    assert (_stun(bears), _stun(angel), _stun(goyf)) == (1, 1, 0)
    assert scenario.player("alice").energy == 1


def test_paying_nothing_taps_but_stuns_nothing_and_asks_no_choice():
    """Declining is paying 0 (CR 118.3's "players can always pay 0" family,
    and `PAY_ENERGY_AMOUNT`'s default answer) - "if you do" is false, so no
    creature is chosen and no question about creatures is put."""
    scenario = _board(energy=3)
    bears, angel, goyf = (scenario.creature(name, "bob") for name in BOBS_TEAM)

    _cast(scenario)

    assert bears.tapped and angel.tapped and goyf.tapped
    assert _stun(bears) == _stun(angel) == _stun(goyf) == 0
    assert scenario.player("alice").energy == 3
    assert not any(
        question.kind is DecisionKind.CHOOSE_CARDS for question in scenario.questions_asked()
    )


def test_with_no_energy_nothing_can_be_paid_and_the_tap_still_happens():
    scenario = _board(energy=0)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario)

    assert bears.tapped
    assert _stun(bears) == 0
    assert scenario.player("alice").energy == 0


def test_an_already_tapped_creature_is_not_tapped_this_way_and_cannot_be_chosen():
    """The ruling's own example: a creature tapped before the Ray resolved is
    not one "tapped this way" - it is never offered, however much is paid."""
    scenario = _board(energy=3)
    bears, angel, goyf = (scenario.creature(name, "bob") for name in BOBS_TEAM)
    bears.tapped = True
    scenario.will_pay_energy_amount(3)
    scenario.will_choose_cards(angel, goyf)

    _cast(scenario)

    (choice,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert bears.id not in choice.cards
    assert set(choice.cards) == {angel.id, goyf.id}
    assert choice.amount == 2, "paying 3 with only 2 tapped this way caps the choice at 2"
    assert _stun(bears) == 0
    assert _stun(angel) == _stun(goyf) == 1


def test_up_to_means_fewer_than_paid_may_be_chosen():
    """ "Up to that many": paying 2 and choosing only one is legal, and the
    energy paid stays paid."""
    scenario = _board(energy=2)
    bears, angel, goyf = (scenario.creature(name, "bob") for name in BOBS_TEAM)
    scenario.will_pay_energy_amount(2)
    scenario.will_choose_cards(goyf)

    _cast(scenario)

    assert (_stun(bears), _stun(angel), _stun(goyf)) == (0, 0, 1)
    assert scenario.player("alice").energy == 0


def test_the_choice_is_only_among_the_target_players_creatures():
    """alice's Memnite is not tapped (not bob's) and so never offered, and a
    non-creature bob controls (his Island) is neither tapped nor offered."""
    scenario = _board(energy=5)
    memnite = scenario.creature("Memnite", "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    scenario.will_pay_energy_amount(1)
    scenario.will_choose_cards(scenario.creature("Grizzly Bears", "bob"))

    _cast(scenario)

    (choice,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert memnite.id not in choice.cards and island.id not in choice.cards
    assert not memnite.tapped and not island.tapped
    assert choice.amount == 1


def test_a_target_player_with_no_creatures_offers_no_choice():
    scenario = _board(energy=2, bobs=[])
    scenario.will_pay_energy_amount(2)

    _cast(scenario)

    assert scenario.player("alice").energy == 0, "paying is still a legal choice"
    assert not any(
        question.kind is DecisionKind.CHOOSE_CARDS for question in scenario.questions_asked()
    )


def test_a_stunned_creature_stays_tapped_through_its_untap_step_and_loses_the_counter():
    """CR 122.1d, proven end to end: aimed at alice herself so her own untap
    step is the one that runs - the stunned Memnite spends its counter
    instead of untapping, the unstunned lands untap normally."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Suppression Ray"],
            battlefield=["Plains"] * 5 + ["Memnite", "Ornithopter"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.add_player_counters("alice", Counter.ENERGY, 1)
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.will_pay_energy_amount(1)
    scenario.will_choose_cards(memnite)

    _cast(scenario, target="alice")
    assert memnite.tapped and thopter.tapped
    scenario.game.untap_step()

    assert memnite.tapped, "the stun counter replaced the untap"
    assert _stun(memnite) == 0
    assert not thopter.tapped

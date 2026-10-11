"""Jace, the Mind Sculptor, whole card: the `0` (Brainstorm shape) and `-1`
(bounce) abilities, plus the loyalty-ability rules around all four. The `+2`
and `-12` have their own mechanic files
(`test_look_top_card_of_target_library_may_bottom.py`,
`test_exile_target_library_shuffle_hand_in.py`); here they are played as part of
the same card.

- **CR 606.3** - one loyalty ability per permanent per turn.
- **CR 606.6** - a negative loyalty cost needs that many loyalty counters.
- **CR 401.4** - cards put into the same library position at once go in the
  order their owner picks.
- **CR 704.5i** - a planeswalker with no loyalty counters is put into its
  owner's graveyard.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

JACE = "Jace, the Mind Sculptor"


def _scenario(*, alice_library=("Forest", "Island", "Mountain", "Swamp", "Plains")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[JACE],
            hand=["Shock", "Giant Growth"],
            library=list(alice_library),
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find(JACE, Zone.BATTLEFIELD, "alice")


def test_jace_enters_with_three_loyalty():
    _, jace = _scenario()
    assert jace.counter_count(Counter.LOYALTY) == 3


def test_zero_draws_three_then_puts_two_cards_from_hand_on_top_in_chosen_order():
    scenario, jace = _scenario()
    alice = scenario.player("alice")
    shock = scenario.find("Shock", Zone.HAND, "alice")
    growth = scenario.find("Giant Growth", Zone.HAND, "alice")

    scenario.will_choose_cards(growth, shock, username="alice")
    scenario.activate(jace, index=1, username="alice")  # 0
    scenario.pass_until_resolved()

    assert len(alice.hand) == 3  # 2 + 3 drawn - 2 put back
    assert [state.name for state in alice.library[:2]] == ["Giant Growth", "Shock"]
    assert [state.name for state in alice.library[2:]] == ["Swamp", "Plains"]
    assert jace.counter_count(Counter.LOYALTY) == 3  # 0 costs nothing


def test_zero_with_a_one_card_library_draws_it_and_still_puts_two_back():
    scenario, jace = _scenario(alice_library=("Forest",))
    alice = scenario.player("alice")

    scenario.activate(jace, index=1, username="alice")
    scenario.pass_until_resolved()

    assert len(alice.hand) + len(alice.library) == 3  # nothing lost; 2 + 1 card total
    assert len(alice.library) == 2


def test_minus_one_returns_target_creature_to_its_owners_hand():
    scenario, jace = _scenario()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(jace, index=2, username="alice", targets=[bears])  # -1
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND
    assert bears in scenario.player("bob").hand
    assert jace.counter_count(Counter.LOYALTY) == 2


def test_minus_one_on_your_own_creature_works_too():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[JACE, "Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.activate(jace, index=2, username="alice", targets=[elves])
    scenario.pass_until_resolved()

    assert elves.zone is Zone.HAND


def test_minus_one_at_one_loyalty_kills_jace_by_sba_after_the_cost():
    scenario, jace = _scenario()
    bears = scenario.creature("Grizzly Bears", "bob")
    jace.remove_counters(Counter.LOYALTY, 2)
    assert jace.counter_count(Counter.LOYALTY) == 1

    scenario.activate(jace, index=2, username="alice", targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND
    assert jace.zone is Zone.GRAVEYARD  # CR 704.5i, 0 loyalty


def test_only_one_loyalty_ability_per_turn_cr_606_3():
    scenario, jace = _scenario()

    scenario.activate(jace, index=1, username="alice")  # 0
    scenario.pass_until_resolved()

    for index in (0, 1, 2):
        assert scenario.why_cannot_activate(jace, index=index, username="alice") is not None


def test_minus_twelve_is_unavailable_at_three_loyalty_cr_606_6():
    scenario, jace = _scenario()

    assert scenario.why_cannot_activate(jace, index=3, username="alice") is not None


def test_plus_two_uses_up_the_turns_loyalty_activation():
    scenario, jace = _scenario()
    scenario.will_take_the_may(False, username="alice")
    scenario.activate(jace, index=0, username="alice", targets=["bob"])
    scenario.pass_until_resolved()
    assert jace.counter_count(Counter.LOYALTY) == 5
    assert scenario.why_cannot_activate(jace, index=1, username="alice") is not None

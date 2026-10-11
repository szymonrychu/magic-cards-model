"""Jace, the Mind Sculptor's -12: "Exile all cards from target player's
library, then that player shuffles their hand into their library."
(`_parse_exile_all_cards_from_library_clause` in `machines/effects/library.py`)
and, as the same exile instruction on a different subject and without the
shuffle tail, Leveler's "When this creature enters, exile all cards from your
library."

- **CR 609.3** - an effect that attempts something impossible does as much as
  possible: an empty library exiles nothing, and the shuffle still happens.
- **CR 701.24a** - a shuffle randomizes the library; **CR 701.24d** - a player
  told to shuffle a set of cards into a library shuffles it even when the set
  is empty.
- **CR 606.6** - a negative loyalty cost can't be paid without that many
  loyalty counters.
- **CR 603.2c** - the library is exiled as one event.
- **CR 400.3** - the hand's cards go to their owner's library.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

JACE = "Jace, the Mind Sculptor"
LIBRARY = ["Forest", "Island", "Mountain", "Swamp", "Plains"]


def _scenario(*, bob_library=LIBRARY, bob_hand=("Llanowar Elves", "Giant Growth"), loyalty=12):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[JACE], library=["Mountain"], hand=["Shock"])
        .player("bob", library=list(bob_library), hand=list(bob_hand))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(jace, Counter.LOYALTY, loyalty - jace.loyalty)
    return scenario, jace


def _exiled_names(scenario, owner):
    return sorted(state.name for state in scenario.game.exile if state.owner == owner)


def test_minus_twelve_exiles_the_library_then_shuffles_the_hand_in():
    scenario, jace = _scenario()
    bob = scenario.player("bob")

    scenario.activate(jace, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert _exiled_names(scenario, "bob") == sorted(LIBRARY)
    assert bob.hand == []
    assert sorted(state.name for state in bob.library) == ["Giant Growth", "Llanowar Elves"]
    assert jace.counter_count(Counter.LOYALTY) == 0


def test_the_hand_is_shuffled_in_after_the_exile_so_it_is_never_exiled():
    """Order matters: were the hand shuffled first, it would be exiled with
    the library."""
    scenario, jace = _scenario()

    scenario.activate(jace, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert "Llanowar Elves" not in _exiled_names(scenario, "bob")
    assert "Giant Growth" not in _exiled_names(scenario, "bob")


def test_minus_twelve_on_yourself_exiles_your_library_and_shuffles_your_hand_in():
    scenario, jace = _scenario()
    alice = scenario.player("alice")

    scenario.activate(jace, index=3, username="alice", targets=["alice"])
    scenario.pass_until_resolved()

    assert _exiled_names(scenario, "alice") == ["Mountain"]
    assert alice.hand == []
    assert [state.name for state in alice.library] == ["Shock"]


def test_an_empty_library_exiles_nothing_but_the_hand_is_still_shuffled_in():
    scenario, jace = _scenario(bob_library=[])
    bob = scenario.player("bob")

    scenario.activate(jace, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert _exiled_names(scenario, "bob") == []
    assert bob.hand == []
    assert sorted(state.name for state in bob.library) == ["Giant Growth", "Llanowar Elves"]


def test_an_empty_hand_leaves_the_exile_standing():
    scenario, jace = _scenario(bob_hand=())
    bob = scenario.player("bob")

    scenario.activate(jace, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert _exiled_names(scenario, "bob") == sorted(LIBRARY)
    assert bob.library == []
    assert bob.hand == []


def test_the_exile_is_a_single_batch_so_the_cards_are_all_in_exile_together():
    scenario, jace = _scenario()

    scenario.activate(jace, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert all(state.zone is Zone.EXILE for state in scenario.game.exile if state.owner == "bob")
    assert len(_exiled_names(scenario, "bob")) == len(LIBRARY)


def test_minus_twelve_can_not_be_activated_below_twelve_loyalty_cr_606_6():
    scenario, jace = _scenario(loyalty=11)

    assert scenario.why_cannot_activate(jace, index=3, username="alice") is not None


# --- generality: the exile instruction without the shuffle tail --------------


def test_leveler_enters_and_exiles_its_controllers_whole_library():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Leveler"],
            battlefield=["Plains"] * 6,
            library=list(LIBRARY),
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")

    scenario.cast_and_resolve("Leveler", *sources, username="alice")
    scenario.pass_until_resolved()

    assert alice.library == []
    assert _exiled_names(scenario, "alice") == sorted(LIBRARY)
    assert [state.name for state in scenario.player("bob").library] == ["Island"]

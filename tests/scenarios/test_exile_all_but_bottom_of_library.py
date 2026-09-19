""" "Exile all but the bottom card of each opponent's library." /  "... of
target player's library." (`_parse_exile_all_but_bottom_of_library_clause`,
`_EXILE_ALL_BUT_BOTTOM_OF_LIBRARY_RE` in `machines/effects.py`).

One instruction, two subjects (the same split `_EACH_SACRIFICES_OF_THEIR_
CHOICE_RE`'s own "who" reads between "opponent" and "player"):

- **Jace, Reality Sculptor**'s own `0`: "Exile all but the bottom card of
  each opponent's library." - no target at all (CR 115.10a), an unscoped
  "each opponent" group. Gated behind its own "Activate only if there are
  twenty-five or more loyalty counters among Jaces you control" (CR 602.5b);
  `test_loyalty_among_named_condition.py` covers that gate on its own, so
  this file only stages enough loyalty to get past it and never below.
- **Nicol Bolas, the Arisen**'s own `-12` (the back face of Nicol Bolas, the
  Ravager, off-set): "Exile all but the bottom card of target player's
  library." - CR 115.1's ordinary player target, and no activation condition
  at all, so this proves the exile clause itself works standalone.

CR 609.3: a library holding the bottom count or fewer cards is left
untouched - there is nothing above the bottom to exile.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 609.3, 115.1, 115.10a, 602.5b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

JACE = "Jace, Reality Sculptor"
NICOL_BOLAS = "Nicol Bolas, the Ravager"

LIBRARY_TOP_FIRST = ["Forest", "Island", "Mountain", "Swamp", "Plains"]


def _make_jace_token_with_loyalty(scenario, total_loyalty: int):
    """Cast Academic Ascent ("Empower Jace 2.") to create the Jace
    planeswalker token, then top its loyalty up directly - the same staging
    `test_loyalty_among_named_condition.py` uses, so alice's `Jace, Reality
    Sculptor` can legally activate its own `0` ability."""
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Academic Ascent", *sources, targets=[elves], username="alice")
    token = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    remaining = total_loyalty - token.counter_count(Counter.LOYALTY)
    if remaining:
        scenario.game.add_counters(token, Counter.LOYALTY, remaining)
    return token


def test_jaces_own_zero_exiles_all_but_the_bottom_card_of_each_opponents_library():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[JACE, "Plains", "Plains", "Llanowar Elves"],
            hand=["Academic Ascent"],
        )
        .player("bob", library=list(LIBRARY_TOP_FIRST))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    _make_jace_token_with_loyalty(scenario, 25)
    bob = scenario.player("bob")

    scenario.activate(jace, index=2, username="alice")  # 0
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Plains"]
    exiled = {state.name for state in scenario.game.exile if state.owner == "bob"}
    assert exiled == {"Forest", "Island", "Mountain", "Swamp"}


def test_nicol_bolas_the_arisens_minus_twelve_exiles_all_but_bottom_of_target_players_library():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[NICOL_BOLAS])
        .player("bob", library=list(LIBRARY_TOP_FIRST))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    front = scenario.find(NICOL_BOLAS, Zone.HAND, "alice")
    nicol = scenario.game.put_onto_battlefield(front, "alice", transformed=True)
    assert nicol.loyalty == 7
    scenario.game.add_counters(nicol, Counter.LOYALTY, 5)  # up to 12, for the -12 cost
    bob = scenario.player("bob")

    scenario.activate(nicol, index=3, username="alice", targets=["bob"])  # -12
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Plains"]
    exiled = {state.name for state in scenario.game.exile if state.owner == "bob"}
    assert exiled == {"Forest", "Island", "Mountain", "Swamp"}


def test_a_library_at_or_below_the_bottom_count_is_left_untouched():
    """CR 609.3: with only one card in the library, there is nothing above
    the bottom card to exile."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[JACE, "Plains", "Plains", "Llanowar Elves"],
            hand=["Academic Ascent"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    _make_jace_token_with_loyalty(scenario, 25)
    bob = scenario.player("bob")

    scenario.activate(jace, index=2, username="alice")  # 0
    scenario.pass_until_resolved()

    assert [state.name for state in bob.library] == ["Island"]
    assert [state for state in scenario.game.exile if state.owner == "bob"] == []

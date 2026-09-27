"""Deepway Navigator: "When this creature enters, untap each other Merfolk
you control." plus "As long as you attacked with three or more Merfolk this
turn, Merfolk you control get +1/+0."

Two new pieces:

- **`_parse_untap_each_subtype_clause`** (`machines/effects.py`) - the
  subtype-filtered twin of the existing `_UNTAP_ALL_GROUP_RE`'s closed
  card-type list, generalised over any CR 205.3 creature type.
- **A per-turn, per-player *count* ledger** (`Game.note_turn_count`, already
  the counting twin `turn_counts`'s own docstring describes for `turn_facts`)
  - `Game.declare_attackers` now counts `attacked_with_type_facts` as well as
  recording them as a plain "did you" fact, and `LayerContext.turn_counts`
  carries the ledger to a static ability the way `turn_facts` already does.
  `_ATTACKED_WITH_N_TYPE_GROUP_PUMP_RE` (`machines/layers.py`) reads it for a
  group pump gated on "N or more", not just "did you".

CR numbers verified this session with `mise run rules:find`:

- **CR 701.26a/b** - tap and untap.
- **CR 508.1** - declaring attackers.
- **CR 611.3a** - a static ability's effect "isn't 'locked in'"; it is
  re-evaluated continuously.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- "untap each other Merfolk you control" -----------------------------------


def test_deepway_navigator_untaps_other_merfolk_but_not_itself_or_non_merfolk():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deepway Navigator"],
            battlefield=["Ambassador Laquatus", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    laquatus = scenario.creature("Ambassador Laquatus", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    laquatus.tap()
    elves.tap()

    # Deepway Navigator has flash and costs {W}{U}; put it straight down for
    # a clean ETB test rather than staging a full mana base.
    navigator = scenario.put_onto_battlefield("Deepway Navigator", "alice", from_zone=Zone.HAND)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not laquatus.tapped, "another Merfolk - untapped"
    assert elves.tapped, "not a Merfolk - stays tapped"
    assert navigator.zone is Zone.BATTLEFIELD


def test_deepway_navigator_does_not_untap_itself():
    scenario = Scenario().player("alice", hand=["Deepway Navigator"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    navigator = scenario.put_onto_battlefield("Deepway Navigator", "alice", from_zone=Zone.HAND)
    navigator.tap()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert navigator.tapped, '"other" excludes the entering Merfolk itself'


# -- "As long as you attacked with three or more Merfolk this turn, Merfolk --
# -- you control get +1/+0." -------------------------------------------------


def test_merfolk_get_pumped_once_three_have_attacked_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Deepway Navigator",
                "Ambassador Laquatus",
                "Caller of Gales",
                "Llanowar Elves",
            ],
        )
        .player("bob")
        .build()
    )
    navigator = scenario.creature("Deepway Navigator", "alice")
    laquatus = scenario.creature("Ambassador Laquatus", "alice")
    caller = scenario.creature("Caller of Gales", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(navigator, laquatus, caller, elves)

    # Three Merfolk attacked (Navigator, Laquatus, Caller of Gales), so all
    # three get the group's own +1/+0; Llanowar Elves is not a Merfolk.
    assert _pt(scenario, navigator) == (3, 2), "2/2 base +1/+0"
    assert _pt(scenario, laquatus) == (2, 3), "1/3 base +1/+0"
    assert _pt(scenario, caller) == (2, 1), "1/1 base +1/+0"
    assert _pt(scenario, elves) == (1, 1), "not a Merfolk - unaffected"


def test_merfolk_are_not_pumped_when_fewer_than_three_attacked():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Deepway Navigator", "Ambassador Laquatus"])
        .player("bob")
        .build()
    )
    navigator = scenario.creature("Deepway Navigator", "alice")
    laquatus = scenario.creature("Ambassador Laquatus", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(navigator, laquatus)

    assert _pt(scenario, navigator) == (2, 2), "only 2 Merfolk attacked"
    assert _pt(scenario, laquatus) == (1, 3)


def test_the_pump_clears_once_a_new_turn_resets_the_count():
    """`Game.turn_counts` is cleared on every new turn the same way `turn_
    facts` already is (both fields' own docstrings); this is not new
    lifecycle code, only a new *reader* of the ledger, so the check reads
    the ledger directly rather than staging a full second turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Deepway Navigator", "Ambassador Laquatus", "Caller of Gales"],
        )
        .player("bob")
        .build()
    )
    navigator = scenario.creature("Deepway Navigator", "alice")
    laquatus = scenario.creature("Ambassador Laquatus", "alice")
    caller = scenario.creature("Caller of Gales", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(navigator, laquatus, caller)
    assert _pt(scenario, navigator) == (3, 2)

    scenario.game.turn_counts = {}
    assert _pt(scenario, navigator) == (2, 2), "no attack-count record for this turn any more"

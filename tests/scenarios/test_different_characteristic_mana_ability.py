"""Loot, the Nexus's mana ability (CR 605.1a, CR 605.3b): "{T}: Choose a
color. Add one mana of that color for each different power among creatures
you control."

The same "Choose a color. Add ... of that color ..." shape Nykthos, Shrine to
Nyx already reads for its own devotion count (`test_devotion_mana_ability.py`)
- CR 605.1a's criteria (no target, could add mana, not a loyalty ability)
make this a genuine mana ability too, so it never uses the stack. What is new
is the count itself: not devotion, but the number of *distinct* power values
among the controller's own creatures (a 1/1, a 1/1, and a 3/3 is two
different powers, not three or one) - `machines/effects._DIFFERENT_
CHARACTERISTIC_AMONG_RE`, the sibling of the already-built "greatest power
among creatures you control" (an extremum, not a count of distinct values).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 605.1a** - the four criteria that make an ability a mana ability.
- **CR 605.3b** - a mana ability resolves immediately, never using the stack.
- **CR 613.5** - power/toughness are read off the computed board (layers),
  not the printed card.
- **CR 208.5** - a creature with no defined power or toughness has 0.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

LOOT = "Loot, the Nexus"
LOOT_ABILITY = 0


def _board(battlefield: list[str]) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", battlefield=battlefield)


def test_two_different_powers_add_two_mana_of_the_chosen_color():
    """Loot (power 2) and a Grizzly Bears (power 2) share one power value;
    a Llanowar Elves (power 1) is a second - two different powers, so
    choosing a color adds two mana of it."""
    scenario = _board([LOOT, "Grizzly Bears", "Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loot = scenario.creature(LOOT, "alice")

    scenario.activate(loot, index=LOOT_ABILITY, color=Color.BLUE)

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 2}


def test_three_creatures_sharing_one_power_add_only_one_mana():
    """Loot, Grizzly Bears, and a second Grizzly Bears are all power 2 - one
    distinct value among three creatures, not three."""
    scenario = _board([LOOT, "Grizzly Bears", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loot = scenario.creature(LOOT, "alice")

    scenario.activate(loot, index=LOOT_ABILITY, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def test_the_chosen_color_pays_for_a_spell():
    """The mana produced is not just recorded - it pays a real cost."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=[LOOT, "Grizzly Bears", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loot = scenario.creature(LOOT, "alice")
    scenario.activate(loot, index=LOOT_ABILITY, color=Color.GREEN)

    casting = scenario.cast("Grizzly Bears", username="alice")
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    second_bears = scenario.resolve_top()

    assert second_bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.total == 0


def test_pumping_a_creature_changes_which_powers_are_different():
    """CR 613.5: the count reads the *computed* board, counters included -
    Llanowar Elves (power 1) gaining a +1/+1 counter matches Loot's own
    power 2 exactly, collapsing what were two distinct powers into one."""
    scenario = _board([LOOT, "Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loot = scenario.creature(LOOT, "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    assert loot.card.power == "2" and elves.card.power == "1"

    scenario.game.add_counters(elves, Counter.PLUS_ONE, 1)
    assert scenario.game.power_of(elves) == 2, "the counter is live on the computed board"

    scenario.activate(loot, index=LOOT_ABILITY, color=Color.WHITE)

    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1}

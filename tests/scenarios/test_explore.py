"""Scenario: explore, the keyword action, and the conditional wipe hung off it.

Explore is one keyword action that branches on a single card's type, and the two
branches differ in more than where the card ends up: only the nonland branch adds
a +1/+1 counter, and only the nonland branch asks its controller a question. A
file that tested the counter and the hand separately would still miss the case
that matters - a land reveal must leave the exploring creature's power alone.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **CR 701.44a** - "Certain spells and abilities instruct a permanent to
  explore. To do so, that permanent's controller reveals the top card of their
  library. If a land card is revealed this way, that player puts that card into
  their hand." Otherwise a +1/+1 counter goes on the exploring permanent and the
  revealed card goes back on top or into the graveyard, at its controller's
  choice.
- **CR 701.44b** - "A permanent 'explores' after the process described in rule
  701.44a is complete, even if some or all of those actions were impossible." An
  empty library is what makes that sentence do work.
- **CR 122.1a** - +1/+1 counters change power and toughness, which is why the
  "exactly 20" check below reads the counter this same resolution just added.
- **CR 704.5b** - a player who tried to draw from an empty library loses. It is
  cited here only to say that explore is *not* a draw, so the empty-library case
  costs nobody the game.

The card is Amalia Benavides Aguirre: "Whenever you gain life, Amalia Benavides
Aguirre explores. Then destroy all other creatures if its power is exactly 20."
The life is gained by attacking with Griselbrand, a real 7/7 with flying and
lifelink, so the trigger fires off a real game event rather than being poked.
Lightning Helix does *not* work here - see the note at the bottom of this file.

Explore's back-or-graveyard half is asked through `Game.look_at_top_and_split`,
which reuses `DecisionKind.SCRY`, so the harness answers it with
`scry_bottoming` / `scry_keeping_everything_on_top`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*library: str, battlefield: list[str] | None = None) -> Scenario:
    """Alice with Amalia and a lifelinker; bob high enough not to die to it."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=list(library),
            battlefield=["Amalia Benavides Aguirre", "Griselbrand", *(battlefield or [])],
        )
        .player("bob", life=40)
    )


def _explore(scenario) -> None:
    """Gain life with lifelink, then resolve Amalia's trigger."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Griselbrand", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    assert [ability.source_name for ability in scenario.pending_triggers] == [
        "Amalia Benavides Aguirre"
    ]
    scenario.pass_priority("alice")
    scenario.resolve_top()


def _library_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").library]


def _hand_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").hand]


def test_a_nonland_on_top_adds_a_counter_and_leaves_it_on_top():
    """The happy path (CR 701.44a): reveal a nonland, counter on, card back.

    "Back on top" is the least destructive of the two options and the default
    this engine takes when nobody answers - see `machines/decisions.py`.
    """
    scenario = _board("Llanowar Elves", "Forest").build()
    _explore(scenario)

    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    assert amalia.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.power_of(amalia) == 3
    assert _library_names(scenario) == ["Llanowar Elves", "Forest"]
    assert _hand_names(scenario) == []


def test_a_land_on_top_goes_to_hand_and_adds_no_counter():
    """CR 701.44a's land branch stops at the hand.

    The +1/+1 counter belongs to the *other* branch only. A model that added it
    unconditionally would still pass a test that only checked the hand, so the
    absence of the counter is asserted here rather than assumed.
    """
    scenario = _board("Forest", "Llanowar Elves").build()
    _explore(scenario)

    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    assert Counter.PLUS_ONE not in amalia.counters
    assert scenario.game.power_of(amalia) == 2
    assert _hand_names(scenario) == ["Forest"]
    assert _library_names(scenario) == ["Llanowar Elves"]


def test_no_question_is_asked_when_the_revealed_card_is_a_land():
    """The land branch never reaches the back-or-graveyard question.

    Asserting on what was *not* asked is the only way to tell "the question was
    asked and answered with the default" apart from "the branch was never
    entered at all" - both leave the same board.
    """
    scenario = _board("Forest", "Llanowar Elves").build()
    _explore(scenario)

    assert scenario.questions_asked() == []


def test_the_controller_may_send_the_revealed_nonland_to_the_graveyard():
    """CR 701.44a leaves the destination to the controller: back, or binned.

    The counter is added either way - it is not contingent on the destination,
    and the graveyard branch is a real zone change (CR 400.7), so the card is
    looked for in the graveyard rather than trusted to be the same object.
    """
    scenario = _board("Llanowar Elves", "Forest").build()
    (elves,) = scenario.top_of_library(1)
    scenario.scry_bottoming(elves)

    _explore(scenario)

    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    assert amalia.counters[Counter.PLUS_ONE] == 1
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _library_names(scenario) == ["Forest"]


def test_an_empty_library_still_explores_and_does_nothing():
    """CR 701.44b: it explored, even though every action was impossible.

    Nothing to reveal means no counter, no card in hand, no card in the
    graveyard - and no error. Explore is not a draw, so CR 704.5b's loss for
    drawing from an empty library never comes near this.
    """
    scenario = _board().build()
    _explore(scenario)

    alice = scenario.player("alice")
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    assert Counter.PLUS_ONE not in amalia.counters
    assert alice.library == []
    assert alice.hand == []
    assert alice.graveyard == []
    assert alice.tried_to_draw_from_empty_library is False
    assert scenario.state_based_actions() == []


def test_the_wipe_does_not_fire_at_a_power_that_is_merely_close():
    """ "if its power is exactly 20" is an equality, not a threshold.

    Eighteen staged counters make Amalia a 20 *before* she explores, and the
    explore's own nineteenth counter takes her to 21 - past the condition
    rather than onto it. A model reading the condition as ">= 20", or checking
    it before the explore instead of after, destroys the board here.
    """
    scenario = _board("Llanowar Elves", "Forest", battlefield=["Grizzly Bears"]).build()
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    scenario.game.add_counters(amalia, Counter.PLUS_ONE, 18)
    assert scenario.game.power_of(amalia) == 20

    _explore(scenario)

    assert scenario.game.power_of(amalia) == 21
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_the_wipe_does_not_fire_at_the_printed_power():
    """The ordinary case: a 3-power Amalia leaves the board alone."""
    scenario = _board("Llanowar Elves", "Forest", battlefield=["Grizzly Bears"]).build()
    _explore(scenario)

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.creature("Griselbrand", "alice").zone is Zone.BATTLEFIELD


def test_the_wipe_reads_the_power_the_explore_itself_produced():
    """The *if* is checked after the explore, so the new counter counts.

    Amalia is a printed 2/2 and CR 122.1a stacks counters on top of that. With
    seventeen counters staged on the board she is a 19; the explore's own
    eighteenth counter is what takes her to exactly 20 and fires the wipe.
    """
    scenario = _board("Llanowar Elves", "Forest", battlefield=["Grizzly Bears"]).build()
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    scenario.game.add_counters(amalia, Counter.PLUS_ONE, 17)
    assert scenario.game.power_of(amalia) == 19

    _explore(scenario)

    assert scenario.game.power_of(amalia) == 20
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_the_exploring_creature_survives_its_own_wipe():
    """ "all *other* creatures" excludes the permanent that explored.

    The first sentence names Amalia, and CR 201.5 makes text referring to an
    object by its own name mean that particular object; "its" in the second
    sentence is the same one. So the creature whose power set the condition is
    the one creature the destruction skips.
    """
    scenario = _board("Llanowar Elves", "Forest", battlefield=["Grizzly Bears"]).build()
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    scenario.game.add_counters(amalia, Counter.PLUS_ONE, 17)

    _explore(scenario)

    assert amalia.zone is Zone.BATTLEFIELD
    assert scenario.battlefield_names().count("Amalia Benavides Aguirre") == 1


def test_a_land_reveal_leaves_the_power_one_short_and_spares_the_board():
    """The same board, one card different on top, and nothing dies.

    The land branch adds no counter (CR 701.44a), so Amalia stays a 19 and the
    condition never holds. This is the cleanest proof that it is the explore's
    own counter doing the work in the test above, not the staged seventeen.
    """
    scenario = _board("Forest", "Llanowar Elves", battlefield=["Grizzly Bears"]).build()
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    scenario.game.add_counters(amalia, Counter.PLUS_ONE, 17)

    _explore(scenario)

    assert scenario.game.power_of(amalia) == 19
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert _hand_names(scenario) == ["Forest"]


def test_the_wipe_takes_creatures_both_players_control():
    """ "All other creatures" is not limited to the controller's own.

    Nothing in the sentence restricts it, so the opponent's board goes too.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Llanowar Elves", "Forest"],
            battlefield=["Amalia Benavides Aguirre", "Griselbrand"],
        )
        .player("bob", life=40, battlefield=["Grizzly Bears"])
        .build()
    )
    amalia = scenario.creature("Amalia Benavides Aguirre", "alice")
    scenario.game.add_counters(amalia, Counter.PLUS_ONE, 17)

    _explore(scenario)

    assert scenario.game.power_of(amalia) == 20
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert "Griselbrand" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# The note the module docstring points at.
#
# CR 119.9 reads "Whenever you gain life" as "whenever a source causes you to
# gain life" - it does not care which effect did it. In this engine only
# `Game.gain_life` emits `TriggerEvent.GAINS_LIFE`, and the parsed "you gain N
# life" clause in `machines/effects.py` calls `Player.gain_life` directly
# instead, so a spell that says so in plain text never fires the trigger.
# Lifelink (`machines/combat.py`) does go through `Game.gain_life`, which is
# why every test above attacks with Griselbrand.


def test_life_gained_by_a_spell_triggers_the_explore_too():
    """Lightning Helix's "you gain 3 life" is a life gain like any other.

    CR 119.9: "Some triggered abilities are written, 'Whenever [a player]
    gains life, . . . .' Such abilities are treated as though they are
    written, 'Whenever a source causes [a player] to gain life, . . . .'" -
    no condition on *which* source, so a spell's own clause fires Amalia
    exactly as lifelink does. `machines/effects.py`'s parsed "you gain N
    life" clause used to call `Player.gain_life` directly, which adjusts the
    total (CR 119.3) but emits nothing; it goes through `Game.gain_life` now.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Llanowar Elves", "Forest"],
            hand=["Lightning Helix"],
            battlefield=["Amalia Benavides Aguirre", "Mountain", "Plains"],
        )
        .player("bob", life=40)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Plains")
    scenario.cast_and_resolve("Lightning Helix", *sources, targets=["bob"])

    assert scenario.player("alice").life == 23
    # `cast_and_resolve` runs through to the next priority, which is exactly
    # where CR 603.3 puts a waiting trigger on the stack.
    assert scenario.stack_names() == ["Amalia Benavides Aguirre's triggered ability"]

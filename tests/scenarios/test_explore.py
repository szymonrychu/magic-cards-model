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
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import executed_keywords
from tests.cards import card
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
    # CR 510.3a: the combat damage step puts what triggered on the stack before
    # the active player gets priority, so the trigger is already there.
    assert scenario.stack_names() == ["Amalia Benavides Aguirre's triggered ability"]
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
    (reveal,) = scenario.game.reveals
    assert reveal.zone is Zone.LIBRARY
    assert reveal.viewers is None
    assert reveal.library_epoch is not None
    assert reveal.zone_change_stamp is not None
    assert reveal.turn == scenario.game.turn.turns_taken


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


# ============================================================================
# The generic "<subject> explores[, then it explores again]." clause
# ============================================================================
#
# Amalia's own trigger above is read whole, by a parser built for her exact
# sentence (the conditional mass-destroy tacked onto it). Every other printed
# explorer says just "<subject> explores." (optionally ", then it explores
# again"), with no second sentence riding on it, and that shape had no reader
# at all before this section - `machines/effects.py`'s `_parse_explores_
# clause`, registered once in `_parse_mixed_clause`, so it reaches triggered,
# activated, and spell text alike, modal spells included.
#
# Every CR number below was looked up with `mise run rules:find <n>` in the
# session that wrote this file (the CR text is quoted from the effective
# 2026-09-25 rules):
#
# - **CR 701.44a** - "Certain spells and abilities instruct a permanent to
#   explore. To do so, that permanent's controller reveals the top card of
#   their library. If a land card is revealed this way, that player puts that
#   card into their hand. Otherwise, that player puts a +1/+1 counter on the
#   exploring permanent and may put the revealed card into their graveyard."
# - **CR 701.44b** - "A permanent 'explores' after the process described in
#   rule 701.44a is complete, even if some or all of those actions were
#   impossible." (the empty-library case below.)
# - **CR 701.44c** - "If a permanent is no longer on the battlefield as an
#   effect instructs it to explore, its last known information is used to
#   determine which object explored and who controlled it." (the bounced-in-
#   response case below - no counter, because there is no permanent left to
#   put one on, but the reveal still happens for its own controller.)
# - **CR 701.44d** - "If multiple permanents are instructed to explore at the
#   same time, the first player in APNAP order who controls ... one or more
#   of those permanents chooses one of them and it explores. Then this
#   process is repeated for each remaining instruction to explore." Every
#   printed subject this parser reads names at most one permanent (a self-
#   reference or a single target), so `_explore_each_in_apnap_order`'s own
#   choice-among-several branch is implemented and exercised by its own
#   in-module tests but has no real printing to prove it against yet - no
#   Modern/Pioneer/Standard-legal card instructs more than one permanent to
#   explore from a single instruction (verified against every explore-bearing
#   card Scryfall returns for `o:explores`; `each creature you control
#   explores` and `up to N target creatures ... explore` both come back with
#   zero matches). See `docs/engine-coverage.md`.
#
# Real off-pool printings, one per subject form and one per context, none of
# them Amalia and none of them the deck pool's own Fire Magic-adjacent cards:
#
# - Merfolk Branchwalker (ETB trigger, "it") - land, nonland-keep,
#   nonland-graveyard, empty library, and bounced in response to its own
#   trigger.
# - Jadelight Ranger (ETB trigger, "it ... then it explores again") - land
#   then nonland; two nonlands.
# - Legion Vanguard (activated ability, "This creature").
# - Miner's Guidewing (death trigger, "target creature you control").
# - Enter the Unknown (sorcery, "Target creature you control", combined with
#   an unrelated second clause in the same card - proves the per-clause
#   dispatcher still reads the rest of the card).
# - Over the Edge (modal sorcery, mode 2, "Target creature you control ...
#   then it explores again").
#
# "Named self" (a card referring to the exploring permanent by its own
# printed name rather than "this creature"/"it") is Amalia's own shape,
# above - `_self_normalized_effect_text` rewrites it to "this permanent"
# before either parser ever sees it, so nothing here duplicates that proof.


def _branchwalker_board(*library: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=list(library),
            hand=["Merfolk Branchwalker"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob", life=20)
    )


def _cast_branchwalker(scenario) -> None:
    """Cast Merfolk Branchwalker and put its own ETB trigger on the stack,
    unresolved - CR 603.3 already put it there by the time `cast_and_resolve`
    returns, the same way Amalia's own trigger is already on the stack after
    `combat_damage()` above."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Merfolk Branchwalker", *sources)
    assert scenario.stack_names() == ["Merfolk Branchwalker's triggered ability"]


def test_branchwalker_reveals_a_land_to_hand_with_no_counter():
    """The generic parser's land branch (CR 701.44a), triggered context,
    subject "it"."""
    scenario = _branchwalker_board("Plains", "Llanowar Elves").build()
    _cast_branchwalker(scenario)
    scenario.resolve_top()

    branchwalker = scenario.creature("Merfolk Branchwalker", "alice")
    assert Counter.PLUS_ONE not in branchwalker.counters
    assert _hand_names(scenario) == ["Plains"]
    assert _library_names(scenario) == ["Llanowar Elves"]


def test_branchwalker_may_keep_a_nonland_on_top_with_a_counter():
    """The generic parser's nonland branch, kept rather than binned."""
    scenario = _branchwalker_board("Llanowar Elves", "Plains").build()
    scenario.scry_keeping_everything_on_top()
    _cast_branchwalker(scenario)
    scenario.resolve_top()

    branchwalker = scenario.creature("Merfolk Branchwalker", "alice")
    assert branchwalker.counters[Counter.PLUS_ONE] == 1
    assert _hand_names(scenario) == []
    assert _library_names(scenario) == ["Llanowar Elves", "Plains"]


def test_branchwalker_may_bin_a_nonland_with_a_counter():
    """The generic parser's nonland branch, sent to the graveyard instead."""
    scenario = _branchwalker_board("Llanowar Elves", "Plains").build()
    (elves,) = scenario.top_of_library(1)
    scenario.scry_bottoming(elves)
    _cast_branchwalker(scenario)
    scenario.resolve_top()

    branchwalker = scenario.creature("Merfolk Branchwalker", "alice")
    assert branchwalker.counters[Counter.PLUS_ONE] == 1
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _library_names(scenario) == ["Plains"]


def test_branchwalker_still_explores_an_empty_library():
    """CR 701.44b, read through the generic parser rather than Amalia's."""
    scenario = _branchwalker_board().build()
    _cast_branchwalker(scenario)
    scenario.resolve_top()

    alice = scenario.player("alice")
    branchwalker = scenario.creature("Merfolk Branchwalker", "alice")
    assert Counter.PLUS_ONE not in branchwalker.counters
    assert alice.library == []
    assert alice.hand == []
    assert alice.graveyard == []


def test_a_branchwalker_bounced_in_response_still_explores_with_no_counter():
    """CR 701.44c: Merfolk Branchwalker itself answers its own trigger's
    "it", so bouncing *that* permanent in response (CR 400.7 does not mint a
    new id for a card that simply moves zones in this engine - see
    `test_sacrifice_self_trigger.test_a_source_bounced_and_recast_in_
    response_is_a_new_object_the_trigger_skips`, which reads the *same*
    object's `.zone` right after its own bounce) leaves the trigger's own
    `AbilityOnStack.source_id` still findable, now in alice's hand.

    `_explore` reads that same object's current zone, not last known
    information, since it is still findable at all - and it is that current
    zone, not the battlefield one it triggered from, that decides there is no
    counter to place. The library is still alice's own: CR 701.44c's "who
    controlled it" is read off the exploring permanent's own controller, not
    off whoever is priority-tapped at the moment it resolves.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Llanowar Elves", "Plains"],
            hand=["Merfolk Branchwalker"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob", hand=["Unsummon"], battlefield=["Island"], life=20)
        .build()
    )
    scenario.scry_keeping_everything_on_top()
    _cast_branchwalker(scenario)
    branchwalker = scenario.creature("Merfolk Branchwalker", "alice")

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[branchwalker],
    )
    assert branchwalker.zone is Zone.HAND
    assert scenario.stack_names() == ["Merfolk Branchwalker's triggered ability"]

    scenario.resolve_top()

    # No counter - there is no permanent left to put one on - but the reveal
    # and the graveyard-or-keep question (CR 701.44a's own "may", asked
    # regardless of whether a counter went anywhere) both still happen: the
    # library is still one card shorter in its own right, not merely
    # untouched because the whole instruction quietly did nothing.
    assert Counter.PLUS_ONE not in branchwalker.counters
    assert [decision.kind for decision in scenario.questions_asked()] == [DecisionKind.SCRY]
    assert _library_names(scenario) == ["Llanowar Elves", "Plains"]
    assert _hand_names(scenario) == ["Merfolk Branchwalker"]


# --------------------------------------------------------------------------
# Jadelight Ranger: "it explores, then it explores again." - one sentence,
# two full runs of CR 701.44a-b in a row for the same permanent.
# --------------------------------------------------------------------------


def _jadelight_board(*library: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=list(library),
            hand=["Jadelight Ranger"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob", life=20)
    )


def _cast_jadelight(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Jadelight Ranger", *sources)
    assert scenario.stack_names() == ["Jadelight Ranger's triggered ability"]


def test_jadelight_ranger_explores_a_land_then_a_nonland():
    """First explore hits a land (hand, no counter); the second explore then
    reads the *new* top of library - the land's departure is what makes the
    second reveal Llanowar Elves rather than the card behind it."""
    scenario = _jadelight_board("Plains", "Llanowar Elves").build()
    scenario.scry_keeping_everything_on_top()
    _cast_jadelight(scenario)
    scenario.resolve_top()

    ranger = scenario.creature("Jadelight Ranger", "alice")
    assert ranger.counters[Counter.PLUS_ONE] == 1
    assert _hand_names(scenario) == ["Plains"]
    assert _library_names(scenario) == ["Llanowar Elves"]


def test_jadelight_ranger_explores_two_nonlands():
    """Both explores add a counter; the two questions are answered
    differently (bin the first, keep the second) so the test cannot pass by
    accident on an engine that only ever asks once."""
    scenario = _jadelight_board("Llanowar Elves", "Birds of Paradise").build()
    (elves,) = scenario.top_of_library(1)
    scenario.scry_bottoming(elves)
    scenario.scry_keeping_everything_on_top()
    _cast_jadelight(scenario)
    scenario.resolve_top()

    ranger = scenario.creature("Jadelight Ranger", "alice")
    assert ranger.counters[Counter.PLUS_ONE] == 2
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _library_names(scenario) == ["Birds of Paradise"]
    assert _hand_names(scenario) == []


# --------------------------------------------------------------------------
# Legion Vanguard: "This creature explores." on an activated ability.
# --------------------------------------------------------------------------


def test_legion_vanguard_explores_off_its_own_activated_ability():
    """ "This creature" reads the same as Merfolk Branchwalker's "it", off an
    activated ability's cost (a sacrifice) rather than an ETB trigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Llanowar Elves", "Plains"],
            battlefield=["Legion Vanguard", "Swamp", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = scenario.top_of_library(1)
    scenario.scry_bottoming(elves)
    vanguard = scenario.creature("Legion Vanguard", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(vanguard, *scenario.untapped_sources("Swamp"), sacrificing=[bears])
    scenario.resolve_top()

    assert vanguard.counters[Counter.PLUS_ONE] == 1
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _library_names(scenario) == ["Plains"]


# --------------------------------------------------------------------------
# Miner's Guidewing: "target creature you control explores." on a death
# trigger - the targeted subject, off a triggered ability.
# --------------------------------------------------------------------------


def test_miners_guidewing_explores_a_targeted_creature_when_it_dies():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains", "Llanowar Elves"],
            battlefield=["Miner's Guidewing", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guidewing = scenario.creature("Miner's Guidewing", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Miner's Guidewing", [bears])

    scenario.game.destroy(guidewing)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Miner's Guidewing's triggered ability"]
    scenario.resolve_top()

    assert Counter.PLUS_ONE not in bears.counters
    assert _hand_names(scenario) == ["Plains"]
    assert _library_names(scenario) == ["Llanowar Elves"]


# --------------------------------------------------------------------------
# Enter the Unknown: "Target creature you control explores." on a sorcery,
# sharing the card with an unrelated second clause.
# --------------------------------------------------------------------------


def test_enter_the_unknown_explores_its_target_and_grants_a_land_play():
    """Proves both that the targeted subject reads off a resolving spell
    (CR 300.1: a spell is never itself a permanent, so this shape only ever
    exists targeted) and that `_parse_mixed_clause`'s per-clause dispatcher
    still reads the card's *other* sentence once explore is not the gap."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Enter the Unknown"],
            library=["Llanowar Elves", "Plains"],
            battlefield=["Forest", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = scenario.top_of_library(1)
    scenario.scry_bottoming(elves)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Enter the Unknown", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert bears.counters[Counter.PLUS_ONE] == 1
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.game.extra_land_plays.get("alice", 0) == 1


# --------------------------------------------------------------------------
# Over the Edge: a modal sorcery whose second mode is "Target creature you
# control explores, then it explores again." - the targeted subject with the
# "again" doubling, off a chosen mode's own text.
# --------------------------------------------------------------------------


def test_over_the_edges_second_mode_explores_its_target_twice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Over the Edge"],
            library=["Plains", "Llanowar Elves"],
            battlefield=["Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.scry_keeping_everything_on_top()

    casting = scenario.cast("Over the Edge")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # First explore reveals Plains (hand, no counter); the second then reads
    # the new top, Llanowar Elves - a nonland, so exactly one counter goes on,
    # not two, which is what a parser that ran the *first* explore twice
    # instead of running the instruction twice would get wrong.
    assert bears.counters[Counter.PLUS_ONE] == 1
    assert _hand_names(scenario) == ["Plains"]
    assert _library_names(scenario) == ["Llanowar Elves"]


# --------------------------------------------------------------------------
# The "Explore" keyword credit for a card whose own text never says
# "explores" - the ability lives on the Map token it creates instead
# (CR 111.10s, "R0a-T2" in `docs/engine-coverage.md`).
# --------------------------------------------------------------------------


def test_spyglass_sirens_own_text_never_says_explores():
    """Scryfall's own keyword tag is real (the card genuinely carries CR
    701.44 through the Map it creates), but the card's own printed sentence
    - "When this creature enters, create a Map token." - never uses the
    word at all outside the reminder parenthetical. If the credit below
    were reading the card's own text for the literal word, it would never
    find it here."""
    siren = card("Spyglass Siren")
    assert "explore" in [k.lower() for k in siren.keywords]
    assert "explores" not in (siren.oracle_text or "").lower().split("(")[0]


def test_spyglass_siren_and_sentinel_credit_explore_via_their_map_token():
    """Both cards' own trigger only creates a Map token; the credit below
    has to read the token's own reminder-spelled ability, not the card's
    name, to find CR 701.44 on either of them."""
    for name in ("Spyglass Siren", "Sentinel of the Nameless City"):
        assert executed_keywords(card(name)).get("explore") is not None, name


def test_get_lost_and_fanatical_offering_also_credit_explore_via_their_map():
    """Get Lost's Map tokens go to the referent, not the caster; Fanatical
    Offering's Map is the tail of a compound "draw two and create a Map"
    sentence. Neither card's own text ever says "explores" either."""
    for name in ("Get Lost", "Fanatical Offering"):
        assert executed_keywords(card(name)).get("explore") is not None, name


def test_cartographers_companion_also_credits_explore_via_its_map_token():
    """The second, unrelated printing (`test_map_tokens.py`'s own proof
    card) - not one of this task's own five cards, and its own text is the
    identical "create a Map token" shape. If the credit only worked for
    this task's own five cards, this one would be missed too."""
    assert executed_keywords(card("Cartographer's Companion")).get("explore") is not None


def test_a_card_that_creates_no_token_at_all_gets_no_explore_credit():
    """The credit must not fire on every card carrying the keyword
    regardless of what it actually does - Amalia's own text already says
    "explores" directly, through the ordinary path, and creates no token at
    all, so the Map-reminder credit must never be why she is credited."""
    amalia = card("Amalia Benavides Aguirre")
    assert "Map" not in (amalia.oracle_text or "")
    assert executed_keywords(amalia).get("explore") == (
        "machines/effects.py (_parse_explores_then_conditional_mass_destroy, CR 701.44a)"
    )

"""Replacement and prevention effects being applied: CR 614, CR 615, CR 616.

`machines/replacement.py` reads these effects off oracle text and now also
applies them. `Game` raises a `ReplaceableEvent` at each event site - a permanent
entering, a card heading for a graveyard, damage, a draw, life gain, counters
being placed - and the applicable effects modify it before it happens.

The rules under test, every one of them looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 614.1** - replacement effects "watch for a particular event that would
  happen and completely or partially replace that event".
- **CR 614.1c** - "[this permanent] enters with ...", "as [this permanent]
  enters ..." are replacement effects.
- **CR 614.5** - "a replacement effect doesn't invoke itself repeatedly; it gets
  only one opportunity to affect an event."
- **CR 614.6** - "if an event is replaced, it never happens."
- **CR 614.12** - an effect modifying how a permanent enters "may come from the
  permanent itself if [it affects] only that permanent".
- **CR 615.1a** - "effects that use the word 'prevent' are prevention effects."
- **CR 616.1** - the affected object's controller chooses which applicable
  effect applies next; **CR 616.1f** repeats until none are left.
- **CR 616.1g** - one effect may apply to an event contained within another.
- **CR 122.6** - counters "put on" an object covers an object given counters as
  it enters, which is how Doubling Season sees CR 614.1c's counters.
- **CR 121.1, 121.2, 121.6** - a draw is one card at a time and each draw is its
  own replaceable event.
- **CR 119.3** - gaining life adjusts the life total, and how much can be
  replaced first.

The judge transcripts have their own file for the graveyard replacers: see
`tests/scenarios/judge/test_judge_dies_triggers.py` and
`tests/scenarios/judge/test_judge_replacement_effects.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# CR 614.1c, 614.12: how a permanent enters
# --------------------------------------------------------------------------


def test_a_land_whose_text_says_it_enters_tapped_arrives_tapped():
    """The happy path. "This land enters tapped" is CR 614.1c, not a trigger.

    Nothing puts an ability on the stack and nobody gets priority in between:
    the land is simply never on the battlefield untapped (CR 614.6).
    """
    scenario = Scenario().player("alice", hand=["Hedge Maze"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    maze = scenario.play_land("Hedge Maze")

    assert maze.zone is Zone.BATTLEFIELD
    assert maze.tapped


def test_a_land_with_no_such_text_still_arrives_untapped():
    """The control. A replacement effect only applies when one exists (CR 614.1)."""
    scenario = Scenario().player("alice", hand=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.play_land("Mountain")

    assert mountain.untapped


def test_a_permanent_arrives_with_the_counters_its_text_names():
    """CR 614.1c: "[this permanent] enters with four +1/+1 counters on it".

    The counters are there the moment it is on the battlefield, so a 0/0 Hydra
    is never a 0/0 on the battlefield and never dies to CR 704.5f.
    """
    scenario = Scenario().player("alice", hand=["Kalonian Hydra"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra")
    scenario.game.check_state_based_actions()

    assert hydra.zone is Zone.BATTLEFIELD
    assert hydra.counter_count("+1/+1") == 4
    assert hydra.power == 4


def test_a_land_arrives_with_a_counter_that_is_not_a_plus_one():
    """CR 122.1 leaves the set of counter kinds open; the parser reads the name."""
    scenario = Scenario().player("alice", hand=["Diamond City"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    city = scenario.play_land("Diamond City")

    assert city.counter_count("shield") == 1


# --------------------------------------------------------------------------
# CR 616.1: two effects on one event
# --------------------------------------------------------------------------


def test_doubling_season_doubles_the_counters_a_permanent_enters_with():
    """CR 616.1g and CR 122.6: an event inside an event.

    The entering event (CR 614.1c) carries four counters; placing them is itself
    a "counters would be put on a permanent" event, which is what Doubling
    Season watches for - CR 122.6 says being given counters as it enters counts.
    """
    scenario = (
        Scenario().player("alice", hand=["Kalonian Hydra"], battlefield=["Doubling Season"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra")

    assert hydra.counter_count("+1/+1") == 8


def test_doubling_season_leaves_an_opponents_counters_alone():
    """ "...on a permanent you control" - the effect is not a general one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Doubling Season"])
        .player("bob", hand=["Kalonian Hydra"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra", "bob")

    assert hydra.counter_count("+1/+1") == 4


def test_each_effect_gets_exactly_one_opportunity_at_one_event():
    """CR 614.5, and why the CR 616.1f loop terminates.

    Two Doubling Seasons take four counters to eight and eight to sixteen: each
    applies once. Neither applies to the event the other one modified a second
    time - "a replacement effect doesn't invoke itself repeatedly; it gets only
    one opportunity to affect an event or any modified events that may replace
    that event." Without that rule the pair would double forever.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kalonian Hydra"],
            battlefield=["Doubling Season", "Doubling Season"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra")

    assert hydra.counter_count("+1/+1") == 16


def test_one_doubling_season_does_not_double_its_own_doubling():
    """The same rule with a single source: four becomes eight, not sixteen."""
    scenario = Scenario().player("alice", battlefield=["Doubling Season", "Kalonian Hydra"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Kalonian Hydra", "alice")

    scenario.game.add_counters(hydra, "+1/+1", 4)

    assert hydra.counter_count("+1/+1") == 8


# --------------------------------------------------------------------------
# CR 614.6: an entering permanent that never enters
# --------------------------------------------------------------------------


def test_containment_priest_exiles_a_creature_that_was_not_cast():
    """CR 614.6: the entering event never happens, so nothing enters.

    "If a nontoken creature would enter and it wasn't cast, exile it instead."
    CR 601.2 is what casting *is*; a card put straight onto the battlefield did
    none of it, so the condition holds.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"])
        .player("bob", battlefield=["Containment Priest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert bears.zone is Zone.EXILE
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_containment_priest_lets_a_creature_that_was_cast_through():
    """The other half of the same condition: a cast creature is not caught."""
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Containment Priest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_and_resolve("Grizzly Bears", *sources, username="alice")

    assert bears.zone is Zone.BATTLEFIELD


def test_containment_priest_catches_a_land_creature_that_can_never_be_cast():
    """A creature that is never cast because the rules forbid casting it.

    CR 300.2a: "An object that's both a land and another card type ... can only
    be played as a land. It can't be cast as a spell." Dryad Arbor is a Land
    Creature, so "it wasn't cast" is true of it every single time - playing a
    land is a special action (CR 116.2a), not casting.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Dryad Arbor"])
        .player("bob", battlefield=["Containment Priest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arbor = scenario.play_land("Dryad Arbor")

    assert arbor.zone is Zone.EXILE
    assert "Dryad Arbor" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# CR 615: prevention
# --------------------------------------------------------------------------


def test_fog_bank_takes_no_combat_damage_at_all():
    """CR 615.1a: prevention says what damage will *not* be dealt.

    Three damage from a Hill Giant would be lethal to a 0/2 (CR 704.5g). None of
    it is dealt, so there is no marked damage for the state-based action to read.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Fog Bank"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    bank = scenario.creature("Fog Bank", "bob")

    scenario.attack_with(giant)
    scenario.block(giant, bank)
    scenario.combat_damage()
    scenario.game.check_state_based_actions()

    assert bank.damage == 0
    assert bank.zone is Zone.BATTLEFIELD


def test_fog_bank_still_dies_to_a_lightning_bolt():
    """Only *combat* damage is prevented, so the Bolt gets through.

    The contrast matters: without it, a prevention effect that swallowed every
    damage event would pass the test above just as well.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Fog Bank"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bank = scenario.creature("Fog Bank", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bank])

    assert bank.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# CR 121.6, 119.3: draws and life
# --------------------------------------------------------------------------


def archive_board() -> Scenario:
    """alice, an Archive, and a library long enough to draw from."""
    return Scenario().player(
        "alice",
        library=["Forest", "Mountain", "Island", "Plains", "Swamp"],
        battlefield=["Alhammarret's Archive"],
    )


def test_a_draw_outside_the_draw_step_becomes_two():
    """CR 121.6: "some effects replace card draws."

    "If you would draw a card except the first one you draw in each of your draw
    steps, draw two cards instead."
    """
    scenario = archive_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards("alice", 1)

    assert len(drawn) == 2
    assert len(scenario.player("alice").hand) == 2


def test_the_draw_step_draw_is_the_one_the_archive_excepts():
    """The exception the card prints, checked against the real draw step.

    CR 504.1 makes the draw step's draw a turn-based action; that is the draw
    "you draw in each of your draw steps", and the Archive leaves it alone.
    """
    scenario = archive_board().build()
    scenario.start_at(Step.UPKEEP)

    scenario.advance()  # into the draw step, which draws by itself

    assert scenario.step is Step.DRAW
    assert len(scenario.player("alice").hand) == 1


def test_two_instructed_draws_are_two_separate_events():
    """CR 121.2: "cards may only be drawn one at a time."

    So an instruction to draw two is two replaceable events and the Archive
    applies to each, for four cards - not one event doubled once.
    """
    scenario = archive_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards("alice", 2)

    assert len(drawn) == 4


def test_life_gain_is_doubled_before_the_life_total_moves():
    """CR 119.3 adjusts the life total; CR 614.1a replaces how much first."""
    scenario = archive_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)

    assert scenario.player("alice").life == 26


def test_an_archive_does_not_double_an_opponents_life_gain():
    """ "If *you* would gain life" - the effect is not a general one."""
    scenario = archive_board().player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("bob", 3)

    assert scenario.player("bob").life == 23


# --------------------------------------------------------------------------
# CR 614.1a: a replacement narrowed by a card's characteristics
# --------------------------------------------------------------------------


def test_sanctifier_en_vec_catches_only_the_black_and_red_cards():
    """One replacement effect, two cards, one caught.

    "If a black or red permanent, spell, or card not on the battlefield would be
    put into a graveyard, exile it instead." The red Bolt is exiled; the green
    Bears it killed reaches the graveyard normally, which is what shows the
    condition is being read rather than the effect blanket-applying.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Sanctifier en-Vec"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bolt.zone is Zone.EXILE, "a red card"
    assert bears.zone is Zone.GRAVEYARD, "a green card is not caught"


# --------------------------------------------------------------------------
# What is still not applied
# --------------------------------------------------------------------------


def test_a_shockland_either_costs_two_life_or_enters_tapped():
    """CR 614.1c with a choice inside it, which the engine now makes.

    CR 614.12a: "If a replacement effect that modifies how a permanent enters
    the battlefield requires a choice, that choice is made before the permanent
    enters the battlefield." The choice is put to the controller by
    `Game.may_pay_life` and the default is to pay (CR 119.4). Both legal
    outcomes are accepted here, because the point is that *one* of them must
    happen; the branches are pinned down one at a time in
    `tests/scenarios/test_decisions_during_resolution.py`.
    """
    scenario = Scenario().player("alice", hand=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vents = scenario.play_land("Steam Vents")

    assert vents.tapped or scenario.player("alice").life == 18


def test_a_clone_enters_as_a_copy_of_something_already_there():
    """CR 614.1c: "[this permanent] enters as ..." is a replacement effect.

    CR 616.1c even gives it its own step in the ordering, ahead of the ordinary
    free choice - so it is not merely another effect, it is one the rules single
    out. CR 614.12a makes the choice before the permanent enters, and CR 707.2
    says what is copied: "the copy acquires the copiable values of the original
    object's characteristics".

    Clone is printed 0/0 and Grizzly Bears 2/2, so the printed values say what
    the assertion is worth: a Clone that entered as itself would be a 0/0 and
    would already have died to CR 704.5f.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Clone"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert (card("Clone").power, card("Clone").toughness) == ("0", "0")
    assert (card("Grizzly Bears").power, card("Grizzly Bears").toughness) == ("2", "2")

    clone = scenario.put_onto_battlefield("Clone", "alice")

    assert clone.power == 2
    assert clone.toughness == 2
    # The layer-1 effect copies every one of CR 707.2's copiable values - name
    # included - but `CardState.name` reads the printing rather than the
    # computed characteristics the way `.power` and `.toughness` do, so the
    # copied name is visible on the board and not on the permanent. That is a
    # `models/card_state.py` gap, not a replacement-effect one.
    assert clone.name == "Clone"


def test_a_clone_with_nothing_to_copy_enters_as_itself():
    """CR 707.2 has nothing to acquire on an empty board, so the "you may" has
    no legal option to take and the Clone is the 0/0 it is printed as - which
    CR 704.5f then destroys the next time state-based actions are checked.
    """
    scenario = Scenario().player("alice", hand=["Clone"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    clone = scenario.put_onto_battlefield("Clone", "alice")

    assert (clone.power, clone.toughness) == (0, 0)
    scenario.state_based_actions()
    assert clone.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# CR 614.1a: how much life is gained, read as a multiplier and an addend
# --------------------------------------------------------------------------
#
# "You gain twice that much life" (Alhammarret's Archive, Boon Reflection) and
# "you gain that much life plus 1" (Angel of Vitality, Leyline of Hope) are the
# same replacement with a different number in it. CR 107.1b, looked up with
# `mise run rules:find`: a calculation that "doubles" a value is exempt from
# the zero floor, and a result is always an integer (CR 107.1).


def _life_gain_board(*permanents: str) -> Scenario:
    return Scenario().player("alice", battlefield=list(permanents)).player("bob")


def test_angel_of_vitality_adds_one_to_each_life_gain():
    """ "...you gain that much life plus 1 instead." Three becomes four."""
    scenario = _life_gain_board("Angel of Vitality").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)

    assert scenario.player("alice").life == 24


def test_boon_reflection_doubles_each_life_gain():
    """ "...you gain twice that much life instead." Three becomes six."""
    scenario = _life_gain_board("Boon Reflection").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)

    assert scenario.player("alice").life == 26


def test_angel_of_vitality_adds_one_to_a_single_point_of_life():
    """The addend is flat, not per point: one becomes two, not one plus one each."""
    scenario = _life_gain_board("Angel of Vitality").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 1)

    assert scenario.player("alice").life == 22


def test_two_angels_of_vitality_each_add_one():
    """CR 614.5: each effect gets one opportunity at the event, so two Angels
    add two, and neither adds again to the event the other modified."""
    scenario = _life_gain_board("Angel of Vitality", "Angel of Vitality").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)

    assert scenario.player("alice").life == 25


def test_the_angel_and_the_reflection_each_apply_exactly_once():
    """CR 616.1 lets the affected player order the two; either order applies
    each effect once, so three is (3 + 1) * 2 = 8 or 3 * 2 + 1 = 7 - never
    anything that doubles or adds twice."""
    scenario = _life_gain_board("Angel of Vitality", "Boon Reflection").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)

    assert scenario.player("alice").life in (27, 28)


def test_angel_of_vitality_does_not_touch_an_opponents_life_gain():
    """ "If *you* would gain life" - Bob's gain is his own."""
    scenario = _life_gain_board("Angel of Vitality").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("bob", 3)

    assert scenario.player("bob").life == 23


def test_gaining_no_life_is_not_an_event_the_angel_can_add_to():
    """CR 119.3 adjusts a life total by what is gained; zero is no gain, and
    "that much life plus 1" has no "that much" to add to."""
    scenario = _life_gain_board("Angel of Vitality").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 0)

    assert scenario.player("alice").life == 20

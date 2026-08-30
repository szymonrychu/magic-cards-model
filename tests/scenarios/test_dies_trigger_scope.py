"""How far a DIES condition reaches beyond the purely self-referential form.

CR 700.4: "The term dies means 'is put into a graveyard from the battlefield.'"
That definition does not mention creatures specifically, so a permanent of any
type spelling the phrase out - Flagstones of Trokair's land - dies exactly like
a creature does, and CR 603.10a lets either kind of trigger look back at the
object that just left.

`machines/triggers.condition_matches` used to read only "When this creature
dies"; it now also reads:

- "Whenever this creature or another creature dies" (Blood Artist) - the self
  half and the general half of the same sentence, matched independently so a
  card that combines them fires on both, not only the one `_self_referential`
  happens to notice first.
- "Whenever another creature you control dies" / "... one or more other Cats
  you control die" (Ajani, Nacatl Pariah) - the "you control" clause and an
  optional creature subtype, read the same way `intervening_if_holds` already
  reads a subtype for Thopter Assembly.
- The spelled-out CR 700.4 form itself (Flagstones of Trokair), which
  `_trigger_event` now recognises as the same event as the word "dies".

Every case above excludes the source's own death unless the condition also
names itself - `test_a_source_that_only_reads_the_self_form_does_not_fire_for_
another_creature` is the fail-closed check that a plain "dies" condition does
not spuriously widen.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Ajani, Nacatl Pariah: "one or more other Cats you control die" --------


def test_another_cat_dying_triggers_ajanis_transform_ability():
    """A Cat token or card dying puts Ajani's second ability on the stack.

    The effect - exiling and returning him transformed - has no `EFFECTS`
    entry yet (see `docs/engine-coverage.md` and the xfail in
    `test_tokens.py::test_a_cat_token_dying_flips_ajani`), so this only checks
    that the trigger fires, not what it does.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Ajani, Nacatl Pariah", "Steppe Lynx"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lynx = scenario.creature("Steppe Lynx", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[lynx])

    assert lynx.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Ajani, Nacatl Pariah's triggered ability"]


def test_ajanis_own_death_does_not_trigger_his_other_ability():
    """ "Other Cats" excludes Ajani himself, even though he is a Cat Warrior."""
    scenario = (
        Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")

    scenario.game.destroy(ajani)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_noncat_creature_dying_does_not_trigger_ajani():
    """The subtype restriction: Grizzly Bears is not a Cat."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_an_opponents_cat_dying_does_not_trigger_ajani():
    """The "you control" restriction: Steppe Lynx belongs to bob here."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player("bob", battlefield=["Steppe Lynx"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lynx = scenario.creature("Steppe Lynx", "bob")

    scenario.game.destroy(lynx)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# -- Blood Artist: "this creature or another creature dies" ----------------


def test_blood_artist_triggers_on_its_own_death():
    scenario = Scenario().player("alice", battlefield=["Blood Artist"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    artist = scenario.creature("Blood Artist", "alice")

    scenario.game.destroy(artist)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Blood Artist's triggered ability"]


def test_blood_artist_triggers_on_any_other_creature_dying_including_an_opponents():
    """No "you control" clause is printed, so this reaches across the table."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blood Artist"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Blood Artist's triggered ability"]


def test_a_source_that_only_reads_the_self_form_does_not_fire_for_another_creature():
    """Fail-closed check: a plain self-referential dies condition, with no
    "another"/"other" in it at all, must not widen to anyone else's death.

    Wurmcoil Engine's own dies trigger ("When this creature dies, create...")
    is the pool's example of that pure form.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wurmcoil Engine", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# -- Flagstones of Trokair: the spelled-out CR 700.4 form -------------------


def test_flagstones_death_trigger_fires_and_fetches_a_plains():
    """ "Is put into a graveyard from the battlefield" is "dies" by definition
    (CR 700.4), so this now runs the whole way through: the trigger reaches
    the stack, resolves, and the search actually happens.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Plains", "Forest"], battlefield=["Flagstones of Trokair"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    flagstones = scenario.find("Flagstones of Trokair", Zone.BATTLEFIELD)
    scenario.will_take_the_may(True, username="alice")

    scenario.game.destroy(flagstones)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Flagstones of Trokair's triggered ability"]

    scenario.pass_until_resolved()

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.tapped is True
    assert [state.name for state in scenario.player("alice").library] == ["Forest"]


# -- fail-closed: a condition this module still cannot read ---------------


def test_a_leaves_the_battlefield_condition_still_never_fires():
    """Thought-Knot Seer: "When this creature leaves the battlefield, ..."

    CR 603.6c: a leaves-the-battlefield ability is broader than "dies" - it
    also covers exile, bounce, and sacrifice - and nothing in the pool forces
    that broader event to exist yet (see `docs/engine-coverage.md`). Its
    condition parses to no `TriggerEvent` at all, so dying - the one way to
    leave the battlefield this test can drive without a bounce or exile
    effect - must not fire it either. The safe direction to be wrong in.
    """
    scenario = Scenario().player("alice", battlefield=["Thought-Knot Seer"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")

    scenario.game.destroy(seer)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_declining_flagstones_search_leaves_the_library_alone():
    """CR 701.23g: the "you may" can be declined, and CR 700.4's dies event
    still fired even though nothing further happened.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Plains", "Forest"], battlefield=["Flagstones of Trokair"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    flagstones = scenario.find("Flagstones of Trokair", Zone.BATTLEFIELD)
    scenario.will_take_the_may(False, username="alice")

    scenario.game.destroy(flagstones)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert "Plains" not in scenario.battlefield_names()
    assert [state.name for state in scenario.player("alice").library] == ["Plains", "Forest"]

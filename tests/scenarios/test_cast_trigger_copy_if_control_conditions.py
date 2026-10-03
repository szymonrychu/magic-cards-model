"""Scenario: "When you cast this spell from your hand, copy it if you
control an artifact, then copy it if you control an enchantment. You may
choose new targets for the copies." - Banish into Fable.

Two independent conditions, each checked as the trigger resolves (CR 611.2c),
either of which may make a copy - not a shared condition applied twice. The
"from your hand" qualifier on the condition itself (CR 601.2a) is the reason
this card needed a fix to `machines/triggers.condition_matches`'s "this
spell" branch, which used to skip the origin-zone check entirely for a
self-referential cast trigger.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 117.2a / 603.3** - the trigger resolves above its own spell.
- **CR 601.2a** - "from your hand" is the zone the card was cast out of.
- **CR 113.6k** - a "when you cast this spell" ability's printed paragraph
  is a triggered ability of its own, distinct from the spell's own
  resolution instructions that follow it.
- **CR 707.10 / 707.10c** - to copy a spell is to put a copy of it on the
  stack, uncast; its controller may choose new targets for the copy.
- **CR 611.2c** - a condition checked "if you control ..." is read off the
  board as the ability resolves, not as it was put on the stack.

The effect is `parse_copy_it_if_control_twice_clause` in
`machines/cast_copies.py`, tried by `cast_copy_ability_effect` (`machines/
effects.py`'s `_c02_t6_ability_effect`). The origin-zone fix is in
`machines/triggers.py`'s `condition_matches`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

#: {4}{W}{U}: one Plains, one Island, four generic sources.
LANDS_FOR_FABLE = ["Plains", "Island", "Wastes", "Wastes", "Wastes", "Wastes"]


def _fable_board(alice_battlefield: list[str], bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Banish into Fable"],
            battlefield=list(LANDS_FOR_FABLE) + alice_battlefield,
        )
        .player("bob", battlefield=bob_battlefield)
    )


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    scenario = _fable_board([], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])

    assert scenario.stack_names() == [
        "Banish into Fable",
        "Banish into Fable's triggered ability",
    ]


def test_controlling_neither_artifact_nor_enchantment_makes_no_copy():
    scenario = _fable_board([], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()  # the trigger only

    assert scenario.stack_names() == ["Banish into Fable"]


def test_controlling_only_an_artifact_makes_exactly_one_copy():
    scenario = _fable_board(["Ornithopter"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()

    fables = [name for name in scenario.stack_names() if name == "Banish into Fable"]
    assert len(fables) == 2


def test_controlling_only_an_enchantment_makes_exactly_one_copy():
    scenario = _fable_board(["Aggravated Assault"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()

    fables = [name for name in scenario.stack_names() if name == "Banish into Fable"]
    assert len(fables) == 2


def test_controlling_both_an_artifact_and_an_enchantment_makes_two_copies():
    scenario = _fable_board(["Ornithopter", "Aggravated Assault"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()

    fables = [name for name in scenario.stack_names() if name == "Banish into Fable"]
    assert len(fables) == 3, "the original plus one copy per condition that held"


def test_each_copy_actually_resolves_the_bounce_and_makes_a_knight_token():
    """CR 707.1/707.10: a copy is a spell like any other and resolves its
    own printed effect in full - proved by retargeting both copies onto
    Watchwolf (CR 707.10c) so each of the three resolutions (two copies plus
    the original, still aimed at Grizzly Bears) has its own legal target and
    makes its own token, rather than the second and third simply fizzling
    (CR 608.2b) against a Grizzly Bears the first already bounced.
    """
    scenario = _fable_board(
        ["Ornithopter", "Aggravated Assault"], ["Grizzly Bears", "Watchwolf"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)
    scenario.will_choose_targets(wolf, username="alice", source="Banish into Fable", times=2)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()  # the trigger: two copies queued, both retargeted
    scenario.pass_until_resolved()  # first copy (bounces Watchwolf)
    scenario.pass_until_resolved()  # second copy (Watchwolf already gone, fizzles - CR 608.2b)
    scenario.pass_until_resolved()  # the original (bounces Grizzly Bears)

    knights = [state for state in scenario.game.battlefield if state.name == "Knight Token"]
    assert len(knights) == 2, (
        "the original and the one copy that found a legal target each made one"
    )
    assert all(state.controller == "alice" for state in knights)
    assert bears.zone is Zone.HAND, "the original's own target, bounced by its own resolution"
    assert wolf.zone is Zone.HAND, "the copies' shared new target, bounced by the first of them"


def test_a_land_permanent_does_not_count_as_the_artifact_or_enchantment():
    """Neither an artifact nor an enchantment is a land - a board with only
    lands (beyond the mana sources every board needs) makes no copy."""
    scenario = _fable_board(["Forest"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    scenario.cast_onto_stack("Banish into Fable", *sources, targets=[bears])
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Banish into Fable"]


def test_casting_from_a_graveyard_does_not_trigger_the_copy_at_all():
    """CR 601.2a: this trigger's own condition names an origin zone
    ("from your hand"), so a cast from anywhere else - here, a graveyard
    permission granted directly for the test, the same primitive Flashback's
    own grant uses - never fires it at all. This is the fixed defect:
    `condition_matches`'s "this spell" branch used to return `True` on the
    bare self-reference alone, before the origin-zone check ever ran.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Banish into Fable"],
            battlefield=list(LANDS_FOR_FABLE) + ["Ornithopter"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fable = scenario.find("Banish into Fable", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.grant_play_permission(
        fable,
        "alice",
        action=PlayAction.CAST,
        source_name="test grant",
        zone=Zone.GRAVEYARD,
    )
    sources = scenario.untapped_sources(*LANDS_FOR_FABLE)

    casting = scenario.cast("Banish into Fable", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    assert scenario.stack_names() == ["Banish into Fable"], (
        "cast from the graveyard, not the hand: no triggered ability at all"
    )

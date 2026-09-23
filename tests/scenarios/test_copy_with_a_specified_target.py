"""CR 707.10e's specified-target copy, proved in format on Ivy, Gleeful
Spellthief (added to the pool with `scripts/add_card.py`, off the deck pool).

Ivy's own cast trigger: "Whenever a player casts a spell that targets only a
single creature other than Ivy, you may copy that spell. The copy targets
Ivy." Read as one CR 601.2c/707.10e template shared with Frontline Heroism's
"... that targets only a single creature you control ... The copy targets
that token.": `machines/triggers._targets_only_single_creature_other_than_re`
is the "other than `<self-reference>`" half of the condition (Frontline's own
"you control" half is the other), and `machines/effects._parse_copy_that_
spell_retargeted_clause` is the bare "[you may] copy that spell. The copy
targets `<self-reference>`" effect, once Frontline's own token-creation
prefix is not there to read first.

Before this file, neither half was read at all: `trigger_effect_for` returned
`None` for Ivy's own effect text (verified this session, at the top of the
brief this task worked from), so her ability never fired in a real game.

CR 707.10e, verbatim: "Some effects copy a spell or ability and specify a new
target for the copy... If that player or object isn't a legal target for
each instance of the word 'target,' the copy isn't created." CR 707.10: "A
copy of a spell is owned by the player under whose control it was put on the
stack. A copy of a spell or ability is controlled by the player under whose
control it was put on the stack." - both settled by `Game.copy_spell_
targeting`'s own `controller` argument, which `_parse_copy_that_spell_
retargeted_clause`'s effect passes as `ability.controller` (Ivy's own
controller, never the caster who triggered her).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (CR 707.10, 707.10e, 601.2c, 115.3, 115.5).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ivy_copies_a_single_target_spell_owned_and_controlled_by_her_own_controller():
    """The positive case: bob casts Giant Growth ("Target creature gets
    +3/+3 until end of turn.", no restriction beyond "creature") at his own
    Grizzly Bears - a single target, a creature, and not Ivy, so Ivy's
    condition holds. Alice, Ivy's controller, takes the "you may" and the
    copy is built with Ivy as its own specified target (CR 707.10e), owned
    and controlled by alice (CR 707.10) regardless of bob having cast the
    original, and resolves on Ivy rather than on the Bears.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ivy, Gleeful Spellthief", "Forest"])
        .player("bob", hand=["Giant Growth"], battlefield=["Forest", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ivy = scenario.creature("Ivy, Gleeful Spellthief", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    assert (ivy.power, ivy.toughness) == (2, 1)

    (forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.will_take_the_may(True, source="Ivy, Gleeful Spellthief")
    scenario.cast_onto_stack("Giant Growth", forest, username="bob", targets=[bear])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [
        "Giant Growth",
        "Ivy, Gleeful Spellthief's triggered ability",
    ]

    scenario.resolve_top()  # Ivy's triggered ability - builds the copy
    assert len(scenario.game.stack) == 2
    copy = scenario.game.stack[-1]
    assert copy.name == "Giant Growth"
    # CR 707.10: owned and controlled by alice - Ivy's own controller, not bob.
    assert copy.owner == "alice"
    assert copy.controller == "alice"
    # CR 707.10e: the copy's own specified target is Ivy.
    assert [ref.card_id for ref in copy.targets] == [ivy.id]

    scenario.resolve_top()  # the copy resolves - onto Ivy, not the Bears
    assert (ivy.power, ivy.toughness) == (5, 4)
    assert (bear.power, bear.toughness) == (2, 2), "untouched - the copy never targeted it"

    scenario.resolve_top()  # the original Giant Growth, on the Bears
    assert (bear.power, bear.toughness) == (5, 5)
    assert (ivy.power, ivy.toughness) == (5, 4), "the original never touched Ivy"


def test_ivy_creates_no_copy_when_the_only_legal_target_is_not_ivy():
    """CR 707.10e's disposition: Blade Banish reads "Exile target creature
    with power 4 or greater." - Ivy is a 2-power creature, so she is never a
    legal target for the copy no matter what bob's own original targeted.
    Bob targets his own 4-power Serra Angel (a legal target for the
    original), Ivy's condition still holds (a single creature target, and it
    is not Ivy), so the "may" is offered - alice takes it - but `Game.copy_
    spell_targeting` refuses to build a copy that specifies an illegal
    target: no second object ever reaches the stack, and the original alone
    resolves, exiling the Angel. Ivy herself is never touched.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ivy, Gleeful Spellthief", "Plains"])
        .player(
            "bob",
            hand=["Blade Banish"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Serra Angel"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ivy = scenario.creature("Ivy, Gleeful Spellthief", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    assert ivy.power < 4 <= angel.power

    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="bob")
    scenario.will_take_the_may(True, source="Ivy, Gleeful Spellthief")
    scenario.cast_onto_stack("Blade Banish", *sources, username="bob", targets=[angel])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [
        "Blade Banish",
        "Ivy, Gleeful Spellthief's triggered ability",
    ]

    scenario.resolve_top()  # Ivy's triggered ability - no legal target, no copy
    assert scenario.stack_names() == ["Blade Banish"], (
        "CR 707.10e: the copy isn't created at all, not made and then fizzled"
    )

    scenario.resolve_top()  # the original Blade Banish, on the Angel
    assert angel.zone is Zone.EXILE
    assert ivy.zone is Zone.BATTLEFIELD


def test_ivy_does_not_trigger_on_a_spell_with_two_targets():
    """ "Targets only a single creature" is CR 115.3's exactly-one: Prey Upon
    ("Target creature you control fights target creature you don't
    control.") always announces two targets, so Ivy's condition never holds
    for it - not even when one of those two targets is Ivy herself, which
    this test aims deliberately, to show the two-target count is what stops
    the trigger rather than anything about Ivy being targeted at all.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ivy, Gleeful Spellthief"])
        .player("bob", hand=["Prey Upon"], battlefield=["Forest", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ivy = scenario.creature("Ivy, Gleeful Spellthief", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")

    (forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.cast_onto_stack("Prey Upon", forest, username="bob", targets=[mystic, ivy])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Prey Upon"]

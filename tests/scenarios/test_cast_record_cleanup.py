"""CR 608.2a's recheck must read the cast spell's own `CastRecord`, and a
`CastRecord` that is no longer readable must fail the recheck closed rather
than default to "nothing was spent" (CR 601.2h).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **CR 608.2a** - "If a triggered ability has an intervening 'if' clause, it
  checks whether the clause's condition is true [again as the ability
  resolves]."
- **CR 603.4** - the same clause is first checked "when the trigger event
  occurs" - `machines/triggers.triggers_for` does this correctly, threading
  the triggering `GameEvent` through.
- **CR 701.6a / CR 701.6** - countering: "a countered spell ... is put into
  its owner's graveyard" and never resolves.
- **CR 601.2h** - what mana was spent paying a spell's total cost, which
  `Game.note_cast` records onto `CastRecord.mana_spent`.

Two things were wrong before this fix:

1. `Game._intervening_if_still_true` called `intervening_if_holds` without
   `AbilityOnStack.event`, so `machines/triggers._cast_record_for_clause`
   could never resolve a non-self-referential "it" (Vexing Bauble's "if no
   mana was spent to cast **it**" means the cast spell, not Vexing Bauble)
   and silently read the ability's own source's record instead - the wrong
   object, coincidentally landing on the same answer only because Vexing
   Bauble's own record has always been empty by the time it can trigger (see
   `test_the_recheck_reads_the_cast_spells_record_not_the_sources_seeded`
   below for why no card in the pool makes that divergence observable on its
   own, and how this file constructs it anyway).
2. `Game.counter` and the fizzle branch of `Game.resolve_top` never popped
   `Game.cast_records`, unlike the successful-resolution branch - so a
   countered or fizzled spell's `CastRecord` lingered under its id forever.

Fixing (2) by simply popping raises the question (1) already answers: an
absent record must not be misread as "nothing was spent" (`CastRecord()`'s
truthy-looking default for a "no mana was spent" clause), which is
fail-*open* for the exact class of bug this file exists to keep out. So the
policy is: `Game.counter` and both branches of `Game.resolve_top` all clean
up a spell's `CastRecord` the same way, *and*
`machines/triggers._cast_record_for_clause` returns `None` rather than an
empty `CastRecord` when the record is gone, so
`machines/triggers.intervening_if_holds` can tell "no mana was spent" apart
from "I no longer know" and answer the second with a fail-closed
`InterveningIfNotice` instead of a coincidentally-true default.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Defect 2: a countered or fizzled spell's CastRecord is cleaned up
# --------------------------------------------------------------------------


def test_countering_a_spell_pops_its_cast_record():
    """Lightning Bolt is countered before it ever resolves; nothing on the
    normal path will read what CR 601.2h spent for it again, so
    `Game.counter` must clean the record up exactly as the successful path
    already does.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", library=["Forest"], hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    assert bolt.id in scenario.game.cast_records
    assert scenario.game.cast_record(bolt).mana_of_color_spent(Color.RED) == 1

    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[bolt])

    scenario.pass_until_resolved()  # Counterspell resolves, countering the Bolt

    assert bolt.zone is Zone.GRAVEYARD
    assert bolt.id not in scenario.game.cast_records, (
        "a countered spell's CastRecord must not linger under its id forever"
    )


def test_a_fizzled_spells_cast_record_is_also_popped():
    """The other branch `Game.resolve_top` never popped: Lightning Helix loses
    its only target and fizzles (CR 608.2b) rather than being countered, but
    the cleanup must be identical either way.
    """
    scenario = (
        Scenario()
        .player("alice", life=15, hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player(
            "bob",
            hand=["Swords to Plowshares"],
            battlefield=["Grizzly Bears", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")

    alice_sources = scenario.untapped_sources("Mountain", "Plains", username="alice")
    helix = scenario.cast_onto_stack(
        "Lightning Helix", *alice_sources, username="alice", targets=[bears]
    )
    assert helix.id in scenario.game.cast_records
    assert scenario.game.cast_record(helix).any_mana_spent

    scenario.pass_priority("alice")
    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", bob_plains, username="bob", targets=[bears])
    scenario.pass_until_resolved()  # Swords resolves; the Bears are exiled

    assert scenario.game.spell_fizzles(helix)
    scenario.pass_until_resolved()  # the Helix is removed from the stack unresolved

    assert helix.zone is Zone.GRAVEYARD
    assert helix.id in scenario.game.fizzled
    assert helix.id not in scenario.game.cast_records, (
        "a fizzled spell's CastRecord must not linger under its id forever"
    )


def test_a_countered_spells_gone_cast_record_fails_the_recheck_closed():
    """The reason (2) cannot be fixed by popping alone: Vexing Bauble's
    ability goes on the stack *above* Memnite (CR 603.3), and Memnite is
    countered while that ability is still waiting to resolve - the exact
    shape where CR 608.2a's recheck asks about a spell whose CastRecord has
    already been cleaned up.

    Before this fix, `Game.counter` left Memnite's (empty) CastRecord in
    place, so the recheck happened to read the right, if lingering, answer.
    After this fix the record is gone by the time the recheck runs, and
    `machines/triggers._cast_record_for_clause` must return `None` rather
    than the empty-record default - which `intervening_if_holds` turns into
    an `InterveningIfNotice` and a closed `False`, not a silent, coincidentally
    correct `True`. Vexing Bauble's own counter effect finding nothing to
    counter (Memnite is already in the graveyard) would have hidden the
    difference here, so the assertion is on the notice itself.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Memnite"], battlefield=["Vexing Bauble"])
        .player("bob", library=["Forest"], hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.creature("Vexing Bauble", "alice")

    memnite = scenario.cast_onto_stack("Memnite")
    assert scenario.stack_names() == ["Memnite", f"{bauble.name}'s triggered ability"]

    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[memnite])
    assert scenario.stack_names() == [
        "Memnite",
        f"{bauble.name}'s triggered ability",
        "Counterspell",
    ]

    scenario.pass_until_resolved()  # Counterspell resolves, countering Memnite
    assert memnite.zone is Zone.GRAVEYARD
    assert memnite.id not in scenario.game.cast_records

    scenario.pass_until_resolved()  # Vexing Bauble's ability resolves
    assert scenario.stack_names() == []
    assert len(scenario.game.intervening_if_notices) == 1
    notice = scenario.game.intervening_if_notices[0]
    assert notice.source_name == "Vexing Bauble"
    assert notice.clause == "no mana was spent to cast it"


# --------------------------------------------------------------------------
# Defect 1: the recheck must thread the triggering event through, not read
# the ability's own source
# --------------------------------------------------------------------------


def test_the_recheck_reads_the_cast_spells_record_not_the_sources_seeded():
    """No card in the fixture pool makes defect 1 observable on its own.

    Vexing Bauble is the only card in the pool with a non-self-referential
    mana-spent clause (`test_intervening_if.py`'s survey of the pool's seven
    intervening-if cards), and it begins the game already on the battlefield
    or, if cast, has its own CastRecord popped the moment it resolves (the
    same successful-resolution cleanup this file's other tests exercise for
    Lightning Bolt and Lightning Helix) - so by the time Vexing Bauble's
    ability could ever recheck, `game.cast_records.get(bauble.id)` is *always*
    absent. Both the old, wrong-object read (`game.cast_record(source)`,
    which defaults an absent record to an empty one) and the fixed,
    event-threaded read land on the same "no mana was spent" answer for that
    reason alone - the defect is real but inert, exactly as the review found.

    The only way to make the two readings diverge is to give Vexing Bauble's
    own record a value the *real* cast spell's record does not have - which
    cannot happen through ordinary play under the invariant above. This test
    manufactures that precondition directly with `Game.note_cast`, the same
    production API `machines/casting.Casting.cast` uses to write a
    `CastRecord` in the first place, rather than with a mock: it models
    exactly the state a future record-cleanup gap (defect 2's shape, on some
    other card) could leave behind on a permanent's own past cast.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Memnite"], battlefield=["Vexing Bauble"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.creature("Vexing Bauble", "alice")

    memnite = scenario.cast_onto_stack("Memnite")
    assert scenario.stack_names() == ["Memnite", f"{bauble.name}'s triggered ability"]
    assert not scenario.game.cast_record(memnite).any_mana_spent

    # Seed a wrong, non-empty record under Vexing Bauble's own id - the state
    # `_intervening_if_still_true` would wrongly consult without the fix.
    scenario.game.note_cast(bauble, mana_spent={Color.RED: 1})

    scenario.pass_until_resolved()  # Vexing Bauble's ability resolves

    assert scenario.game.intervening_if_notices == []
    assert memnite.zone is Zone.GRAVEYARD, (
        "the recheck must read Memnite's own (empty) CastRecord and counter "
        "it - reading Vexing Bauble's seeded one instead would wrongly "
        "conclude mana was spent and let Memnite resolve untouched"
    )

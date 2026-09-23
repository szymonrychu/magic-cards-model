"""A resolving instant or sorcery whose printed text no parser reads leaves a
notice behind rather than going to the graveyard with no trace.

Stock Up did exactly that in a live game: `effect_for` returned nothing, and
`Game.resolve` dropped the `None`, so the spell resolved, did nothing and said
nothing. A triggered or activated ability in the same position already records
an `UnmodeledTriggerEffectNotice`; a spell now records the same notice, on the
same `Game.unmodeled_trigger_effect_notices` list, with the spell's own id,
name and whole printed text (none of it ran).

Strix Serenade ("Counter target artifact, creature, or planeswalker spell. Its
controller creates a 2/2 blue Bird creature token with flying.") is the
vehicle: Ponder, this test's own vehicle before the look-top-and-put-back wave
(`tests/scenarios/test_look_at_top_and_put_back.py`) gave it a reader, has one
now, so it can no longer stand for "unread". Strix Serenade's own clause
combines a counter with a token grant for the countered spell's controller - a
shape this wave's look/shuffle readers never touch - and still has no reader
anywhere in `src/`.

Not every `None` is a gap, and the notice must not fire for these:

- a permanent spell, which becomes a permanent as it resolves (CR 608.3a);
  its abilities are judged on their own when they trigger;
- a spell whose resolution leaves a replacement effect instead
  (Plagiarize, CR 614.1a), which `Game._create_resolution_replacements`
  builds without `effect_for`.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import UnmodeledTriggerEffectNotice
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_an_unread_instant_records_a_notice_naming_its_whole_text():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob", hand=["Strix Serenade"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="alice"),
        username="alice",
    )
    scenario.pass_priority("alice")

    serenade = scenario.cast_and_resolve(
        "Strix Serenade",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears],
    )

    assert serenade.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.STACK, "an unread 'counter' clause counters nothing"
    assert scenario.game.unmodeled_trigger_effect_notices == [
        UnmodeledTriggerEffectNotice(
            source_id=serenade.id,
            source_name="Strix Serenade",
            text=serenade.oracle_text,
        )
    ]


def test_a_spell_that_leaves_a_replacement_effect_records_no_notice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Plagiarize"],
            library=["Forest", "Island"],
            battlefield=["Island"] * 4,
        )
        .player("bob", library=["Swamp", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Plagiarize", *scenario.untapped_sources(*["Island"] * 4), targets=["bob"]
    )

    assert scenario.game.draw_redirections, "the replacement is what Plagiarize does"
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_spell_a_parser_reads_records_no_notice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stock Up"],
            library=["Forest", "Island", "Swamp", "Mountain", "Plains"],
            battlefield=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Stock Up", *scenario.untapped_sources(*["Island"] * 3))

    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_permanent_spell_records_no_notice_as_it_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Codecracker Hound"],
            library=["Lightning Bolt", "Forest"],
            battlefield=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hound = scenario.cast_and_resolve(
        "Codecracker Hound", *scenario.untapped_sources(*["Island"] * 3)
    )
    scenario.pass_until_resolved()

    assert hound.zone is Zone.BATTLEFIELD
    assert scenario.game.unmodeled_trigger_effect_notices == []

"""A triggered ability whose effect text nothing reads fails closed.

CR 603.3: a triggered ability that triggered goes on the stack and resolves
(CR 608.2) whether or not this engine can read what it says. When
`trigger_effect_for` has no reader for the printed effect, resolving it used
to do nothing and leave no trace - Dress Down's end step trigger read
"CHANGED NOTHING" in a live game. It now records an
`UnmodeledTriggerEffectNotice` naming the source and the unread text, the same
record a resolving instant or sorcery with unread text already leaves, so a
seat is told the engine skipped it rather than that the ability legally did
nothing.

A trigger whose effect is read records nothing: the notice is for the gap, not
for every resolution.

Coiling Oracle ("When this creature enters, reveal the top card of your
library. If it's a land card, put it onto the battlefield. Otherwise, put that
card into your hand.") is a pool printing whose enters trigger no parser reads
yet. Dress Down's enters trigger ("draw a card") is read.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 603.2, 113.7a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

ORACLE_EFFECT = (
    "reveal the top card of your library. If it's a land card, put it onto the "
    "battlefield. Otherwise, put that card into your hand."
)


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_an_unread_trigger_records_a_notice_as_it_resolves_and_moves_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Coiling Oracle"],
            battlefield=["Forest", "Island"],
            library=["Lightning Bolt", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.top_of_library(1, "alice")[0]

    oracle = scenario.cast_and_resolve(
        "Coiling Oracle", *scenario.untapped_sources("Forest", "Island")
    )
    assert scenario.stack_names() == ["Coiling Oracle's triggered ability"]
    assert scenario.game.unmodeled_trigger_effect_notices == []

    resolve_stack(scenario)

    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert notice.source_id == oracle.id
    assert notice.source_name == "Coiling Oracle"
    assert notice.text == ORACLE_EFFECT
    assert top.zone is Zone.LIBRARY


def test_a_trigger_whose_effect_is_read_records_no_notice():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Dress Down"],
            battlefield=["Island", "Island"],
            library=["Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Dress Down", *scenario.untapped_sources("Island", "Island"))
    resolve_stack(scenario)

    assert len(scenario.player("alice").hand) == 1
    assert scenario.game.unmodeled_trigger_effect_notices == []

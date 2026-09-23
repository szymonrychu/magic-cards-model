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

Darkstar Augur ("At the beginning of your upkeep, reveal the top card of your
library and put that card into your hand. You lose life equal to its mana
value.") is a pool printing whose upkeep trigger no parser reads yet. (Beza, the Bounding Spring
used to be this file's example; S11 reads its four opponent comparisons now.)
Dress Down's enters trigger ("draw a card") is read.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 603.2, 113.7a.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import PlayedScenario, Scenario

AUGUR_EFFECT = (
    "reveal the top card of your library and put that card into your hand. You lose "
    "life equal to its mana value."
)


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_an_unread_trigger_records_a_notice_as_it_resolves_and_moves_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Darkstar Augur"], library=["Grizzly Bears"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    augur = scenario.creature("Darkstar Augur", "alice")
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Darkstar Augur's triggered ability"]
    assert scenario.game.unmodeled_trigger_effect_notices == []

    resolve_stack(scenario)

    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert notice.source_id == augur.id
    assert notice.source_name == "Darkstar Augur"
    assert notice.text == AUGUR_EFFECT
    # Nothing moved and no life was lost.
    assert len(scenario.player("alice").library) == 3
    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 20


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

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

Beza, the Bounding Spring ("When Beza enters, create a Treasure token if an
opponent controls more lands than you. You gain 4 life if an opponent has more
life than you. Create two 1/1 blue Fish creature tokens if an opponent
controls more creatures than you. Draw a card if an opponent has more cards in
hand than you.") is a pool printing whose enters trigger no parser reads yet:
each of its four clauses conditions a grant on comparing a stat against every
opponent's, a shape this wave's `_LOOK_TOP_CARD_CONDITIONAL_RE` widening does
not touch and does not close. Dress Down's enters trigger ("draw a card") is
read.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 603.2, 113.7a.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import PlayedScenario, Scenario

BEZA_EFFECT = (
    "create a Treasure token if an opponent controls more lands than you. You "
    "gain 4 life if an opponent has more life than you. Create two 1/1 blue "
    "Fish creature tokens if an opponent controls more creatures than you. "
    "Draw a card if an opponent has more cards in hand than you."
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
            hand=["Beza, the Bounding Spring"],
            battlefield=["Plains", "Plains", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    beza = scenario.cast_and_resolve(
        "Beza, the Bounding Spring",
        *scenario.untapped_sources("Plains", "Plains", "Forest", "Forest"),
    )
    assert scenario.stack_names() == ["Beza, the Bounding Spring's triggered ability"]
    assert scenario.game.unmodeled_trigger_effect_notices == []

    resolve_stack(scenario)

    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert notice.source_id == beza.id
    assert notice.source_name == "Beza, the Bounding Spring"
    assert notice.text == BEZA_EFFECT
    # None of the four conditional grants happened: no Treasure, no life
    # gained, no Fish tokens, no card drawn.
    assert "Treasure" not in scenario.battlefield_names()
    assert "Fish" not in scenario.battlefield_names()
    assert scenario.player("alice").life == 20
    assert scenario.player("alice").hand == []


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

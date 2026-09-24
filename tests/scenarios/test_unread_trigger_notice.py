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

The unread trigger is chosen by `gap_example`, never named: a creature whose
own "When ~ enters" trigger (no target, so CR 603.3d cannot remove it) no
parser reads yet. Darkstar Augur stood here until S32 read "reveal the top
card ... You lose life equal to its mana value"; Beza, the Bounding Spring
before it, until S11. Dress Down's enters trigger ("draw a card") is read.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 603.2, 113.7a.
"""

import re

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Card
from magic_cards_model.support import SILENT, classify_clauses
from tests.cards import gap_example
from tests.scenarios.harness import PlayedScenario, Scenario

_SELF_ENTERS = re.compile(r"^When (?!(?:a|an|another|one)\b)[^,]+ enters, (?P<effect>.+)$", re.S)


def _unread_self_enters_trigger(printing: Card) -> str | None:
    """The effect text of `printing`'s own untargeted enters trigger when
    `card_support` reports that clause silent, else `None`."""
    if "Creature" not in printing.type_line or "//" in printing.name:
        return None
    for clause in classify_clauses(printing):
        if clause.source != "triggered" or clause.category != SILENT:
            continue
        match = _SELF_ENTERS.match(clause.text)
        if match and "target" not in clause.text:
            return match.group("effect")
    return None


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_an_unread_trigger_records_a_notice_as_it_resolves_and_moves_nothing():
    printing = gap_example(
        "a creature with an unread untargeted enters trigger",
        lambda p: _unread_self_enters_trigger(p) is not None,
    )
    effect = _unread_self_enters_trigger(printing)
    assert effect is not None
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[printing.name], library=["Grizzly Bears"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    source = scenario.put_onto_battlefield(printing.name, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{printing.name}'s triggered ability"]
    assert scenario.game.unmodeled_trigger_effect_notices == []

    resolve_stack(scenario)

    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert notice.source_id == source.id
    assert notice.source_name == printing.name
    assert notice.text in effect
    # Nothing moved and no life was lost.
    assert len(scenario.player("alice").library) == 3
    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20
    assert scenario.battlefield_names() == [printing.name]


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

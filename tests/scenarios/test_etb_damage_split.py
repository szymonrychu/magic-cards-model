""" "When `<this>` enters, it deals `<n>` damage to any target and `<m>`
damage to you." - a self-inflicted damage rider alongside a real CR 115.1
target, printed with a bare "and" `split_effect_clauses` would otherwise cut
into two unreadable halves.

Spicy Oatmeal Pizza: "When this artifact enters, it deals 4 damage to any
target and 3 damage to you."

- **CR 603.6a** - the enters condition, already generic, is stripped before
  this reader ever sees the text; the target belongs to the *triggered
  ability*, not the permanent spell, so it is chosen when that ability goes
  on the stack (CR 603.3d), never at cast time.
- **CR 115.5** - "any target" reaches a creature, player, planeswalker, or
  battle.
- **CR 120.1** - "and 3 damage to you" is not a target at all: it is always
  the controller, named outright, the same shape Char's own "and 2 damage to
  you" already prints on an unrelated card, with no condition in front of it
  at all (CR 201.5's own literal self-name subject instead of a bare "it").
- **CR 608.2h** - an ability's own source is read through its last-known
  information; every scenario here resolves while the artifact is still on
  the battlefield regardless.

Char is the second, non-pool printing that proves the reader is not fitted
to Spicy Oatmeal Pizza's own fixed numbers, its "it" subject, or its
triggered-ability shape - Char is a plain instant with no condition at all
over different fixed amounts. Verified legal in Modern.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_TRIGGER = "Spicy Oatmeal Pizza's triggered ability"


def test_the_artifact_hits_a_target_and_its_own_controller_at_once():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Spicy Oatmeal Pizza"], battlefield=["Mountain", "Mountain", "Mountain"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    alice_life_before = scenario.player("alice").life

    scenario.will_choose_targets(bears, username="alice", source="Spicy Oatmeal Pizza")
    pizza = scenario.cast_and_resolve("Spicy Oatmeal Pizza", *sources)
    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    assert pizza.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD  # 4 damage kills a 2/2
    assert scenario.player("alice").life == alice_life_before - 3


def test_targeting_a_player_still_deals_the_self_damage_too():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Spicy Oatmeal Pizza"], battlefield=["Mountain", "Mountain", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    alice_life_before = scenario.player("alice").life
    bob_life_before = scenario.player("bob").life

    scenario.will_choose_targets("bob", username="alice", source="Spicy Oatmeal Pizza")
    scenario.cast_and_resolve("Spicy Oatmeal Pizza", *sources)
    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == bob_life_before - 4
    assert scenario.player("alice").life == alice_life_before - 3


def test_char_proves_the_reader_generalizes_off_a_second_printing():
    scenario = (
        Scenario()
        .player("alice", hand=["Char"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    alice_life_before = scenario.player("alice").life

    scenario.cast_and_resolve("Char", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == alice_life_before - 2

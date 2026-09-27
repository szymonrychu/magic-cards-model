"""Scenario: Enrage (CR 207.2c ability word) - "Whenever `<this>` is dealt
damage, add that much `<mana>`. Until end of turn, you don't lose this mana
as steps and phases end."

The trigger condition ("Whenever `<this>` is dealt damage") is not new -
Hexhaven Invigorator already proves `TriggerEvent.DEALS_DAMAGE`'s passive-
voice, self-referential reading generically. What this task adds is the
effect clause: a *fixed* colour (not "any one color", the shape Photon,
Mighty Marvel's own "add that much mana of any one color" already reads) kept
past every CR 500.5 step/phase boundary for the rest of the turn -
`models/mana.py`'s `ManaRetentionScope`/`RetainedMana`/`ManaPool.retained`
general mechanism (already built for firebending and Photon) needed no
changes at all; only a new parser to reach it with a fixed-colour count.

CR 106.4: "Each player's mana pool empties at the end of each step and
phase" - the general statement this task's own note cites; CR 500.5/500.5b
is the turn-based-action instance of it that `ManaPool.empty`'s `expiring`
parameter already replaces for retained mana. Both numbers were looked up
this session with `mise run rules:find <n>`.

Two printings: Raphael, Ninja Destroyer (the listed card) and Sakiko, Mother
of Summer (the proof printing - Modern legal, not a listed card, not in any
deck list, verified with `resolve_cards`/Scryfall this session, 2026-09-27):
"Whenever a creature you control deals combat damage to a player, add that
much {G}. Until end of turn, you don't lose this mana as steps and phases
end." - the identical effect-clause template on a different trigger
condition and a different fixed colour, proving the parser reads the
sentence's own shape rather than Raphael's exact wording.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color

from .harness import Scenario


def test_raphael_enrage_adds_red_mana_that_survives_the_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Ninja Destroyer"])
        .player("bob", battlefield=["Watchwolf"])
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raphael = scenario.creature("Raphael, Ninja Destroyer")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(raphael)
    scenario.block(raphael, wolf)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 3  # Watchwolf's power dealt to Raphael

    scenario.advance()  # declare attackers -> declare blockers
    scenario.advance()  # -> combat damage
    scenario.advance()  # -> end of combat
    scenario.advance()  # -> postcombat main
    assert pool.floating.get(Color.RED) == 3, "survives every ordinary boundary this turn"

    scenario.advance()  # -> end step
    scenario.advance()  # -> cleanup step
    assert pool.floating.get(Color.RED) == 3

    scenario.turn_based_actions()  # CR 514.1/514.2's own cleanup action
    assert pool.floating.get(Color.RED, 0) == 0
    assert pool.retained == []


def test_raphael_dealt_no_damage_adds_no_mana():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Ninja Destroyer"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raphael = scenario.creature("Raphael, Ninja Destroyer")
    scenario.attack_with(raphael)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").mana_pool.total == 0


def test_sakiko_proves_the_same_template_with_a_different_colour_and_trigger():
    """Sakiko, Mother of Summer: a combat-damage-dealt (not damage-received)
    trigger, adding {G} rather than {R} - the same "add that much `<mana>`.
    Until end of turn, you don't lose this mana as steps and phases end."
    clause on an unrelated card."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sakiko, Mother of Summer", "Grizzly Bears"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.GREEN) == 2  # Grizzly Bears' power

    scenario.advance()  # declare blockers -> combat damage
    scenario.advance()  # -> end of combat
    assert pool.floating.get(Color.GREEN) == 2, "survives the end of combat step"

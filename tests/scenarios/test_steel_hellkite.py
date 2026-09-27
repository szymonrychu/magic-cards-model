"""Steel Hellkite: "{X}: Destroy each nonland permanent with mana value X
whose controller was dealt combat damage by this creature this turn.
Activate only once each turn." - the identical per-turn "dealt combat
damage" history `machines/conditions/history.dealt_damage_clause_test`
reads for Admiral Beckett Brass's "three or more Pirates" and Hope of
Ghirapur's own self-reference, here filtering a non-targeted mass-
destruction sweep's own subject by its *controller* rather than by a
target or a target's controller.

Rules verified with `mise run rules:find` in the session that wrote this
file:

- CR 120.1: "An object that deals damage is the source of that damage."
- CR 120.2a: combat damage, dealt simultaneously (CR 510.2).
- CR 107.3a: {X} is announced as the ability is activated, and every "X" in
  the ability's own text (including "mana value X") is that same value.
- CR 205.2a: "nonland permanent" excludes CR 205.2a's land card type.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Steel Hellkite", "Grizzly Bears", "Island", "Island"],
            library=["Island"] * 6,
        )
        .player(
            "bob",
            battlefield=["Watchwolf", "Llanowar Empath", "Forest"],
            library=["Forest"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_steel_hellkite_needs_its_own_combat_damage_this_turn():
    """Without Steel Hellkite dealing any combat damage this turn, paying X
    destroys nothing at all - the restriction fails closed, not open."""
    scenario = _board()
    hellkite = scenario.creature("Steel Hellkite", "alice")
    wolf = scenario.find("Watchwolf", Zone.BATTLEFIELD, "bob")

    scenario.activate(hellkite, index=1, x_value=2, auto=True)
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.BATTLEFIELD


def test_steel_hellkite_destroys_only_the_damaged_players_matching_permanents():
    """After Steel Hellkite deals combat damage to bob (its default
    attack target), paying X=2 destroys bob's mana-value-2 Watchwolf, but
    not bob's Llanowar Empath (mana value 4) or Forest (a land, CR 205.2a),
    and not alice's *own* mana-value-2 Grizzly Bears - alice, unlike bob,
    was never dealt combat damage by Steel Hellkite this turn."""
    scenario = _board()
    hellkite = scenario.creature("Steel Hellkite", "alice")
    own_bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    wolf = scenario.find("Watchwolf", Zone.BATTLEFIELD, "bob")
    empath = scenario.find("Llanowar Empath", Zone.BATTLEFIELD, "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(hellkite)
    scenario.no_blocks()
    scenario.combat_damage()

    scenario.activate(hellkite, index=1, x_value=2, auto=True)
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.GRAVEYARD
    assert empath.zone is Zone.BATTLEFIELD
    assert forest.zone is Zone.BATTLEFIELD
    assert own_bears.zone is Zone.BATTLEFIELD


def test_steel_hellkite_x_zero_destroys_only_mana_value_zero_permanents():
    """A different X reads a different mana value (CR 107.3a) - paying X=0
    destroys nothing here, since nothing on the board has mana value 0."""
    scenario = _board()
    hellkite = scenario.creature("Steel Hellkite", "alice")
    wolf = scenario.find("Watchwolf", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(hellkite)
    scenario.no_blocks()
    scenario.combat_damage()

    scenario.activate(hellkite, index=1, x_value=0, auto=True)
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.BATTLEFIELD

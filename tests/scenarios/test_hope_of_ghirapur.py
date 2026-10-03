"""Hope of Ghirapur: "Sacrifice Hope of Ghirapur: Until your next turn,
target player who was dealt combat damage by Hope of Ghirapur this turn
can't cast noncreature spells." - CR 115.1's target restriction is a
per-turn historical fact about *this permanent specifically* (CR 201.5's
self-reference, "this permanent" once `self_normalized_effect_text` has
rewritten the card's own printed name), read through the same shared turn-
history reader (`machines/conditions/history.dealt_damage_clause_test`)
Admiral Beckett Brass's own "three or more Pirates" reads - narrowed here to
one named object instead of a quality and a count.

Rules verified with `mise run rules:find` in the session that wrote this file:

- CR 120.1: "An object that deals damage is the source of that damage."
- CR 120.2a: combat damage, dealt during the combat damage step.
- CR 611.2a: "Until your next turn" is the ability's own stated duration.
- CR 205.2a: "noncreature spell" - every card type but creature.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_restriction
from magic_cards_model.models import Zone

from .harness import Scenario


def _board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hope of Ghirapur"], library=["Island"] * 6)
        .player("bob", hand=["Lightning Bolt", "Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _next_turn(scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_hope_of_ghirapur_cannot_target_a_player_it_never_damaged():
    """The target restriction fails closed before Hope has dealt any combat
    damage this turn."""
    scenario = _board()
    hope = scenario.creature("Hope of Ghirapur", "alice")
    raised = False
    try:
        scenario.activate(hope, sacrificing=[hope], targets=["bob"])
    except ValueError:
        raised = True
    assert raised


def test_hope_of_ghirapur_restricts_noncreature_casting_after_dealing_combat_damage():
    scenario = _board()
    hope = scenario.creature("Hope of Ghirapur", "alice")
    scenario.attack_with(hope)
    scenario.no_blocks()
    scenario.combat_damage()

    scenario.activate(hope, sacrificing=[hope], targets=["bob"])
    scenario.pass_until_resolved()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is not None
    # CR 205.2a: a creature spell is not a noncreature spell - unaffected.
    assert why_cannot_cast_restriction(bears, "bob", scenario.game) is None


def test_hope_of_ghirapur_does_not_restrict_a_creature_spell_only_bystander():
    """A creature spell in the restricted player's hand casts freely; only
    a *noncreature* spell is barred (CR 205.2a) - Hope's own restriction is
    narrower than Orim's Chant's unconditional "can't cast spells"."""
    scenario = _board()
    hope = scenario.creature("Hope of Ghirapur", "alice")
    scenario.attack_with(hope)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.activate(hope, sacrificing=[hope], targets=["bob"])
    scenario.pass_until_resolved()

    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    assert why_cannot_cast_restriction(bears, "bob", scenario.game) is None


def test_hope_of_ghirapur_restriction_ends_at_alices_next_turn():
    """CR 611.2a: "Until your next turn" ends the moment the controller's
    own next turn begins - not the opponent's very next turn."""
    scenario = _board()
    hope = scenario.creature("Hope of Ghirapur", "alice")
    scenario.attack_with(hope)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.activate(hope, sacrificing=[hope], targets=["bob"])
    scenario.pass_until_resolved()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is not None

    _next_turn(scenario)  # bob's turn - still restricted
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is not None

    _next_turn(scenario)  # alice's next turn begins - restriction ends
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is None

"""`machines/legal_actions.py`'s combat enumeration reads the *computed* board
(CR 613.5), matching what `why_cannot_attack`/`why_cannot_block` already
permit - the headline inconsistency this wave exists to close.

A land animated by earthbend (CR 701.66a, "Target land you control becomes a
0/0 land creature with haste in addition to its other types", CR 205.1b) is a
creature the moment the layer system says so (CR 613.5, CR 613.1d layer 4).
`combat.attack_refusal`/`combat.block_refusal` already asked
`game.characteristics_of(...)` and so already answered `None` - legal - for
such a land. `_attacker_actions`/`_blocker_actions` instead filtered candidate
creatures on `Type.CREATURE not in creature.types`, `CardState`'s printed
starting point (CR 613.1), so a live game let the animated land attack or
block when told to while the enumerated action list never offered it: the
permission and the menu disagreed about what the game had just allowed.

`_attacker_actions`'s defender enumeration (planeswalker/battle) has the same
printed-vs-computed shape as `combat._defender_refusal`, fixed for the
identical reason - see that file's own test for why no card in this engine's
pool can make the old and new answer disagree there, only regress.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import CardState

from .harness import PlayedScenario, Scenario


def _of_kind(actions, kind: ActionKind):
    return [action for action in actions if action.kind is kind]


def _animate_a_forest(scenario: PlayedScenario, controller: str) -> tuple[CardState, CardState]:
    """Put `controller`'s own Badgermole Cub straight onto the battlefield
    (CR 302.1's sorcery timing is not what this test is about, and `controller`
    is not always the active player, exactly as `test_layer_computed_type_
    selection.py`'s identical helper does it) and earthbend one of their
    untapped Forests. Returns `(animated, untouched)` - a second, plain
    Forest the ability never targeted, for the inverse assertions.
    """
    animated, untouched = scenario.untapped_sources("Forest", "Forest", username=controller)
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    scenario.put_onto_battlefield("Badgermole Cub", controller)
    scenario.pass_until_resolved()  # the earthbend trigger itself
    return animated, untouched


def _board() -> Scenario:
    """alice, with Badgermole Cub and two Forests, is the active player;
    bob, with the same, is the only opponent - so either side can be the one
    whose land gets animated, attacker or blocker.
    """
    return (
        Scenario()
        .player("alice", hand=["Badgermole Cub"], battlefield=["Forest"] * 2)
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest"] * 2)
    )


def test_an_animated_land_is_offered_as_a_declare_attacker_action():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, untouched = _animate_a_forest(scenario, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.game.why_cannot_attack(animated, "bob") is None, (
        "the engine already permits this attack"
    )

    attacker_actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    attacking_card_ids = {action.card_id for action in attacker_actions}

    assert animated.id in attacking_card_ids, (
        "an animated land the engine permits to attack must be offered as one"
    )
    assert untouched.id not in attacking_card_ids, (
        "a plain, unanimated land is not a creature and must not be offered"
    )


def test_declare_blocker_actions_match_why_cannot_block():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, untouched = _animate_a_forest(scenario, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    assert scenario.game.why_cannot_block(animated, bears) is None, (
        "the engine already permits this block"
    )

    blocker_actions = _of_kind(legal_actions(scenario.game, "bob"), ActionKind.DECLARE_BLOCKER)
    blocking_card_ids = {action.card_id for action in blocker_actions}

    assert animated.id in blocking_card_ids, (
        "an animated land the engine permits to block must be offered as one"
    )
    assert untouched.id not in blocking_card_ids, (
        "a plain, unanimated land is not a creature and must not be offered"
    )


def test_a_plain_land_is_never_offered_to_attack_or_block():
    """The inverse on an ordinary board with no animation at all - the
    computed read must not turn every land into a phantom creature action.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest", "Grizzly Bears"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    forest = scenario.find("Forest", scenario.game.battlefield[0].zone, "alice")

    attacker_actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    assert forest.id not in {action.card_id for action in attacker_actions}


def test_a_transformed_planeswalker_is_offered_as_a_declare_attacker_defender():
    """`_attacker_actions`'s own defender enumeration (CR 508.1b), fixed the
    same way `combat._defender_refusal` was - see that file's test module for
    why no card in this pool can exercise the layer-4 disagreement itself.
    This is the regression: a transformed planeswalker face must still be
    offered as something an attacker may be declared against.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Ajani, Nacatl Pariah"])
        .build()
    )
    ajani = scenario.creature("Ajani, Nacatl Pariah", "bob")
    ajani.transform()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    attacker_actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    defenders_offered = {
        action.defender for action in attacker_actions if action.card_id == bears.id
    }

    assert str(ajani.id) in defenders_offered

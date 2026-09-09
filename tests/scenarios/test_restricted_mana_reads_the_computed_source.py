"""CR 106.6's restricted mana asks what the *source* of the ability is, and
that is the layer-computed answer (CR 613.5), not the printed type line.

Shang-Chi, Master of Kung Fu prints "{T}: Add two mana of any one color.
Spend this mana only to activate abilities of creature sources." Mishra's
Factory prints "{1}: This land becomes a 2/2 Assembly-Worker artifact creature
until end of turn. It's still a land." - a layer-4 type change (CR 613.1d)
that adds creature "in addition to its other types" (CR 205.1b).

Put those two together and the question is exact: once the Factory has
animated itself, is it a creature source? It is. `machines/legal_actions.py`
used to build the `ManaSpend` from `permanent.card` - the printed front face,
which is a Land and nothing else - so the restricted mana was refused and the
Factory's own ability was enumerated as unaffordable while the engine's mana
pool actually held enough to pay it.

The inverse matters just as much and is asserted here too: an *unanimated*
Mishra's Factory is a land, restricted mana must not pay for it, and the
action must be enumerated as unaffordable rather than quietly dropped
(CR 118.6: an unpayable activation is still a legal one).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.card import Color, Type

from .harness import PlayedScenario, Scenario

#: Mishra's Factory's own self-animation, the ability under test. Index 0 is
#: its intrinsic `{T}: Add {C}` and index 2 the Assembly-Worker pump.
_ANIMATE = 1


def _board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shang-Chi, Master of Kung Fu", "Mishra's Factory", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _animate_action(scenario: PlayedScenario):
    factory = scenario.find("Mishra's Factory", Zone.BATTLEFIELD, "alice")
    for action in legal_actions(scenario.game, "alice"):
        if (
            action.kind is ActionKind.ACTIVATE
            and action.card_id == factory.id
            and action.ability_index == _ANIMATE
        ):
            return action
    return None


def test_restricted_mana_pays_for_an_animated_lands_own_ability():
    """The Factory animates itself off an ordinary Forest, and only then does
    Shang-Chi's restricted mana become spendable on it.
    """
    scenario = _board()
    factory = scenario.find("Mishra's Factory", Zone.BATTLEFIELD, "alice")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(factory, forest, index=_ANIMATE)
    scenario.pass_until_resolved()
    assert Type.CREATURE in scenario.game.characteristics_of(factory).types
    assert Type.CREATURE not in factory.types, "the printed type line is still just Land"

    shang = scenario.find("Shang-Chi, Master of Kung Fu", Zone.BATTLEFIELD, "alice")
    scenario.activate(shang, index=0, color=Color.GREEN)
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 2
    # The Factory prints its own `{T}: Add {C}` and could otherwise pay for
    # itself, which would make this assertion pass for the wrong reason.
    factory.tap()

    action = _animate_action(scenario)
    assert action is not None, "CR 118.6: the activation is enumerated either way"
    assert action.affordable is Affordability.YES, (
        "an animated land is a creature source, so CR 106.6's restricted mana pays"
    )


def test_restricted_mana_does_not_pay_for_a_plain_land():
    """The inverse, and the reason the fix cannot simply drop the restriction:
    an unanimated Mishra's Factory is a land, Shang-Chi's mana may not be spent
    on it, and the action is still enumerated - as unaffordable.
    """
    scenario = _board()
    factory = scenario.find("Mishra's Factory", Zone.BATTLEFIELD, "alice")
    assert Type.CREATURE not in scenario.game.characteristics_of(factory).types

    shang = scenario.find("Shang-Chi, Master of Kung Fu", Zone.BATTLEFIELD, "alice")
    scenario.activate(shang, index=0, color=Color.GREEN)
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 2
    # Leave Shang-Chi's restricted two the only mana available: the Forest and
    # the Factory's own `{T}: Add {C}` would each pay the {1} unrestricted.
    for land in scenario.untapped_sources("Forest"):
        land.tap()
    factory.tap()

    action = _animate_action(scenario)
    assert action is not None, "CR 118.6: an unpayable activation is still a legal one"
    assert action.affordable is Affordability.NO, "a land is not a creature source"

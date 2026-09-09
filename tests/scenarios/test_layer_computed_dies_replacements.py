"""Two "would die" / "would be put into a graveyard" replacement effects in
`machines/replacement.py` that read a dying object's *computed* characteristics
rather than its printed ones, for a battlefield-origin event (CR 613.5).

`_kalitas_applies` ("If a nontoken creature an opponent controls would die...")
checked `Type.CREATURE in card.types` - the printed type line. `_black_or_red`
("...a black or red permanent...would be put into a graveyard, exile it
instead" - Sanctifier en-Vec) read `card.colors` the same way. Both fire while
the dying object is still on the battlefield (`event.origin is Zone.
BATTLEFIELD`, or here, equivalently, `card.zone is Zone.BATTLEFIELD` at the
moment the replacement is checked - the move to the graveyard has not
happened yet), which is exactly the case `Game.characteristics_of` answers
correctly and the printed reading does not.

Earthbend (CR 701.66a) is what makes an object's printed and computed *types*
disagree with a real card, exactly as `test_earthbend.py` and `test_layer_
computed_type_selection.py` already use it. No real, already-implemented card
changes a permanent's *colour* on the battlefield in this pool the way a
generic parser here would recognise (Purelace-style "becomes red" shapes are
one-shot until-end-of-turn effects on the stack, not the static kind these
tests need), so the colour half is built with the engine's own real
`set_colors` `Modification`, added through `ContinuousEffects.add` -
documented as the entry point "for a caller that is not going through the
registry" - the same pattern `test_layer_computed_planeswalker.py` and
`test_layer_computed_cast_grants.py` already use.

Every CR number here was already verified this session (CR 613.5, CR 613.1d,
CR 205.1b, CR 701.66a); Kalitas's and Sanctifier en-Vec's own oracle text and
CR 700.4/614.6's dies/replacement shape are unchanged from `tests/scenarios/
judge/test_judge_dies_triggers.py` and `tests/scenarios/test_replacement_
effects.py`, which already cover this module's ordinary (printed-agrees-with-
computed) behaviour.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    only_this_incarnation,
    set_colors,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _earthbent_forest_board():
    """alice holds a Bolt and Kalitas; bob has Badgermole Cub and enough
    Forests to animate one of them without needing to cast the Cub at
    sorcery speed on alice's turn (see `test_earthbend.py`'s identical note)."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Kalitas, Traitor of Ghet"]
        )
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, *_rest = scenario.untapped_sources("Forest", "Forest", "Forest", username="bob")
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    scenario.put_onto_battlefield("Badgermole Cub", "bob")
    scenario.pass_until_resolved()
    return scenario, animated


def test_kalitas_exiles_an_opponents_animated_land_instead_of_letting_it_die():
    """The positive case: the printed Forest is not a creature, but CR 701.66a
    already made it one on the computed board (CR 613.1d), and Kalitas's own
    "nontoken creature an opponent controls" (CR 700.4's "dies") has to see
    that or it lets the death through instead of exiling it.
    """
    scenario, animated = _earthbent_forest_board()
    assert scenario.game.characteristics_of(animated).is_creature
    assert not animated.is_creature, "the printed type line is still just Land"

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[animated])

    assert animated.zone is Zone.EXILE, "Kalitas: a nontoken creature an opponent controls"
    assert animated not in scenario.player("bob").graveyard


def test_kalitas_does_not_touch_your_own_animated_land():
    """The inverse against the *other* half of Kalitas's own condition: even
    once the type check is fixed, it still must not fire on alice's own
    creature. alice controls both Kalitas and the earthbent land here.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Badgermole Cub"],
            battlefield=["Mountain", "Kalitas, Traitor of Ghet", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    pay_sources, target_forest = forests[:2], forests[2]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources, username="alice")
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(target_forest).is_creature

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[target_forest])

    assert target_forest.zone is Zone.GRAVEYARD, "not an opponent's creature, so Kalitas is silent"


def _make_the_bears_red(scenario, bears) -> None:
    """A real layer-5 continuous effect (CR 613.1e) setting colour, through
    the documented "not going through the registry" entry point - the same
    `Modification` a text-parsed "becomes red" static ability would build.
    """
    store = scenario.game.continuous_effects
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description="test: Grizzly Bears becomes red",
                layer=Layer.COLOR,
                timestamp=store.tick(),
                selector=only_this_incarnation(bears, bears.zone_change_stamp),
                modification=set_colors(Color.RED),
            )
        )


def test_sanctifier_en_vec_exiles_a_permanent_the_computed_board_made_red():
    """The positive case for `_black_or_red`: Grizzly Bears prints green, but
    a layer-5 effect already made it red (CR 613.1e) by the time it would be
    put into a graveyard - Sanctifier en-Vec's "a black or red permanent...
    would be put into a graveyard, exile it instead" has to read that,
    not the printing.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Sanctifier en-Vec"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    assert Color.RED not in bears.colors, "the printed colour is green"
    _make_the_bears_red(scenario, bears)
    assert Color.RED in scenario.game.characteristics_of(bears).colors

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.EXILE, "the computed board says red"


def test_sanctifier_en_vec_leaves_a_still_green_permanent_alone():
    """The inverse: without the colour-changing effect, the same board's
    Grizzly Bears is a perfectly ordinary green creature and dies normally -
    the control `test_sanctifier_en_vec_catches_only_the_black_and_red_
    cards` in `test_replacement_effects.py` already proves for a spell; this
    is the same shape for a permanent already on the battlefield.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Sanctifier en-Vec"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD, "still green - Sanctifier en-Vec is silent"

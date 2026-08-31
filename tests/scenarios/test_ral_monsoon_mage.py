"""Ral, Monsoon Mage // Ral, Leyline Prodigy - a transforming double-faced
card, front face a creature, back face a planeswalker. Printed text (verified
with `resolve_cards` in this session, against
`tests/fixtures/cards/ral__monsoon_mage.json`):

    Ral, Monsoon Mage (front, creature)
    Instant and sorcery spells you cast cost {1} less to cast.
    Whenever you cast an instant or sorcery spell during your turn, flip a
    coin. If you lose the flip, Ral deals 1 damage to you. If you win the
    flip, you may exile Ral. If you do, return him to the battlefield
    transformed under his owner's control.

    Ral, Leyline Prodigy (back, planeswalker)
    Ral enters with an additional loyalty counter on him for each instant
    and sorcery spell you've cast this turn.
    +1: Until your next turn, instant and sorcery spells you cast cost {1}
    less to cast.
    -2: Ral deals 2 damage divided as you choose among one or two targets.
    Draw a card if you control a blue permanent other than Ral.
    -8: Exile the top eight cards of your library. You may cast instant and
    sorcery spells from among them this turn without paying their mana
    costs.

`Game.coin_flip` is CR 705.1's own primitive: no randomness primitive existed
before this wave, so it follows `Game.shuffle`'s own reproducibility
convention (`shuffle_seed` mixed with a running count) rather than inventing
an unseeded one. `scenario.game.shuffle_seed` is set explicitly in every test
below that flips a coin, so both outcomes are pinned deterministically rather
than asserted on a live coin.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 705.1** - "flip a coin... a two-sided object with easily distinguished
  sides and equal likelihood that either side lands face up."
- **CR 705.3** - "An effect may state that a coin flip has a certain result
  ... ignore the actual results of that flip and use the indicated results
  instead" - the rules text for what a deterministic seed stands in for.
- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up."
- **CR 712.14a** - a permanent put onto the battlefield "transformed" enters
  with its back face up.
- **CR 306.5b** - a planeswalker's intrinsic "enters with a number of loyalty
  counters on it equal to its printed loyalty number" replacement effect -
  the back face's own "additional" clause layers on top of this.
- **CR 606.6** - a negative loyalty ability can't be activated without enough
  loyalty counters to remove.
- **CR 601.2f** - the front face's own board-wide cost reduction, and the +1's
  time-boxed one.
- **CR 118.12** - "[Do something]. If [a player] does, [effect]" (the −2's
  own conditional draw, and the front face's "you may exile ... if you do").
- **CR 205.2b** - a multi-type spell (an artifact creature, say) still
  qualifies for "instant and sorcery spells" if it carries either type -
  read here for the −8's own type-filtered grant.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import ManaCost, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _front_board(*, alice_extra_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Ral, Monsoon Mage", "Mountain", "Mountain"]
            + (alice_extra_battlefield or []),
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _ral(scenario, name: str = "Ral, Monsoon Mage"):
    return scenario.find(name, Zone.BATTLEFIELD)


# -- front face: "Instant and sorcery spells you cast cost {1} less to cast." -


def test_front_face_discounts_an_instant_or_sorcery_spell():
    scenario = (
        Scenario()
        .player("alice", hand=["Wrenn's Resolve"], battlefield=["Ral, Monsoon Mage", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Wrenn's Resolve")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_front_face_does_not_discount_a_creature_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Ral, Monsoon Mage", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    assert casting.total_cost.mana == ManaCost.parse("{1}{G}")


# -- front face trigger: flip a coin, damage or exile-and-transform --------


def _cast_bolt_and_resolve_trigger(scenario):
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the trigger


def test_winning_the_flip_lets_you_exile_and_return_ral_transformed():
    scenario = _front_board().build()
    scenario.game.shuffle_seed = 0  # the first flip at this seed is a win
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=None)
    ral = _ral(scenario)

    _cast_bolt_and_resolve_trigger(scenario)

    assert ral.zone is Zone.BATTLEFIELD
    assert ral.name == "Ral, Leyline Prodigy"
    assert ral.is_planeswalker


def test_declining_a_won_flip_leaves_ral_exactly_as_he_was():
    scenario = _front_board().build()
    scenario.game.shuffle_seed = 0
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    ral = _ral(scenario)

    _cast_bolt_and_resolve_trigger(scenario)

    assert ral.zone is Zone.BATTLEFIELD
    assert ral.name == "Ral, Monsoon Mage"


def test_losing_the_flip_deals_1_damage_to_you_and_ral_stays_himself():
    scenario = _front_board().build()
    scenario.game.shuffle_seed = 2  # the first flip at this seed is a loss
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _ral(scenario)

    _cast_bolt_and_resolve_trigger(scenario)

    assert ral.zone is Zone.BATTLEFIELD
    assert ral.name == "Ral, Monsoon Mage"
    assert scenario.player("alice").life == 19


def test_the_trigger_does_not_fire_on_an_instant_cast_during_the_opponents_turn():
    """ "during your turn" - bob casting his own instant on his own turn
    never triggers alice's Ral."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ral, Monsoon Mage"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Lightning Bolt"]


# -- back face ETB: additional loyalty per instant/sorcery cast this turn --


def test_transforming_after_one_instant_or_sorcery_this_turn_adds_one_loyalty():
    """Ral, Leyline Prodigy's printed loyalty is 2; the Bolt whose own cast
    triggered the flip already counts (CR 601.2h: casting happens before the
    triggered ability that watches for it ever resolves)."""
    scenario = _front_board().build()
    scenario.game.shuffle_seed = 0
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=None)
    ral = _ral(scenario)

    _cast_bolt_and_resolve_trigger(scenario)

    assert ral.name == "Ral, Leyline Prodigy"
    assert ral.loyalty == 3  # printed 2 + 1 instant/sorcery cast this turn


def test_transforming_with_no_other_instant_or_sorcery_cast_yet_adds_nothing():
    """Reached straight through `Game.put_onto_battlefield`, without a
    triggering cast on the stack at all - the additional-loyalty replacement
    only ever counts what `Game.spells_cast_this_turn` actually holds."""
    scenario = _front_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _ral(scenario)

    exiled = scenario.game.exile_permanent(ral)
    returned = scenario.game.put_onto_battlefield(exiled, "alice", transformed=True)

    assert returned.name == "Ral, Leyline Prodigy"
    assert returned.loyalty == 2


# -- back face +1: "Until your next turn, instant and sorcery spells you
# cast cost {1} less to cast." --------------------------------------------


def test_plus_one_grants_a_temporary_cost_reduction():
    scenario = (
        Scenario()
        .player("alice", hand=["Wrenn's Resolve"], battlefield=["Ral, Monsoon Mage", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _ral(scenario)
    ral.transform()
    ral.add_counters(Counter.LOYALTY, 2)  # printed 2, so this is a stand-in transform

    scenario.activate(ral, index=0)
    scenario.pass_until_resolved()
    casting = scenario.cast("Wrenn's Resolve")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_plus_one_discount_is_gone_by_the_controllers_own_next_turn():
    """CR 800.4m: an "until your next turn" effect "will last until that turn
    would have begun" - so by the time alice is back in her own precombat
    main a full turn cycle later, the +1's discount must be gone and Wrenn's
    Resolve (printed {1}{R}, verified with `resolve_cards`) costs its full
    price again, with no other reducer on the board."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wrenn's Resolve"],
            battlefield=["Ral, Monsoon Mage", "Mountain", "Mountain"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _ral(scenario)
    ral.transform()
    ral.add_counters(Counter.LOYALTY, 2)  # printed 2, so this is a stand-in transform

    scenario.activate(ral, index=0)
    scenario.pass_until_resolved()

    while scenario.turn.active_player != "bob":
        scenario.advance()
    while scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Wrenn's Resolve")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


# -- back face -2: divided damage, plus a conditional draw -----------------


def _transformed_ral(scenario, loyalty: int = 5):
    ral = _ral(scenario)
    ral.transform()
    ral.add_counters(Counter.LOYALTY, loyalty)
    return ral


def test_minus_two_kills_a_2_2_and_draws_no_card_without_a_blue_permanent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ral, Monsoon Mage", "Island"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _transformed_ral(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(ral, index=1, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").hand == []
    assert ral.loyalty == 3  # 5 - 2


def test_minus_two_draws_a_card_when_you_control_a_blue_permanent():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ral, Monsoon Mage", "Delver of Secrets", "Island"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _transformed_ral(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(ral, index=1, targets=[bears])
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]


def test_minus_two_divides_damage_between_two_targets():
    """No `Casting.announce_division`-equivalent exists for an ability yet
    (`AbilityOnStack.division` stays `None`), so the 2 damage falls through
    to `_divided_damage_shares`'s own even-split fallback - the same one an
    un-announced spell division already uses - and lands 1 on each 2/2
    rather than being able to choose 2-and-0."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ral, Monsoon Mage"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _transformed_ral(scenario)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")

    scenario.activate(ral, index=1, targets=[first, second])
    scenario.pass_until_resolved()

    assert first.zone is Zone.BATTLEFIELD
    assert first.damage == 1
    assert second.zone is Zone.BATTLEFIELD
    assert second.damage == 1


def test_minus_two_cannot_be_activated_below_two_loyalty():
    """CR 606.6: the counters a negative cost removes have to already be
    there."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ral, Monsoon Mage"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _ral(scenario)
    ral.transform()  # printed loyalty only (2, since a bare `.transform()`
    # skips CR 306.5b's own entry replacement - see `test_class_levels.py`'s
    # sibling note on the same primitive)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="its −2 cost removes|CR 606.6"):
        scenario.activate(ral, index=1, targets=[bears])


# -- back face -8: exile 8, cast instant/sorcery from among them free -----


def test_minus_eight_grants_a_free_cast_permission_to_instants_and_sorceries_only():
    library = [
        "Lightning Bolt",
        "Forest",
        "Grizzly Bears",
        "Counterspell",
        "Island",
        "Sol Ring",
        "Mountain",
        "Wrenn's Resolve",
    ]
    scenario = (
        Scenario().player("alice", battlefield=["Ral, Monsoon Mage"], library=library).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _transformed_ral(scenario, loyalty=9)

    scenario.activate(ral, index=2)
    scenario.pass_until_resolved()

    exiled_by_name = {state.name: state for state in scenario.game.exile}
    assert set(exiled_by_name) == set(library)
    for name in ("Lightning Bolt", "Counterspell", "Wrenn's Resolve"):
        permission = scenario.game.play_permission_for(exiled_by_name[name], "alice")
        assert permission is not None
        assert permission.pays_mana_cost is False
        assert permission.action is PlayAction.CAST
    for name in ("Forest", "Grizzly Bears", "Island", "Sol Ring", "Mountain"):
        assert scenario.game.play_permission_for(exiled_by_name[name], "alice") is None


def test_minus_eight_lets_you_cast_the_free_instant_this_turn():
    library = ["Lightning Bolt"] + ["Forest"] * 7
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ral, Monsoon Mage"], library=library)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = _transformed_ral(scenario, loyalty=9)
    scenario.activate(ral, index=2)
    scenario.pass_until_resolved()
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([bears])
    assert str(casting.total_cost.mana) == ""

    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD

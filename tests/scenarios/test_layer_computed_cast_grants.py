"""`machines/casting.py`'s two battlefield sweeps for a granted cast option -
`granted_cast_options` (CR 610.5) and `static_free_cast_grants` (CR 118.9's
"or applied to it from another effect") - read the *computed* ability list of
each permanent they scan, not the printed oracle text (CR 613.5, CR 613.1f).

Both sweeps used to call `parse_abilities(permanent.card)` - the printing -
so a permanent whose granting static ability layer 6 already stripped still
granted the option, and the reverse (a static ability layer 6 *granted*)
never did. `tests/scenarios/judge/test_judge_granted_evoke.py` already
covers Ashling, the Limitless granting evoke off its own printing; this file
covers the same two real cards - Ashling and Omniscience - with their own
granting ability removed by a real layer-6 continuous effect
(`lose_all_abilities`, the same production `Modification` Humility and
Ovinize's own generic parsers already use, added through `ContinuousEffects.
add` the way `test_layer_computed_planeswalker.py` does), and checks the
grant disappears with it.

No printed card in this pool has its OWN static ability granted to it by
something else (the inverse direction: gaining a grant only on the computed
board), so that half of the fix is exercised through `test_layer_computed_
token_attacking.py`'s and `test_layer_computed_totem_armor.py`'s
own `add_type`/keyword-grant coverage instead of duplicated here - this file
is about the *removal* half, which both Ashling and Omniscience can exercise
with real cards.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    lose_all_abilities,
    only_this_incarnation,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _strip_all_abilities(scenario, permanent) -> None:
    """A real layer-6 continuous effect (CR 613.1f) removing every ability
    the permanent has, the same shape Humility's own parsed effect produces -
    built directly through the documented "caller not going through the
    registry" entry point rather than needing a second printed card whose
    own text happens to strip Ashling's or Omniscience's specific line.
    """
    store = scenario.game.continuous_effects
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description=f"test: {permanent.name} loses all abilities",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=lose_all_abilities,
            )
        )


def test_granted_evoke_disappears_once_ashlings_grant_is_stripped():
    """`granted_cast_options` (CR 610.5) must stop offering evoke once
    Ashling's own granting line is gone from the *computed* ability list,
    even though it is still sitting right there on the printed card.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ashmouth Hound"],
            battlefield=["Ashling, the Limitless", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashling = scenario.creature("Ashling, the Limitless", "alice")
    _strip_all_abilities(scenario, ashling)

    assert scenario.game.characteristics_of(ashling).abilities == ()
    assert "Elemental permanent spells you cast" in (ashling.oracle_text or "")

    casting = scenario.cast("Ashmouth Hound", username="alice")
    try:
        casting.use_keyword("evoke")
    except ValueError as exc:
        assert "no evoke ability" in str(exc)
    else:
        raise AssertionError("evoke should no longer be granted once the grant is stripped")


def test_granted_evoke_is_still_offered_without_the_strip():
    """The control: the same board, minus the layer-6 strip, still grants
    evoke exactly as `test_judge_granted_evoke.py` already proves - this is
    the premise the test above needs to be a meaningful negative.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ashmouth Hound"],
            battlefield=["Ashling, the Limitless", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="alice")
    casting.use_keyword("evoke")

    assert str(casting.total_cost.mana) == "{4}"


def test_omniscience_free_cast_grant_disappears_once_stripped():
    """`static_free_cast_grants` (CR 118.9) must stop granting alternative
    costs of nothing once Omniscience's own granting line is gone from the
    computed ability list, the same shape as evoke's grant above.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Omniscience"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    omniscience = scenario.find("Omniscience", Zone.BATTLEFIELD, "alice")
    _strip_all_abilities(scenario, omniscience)

    assert scenario.game.characteristics_of(omniscience).abilities == ()

    casting = scenario.cast("Lightning Bolt")
    assert casting.alternative_costs == []


def test_omniscience_free_cast_grant_is_still_offered_without_the_strip():
    """The control, mirroring `test_alternative_costs.py`'s own coverage."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Omniscience"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")
    (option,) = casting.alternative_costs
    assert option.available

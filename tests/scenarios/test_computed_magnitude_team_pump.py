"""Scenario: "Creatures you control [gain <keyword> and] get +X/+X until end
of turn, where X is the number of creatures you control." (CR 611.2) - a
duration-bearing team-wide pump whose magnitude and whose affected group are
both fixed the moment the effect begins (CR 611.2c), not recomputed on every
later board pass. Craterhoof Behemoth's own ETB is the card; Violent Outburst's
simpler fixed-magnitude sibling ("Creatures you control get +1/+0 until end of
turn.") is covered in `test_cascade.py`.

`docs/engine-coverage.md` used to carry a row for this - "A team-wide temporary
pump with no target" - recording that the shape reached a `LayerNotice`
instead of a working continuous effect. This file is what closes it.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def craterhoof_board(*, alice_extra: list[str] | None = None) -> Scenario:
    """Alice with Craterhoof Behemoth in hand, enough green to cast it
    ({5}{G}{G}{G} = 8 mana), and whatever other creatures the test wants."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Craterhoof Behemoth"],
            battlefield=[*(alice_extra or []), *["Forest"] * 8],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _cast_and_resolve_craterhoof(scenario: Scenario):
    sources = scenario.untapped_sources(*["Forest"] * 8, username="alice")
    scenario.cast_and_resolve("Craterhoof Behemoth", *sources, auto=True)
    assert scenario.stack_names() == ["Craterhoof Behemoth's triggered ability"]
    scenario.resolve_top()


def test_craterhoof_pumps_every_creature_alice_controls_by_the_number_she_controls():
    """Alice controls Craterhoof plus two Grizzly Bears when it resolves, so
    X = 3: every one of the three gets +3/+3 and trample."""
    scenario = craterhoof_board(alice_extra=["Grizzly Bears", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    _cast_and_resolve_craterhoof(scenario)
    hoof = scenario.creature("Craterhoof Behemoth", "alice")

    # Printed values, spelled out. `creature.power` must NOT appear on this
    # side: once a battlefield permanent is bound to its game (CR 613.5),
    # `CardState.power` answers with the computed value - the very thing the
    # left-hand side is asserting - so `creature.power + 3` would compare the
    # computed answer against itself plus X and fail by exactly X. It passed
    # only while power happened to be the printed value.
    expected = {"Craterhoof Behemoth": (5 + 3, 5 + 3), "Grizzly Bears": (2 + 3, 2 + 3)}

    for creature in [hoof, *bears]:
        assert scenario.game.characteristics_of(creature).power_toughness == expected[creature.name]
        assert has_keyword(creature, Keyword.TRAMPLE, scenario.game)


def test_craterhoof_does_not_pump_an_opponents_creature():
    """CR 611.2c's group is "creatures you control" - bob's Bear is excluded."""
    scenario = craterhoof_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_bear = scenario.creature("Grizzly Bears", "bob")

    _cast_and_resolve_craterhoof(scenario)

    assert scenario.game.characteristics_of(bobs_bear).power_toughness == (2, 2)
    assert not has_keyword(bobs_bear, Keyword.TRAMPLE, scenario.game)


def test_craterhoof_does_not_pump_a_creature_that_enters_afterward():
    """CR 611.2c: "any objects that come under [that] control later aren't
    affected." Alice controls only Craterhoof (X = 1) when it resolves; a
    second Grizzly Bears entering afterward never grows into the group."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Craterhoof Behemoth", "Grizzly Bears"],
            battlefield=[*["Forest"] * 8],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_and_resolve_craterhoof(scenario)
    hoof = scenario.creature("Craterhoof Behemoth", "alice")
    assert scenario.game.characteristics_of(hoof).power_toughness == (6, 6)  # 5/5 base + X=1

    later_bear = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert scenario.game.characteristics_of(later_bear).power_toughness == (2, 2)
    assert not has_keyword(later_bear, Keyword.TRAMPLE, scenario.game)
    # Craterhoof's own pump is unaffected by who arrives afterward.
    assert scenario.game.characteristics_of(hoof).power_toughness == (6, 6)


def test_craterhoofs_pump_and_trample_wear_off_in_cleanup():
    """CR 514.2/CR 703.4p: an "until end of turn" effect ends in the cleanup
    step, not merely at the end step."""
    scenario = craterhoof_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_and_resolve_craterhoof(scenario)
    hoof = scenario.creature("Craterhoof Behemoth", "alice")
    assert scenario.game.characteristics_of(hoof).power_toughness == (6, 6)

    scenario.game.continuous_effects.end_the_turn()

    assert scenario.game.characteristics_of(hoof).power_toughness == (5, 5)
    assert not has_keyword(hoof, Keyword.TRAMPLE, scenario.game)


def test_craterhoof_pumps_nothing_when_it_has_already_left_before_its_trigger_resolves():
    """X = 0: alice controls no creatures at all by the time the trigger
    resolves, because Craterhoof itself - her only creature - was destroyed
    in response to its own ETB trigger. CR 603.10a lets the ability resolve
    anyway; the effect must count zero creatures and do nothing rather than
    raise or read a stale board."""
    scenario = craterhoof_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 8, username="alice")
    scenario.cast_and_resolve("Craterhoof Behemoth", *sources, auto=True)
    hoof = scenario.find("Craterhoof Behemoth", Zone.BATTLEFIELD)
    assert scenario.stack_names() == ["Craterhoof Behemoth's triggered ability"]

    scenario.game.destroy(hoof)
    assert hoof.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # must not raise

    assert scenario.game.continuous_effects.layer_notices == []
    assert scenario.game.continuous_effects.effects == []

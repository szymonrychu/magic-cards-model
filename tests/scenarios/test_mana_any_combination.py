"""CR 106.1a / CR 605: "Add N mana in any combination of <colours>" - N mana,
each of its own colour, drawn from the colours the sentence names: every
colour ("any combination of colors"), a printed palette ("any combination of
{U} and/or {R}"), or the colours of an object ("any combination of its
colors"). One real printing per wording and per shape of count: a printed
number, CR 107.3's X defined by a "where X is" clause, an X announced by the
ability's own cost ("Remove X storage counters", "{X}"), and "that much"
read off the triggering event.

The second half is payment: auto-tap (CR 601.2g, CR 605.3a) plans the split
a cost actually needs from one mixed source, and a seat choosing by hand can
name it (`Action.color_choice_count`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import plan_mana_payment
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def _ability_index(scenario, permanent, starts_with: str) -> int:
    """The index of `permanent`'s activated ability whose effect starts with
    `starts_with` - read off the engine, never hardcoded per printing."""
    for index, ability in enumerate(scenario.game.activated_abilities(permanent)):
        if ability.effect.startswith(starts_with):
            return index
    raise AssertionError(f"{permanent.name} has no ability starting {starts_with!r}")


# --------------------------------------------------------------------------
# The storage lands: "{1}, Remove X storage counters from this land: Add X
# mana in any combination of {A} and/or {B}." CR 107.3a: X is announced as
# the ability is activated, and the cost removes that many counters.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("land", "split"),
    [
        ("Saltcrusted Steppe", [Color.GREEN, Color.GREEN, Color.WHITE]),
        ("Dreadship Reef", [Color.BLUE, Color.BLACK, Color.BLACK]),
        ("Calciform Pools", [Color.WHITE, Color.BLUE, Color.BLUE]),
        ("Molten Slagheap", [Color.BLACK, Color.RED, Color.RED]),
        ("Fungal Reaches", [Color.RED, Color.GREEN, Color.GREEN]),
    ],
)
def test_storage_land_adds_x_mana_split_across_its_two_colours(land, split):
    """Three counters removed is three mana, split as named across the two
    printed colours - not one mana of one colour."""
    scenario = Scenario().player("alice", battlefield=[land, "Wastes"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    storage = scenario.find(land, Zone.BATTLEFIELD)
    scenario.game.add_counters(storage, "storage", 4)
    (wastes,) = scenario.untapped_sources("Wastes", username="alice")
    index = _ability_index(scenario, storage, "Add X mana")

    assert scenario.activate(storage, wastes, index=index, x_value=3, color=split) is None

    expected: dict[Color, int] = {}
    for color in split:
        expected[color] = expected.get(color, 0) + 1
    assert scenario.game.player("alice").mana_pool.floating == expected
    assert storage.counter_count("storage") == 1


def test_storage_land_refuses_a_colour_outside_its_palette():
    """Fungal Reaches makes red and green only: a {U} in the named split is
    mana the printing never offered, and the activation is refused with the
    counters still on the land."""
    scenario = (
        Scenario().player("alice", battlefield=["Fungal Reaches", "Wastes"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reaches = scenario.find("Fungal Reaches", Zone.BATTLEFIELD)
    scenario.game.add_counters(reaches, "storage", 2)
    (wastes,) = scenario.untapped_sources("Wastes", username="alice")
    index = _ability_index(scenario, reaches, "Add X mana")

    with pytest.raises(ValueError):
        scenario.activate(reaches, wastes, index=index, x_value=2, color=[Color.RED, Color.BLUE])

    assert scenario.game.player("alice").mana_pool.total == 0
    assert reaches.counter_count("storage") == 2


# --------------------------------------------------------------------------
# A "where X is" count over a printed palette.
# --------------------------------------------------------------------------


def test_vivi_ornitier_adds_its_power_in_blue_and_red():
    """Vivi Ornitier: "{0}: Add X mana in any combination of {U} and/or {R},
    where X is Vivi Ornitier's power." Three +1/+1 counters, three mana:
    one blue and two red."""
    scenario = Scenario().player("alice", battlefield=["Vivi Ornitier"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    scenario.game.add_counters(vivi, Counter.PLUS_ONE, 3)
    index = _ability_index(scenario, vivi, "Add X mana")

    assert scenario.activate(vivi, index=index, color=[Color.BLUE, Color.RED, Color.RED]) is None

    assert scenario.game.player("alice").mana_pool.floating == {Color.BLUE: 1, Color.RED: 2}


def test_vivi_ornitier_refuses_green():
    """Green is not in "{U} and/or {R}"."""
    scenario = Scenario().player("alice", battlefield=["Vivi Ornitier"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    scenario.game.add_counters(vivi, Counter.PLUS_ONE, 2)
    index = _ability_index(scenario, vivi, "Add X mana")

    with pytest.raises(ValueError):
        scenario.activate(vivi, index=index, color=[Color.GREEN, Color.RED])

    assert scenario.game.player("alice").mana_pool.total == 0


def test_vivi_ornitier_action_names_its_palette_and_its_power_as_the_choice_count():
    """A seat choosing by hand reads the choice off the enumerated action:
    the two printed colours, and one colour per mana - Vivi's power."""
    scenario = Scenario().player("alice", battlefield=["Vivi Ornitier"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    scenario.game.add_counters(vivi, Counter.PLUS_ONE, 3)
    index = _ability_index(scenario, vivi, "Add X mana")

    (action,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE_MANA
        and action.card_id == vivi.id
        and action.ability_index == index
    ]

    assert set(action.color_options) == {Color.BLUE, Color.RED}
    assert action.color_choice_count == 3


def test_xenagos_plus_one_adds_one_mana_per_creature_split_red_and_green():
    """Xenagos, the Reveler: "+1: Add X mana in any combination of {R}
    and/or {G}, where X is the number of creatures you control." A loyalty
    ability, so it resolves from the stack (CR 605.1a, CR 606.2); two
    creatures, two mana, each colour chosen on its own as it resolves."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Xenagos, the Reveler", "Grizzly Bears", "Fog Bank"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    xenagos = scenario.find("Xenagos, the Reveler", Zone.BATTLEFIELD)
    index = _ability_index(scenario, xenagos, "Add X mana")
    scenario.will_choose(Color.RED.value, source="Xenagos, the Reveler")
    scenario.will_choose(Color.GREEN.value, source="Xenagos, the Reveler")

    scenario.activate(xenagos, index=index)
    scenario.pass_until_resolved()

    assert scenario.game.player("alice").mana_pool.floating == {Color.RED: 1, Color.GREEN: 1}
    assert xenagos.counter_count(Counter.LOYALTY) == 4


# --------------------------------------------------------------------------
# "that much" off the trigger event, and CR 500.5's mana kept until end of
# turn.
# --------------------------------------------------------------------------


def test_grand_warlord_radha_adds_one_mana_per_attacker_and_keeps_it():
    """Grand Warlord Radha: "Whenever one or more creatures you control
    attack, add that much mana in any combination of {R} and/or {G}. Until
    end of turn, you don't lose this mana as steps and phases end." Three
    attackers, three mana, still in the pool after combat ends."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grand Warlord Radha", "Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    radha = scenario.creature("Grand Warlord Radha", "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.will_choose(Color.RED.value, source="Grand Warlord Radha")
    scenario.will_choose(Color.GREEN.value, source="Grand Warlord Radha", times=2)

    scenario.attack_with(radha, *bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.total == 3
    assert pool.floating == {Color.RED: 1, Color.GREEN: 2}
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
    assert scenario.player("alice").mana_pool.total == 3


# --------------------------------------------------------------------------
# An X the ability's own cost announces is still a mana ability: no stack
# (CR 605.1a, CR 605.3b).
# --------------------------------------------------------------------------


def test_crucible_of_the_spirit_dragon_is_a_mana_ability_adding_x_restricted():
    """Crucible of the Spirit Dragon: "{T}, Remove X storage counters from
    this land: Add X mana in any combination of colors. Spend this mana only
    to cast Dragon spells or activate abilities of Dragons." The mana lands
    immediately, two mana of two colours, restricted."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Crucible of the Spirit Dragon"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crucible = scenario.find("Crucible of the Spirit Dragon", Zone.BATTLEFIELD)
    scenario.game.add_counters(crucible, "storage", 2)
    index = _ability_index(scenario, crucible, "Add X mana")

    on_stack = scenario.activate(crucible, index=index, x_value=2, color=[Color.RED, Color.WHITE])

    assert on_stack is None
    assert scenario.game.stack == []
    pool = scenario.game.player("alice").mana_pool
    assert pool.floating == {Color.RED: 1, Color.WHITE: 1}
    assert sum(entry.total for entry in pool.restricted) == 2
    assert crucible.counter_count("storage") == 0


def test_wizards_rockets_is_a_mana_ability_adding_its_announced_x():
    """Wizard's Rockets: "{X}, {T}, Sacrifice this artifact: Add X mana in
    any combination of colors." X=2 paid with two Wastes: two mana, a red
    and a green, straight into the pool."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wizard's Rockets", "Wastes", "Wastes"], library=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rockets = scenario.find("Wizard's Rockets", Zone.BATTLEFIELD)
    rockets.untap()
    wastes = scenario.untapped_sources("Wastes", "Wastes", username="alice")
    index = _ability_index(scenario, rockets, "Add X mana")

    on_stack = scenario.activate(
        rockets,
        *wastes,
        index=index,
        x_value=2,
        sacrificing=[rockets],
        color=[Color.RED, Color.GREEN],
    )

    assert on_stack is None
    assert scenario.game.player("alice").mana_pool.floating == {Color.RED: 1, Color.GREEN: 1}
    assert rockets.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# A delayed trigger's X (CR 603.7) and an object's colours.
# --------------------------------------------------------------------------


def test_plasm_capture_adds_the_countered_spells_mana_value_next_first_main_phase():
    """Plasm Capture: "Counter target spell. At the beginning of your next
    first main phase, add X mana in any combination of colors, where X is
    that spell's mana value." Countering bob's Lightning Helix (mana value 2) gives
    alice two mana of her choice at the start of her next precombat main
    phase - not before."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Plasm Capture"],
            battlefield=["Forest", "Forest", "Island", "Island"],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Helix"],
            battlefield=["Mountain", "Plains"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    helix = scenario.cast_onto_stack(
        "Lightning Helix", username="bob", auto=True, targets=["alice"]
    )
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Plasm Capture", username="alice", auto=True, targets=[helix])
    scenario.resolve_top()
    assert helix.zone is Zone.GRAVEYARD
    assert scenario.player("alice").mana_pool.total == 0

    scenario.will_choose(Color.WHITE.value, source="Plasm Capture", username="alice")
    scenario.will_choose(Color.BLACK.value, source="Plasm Capture", username="alice")
    scenario.advance()
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN):
        assert scenario.player("alice").mana_pool.total == 0
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1, Color.BLACK: 1}


# --------------------------------------------------------------------------
# A granted mana ability (CR 613.1f) with a printed count.
# --------------------------------------------------------------------------


def test_leyline_immersion_grants_five_mana_in_any_combination():
    """Leyline Immersion: enchanted legendary creature has "{T}: Add five
    mana in any combination of colors. Spend this mana only to cast spells."
    Tapped for {W}{U}{B}{R}{G}, all five restricted."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vivi Ornitier"], hand=["Leyline Immersion"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    immersion = scenario.put_onto_battlefield("Leyline Immersion", "alice")
    immersion.attach_to(vivi)
    vivi.summoning_sick = False
    index = _ability_index(scenario, vivi, "Add five mana")

    scenario.activate(
        vivi,
        index=index,
        color=[Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN],
    )

    pool = scenario.game.player("alice").mana_pool
    assert sum(entry.total for entry in pool.restricted) == 5


# --------------------------------------------------------------------------
# Auto-tap plans the split (CR 601.2g, CR 605.3a), not one colour.
# --------------------------------------------------------------------------


def test_auto_tap_pays_red_and_white_from_one_axebane_guardian():
    """Two defenders make Axebane Guardian add two mana in any combination:
    Lightning Helix's {R}{W} is paid by it alone, planned as one red and one
    white."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Axebane Guardian", "Fog Bank"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find("Axebane Guardian", Zone.BATTLEFIELD)

    plan = plan_mana_payment(
        ManaCost.parse("{R}{W}"),
        scenario.game.permanents_controlled_by("alice"),
        game=scenario.game,
        payer="alice",
    )

    assert plan is not None
    assert [(source.id, sorted(colors)) for source, colors, _r in plan] == [
        (guardian.id, sorted([Color.RED, Color.WHITE]))
    ]


def test_auto_tap_casts_with_the_planned_split_and_a_land_beside_it():
    """Axebane Guardian (two defenders) beside a Forest pays Electrolyze's
    {1}{U}{R}: the Guardian's mixture covers {U}{R}, the Forest the {1}."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Electrolyze"],
            battlefield=["Axebane Guardian", "Fog Bank", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "Electrolyze", username="alice", auto=True, targets=[bears], division=[2]
    )

    tapped = sorted(s.name for s in scenario.game.permanents_controlled_by("alice") if s.tapped)
    assert tapped == ["Axebane Guardian", "Forest"]
    assert scenario.game.player("alice").mana_pool.total == 0


def test_auto_tap_still_refuses_what_the_mixture_cannot_cover():
    """One mixed source of two mana cannot pay three coloured symbols: the
    split is planned, not invented."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Axebane Guardian", "Fog Bank"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    plan = plan_mana_payment(
        ManaCost.parse("{U}{R}{W}"),
        scenario.game.permanents_controlled_by("alice"),
        game=scenario.game,
        payer="alice",
    )

    assert plan is None


def test_a_hand_named_split_is_tripled_under_nyxbloom_ancient():
    """CR 106.12b: Nyxbloom Ancient triples what a permanent is tapped for.
    Axebane Guardian (two defenders) named for {R}{W} by hand makes
    {R}{R}{R}{W}{W}{W} - the payment recognises the tripled split as the
    Guardian's own mixture, not mana it never offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Helix"],
            battlefield=["Nyxbloom Ancient", "Axebane Guardian", "Fog Bank"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find("Axebane Guardian", Zone.BATTLEFIELD)
    payment = scenario.cast("Lightning Helix", "alice", targets=["bob"]).begin_paying()

    payment.tap_for_mana(guardian, [Color.RED, Color.WHITE] * 3)

    assert guardian.tapped
    assert not payment.shortfall


def test_auto_tap_plans_the_split_under_nyxbloom_ancient():
    """The same board through auto-tap: the Guardian alone pays the Helix."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Helix"],
            battlefield=["Nyxbloom Ancient", "Axebane Guardian", "Fog Bank"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Lightning Helix", username="alice", auto=True, targets=["bob"])

    tapped = [s.name for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert tapped == ["Axebane Guardian"]

"""A token whose ability is granted by the *next* sentence:
"Create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this
token: Add {C}.""

- **CR 111.3** - the spell or ability that creates a token may define any
  number of its characteristics; this becomes the token's "text". The quoted
  ability in the following "It has" sentence is part of that definition.
- **CR 608.2c** - "later text on the card may modify the meaning of earlier
  text"; "It has ..." modifies the token the previous sentence created, it is
  not an instruction of its own.
- **CR 605.1a** - "Sacrifice this token: Add {C}." has no target and adds mana,
  so it is a mana ability: it resolves immediately, never using the stack.

Warping Wail's third mode is the listed card. Spawning Breath (a spell whose
token sentence follows a damage sentence) and Blisterpod (the same template
inside a dies trigger) are the second printings.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _tokens(scenario, name: str, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == username
    ]


def _warping_wail_scion(scenario) -> None:
    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([3])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username="alice")
    casting.begin_paying()
    casting.cast()
    scenario.pass_until_resolved()


def _wail_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Warping Wail", "Warping Wail"],
            battlefield=["Eldrazi Temple", "Wastes", "Island"],
        )
        .player("bob", battlefield=["Memnite"])
    )


def test_warping_wail_creates_a_colorless_1_1_scion():
    scenario = _wail_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _warping_wail_scion(scenario)

    (scion,) = _tokens(scenario, "Eldrazi Scion Token")
    assert (scion.power, scion.toughness) == (1, 1)
    assert scion.card.colors == []
    assert scion.card.subtypes == ["Eldrazi", "Scion"]
    assert scion.card.oracle_text == "Sacrifice this token: Add {C}."


def test_warping_wail_scion_sacrifices_for_colorless_mana():
    """The granted ability is a working mana ability (CR 605.1a): activating it
    sacrifices the Scion and adds {C}, with nothing put on the stack."""
    scenario = _wail_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _warping_wail_scion(scenario)
    (scion,) = _tokens(scenario, "Eldrazi Scion Token")

    on_stack = scenario.activate(scion, username="alice")

    assert on_stack is None
    assert scenario.game.stack == []
    assert _tokens(scenario, "Eldrazi Scion Token") == []
    assert scion.zone is not Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


def test_warping_wail_scion_mana_pays_for_a_spell():
    """The Scion's {C} pays for the second Warping Wail's {C} pip."""
    scenario = _wail_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Pay the first Wail with Eldrazi Temple and Wastes.
    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([3])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Eldrazi Temple", "Wastes", username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    (scion,) = _tokens(scenario, "Eldrazi Scion Token")

    assert scenario.activate(scion, username="alice") is None  # {C} floats
    second = scenario.cast("Warping Wail", username="alice")
    second.choose_modes([3])
    payment = second.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", username="alice"))
    scenario.put_on_stack(second)
    scenario.pass_until_resolved()

    assert scion.zone is not Zone.BATTLEFIELD
    assert len(_tokens(scenario, "Eldrazi Scion Token")) == 1
    assert scenario.player("alice").mana_pool.floating == {}


def test_warping_wail_other_modes_still_work():
    """Mode 1 exiles a creature with power or toughness 1 or less."""
    scenario = _wail_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")

    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([memnite])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username="alice")
    casting.begin_paying()
    casting.cast()
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.EXILE
    assert _tokens(scenario, "Eldrazi Scion Token") == []


def test_spawning_breath_deals_damage_then_creates_a_spawn_with_the_ability():
    """The token sentence follows a damage sentence; both happen, in order."""
    scenario = (
        Scenario()
        .player("alice", hand=["Spawning Breath"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life = scenario.player("bob").life

    scenario.cast_and_resolve("Spawning Breath", auto=True, username="alice", targets=["bob"])

    assert scenario.player("bob").life == bob_life - 1
    (spawn,) = _tokens(scenario, "Eldrazi Spawn Token")
    assert (spawn.power, spawn.toughness) == (0, 1)
    assert spawn.card.oracle_text == "Sacrifice this token: Add {C}."

    assert scenario.activate(spawn, username="alice") is None
    assert spawn.zone is not Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


def test_blisterpod_dies_trigger_creates_a_scion_with_the_ability():
    """The same template inside a dies trigger."""
    scenario = Scenario().player("alice", battlefield=["Blisterpod"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pod = scenario.creature("Blisterpod", "alice")

    scenario.game.destroy(pod)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    (scion,) = _tokens(scenario, "Eldrazi Scion Token")
    assert (scion.power, scion.toughness) == (1, 1)
    assert scion.card.oracle_text == "Sacrifice this token: Add {C}."
    assert scenario.activate(scion, username="alice") is None
    assert scion.zone is not Zone.BATTLEFIELD


def test_warping_wail_counter_mode_still_works():
    """Mode 2 counters a sorcery - here alice's own Bestial Menace, countered
    while she holds priority - and makes no Scion."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bestial Menace", "Warping Wail"],
            battlefield=["Forest"] * 5 + ["Wastes", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    menace = scenario.cast_onto_stack(
        "Bestial Menace",
        *scenario.untapped_sources(*["Forest"] * 5, username="alice"),
        username="alice",
    )

    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([menace])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Wastes", "Island", username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert menace.zone is Zone.GRAVEYARD
    assert [state for state in scenario.game.battlefield if state.name.endswith(" Token")] == []

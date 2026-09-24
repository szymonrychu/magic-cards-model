"""CR 602.1b: who may activate an ability, and instructions printed after a
quoted ability.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 602.1b** - activation instructions "may state which players can
  activate that ability, may restrict when a player can activate the
  ability ... If an activated ability has any activation instructions, they
  appear last, after the ability's effect."
- **CR 602.2** - "Only an object's controller (or its owner, if it doesn't
  have a controller) can activate its activated ability unless the object
  specifically says otherwise."
- **CR 602.2a** - the activated ability's "controller is the player who
  activated the ability".
- **CR 109.5** - "you" and "your" on an object are its controller: "Only
  your opponents may activate this ability" names the object's controller's
  opponents.
- **CR 602.5b** - a restriction "continues to apply to that object even if its
  controller changes".
- **CR 602.5d** / **CR 307.5** - "Activate only as a sorcery": priority, the
  activating player's own main phase, and an empty stack.

Two parse gaps closed here: "Only your opponents may activate this ability"
was left inside the effect text (never read, and the opponents could never
activate it at all), and "Activate only as a sorcery" printed after a quoted
ability (`... with "This token saddles Mounts ..." Activate only as a
sorcery.`) was left inside the effect too, so the ability was activatable at
instant speed (fail-open).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import ActivatedAbility, parse_abilities
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario


def _activated(name: str) -> list[ActivatedAbility]:
    return [a for a in parse_abilities(card(name)) if isinstance(a, ActivatedAbility)]


def _offered(scenario: PlayedScenario, permanent, username: str) -> list:
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.card_id == permanent.id
        and action.kind in {ActionKind.ACTIVATE, ActionKind.ACTIVATE_MANA}
    ]


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


# -- the parse: instructions are found, not left in the effect ----------------


def test_only_your_opponents_is_read_as_an_instruction_not_an_effect():
    (ability,) = _activated("Knight of the Holy Nimbus")
    assert ability.effect == "This creature can't be regenerated this turn."
    assert ability.instructions == "Only your opponents may activate this ability."


def test_a_joined_who_and_when_instruction_is_read_whole():
    (ability,) = _activated("Detention Vortex")
    assert ability.effect == "Destroy this Aura."
    assert ability.instructions == (
        "Only your opponents may activate this ability and only as a sorcery."
    )


def test_an_instruction_after_a_quoted_ability_is_found():
    """Reef Roads' quoted token ability ends in its own period and closing
    quote; the instruction after it is still the ability's last sentence."""
    ability = _activated("Reef Roads")[-1]
    assert ability.instructions == "Activate only as a sorcery."
    assert ability.effect.endswith('as though its power were 2 greater."')


# -- only your opponents may activate -----------------------------------------


def test_the_controller_may_not_activate_an_opponents_only_ability():
    """Knight of the Holy Nimbus: "{2}: This creature can't be regenerated this
    turn. Only your opponents may activate this ability." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Knight of the Holy Nimbus", "Plains", "Plains"])
        .player("bob", battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of the Holy Nimbus", "alice")

    refusal = scenario.why_cannot_activate(knight, username="alice")
    assert refusal == (
        "only alice's opponents may activate Knight of the Holy Nimbus's ability, "
        "and alice controls it (CR 602.1b)"
    )
    with pytest.raises(ValueError, match="only alice's opponents may activate"):
        scenario.activate(knight, *scenario.untapped_sources("Plains", "Plains"))
    assert _offered(scenario, knight, "alice") == []


def test_an_opponent_activates_it_pays_for_it_and_controls_the_ability():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Knight of the Holy Nimbus"])
        .player("bob", battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of the Holy Nimbus", "alice")

    assert scenario.why_cannot_activate(knight, username="bob") is None
    assert [action.ability_index for action in _offered(scenario, knight, "bob")] == [0]
    scenario.pass_priority("alice")  # CR 117.3d: bob gets priority
    ability = scenario.activate(
        knight, *scenario.untapped_sources("Mountain", "Mountain", username="bob"), username="bob"
    )
    assert ability is not None
    assert ability.controller == "bob"
    assert all(mountain.tapped for mountain in scenario.game.permanents_controlled_by("bob"))
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty


def test_only_your_opponents_follows_the_new_controller():
    """CR 602.5b and CR 109.5: once bob controls the Knight (Soul Ransom),
    "your opponents" are bob's - alice may now activate it and bob may not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Knight of the Holy Nimbus", "Plains", "Plains"])
        .player(
            "bob",
            hand=["Soul Ransom"],
            battlefield=["Island", "Island", "Swamp", "Swamp"],
            library=["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of the Holy Nimbus", "alice")
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Soul Ransom",
        *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="bob"),
        targets=[knight],
        username="bob",
    )
    assert scenario.game.controller_of(knight).username == "bob"
    assert scenario.why_cannot_activate(knight, username="alice") is None
    refusal = scenario.why_cannot_activate(knight, username="bob")
    assert refusal is not None and "only bob's opponents may activate" in refusal


def test_only_your_opponents_and_only_as_a_sorcery():
    """Detention Vortex: "{3}: Destroy this Aura. Only your opponents may
    activate this ability and only as a sorcery." - both halves: bob may not
    on alice's turn (CR 307.5's "main phase of their turn"), and on his own
    he activates it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Detention Vortex"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Plains"] * 4,
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Mountain", "Mountain", "Mountain"],
            library=["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    vortex = scenario.cast_and_resolve(
        "Detention Vortex",
        *scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[bears],
    )
    assert vortex.zone is Zone.BATTLEFIELD

    refusal = scenario.why_cannot_activate(vortex, username="bob")
    assert refusal is not None and "as a sorcery" in refusal
    assert "only alice's opponents" in (
        scenario.why_cannot_activate(vortex, username="alice") or ""
    )

    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.why_cannot_activate(vortex, username="bob") is None
    ability = scenario.activate(
        vortex,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        username="bob",
    )
    assert ability is not None and ability.controller == "bob"
    assert scenario.stack_names() == ["Detention Vortex's activated ability"]


# -- any player may activate -------------------------------------------------


def test_any_player_may_activate():
    """Oona's Prowler: "Discard a card: This creature gets -2/-0 until end of
    turn. Any player may activate this ability." - its controller and an
    opponent alike; the opponent discards from their own hand."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Oona's Prowler"], hand=["Plains"])
        .player("bob", hand=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prowler = scenario.creature("Oona's Prowler", "alice")
    assert scenario.why_cannot_activate(prowler, username="alice") is None
    assert scenario.why_cannot_activate(prowler, username="bob") is None
    assert _offered(scenario, prowler, "bob") != []

    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    scenario.pass_priority("alice")  # CR 117.3d: bob gets priority
    scenario.activate(prowler, discarding=[mountain], username="bob")
    scenario.pass_until_resolved()
    assert mountain.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(prowler) == 1


# -- "Activate only as a sorcery" after a quoted ability ----------------------


def _roads(step: Step) -> tuple[PlayedScenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Reef Roads", "Island", "Island"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(step)
    return scenario, scenario.creature("Reef Roads", "alice")


def test_a_stranded_sorcery_instruction_is_enforced():
    """Reef Roads: "{1}{U}, {T}, Sacrifice this land: Create a 1/1 colorless
    Pilot creature token with "This token saddles Mounts and crews Vehicles
    as though its power were 2 greater." Activate only as a sorcery." -
    refused in combat, allowed in the main phase."""
    scenario, roads = _roads(Step.BEGINNING_OF_COMBAT)
    refusal = scenario.why_cannot_activate(roads, index=1)
    assert refusal is not None and "as a sorcery" in refusal and "CR 602.5d" in refusal

    scenario, roads = _roads(Step.PRECOMBAT_MAIN)
    assert scenario.why_cannot_activate(roads, index=1) is None
    scenario.activate(roads, *scenario.untapped_sources("Island", "Island"), index=1)
    scenario.pass_until_resolved()
    assert [state.name for state in scenario.game.permanents_controlled_by("alice")].count(
        "Pilot Token"
    ) == 1


def test_a_stranded_sorcery_instruction_on_a_second_printing():
    """Geth, Thane of Contracts: "{1}{B}{B}, {T}: Return target creature card
    from your graveyard to the battlefield. It gains "If this creature would
    leave the battlefield, exile it instead of putting it anywhere else."
    Activate only as a sorcery." - refused on an opponent's turn."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Geth, Thane of Contracts", "Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    geth = scenario.creature("Geth, Thane of Contracts", "alice")
    assert scenario.why_cannot_activate(geth) is None
    _next_turn(scenario)
    refusal = scenario.why_cannot_activate(geth, username="alice")
    assert refusal is not None and "as a sorcery" in refusal


def test_a_stranded_sorcery_instruction_off_the_battlefield():
    """Expendable Lackey: "{1}{U}, Exile this card from your graveyard: Create
    a 1/1 blue Fish creature token with "This token can't be blocked."
    Activate only as a sorcery." - from the graveyard (CR 113.6j)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Expendable Lackey"], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    lackey = scenario.find("Expendable Lackey", Zone.GRAVEYARD, "alice")
    refusal = off_battlefield_activation(scenario.game, lackey, "alice").why_not()
    assert refusal is not None and "as a sorcery" in refusal
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    assert off_battlefield_activation(scenario.game, lackey, "alice").why_not() is None

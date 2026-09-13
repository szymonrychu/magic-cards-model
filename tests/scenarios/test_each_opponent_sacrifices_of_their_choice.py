"""Scenario: "each opponent sacrifices a <description> of their choice".

The edict template. CR 701.21a: "To sacrifice a permanent, its controller moves
it from the battlefield directly to its owner's graveyard. A player can't
sacrifice something that isn't a permanent, or something that's a permanent
they don't control." Nothing is targeted (CR 115.10a), so which permanent goes
is a choice made while the effect is applied (CR 608.2d), by the sacrificing
player - "of their choice" - and only among permanents matching the printed
description. With several opponents, CR 101.4 has them choose in APNAP order
and then the sacrifices happen simultaneously.

The description is read by the same grammar a "target ..." phrase is
(`machines/targeting.py`), so token-ness (CR 111.1), card types, "non-" types
and a trailing "with <keyword>" all come from one reader:

- **Sheoldred's Edict** - three modes (CR 700.2a): "a nontoken creature",
  "a creature token", "a planeswalker".
- **Yawning Fissure** - off-pool, "a land": a different card type.
- **Clip Wings** - off-pool, "a creature of their choice with flying": the
  keyword qualifier printed *after* "of their choice", a different word order.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 701.21a, 608.2d, 101.4, 111.1, 700.2a, 115.10a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

EDICT = "Sheoldred's Edict"


def _cast_edict(scenario, mode: int) -> None:
    """Alice casts Sheoldred's Edict choosing `mode`, and it resolves."""
    casting = scenario.cast(EDICT, username="alice")
    casting.choose_modes([mode])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _bob_with_spirits(*battlefield: str) -> Scenario:
    """Bob is active and makes three 1/1 Spirit tokens with Spectral
    Procession; alice answers at instant speed once bob passes."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Spectral Procession"],
            battlefield=["Plains", "Plains", "Plains", *battlefield],
        )
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp", "Llanowar Elves"])
    )


def _make_spirits(scenario) -> list:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="bob")
    scenario.cast_and_resolve("Spectral Procession", *plains, username="bob")
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.name == "Spirit Token" and state.controller == "bob"
    ]
    assert len(spirits) == 3
    scenario.pass_priority("bob")
    return spirits


def _sacrifice_questions(scenario, username: str) -> list:
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.player == username
    ]


# -- Sheoldred's Edict, mode 1: a nontoken creature ---------------------------


def test_nontoken_mode_sacrifices_the_creature_card_and_ignores_the_tokens():
    """CR 111.1: a token is a permanent not represented by a card, so "nontoken"
    leaves Grizzly Bears as bob's only candidate and the Spirits stay."""
    scenario = _bob_with_spirits("Grizzly Bears").build()
    spirits = _make_spirits(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_edict(scenario, 1)

    assert bears.zone is Zone.GRAVEYARD
    assert all(spirit.zone is Zone.BATTLEFIELD for spirit in spirits)
    assert scenario.game.mode_notices == []


def test_nontoken_mode_with_only_tokens_sacrifices_nothing():
    """No nontoken creature: CR 608.2d cannot ask for an impossible choice, so
    nothing is sacrificed and no question is put to bob."""
    scenario = _bob_with_spirits().build()
    spirits = _make_spirits(scenario)

    _cast_edict(scenario, 1)

    assert all(spirit.zone is Zone.BATTLEFIELD for spirit in spirits)
    assert _sacrifice_questions(scenario, "bob") == []
    assert scenario.game.mode_notices == []


def test_the_casters_own_creatures_are_not_touched():
    """ "Each opponent" - alice's own Llanowar Elves is no candidate at all."""
    scenario = _bob_with_spirits("Grizzly Bears").build()
    _make_spirits(scenario)
    elves = scenario.creature("Llanowar Elves", "alice")

    _cast_edict(scenario, 1)

    assert elves.zone is Zone.BATTLEFIELD


def test_the_sacrificing_player_chooses_among_several():
    """ "Of their choice": bob, not alice, picks which of two nontoken
    creatures goes, and his pick is the one sacrificed."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_cards(giant, username="bob", source=EDICT)

    _cast_edict(scenario, 1)

    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    (question,) = _sacrifice_questions(scenario, "bob")
    assert set(question.cards) == {bears.id, giant.id}
    assert question.amount == 1


def test_every_opponent_sacrifices_one():
    """Two opponents each lose one of their own creatures (CR 101.4: both
    choose, then both sacrifices happen)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .player("carol", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "carol")

    _cast_edict(scenario, 1)

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD


# -- Sheoldred's Edict, mode 2: a creature token ------------------------------


def test_token_mode_sacrifices_a_token_and_ignores_the_creature_card():
    """ "A creature token" is the mirror image of mode 1: Grizzly Bears is not
    a candidate, and bob's chosen Spirit is the one that goes."""
    scenario = _bob_with_spirits("Grizzly Bears").build()
    spirits = _make_spirits(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(spirits[1], username="bob", source=EDICT)

    _cast_edict(scenario, 2)

    assert bears.zone is Zone.BATTLEFIELD
    assert spirits[1].zone is not Zone.BATTLEFIELD
    assert spirits[0].zone is Zone.BATTLEFIELD
    assert spirits[2].zone is Zone.BATTLEFIELD
    (question,) = _sacrifice_questions(scenario, "bob")
    assert set(question.cards) == {spirit.id for spirit in spirits}
    assert scenario.game.mode_notices == []


def test_token_mode_with_no_tokens_sacrifices_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_edict(scenario, 2)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.mode_notices == []


# -- Sheoldred's Edict, mode 3: a planeswalker --------------------------------


def test_planeswalker_mode_sacrifices_the_planeswalker_not_the_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Karn, the Great Creator", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_edict(scenario, 3)

    assert karn.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.mode_notices == []


def test_planeswalker_mode_with_no_planeswalker_sacrifices_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EDICT], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_edict(scenario, 3)

    assert bears.zone is Zone.BATTLEFIELD
    assert ring.zone is Zone.BATTLEFIELD


# -- Off-pool printings of the same template ----------------------------------


def test_yawning_fissure_sacrifices_a_land_of_the_opponents_choice():
    """Off-pool, a different card type: bob keeps his creature and loses the
    land he picks."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Yawning Fissure"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Forest", "Island", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(island, username="bob", source="Yawning Fissure")

    mountains = scenario.untapped_sources(*["Mountain"] * 5, username="alice")
    scenario.cast_and_resolve("Yawning Fissure", *mountains, username="alice")

    assert island.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD


def test_clip_wings_reads_the_keyword_printed_after_of_their_choice():
    """Off-pool, "a creature of their choice with flying": Wind Drake is the
    only creature with flying, so it goes and Grizzly Bears stays."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Clip Wings"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Wind Drake", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drake = scenario.creature("Wind Drake", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Clip Wings", *forests, username="alice")

    assert drake.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_clip_wings_with_no_flyer_sacrifices_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Clip Wings"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Clip Wings", *forests, username="alice")

    assert bears.zone is Zone.BATTLEFIELD

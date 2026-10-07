"""CR 106.6 / CR 716.2a: "Spend this mana only to ... gain a Class level."

Sorcerer Class (Level 2): Creatures you control have "{T}: Add {U} or {R}.
Spend this mana only to cast an instant or sorcery spell or to gain a Class
level."

A Class gains a level only through its level bar, "[Cost]: Level N", which CR
716.2a defines as an activated ability ("[Cost]: This Class's level becomes
N. Activate only if this Class is level N-1 and only as a sorcery"). So the
second clause permits the mana to pay a level bar's activation cost, and
nothing else that is activated - not even another ability of the same Class.

CR numbers used, read with `mise run rules:find` in this session: CR 106.6,
CR 716.2a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost.payment import spend_restriction
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.mana import ManaSpend, SpendPurpose
from tests.cards import card

from .harness import Scenario

SORCERER_CLASS_MANA = (
    "{T}: Add {U} or {R}. Spend this mana only to cast an instant or sorcery spell "
    "or to gain a Class level."
)


def test_the_restriction_reads_into_a_cast_clause_and_a_class_level_clause():
    restriction = spend_restriction(SORCERER_CLASS_MANA)

    assert restriction is not None and restriction.understood
    assert [clause.purpose for clause in restriction.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]
    assert [clause.class_level for clause in restriction.clauses] == [False, True]


def test_the_mana_pays_a_level_bar_and_an_instant_but_not_other_costs():
    restriction = spend_restriction(SORCERER_CLASS_MANA)
    assert restriction is not None
    sorcerer_class = card("Sorcerer Class")

    assert restriction.allows(ManaSpend.activating(sorcerer_class, class_level=True)) is True
    assert restriction.allows(ManaSpend.casting(card("Lightning Bolt"), zone=Zone.HAND)) is True
    # Another activated ability, even of a Class, is not a level bar.
    assert restriction.allows(ManaSpend.activating(sorcerer_class)) is False
    assert restriction.allows(ManaSpend.activating(card("Grizzly Bears"))) is False
    assert restriction.allows(ManaSpend.casting(card("Grizzly Bears"), zone=Zone.HAND)) is False


def _board(hand: list[str] | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand or [],
            battlefield=["Sorcerer Class", *["Grizzly Bears"] * 5],
            library=["Island"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.find("Sorcerer Class", Zone.BATTLEFIELD, "alice").class_level = 2
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_creatures_mana_pays_for_sorcerer_class_level_3():
    scenario = _board()
    sorcerer_class = scenario.find("Sorcerer Class", Zone.BATTLEFIELD, "alice")

    scenario.activate(sorcerer_class, index=1, auto=True)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    assert sorcerer_class.class_level == 3
    bears = [
        p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Grizzly Bears"
    ]
    assert len(bears) == 5 and not any(bear.untapped for bear in bears)


def test_creatures_mana_cannot_cast_a_creature_spell():
    scenario = _board(hand=["Grizzly Bears"])
    in_hand = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    casts = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == in_hand.id
    ]

    assert casts and all(action.affordable is Affordability.NO for action in casts)

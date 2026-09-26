"""Scenario: "Whenever you cast a spell with {X} in its mana cost, [effect]."
(Geometer's Arthropod, Matterbending Mage) and Repartee - CR 207.2c, no rules
meaning of its own - "Whenever you cast an instant or sorcery spell that
targets a creature, [effect]." (Snooping Page).

The {X}-in-mana-cost restriction (`machines/triggers.
_CAST_SPELL_MANA_COST_SYMBOL_RE`) reads the cast spell's own *printed* mana
cost for the literal symbol named, never CR 202.3's mana value and never the
announced value of X itself - a spell with no {X} at all in its cost never
matches, however much mana was spent casting it. Geometer's Arthropod's own
effect then reads the announced X (CR 107.3a) off the *triggering* spell's
own `CastRecord.x_value`, not the ability's (a triggered ability announces
none of its own).

Proof of generality: searched with Scryfall's own card search in this
session for a second Modern/Pioneer/Standard-legal "cast a spell with {X} in
its mana cost" cast trigger distinct from the two listed round cards -
Anina, Natural Parallelist; Zaxara, the Exemplary; Elementalist's Palette;
Brass Infiniscope and the rest all print the identical restriction but are
Commander-only. None was found; see the dated MEMORY.md line. The two round
cards stand as mutual proof instead: the identical restriction reader
correctly gates two independently different effects below (an evasion grant
on Matterbending Mage, a library dig on Geometer's Arthropod), and the
restriction's own regex is written against the symbol named in the text
rather than a hardcoded "{X}", so it is not fitted to either card's
printing.

Endless One ({X}, "This creature enters with X +1/+1 counters on it.",
Modern-legal) is the {X} spell cast throughout - target-agnostic and free of
Traumatic Critique's own unrelated "deals X damage" gap (a resolution-time
`x_value`/`deal_damage_equal_to_expression` mismatch this task does not own
and does not touch; noted in MEMORY.md rather than fixed here). Lightning
Bolt (no {X} at all) is the control that must never fire the restriction.
Neither cast trigger's own restriction cares what card type the {X} spell
is - CR 300.1's "spell" is any of them - so a creature spell proves the
reader exactly as well as an instant would.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_x_spell(scenario: Scenario, x_value: int) -> None:
    card = scenario.find("Endless One", Zone.HAND, "alice")
    sources = scenario.untapped_sources(*(["Forest"] * x_value)) if x_value else []
    scenario.game.cast(card, "alice", x_value=x_value, mana_sources=sources)
    resolve_all(scenario)


# -- Geometer's Arthropod ------------------------------------------------------


def test_arthropod_looks_at_top_x_cards_and_takes_one_on_an_x_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endless One"],
            library=["Mountain", "Forest", "Swamp", "Plains", "Island"],
            battlefield=[
                "Geometer's Arthropod",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_three = scenario.top_of_library(3, "alice")
    scenario.will_choose_cards(top_three[1], source="Geometer's Arthropod")

    _cast_x_spell(scenario, 3)

    hand = scenario.player("alice").hand
    assert top_three[1] in hand
    assert top_three[0] not in hand and top_three[2] not in hand
    # The other two looked-at cards go to the bottom, in some order, never
    # the top and never the graveyard - CR 701.24a's word is never printed
    # here, so it is a plain move, not a shuffle.
    library = scenario.player("alice").library
    bottom_ids = {state.id for state in library[-2:]}
    assert bottom_ids == {top_three[0].id, top_three[2].id}
    top_ids = {state.id for state in library[:2]}
    assert top_three[0].id not in top_ids
    assert top_three[2].id not in top_ids


def test_arthropod_does_not_trigger_on_a_spell_with_no_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            library=["Mountain", "Forest", "Swamp"],
            battlefield=["Geometer's Arthropod", "Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert scenario.pending_triggers == []
    # No card looked at was taken - hand only lost the Bolt itself.
    assert len(scenario.player("alice").hand) == hand_before - 1


# -- Matterbending Mage ---------------------------------------------------------


def test_matterbending_mage_becomes_unblockable_on_an_x_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endless One"],
            battlefield=[
                "Matterbending Mage",
                "Forest",
                "Forest",
            ],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage = scenario.creature("Matterbending Mage", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_x_spell(scenario, 2)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mage)
    assert not scenario.game.can_block(bears, mage)


def test_matterbending_mage_stays_blockable_on_a_spell_with_no_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Matterbending Mage", "Mountain"],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage = scenario.creature("Matterbending Mage", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert scenario.pending_triggers == []
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mage)
    assert scenario.game.can_block(bears, mage)


# -- Snooping Page (Repartee) ---------------------------------------------------


def test_snooping_page_becomes_unblockable_when_the_spell_targets_a_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Snooping Page", "Mountain"],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    page = scenario.creature("Snooping Page", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    resolve_all(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(page)
    assert not scenario.game.can_block(bears, page)


def test_snooping_page_stays_blockable_when_the_spell_targets_a_player():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Snooping Page", "Mountain"],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    page = scenario.creature("Snooping Page", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert scenario.pending_triggers == []
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(page)
    assert scenario.game.can_block(bears, page)

"""Sneak granted to cards in a graveyard, and cast from there using it.

**Ninja Teen**'s level 3 (a Class, CR 716):

- "Creature cards in your graveyard have sneak {3}{B}." - CR 611.3d: a static
  ability granting a card in a zone an ability that lets it be cast.
- "You may cast creature spells from your graveyard using their sneak
  abilities." - CR 601.3's permission. Sneak on its own casts from the hand
  (CR 702.190a), so the grant alone would do nothing; this sentence is what
  opens the graveyard, and it covers a creature card's *printed* sneak as
  much as the granted one (Ninja Teen's own ruling: "If a creature card in
  your graveyard has multiple sneak abilities, you can cast it from your
  graveyard using any of those sneak abilities").

No other printing grants a keyword to graveyard cards and pairs it with
"using their `<keyword>` abilities" (searched on Scryfall this session:
`o:"using their"` finds Ninja Teen alone). The reader under it -
`_GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE`, widened here to the plural "`<quality>`
cards in your graveyard have" - is Iroh, Grand Lotus's flashback grant's own;
`test_granted_flashback_from_graveyard`-style coverage of the singular form
already exists, and the plural is proved here on Ninja Teen's own line.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 702.190a** - sneak's window (the caster's declare blockers step, at
  instant timing) and its cost (the sneak cost plus returning an unblocked
  creature to its owner's hand).
- **CR 702.190b** - the permanent enters tapped and attacking the returned
  creature's defender.
- **CR 716.2a** - a Class has only the abilities of the levels it has reached.
- **CR 400.7g** - the granted ability keeps applying once the card is on the
  stack.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SWAMPS = ["Swamp", "Swamp", "Swamp", "Swamp"]


def _in_declare_blockers(graveyard, *, level=3, hand=(), bob_graveyard=(), extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ninja Teen", "Grizzly Bears", *SWAMPS, *extra],
            graveyard=list(graveyard),
            hand=list(hand),
            library=["Swamp"] * 6,
        )
        .player("bob", graveyard=list(bob_graveyard), library=["Island"] * 6)
        .build()
    )
    scenario.find("Ninja Teen", Zone.BATTLEFIELD, "alice").class_level = level
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    return scenario


def _resolve_stack(scenario):
    """The spell and Ninja Teen's own leaves-the-battlefield trigger (the
    returned attacker left), in stack order."""
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _sneak(scenario, card, returning, username="alice"):
    return scenario.game.cast(
        card,
        username,
        keyword="Sneak",
        choosing=[returning],
        mana_sources=scenario.game.permanents_controlled_by(username),
    )


def test_a_creature_card_is_sneaked_out_of_the_graveyard_tapped_and_attacking():
    scenario = _in_declare_blockers(["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    spell = _sneak(scenario, giant, bears)

    assert bears.zone is Zone.HAND, "returning the unblocked attacker is part of the cost"
    record = scenario.game.cast_record(spell)
    assert record.keyword == "Sneak"
    assert record.origin_zone is Zone.GRAVEYARD
    _resolve_stack(scenario)

    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "alice")
    assert giant.tapped
    attack = scenario.game.combat.attack_by(giant.id)
    assert attack is not None and attack.defender.username == "bob"
    scenario.combat_damage()
    # Level 1's trigger took 1 when the returned Bears left the battlefield,
    # and level 2 is still there at level 3 (CR 716.2a): the 3/3 is a 4/3.
    assert scenario.player("bob").life == 20 - 1 - 4


def test_the_granted_sneak_costs_three_and_black():
    """{3}{B} is paid out of the four Swamps: only one is left untapped."""
    scenario = _in_declare_blockers(["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _sneak(scenario, scenario.find("Hill Giant", Zone.GRAVEYARD, "alice"), bears)
    untapped = [
        land
        for land in scenario.game.permanents_controlled_by("alice")
        if land.name == "Swamp" and not land.tapped
    ]
    assert len(untapped) == 0


def test_below_level_three_the_graveyard_is_closed():
    """CR 716.2a: at level 2 Ninja Teen has neither level 3 ability."""
    scenario = _in_declare_blockers(["Hill Giant"], level=2)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, giant, bears)
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_levelling_up_through_both_bars_opens_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ninja Teen", "Grizzly Bears", *SWAMPS, "Swamp", "Swamp", "Swamp"],
            graveyard=["Hill Giant"],
            library=["Swamp"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teen = scenario.find("Ninja Teen", Zone.BATTLEFIELD, "alice")
    swamps = [p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Swamp"]
    scenario.activate(teen, swamps[0], swamps[1], index=0)
    scenario.pass_until_resolved()
    scenario.activate(teen, swamps[2], index=1)
    scenario.pass_until_resolved()
    assert teen.class_level == 3

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    bears = scenario.creature("Grizzly Bears", "alice")
    _sneak(scenario, scenario.find("Hill Giant", Zone.GRAVEYARD, "alice"), bears)
    _resolve_stack(scenario)
    assert "Hill Giant" in scenario.battlefield_names()


def test_not_in_a_main_phase():
    """CR 702.190a: only during the caster's declare blockers step."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ninja Teen", "Grizzly Bears", *SWAMPS],
            graveyard=["Hill Giant"],
            library=["Swamp"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.find("Ninja Teen", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, giant, scenario.creature("Grizzly Bears", "alice"))
    assert giant.zone is Zone.GRAVEYARD


def test_a_noncreature_sneak_card_stays_in_the_graveyard():
    """ "creature spells": Michelangelo's Technique prints Sneak {3}{G}, but it
    is a sorcery, so neither level 3 sentence reaches it."""
    scenario = _in_declare_blockers(["Michelangelo's Technique"], extra=["Forest"])
    technique = scenario.find("Michelangelo's Technique", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, technique, scenario.creature("Grizzly Bears", "alice"))
    assert technique.zone is Zone.GRAVEYARD


def test_a_creatures_own_printed_sneak_works_from_the_graveyard_too():
    """Leonardo, Sewer Samurai prints Sneak {2}{W}{W}; the permission covers
    "their sneak abilities", printed and granted alike."""
    scenario = _in_declare_blockers(
        ["Leonardo, Sewer Samurai"], extra=["Plains", "Plains", "Plains", "Plains"]
    )
    leonardo = scenario.find("Leonardo, Sewer Samurai", Zone.GRAVEYARD, "alice")
    _sneak(scenario, leonardo, scenario.creature("Grizzly Bears", "alice"))
    _resolve_stack(scenario)
    assert scenario.find("Leonardo, Sewer Samurai", Zone.BATTLEFIELD, "alice").tapped


def test_a_creature_card_in_hand_gains_no_sneak():
    """ "in your graveyard": a creature card in hand has no sneak to use."""
    scenario = _in_declare_blockers([], hand=["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, giant, scenario.creature("Grizzly Bears", "alice"))
    assert giant.zone is Zone.HAND


def test_an_opponents_graveyard_is_not_yours():
    scenario = _in_declare_blockers([], bob_graveyard=["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        _sneak(scenario, giant, scenario.creature("Grizzly Bears", "alice"))


def test_no_unblocked_attacker_no_sneak():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ninja Teen", "Grizzly Bears", *SWAMPS],
            graveyard=["Hill Giant"],
            library=["Swamp"] * 6,
        )
        .player("bob", battlefield=["Hill Giant", "Llanowar Elves"], library=["Island"] * 6)
        .build()
    )
    scenario.find("Ninja Teen", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    # Level 2 gave the Bears menace (CR 702.111b): two blockers.
    scenario.block(
        bears, scenario.creature("Hill Giant", "bob"), scenario.creature("Llanowar Elves", "bob")
    )
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, giant, bears)
    assert giant.zone is Zone.GRAVEYARD


def test_legal_actions_offer_the_graveyard_sneak():
    scenario = _in_declare_blockers(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    assert any(
        getattr(action, "card_id", None) == giant.id and getattr(action, "keyword", None) == "Sneak"
        for action in legal_actions(scenario.game, "alice")
    )

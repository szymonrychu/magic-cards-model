""" "Exile target card from a graveyard. If it was a `<quality>` card, create
a `<token>`." - Invasion of Innistrad // Deluge of the Dead's own `{2}{B}`
ability.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2h** - "if the object has left the zone it was expected to be in,
  the effect uses the object's last known information" - the "if it was a
  creature card" read happens off the card as it stood in the graveyard,
  before this same ability's own exile takes it out of that zone.
- **CR 608.2b** - with no legal target left, the ability does not resolve at
  all and neither sentence runs.
- **CR 111.4** - a token's name is set to its own subtype(s) when the
  creating ability names none.

`machines/effects._parse_if_it_was_target_card_quality_rider_clause_pair` is
the parser this exercises - the "was" twin of `_parse_if_target_card_
quality_rider_clause_pair` (already used elsewhere for a present-tense "if
it's a ... card"), needed because this antecedent moves its own target out
of the zone that named it before the second sentence looks back at it.
General's Enforcer ("{2}{W}{B}: Exile target card from a graveyard. If it
was a creature card, create a 1/1 white Human Soldier creature token.",
verified Pioneer/Modern legal by Scryfall search, not in the deck pool) is
the proof printing: same verb and same "if it was" reading, a different
activation cost, creature, and token.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

INNISTRAD = "Invasion of Innistrad // Deluge of the Dead"


def test_exiling_a_creature_card_creates_a_zombie_token():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[INNISTRAD],
            graveyard=["Grizzly Bears", "Mountain"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of Innistrad", Zone.HAND, "alice")
    deluge = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    scenario.pass_until_resolved()  # Deluge's own ETB trigger: create two Zombies
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.activate(
        deluge, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=[bears]
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    zombies = [c for c in scenario.game.battlefield if c.name == "Zombie Token"]
    # Deluge's own ETB trigger already made two; the ability's rider makes
    # a third.
    assert len(zombies) == 3
    for zombie in zombies:
        assert zombie.card.power == "2"
        assert zombie.card.toughness == "2"


def test_exiling_a_land_card_creates_no_token():
    """The rider is conditional on the exiled card's own quality - a
    Mountain exiled instead creates nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[INNISTRAD],
            graveyard=["Grizzly Bears", "Mountain"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of Innistrad", Zone.HAND, "alice")
    deluge = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    scenario.pass_until_resolved()  # Deluge's own ETB trigger: create two Zombies
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "alice")

    scenario.activate(
        deluge, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=[mountain]
    )
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.EXILE
    zombies = [c for c in scenario.game.battlefield if c.name == "Zombie Token"]
    # Only the ETB trigger's own two - the ability's rider never fires.
    assert len(zombies) == 2


def test_generals_enforcer_creates_a_human_soldier_token_instead():
    """Same mechanic, a different real printing: different cost, creature,
    and created token, proving the parser reads the shape rather than this
    one card's own words."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["General's Enforcer", "Plains", "Plains", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    enforcer = scenario.creature("General's Enforcer", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.activate(
        enforcer,
        *scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp"),
        targets=[bears],
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    soldiers = [c for c in scenario.game.battlefield if c.name == "Human Soldier Token"]
    assert len(soldiers) == 1
    (soldier,) = soldiers
    assert soldier.card.power == "1"
    assert soldier.card.toughness == "1"

"""Scenario: "`<this spell>` deals N damage to target creature. If
`<condition>`, `<this spell>` also deals M damage to that creature's
controller." - one shape, three printings with three different conditions
and two different subjects for the rider:

- **Blooming Blast** - "If the gift was promised, Blooming Blast also deals 3
  damage to that creature's controller." (gift, CR 702.174k; the rider names
  the card, not "it").
- **Misthios's Fury** - "If you control an Equipment, Misthios's Fury also
  deals 2 damage to that creature's controller." (a board condition).
- **Repulsor Blast** - "If this spell was cast using teamwork, it also deals 2
  damage to that creature's controller." (the "it" form, already covered in
  `test_teamwork_riders.py`; asserted handled here only).

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 702.174a/h** - "Gift a Treasure": as an additional cost the caster may
  choose an opponent; that player creates a Treasure token.
- **CR 702.174j** - the gift effect happens before any other spell ability of
  the card, and not at all if the spell leaves the stack before resolving.
- **CR 702.174k** - the gift was promised if the caster declared the intention
  to pay the gift cost.
- **CR 608.2b** - with its only target illegal the spell does not resolve: no
  gift, no damage, and no damage to "that creature's controller" either.
- **CR 120.3a** - damage dealt to a player causes that player to lose that much
  life.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

BLAST = "Blooming Blast"
FURY = "Misthios's Fury"


def test_every_printing_of_the_shape_is_fully_handled():
    for name in (BLAST, FURY, "Repulsor Blast"):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _blast(alice_battlefield=(), bob_battlefield=("Grizzly Bears",), **alice) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            hand=[BLAST, *alice.get("hand", [])],
            battlefield=["Mountain", "Mountain", "Mountain", *alice_battlefield],
        )
        .player("bob", library=["Mountain"], battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_blast(scenario: Scenario, target, *, gift: str | None):
    spell = scenario.find(BLAST, Zone.HAND, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.game.cast(spell, "alice", targets=[target], mana_sources=sources, gift=gift)


def _treasures(scenario: Scenario) -> list[str | None]:
    return [state.controller for state in scenario.game.battlefield if "Treasure" in state.name]


def test_without_the_gift_only_the_creature_is_damaged():
    scenario = _blast(bob_battlefield=("Craw Wurm",))
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast_blast(scenario, wurm, gift=None)
    scenario.pass_until_resolved()

    assert wurm.damage == 2
    assert scenario.player("bob").life == 20
    assert _treasures(scenario) == []


def test_with_the_gift_the_creatures_controller_takes_three_too():
    scenario = _blast()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_blast(scenario, bears, gift="bob")
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "2 damage is lethal to a 2/2"
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20
    assert _treasures(scenario) == ["bob"], "the gift: bob creates the Treasure"


def test_the_controller_is_read_even_though_the_damage_killed_the_creature():
    """The creature dies to state-based actions only after the spell is done,
    but its controller is the one taking the extra damage either way."""
    scenario = _blast()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_blast(scenario, bears, gift="bob")
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17


def test_targeting_your_own_creature_with_the_gift_damages_you_not_the_gift_receiver():
    """ "That creature's controller" is whoever controls the target - here the
    caster - not the opponent the gift went to."""
    scenario = _blast(alice_battlefield=("Craw Wurm",), bob_battlefield=())
    wurm = scenario.creature("Craw Wurm", "alice")
    _cast_blast(scenario, wurm, gift="bob")
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20
    assert _treasures(scenario) == ["bob"]


def test_an_illegal_target_means_no_gift_and_no_damage_to_the_controller():
    """CR 608.2b and CR 702.174j: the bears leave before the Blast resolves,
    so the spell does not resolve - no Treasure and no 3 damage to bob."""
    scenario = _blast(hand=["Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_blast(scenario, bears, gift="bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])
    scenario.pass_until_resolved()  # the Bolt kills the bears
    scenario.pass_until_resolved()  # the Blast has no legal target left

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20
    assert _treasures(scenario) == []
    assert scenario.find(BLAST, Zone.GRAVEYARD, "alice")


# -- second printing: Misthios's Fury, a board condition ---------------------


def _fury(*alice_battlefield: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            hand=[FURY],
            battlefield=["Mountain", "Mountain", *alice_battlefield],
        )
        .player("bob", library=["Mountain"], battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_fury_with_an_equipment_damages_the_controller():
    scenario = _fury("Bonesplitter")
    wurm = scenario.creature("Craw Wurm", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve(FURY, *sources, targets=[wurm])

    assert wurm.damage == 3
    assert scenario.player("bob").life == 18


def test_fury_without_an_equipment_damages_only_the_creature():
    scenario = _fury()
    wurm = scenario.creature("Craw Wurm", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve(FURY, *sources, targets=[wurm])

    assert wurm.damage == 3
    assert scenario.player("bob").life == 20

"""Scenario: a targeted damage or counter amount multiplied "for each <thing>"
or defined as CR 107.3a's X "where X is <expr>", instead of the single fixed
number these clauses used to read.

Two shapes, both read once as the ability or spell begins to resolve
(CR 608.2h fixes a "for each" count "at the time the ability or effect... is
about to be performed"; CR 611.2c fixes a spell's own magnitude the moment it
resolves) and then applied unchanged to every target:

- **Immaculate Magistrate** (verified with `resolve_cards`): "{T}: Put a
  +1/+1 counter on target creature for each Elf you control." The regex used
  to read "target creature for each Elf you control" as the whole target
  phrase and pin the count at one, ignoring the multiplier entirely - a
  **wrong-amount** bug invisible to `scripts/sweep_pool.py` (the clause still
  "handled", just for the wrong number).
- **Lotleth Giant** (off-pool, verified with `resolve_cards`): "Undergrowth -
  When this creature enters, it deals 1 damage to target opponent for each
  creature card in your graveyard." Same multiplier shape, off a damage
  clause instead of a counter one, proving the fix generalizes past
  Immaculate Magistrate's own card.
- **Tribal Flames** (off-pool, verified with `resolve_cards`): "Domain -
  Tribal Flames deals X damage to any target, where X is the number of
  basic land types among lands you control." A literal X, evaluated off
  Domain's own count expression rather than a fixed digit - this clause used
  to be silent outright, since `COUNT` never matches the word "X".

Every CR number here was looked up with `knowledge_search(type="rules")`:

- **CR 608.2h** - "for each" count is determined as the ability begins to
  resolve.
- **CR 611.2c** - a spell's own effect magnitude is fixed as it resolves.
- **CR 107.3a** - X is a placeholder the caster announces as part of casting.
- **CR 122.1** - putting counters on an object or player.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Immaculate Magistrate: "for each Elf you control" (a counter multiplier)
# --------------------------------------------------------------------------


def test_immaculate_magistrate_counts_every_elf_including_itself():
    """Magistrate is itself an Elf Shaman, so two Elves on the board (itself
    plus one more) puts two counters on the target, not the one the old
    fixed-amount reading always put."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Immaculate Magistrate", "Llanowar Elves", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    magistrate = scenario.creature("Immaculate Magistrate", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(magistrate, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 2


def test_a_third_elf_puts_a_third_counter():
    """The multiplier is read fresh each activation - a different Elf count
    gives a different amount, proving this is not a second fixed number."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Immaculate Magistrate",
                "Llanowar Elves",
                "Llanowar Elves",
                "Grizzly Bears",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    magistrate = scenario.creature("Immaculate Magistrate", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(magistrate, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 3


# --------------------------------------------------------------------------
# Lotleth Giant: "for each creature card in your graveyard" (a damage
# multiplier)
# --------------------------------------------------------------------------


def test_lotleth_giants_etb_damages_the_opponent_once_per_creature_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lotleth Giant"],
            battlefield=["Swamp"] * 7,
            graveyard=["Grizzly Bears", "Watchwolf", "Memnite", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Lotleth Giant", ["bob"])

    sources = scenario.untapped_sources(*(["Swamp"] * 7), username="alice")
    scenario.cast_onto_stack("Lotleth Giant", *sources, username="alice")
    scenario.pass_until_resolved()  # Lotleth Giant resolves and enters
    scenario.pass_until_resolved()  # its own ETB trigger

    assert scenario.player("bob").life == 17  # three creature cards, one land


# --------------------------------------------------------------------------
# Tribal Flames: Domain's "where X is the number of basic land types among
# lands you control" (a damage amount, not a multiplier)
# --------------------------------------------------------------------------


def test_tribal_flames_deals_damage_equal_to_domain():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tribal Flames"],
            battlefield=["Mountain", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain, forest = scenario.untapped_sources("Mountain", "Forest", username="alice")

    scenario.cast_and_resolve(
        "Tribal Flames", mountain, forest, username="alice", targets=[scenario.player("bob")]
    )

    assert scenario.player("bob").life == 17  # three basic land types


def test_tribal_flames_does_not_count_a_fourth_untyped_land():
    """A fourth land that is not one of the five basic types does not widen
    Domain - proving the count is basic land *types*, not lands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tribal Flames"],
            battlefield=["Mountain", "Forest", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain, forest = scenario.untapped_sources("Mountain", "Forest", username="alice")

    scenario.cast_and_resolve(
        "Tribal Flames", mountain, forest, username="alice", targets=[scenario.player("bob")]
    )

    assert scenario.player("bob").life == 17  # still three distinct types


def test_tribal_flames_can_hit_a_creature_too():
    """ "any target" (CR 115.4), not "any player" - a creature works too, and
    a lone Mountain plus a colorless source (Domain of one) deals exactly
    one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Tribal Flames"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watchwolf = scenario.creature("Watchwolf", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Tribal Flames", *mountains, username="alice", targets=[watchwolf])

    assert watchwolf.damage == 1
    assert watchwolf.zone is Zone.BATTLEFIELD

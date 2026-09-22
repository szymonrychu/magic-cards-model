"""Scenario: "<destroy/exile> target X. Its/that X's controller <player
clause>." - a generic parser for the anaphoric second sentence
(`_parse_anaphoric_clause_pair` in `machines/effects.py`), read off a card's
own printed text with no per-card table row.

This is Solitude's own defect, reproduced and fixed: its trigger used to
resolve with a legal target and do nothing at all - no exile, no life gain -
because nothing in the registry or the per-clause dispatcher could read "That
creature's controller gains life equal to its power." `_parse_mixed_clauses`
correctly refused the whole effect (CR 608.2c has no notion of running half
an instruction), but silently, with no record anywhere. This file proves the
fix end to end and pins down the traps a naive implementation hits.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - both sentences are instructions, and
  the life gain is not optional once a target was actually exiled.
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen" - "up to one" choosing none means the second sentence
  has nothing to refer back to and does not run either.
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence" - the
  exiled/destroyed object read afterward is not "that creature" any more,
  which is why its controller and power have to be read *before* the first
  sentence's verb runs.
- **CR 608.2i** - a look-back effect uses information "as it existed
  immediately before" the event, not the current game state - the LKI
  snapshot this parser takes.
- **CR 608.2b** - a target no longer in the zone it was targeted in is
  illegal; this governs the *first* sentence's own target only, never
  reapplied to the anaphoric second sentence.
- **CR 107.1b** - "You can't ... gain negative life" - a value expression
  reading a negative last-known power floors at zero.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# -- Solitude: the worked, faithful reproduction of the live defect ---------


def test_solitude_exiles_and_gains_the_targets_controller_life():
    """`When this creature enters, exile up to one other target creature.
    That creature's controller gains life equal to its power.`

    Alice casts Solitude targeting Bob's Grizzly Bears (power 2). The bears
    are exiled and *Bob* - not Alice - gains 2 life (trap 4: life to the
    opponent, not the caster).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Solitude"], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.choose_trigger_targets("Solitude", [bears])

    scenario.cast_and_resolve("Solitude", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").life == 22
    assert scenario.player("alice").life == 20


def test_solitude_up_to_one_with_zero_targets_does_nothing():
    """CR 115.6: choosing zero targets for "up to one" is legal. Nothing is
    exiled and nobody's life changes - not even a gain of 0 (trap 5).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Solitude"], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Plains"] * 5)

    scenario.cast_and_resolve("Solitude", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_solitude_reads_power_with_counters_and_an_anthem_before_the_exile():
    """Trap 1: reading power *after* the exile would see `CardState.move_to`'s
    empty husk - counters cleared to `last_known_counters`, and
    `machines/layers.py` only computing continuous effects for a permanent
    still on the battlefield - so an anthemed, +1/+1-countered creature would
    silently gain its bare printed power back instead of its real one.

    Bob's Grizzly Bears (2/2) carries two +1/+1 counters (4/4) and Bob
    controls a Glorious Anthem ("Creatures you control get +1/+1"), for a
    real power of 5. Bob must gain exactly 5 life, not 2.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Solitude"], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears", "Glorious Anthem"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.PLUS_ONE, 2)
    assert scenario.game.power_of(bears) == 5
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.choose_trigger_targets("Solitude", [bears])

    scenario.cast_and_resolve("Solitude", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").life == 25


# -- Swords to Plowshares: the one-mana twin, and the EFFECTS row it lost ---


def test_swords_to_plowshares_gains_the_targets_controller_life():
    """`Exile target creature. Its controller gains life equal to its
    power.` No "up to one" here - a single mandatory target - and the
    `EFFECTS["Swords to Plowshares"]` row (the old `exile_targets`, which
    exiled and never gained the life at all) is gone; `effect_for`'s fallback
    reads both sentences off the card's own printed text.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Swords to Plowshares", plains, targets=[wolf])

    assert wolf.zone is Zone.EXILE
    assert scenario.player("bob").life == 23
    assert scenario.player("alice").life == 20


def test_swords_to_plowshares_has_no_registry_row_any_more():
    """`EFFECTS` must not have re-grown a Swords to Plowshares row -
    `test_registry_is_minimal.py::test_effects_row_is_not_reachable_through_the_spell_parsers`
    already enforces this across every row, but the point of *this* defect is
    exactly that row, so it gets its own explicit check here too.
    """
    from magic_cards_model.machines.effects import EFFECTS

    assert "Swords to Plowshares" not in EFFECTS


# -- Assassin's Trophy: destroy (not exile), and a search instead of life --


def test_assassins_trophy_destroys_and_lets_the_targets_controller_search():
    """`Destroy target permanent an opponent controls. Its controller may
    search their library for a basic land card, put it onto the battlefield,
    then shuffle.`

    The referent's controller here does the *search*, not a life gain - the
    same LKI resolution feeding a different second-clause shape
    (`_parse_referent_clause`'s search branch, `_REFERENT_SEARCH_RE`).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Assassin's Trophy"], battlefield=["Forest", "Swamp"])
        .player("bob", battlefield=["Mountain"], library=["Plains", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Forest", "Swamp")
    scenario.will_take_the_may(True, username="bob")

    scenario.cast_and_resolve("Assassin's Trophy", *sources, targets=[mountain])

    assert mountain.zone is Zone.GRAVEYARD
    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.tapped is False
    assert [state.card.name for state in scenario.player("bob").library] == ["Island"]


# -- Cityscape Leveler: destroy paired with a mandatory token, not a search -


def test_cityscape_leveler_destroys_and_the_targets_controller_creates_a_powerstone():
    """Control for the indestructible case below: against a destructible
    target, "Its controller creates a tapped Powerstone token." still runs.

    The attack half of `Cityscape Leveler`'s compound condition; the cast
    half is `test_compound_trigger_conditions.py`'s.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cityscape Leveler"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leveler = scenario.creature("Cityscape Leveler", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])

    scenario.attack_with(leveler)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert "Powerstone Token" in [
        state.name for state in scenario.game.permanents_controlled_by("bob")
    ]


# -- A legal target that survives the first sentence still has a controller -
#
# Superseded 2026-09-22: this block used to assert the opposite (no search, no
# token when indestructible refused the destroy). The printed rulings for the
# identical templating say otherwise - Assassin's Trophy (2024-02-02): "If the
# target permanent is a legal target but isn't destroyed, most likely because
# it has indestructible, its controller may search their library."; Beast
# Within (2021-03-19): "If the target is legal but not destroyed ..., its
# controller does create a Beast token." CR 608.2b: a legal target "will
# resolve normally", and CR 702.12b refuses only the destroy itself.


def test_assassins_trophy_does_not_destroy_indestructible_ulamog_but_still_offers_the_search():
    """`Destroy target permanent an opponent controls. Its controller may
    search their library for a basic land card...`, aimed at an indestructible
    permanent: Ulamog stays, and its controller may still search."""
    scenario = (
        Scenario()
        .player("alice", hand=["Assassin's Trophy"], battlefield=["Forest", "Swamp"])
        .player("bob", hand=["Ulamog, the Ceaseless Hunger"], library=["Plains", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.put_onto_battlefield("Ulamog, the Ceaseless Hunger", "bob")
    sources = scenario.untapped_sources("Forest", "Swamp")
    scenario.will_take_the_may(True, username="bob")

    scenario.cast_and_resolve("Assassin's Trophy", *sources, targets=[ulamog])

    assert ulamog.zone is Zone.BATTLEFIELD, "indestructible can't be destroyed (CR 702.12b)"
    assert "Plains" in scenario.battlefield_names(), "the target was legal, so bob searches"


def test_cityscape_leveler_does_not_destroy_indestructible_ulamog_but_still_grants_the_token():
    """`... destroy up to one target nonland permanent. Its controller
    creates a tapped Powerstone token.`, aimed at an indestructible
    permanent - the mandatory twin of the Assassin's Trophy case above."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cityscape Leveler"])
        .player("bob", hand=["Ulamog, the Ceaseless Hunger"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.put_onto_battlefield("Ulamog, the Ceaseless Hunger", "bob")
    leveler = scenario.creature("Cityscape Leveler", "alice")
    scenario.choose_trigger_targets("Cityscape Leveler", [ulamog])

    scenario.attack_with(leveler)
    scenario.pass_until_resolved()

    assert ulamog.zone is Zone.BATTLEFIELD, "indestructible can't be destroyed (CR 702.12b)"
    assert "Powerstone Token" in [
        state.name for state in scenario.game.permanents_controlled_by("bob")
    ], "the target was legal, so its controller still creates the token"


# -- A `*` power creature: the LKI snapshot has to read the computed value --


def test_a_star_power_creature_would_gain_its_computed_power_not_zero():
    """Trap 7: `CardState.power` is `None` for a `*` characteristic-defining
    ability (Tarmogoyf: "power ... equal to the number of card types among
    cards in all graveyards"). The referent snapshot reads `Game.power_of`,
    which runs the layers engine and should answer with the computed value,
    not `None` and not a crash.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Solitude"], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "bob")
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.choose_trigger_targets("Solitude", [goyf])

    scenario.cast_and_resolve("Solitude", *sources)
    scenario.pass_until_resolved()

    assert goyf.zone is Zone.EXILE
    # A single instant (Lightning Bolt) in a graveyard is one card type, so
    # Tarmogoyf should be computed as a 1/2 and bob should gain 1 life.
    assert scenario.player("bob").life == 21

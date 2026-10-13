"""Momo, Friendly Flier's own "first spell each turn" discount, widened.

    "The first non-Lemur creature spell with flying you cast during each of
    your turns costs {1} less to cast."

This is `machines/cost.py`'s pre-existing `_FIRST_SPELL_EACH_TURN_COST_
DECREASE` family (Radagast of Rhosgobel, Melek, Reforged Researcher, Conduit
of Ruin, Eluge, the Shoreless Sea - see `test_conditional_cost_reduction.py`
and `test_flood_counters.py`), widened three ways at once:

- an optional leading subtype **exclusion** ("non-Lemur"), the negative
  counterpart of the type list rather than a positive member of it;
- an optional trailing **keyword requirement** ("with flying"), asked of the
  spell itself off the stack the same way a creature's printed power and
  toughness already are for Doran, Besieged by Time's own filter;
- the turn window spelled "during each of your turns" as well as the
  pre-existing "each turn".

The one correctness point worth stating plainly: "first" is scoped to the
*qualifying* spell, not to any spell at all. An earlier plain creature spell
with no flying does not use up Momo's discount, because it never carried the
subtype exclusion or the keyword requirement either - `Game.
_type_decrease_candidate_matches` asks the identical three-part question of
every earlier spell this turn that it asks of the one being costed now.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 601.2f** - "Some effects may increase or reduce the cost to pay."
- **CR 601.2i** / **CR 601.2b** - the spell being costed is not yet counted
  among "spells you've cast this turn" when its own cost is determined.
- **CR 205.3m** - creature types (Lemur among them).
- **CR 702.9b** - flying, the keyword this discount also demands.
- **CR 102.1** - the active player, which "each of your turns" is silent
  about but the discount does not actually depend on (Momo's own text is a
  per-turn window keyed to *whoever cast the spell*, not to whose turn it is
  - CR 601.2f's "you cast" always means the caster).

Conduit of Ruin (off-pool, not in any deck list) is the second, unqualified
printing that proves the widened regex still reads the pre-existing, plain
"first creature spell you cast each turn" shape - the family this file's
three new groups extend rather than replace, once it is on the battlefield
giving *other* creature spells its own discount (its printed text names no
"this spell" at all).
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _momo_board(hand: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=["Momo, Friendly Flier", "Forest"] + ["Island"] * 6 + ["Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_non_lemur_flying_creature_spell_costs_one_less():
    scenario = _momo_board(["Wind Drake"])

    casting = scenario.cast("Wind Drake")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{U}", "{2}{U} minus {1}"


def test_a_lemur_creature_spell_with_flying_gets_no_reduction():
    """Momo, Playful Pet is itself a Lemur - excluded by name, not by
    number, from its namesake's own discount."""
    scenario = _momo_board(["Momo, Playful Pet"])

    casting = scenario.cast("Momo, Playful Pet")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{W}", "the printed cost, unreduced"


def test_a_non_lemur_creature_spell_with_no_flying_gets_no_reduction():
    scenario = _momo_board(["Grizzly Bears"])

    casting = scenario.cast("Grizzly Bears")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{G}", "the printed cost, unreduced"


def test_an_earlier_non_qualifying_spell_does_not_spend_the_discount():
    """Grizzly Bears (no flying) is not "the first non-Lemur creature spell
    with flying" either, so casting it first leaves Momo's discount
    untouched for the flying creature cast right after it."""
    scenario = _momo_board(["Grizzly Bears", "Wind Drake"])
    # Bears has no flying, so Momo's "another creature you control with flying
    # enters" trigger does not fire and there is nothing further to resolve.
    scenario.cast_and_resolve("Grizzly Bears", auto=True)

    casting = scenario.cast("Wind Drake")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{U}", "still the first *qualifying* spell"


def test_a_second_qualifying_spell_this_turn_gets_no_reduction():
    scenario = _momo_board(["Wind Drake", "Pride of the Clouds"])
    scenario.cast_and_resolve("Wind Drake", auto=True)
    scenario.pass_until_resolved()  # Momo's own ETB trigger, off the stack

    casting = scenario.cast("Pride of the Clouds")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{W}{U}", "the second qualifying spell, undiscounted"


def test_a_lemur_spell_cast_first_does_not_spend_the_discount_either():
    """The mirror of the "earlier non-qualifying spell" test, on the other
    excluded axis: a Lemur creature with flying is not the discount's own
    subject, so it does not use the discount up for the flying creature
    that follows."""
    scenario = _momo_board(["Momo, Playful Pet", "Wind Drake"])
    scenario.cast_and_resolve("Momo, Playful Pet", auto=True)
    scenario.pass_until_resolved()  # the *original* Momo's own ETB trigger

    casting = scenario.cast("Wind Drake")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{U}"


def test_conduit_of_ruin_still_reads_the_plain_pre_existing_shape():
    """Off-pool proof that the widened regex has not broken the family's own
    original, unqualified shape - "The first creature spell you cast each
    turn costs {2} less to cast." - once Conduit of Ruin is itself on the
    battlefield giving another creature spell the discount."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Conduit of Ruin", "Forest"] + ["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{G}", "{1}{G} minus {2}, floored at the coloured part"

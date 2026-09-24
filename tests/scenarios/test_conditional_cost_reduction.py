"""Scenario: a spell's own self-reduction (CR 601.2f), three templated
shapes.

`Game.cost_reduction_for` is where CR 601.2f's "the total cost is ... minus
all cost reductions" is computed for a spell's own printed self-discount -
`Game.determine_total_cost` calls it and locks the answer in. Three shapes
here:

- **"This spell costs {N} less to cast if `<condition>`."** (Dreaded
  Bat-Cloud's own "if a creature died this turn", Morbid's own CR 700.4
  wording) - the general "if <condition>" reduction, gated through
  `Game.condition_holds` the same way every other printed condition is.
- **"This spell costs {X} less to cast, where X is the total power of
  creatures you control[ with `<keyword>`]."** (The Lord of the Eagles' own
  flying-filtered sum, Ghalta, Primal Hunger's unqualified one) - a sum over
  the caster's own creatures, optionally keyword-filtered.
- **"The first `<type>` spell you cast each turn costs `<N>` less to cast
  and can be cast as though it had flash."** (Radagast of Rhosgobel) -
  reuses C00-T6's `machines/cost.py` "first spell each turn" cost-reduction
  machinery (`CostModifierEffect.first_each_turn`), widened with a
  `grants_flash` field read by the new `Game.has_first_spell_flash_grant`.

Off-pool proofs: Ghalta, Primal Hunger (the unqualified total-power shape)
and Explore (a plain "You may play an additional land this turn." one-shot,
covered in `test_additional_land_forms.py` instead - see that file), both
real Modern-legal printings outside the deck pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_now

from .harness import Scenario


def test_dreaded_bat_cloud_costs_nothing_extra_with_no_death():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Dreaded Bat-Cloud"], battlefield=["Swamp"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.creatures_died_this_turn == 0

    casting = scenario.cast("Dreaded Bat-Cloud")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{4}{B}", "the printed cost, undiscounted"


def test_dreaded_bat_cloud_costs_three_less_after_a_death_this_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Dreaded Bat-Cloud"],
            battlefield=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)
    assert scenario.game.creatures_died_this_turn == 1

    casting = scenario.cast("Dreaded Bat-Cloud")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{B}", "{4}{B} minus {3} generic (CR 118.7a)"


def test_lord_of_the_eagles_reduces_by_the_flying_power_only():
    """Grizzly Bears has no flying, so only Aerial Doombot contributes."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["The Lord of the Eagles"],
            battlefield=["Island"] * 9 + ["Aerial Doombot", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("The Lord of the Eagles")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{6}{U}{U}", "{7}{U}{U} minus Aerial Doombot's power 1"


def test_ghalta_primal_hunger_reads_the_unqualified_total_power_shape():
    """Off-pool proof: the identical reader, no keyword filter at all - every
    creature's power counts."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ghalta, Primal Hunger"],
            battlefield=["Forest"] * 12 + ["Grizzly Bears", "Aerial Doombot"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ghalta, Primal Hunger")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{7}{G}{G}", (
        "{10}{G}{G} minus 3 (Grizzly Bears' 2 power + Aerial Doombot's 1)"
    )


def test_radagast_reduces_the_first_creature_spell_and_grants_it_flash():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Radagast of Rhosgobel"],
        )
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)  # not alice's main phase - flash is the point.

    casting = scenario.cast("Grizzly Bears")
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{G}", "{1}{G} minus {2}, floored at {G}'s coloured part"
    bears = casting.spell
    casting.cancel()

    reason = why_cannot_cast_now(bears, "alice", scenario.game)
    assert reason is None, "Radagast's own flash grant lets it through outside the main phase"


def test_a_second_creature_spell_this_turn_gets_no_reduction_or_flash():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears", "Runeclaw Bear"],
            battlefield=["Forest", "Forest", "Forest", "Radagast of Rhosgobel"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))

    casting = scenario.cast("Runeclaw Bear")
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}{G}", "the printed cost - Radagast already spent"

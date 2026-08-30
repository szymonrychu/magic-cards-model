"""`CostPayment.auto_tap` - solving mana payment automatically.

The defect this covers: a live playtest of the Azorius Blink deck (almost
entirely shocklands and Ravnica duals) had `cast`/`activate` refuse *every*
spell paid from a dual, quoting `ManaAbility.resolve`'s internal "this ability
offers [['W'], ['U']]; pass the colour chosen" straight from
`machines/abilities.py`, because the caller (the API's default "tap
everything untapped" path) asked a choice ability to produce mana with no
colour chosen at all. `CostPayment.auto_tap` (`machines/cost.py`) is the fix:
given a cost and a set of untapped sources, it finds a legal assignment of
sources to colours itself.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 601.2g** - "Mana abilities must be activated before costs are paid."
- **CR 118.3c** - "Activating mana abilities is not mandatory, even if paying
  a cost is" - so `auto_tap` stops as soon as the pool can pay and never taps
  a source it does not need.
- **CR 106.6** - some mana carries a spend restriction ("Spend this mana only
  to..."). The restriction travels with the mana in the pool, so `auto_tap`
  offers a restricted ability exactly when the restriction permits what is
  being paid for and withholds it otherwise - see
  `tests/scenarios/test_mana_spend_restrictions.py` for the mechanic itself.
- **CR 118.13a** - the choice of how a mana symbol payable in multiple ways is
  covered belongs to the payer; picking which colour a dual makes to reach a
  fixed, already-known cost is bookkeeping downstream of that choice, not a
  new one, which is the rules basis for letting `auto_tap` make it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Minimal tapping and the flexibility preference
# --------------------------------------------------------------------------


def test_minimal_tap_taps_exactly_one_source():
    """A one-mana spell taps exactly one land, not the whole board."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    tapped = [s for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert len(tapped) == 1


def test_flexibility_prefers_the_basic_over_the_dual():
    """Given a basic and a dual that both pay, the basic is spent."""
    scenario = (
        Scenario()
        .player("alice", hand=["Shock"], battlefield=["Sacred Foundry", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (foundry, mountain) = scenario.untapped_sources("Sacred Foundry", "Mountain")

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    assert mountain.tapped is True
    assert foundry.tapped is False


def test_a_dual_alone_still_pays_when_it_is_the_only_source():
    """A one-mana spell off a single dual still taps exactly it."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Sacred Foundry"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (foundry,) = scenario.untapped_sources("Sacred Foundry")

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    assert foundry.tapped is True


# --------------------------------------------------------------------------
# Two colours, from duals that each offer both
# --------------------------------------------------------------------------


def test_two_duals_each_offering_both_colours_pay_a_two_colour_cost():
    """Lightning Helix ({R}{W}) off two Sacred Foundries, neither of which is
    forced to a colour by anything but the cost."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Sacred Foundry"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    foundries = scenario.untapped_sources("Sacred Foundry", "Sacred Foundry")

    scenario.cast_onto_stack("Lightning Helix", username="alice", targets=["alice"], auto=True)

    assert all(foundry.tapped for foundry in foundries)
    assert scenario.player("alice").mana_pool.floating == {}


def test_a_fixed_source_and_a_dual_split_a_two_colour_cost():
    """A Mountain and a Sacred Foundry between them pay {R}{W} - the dual has
    to make the colour the Mountain cannot."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Mountain", "Sacred Foundry"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain, foundry) = scenario.untapped_sources("Mountain", "Sacred Foundry")

    scenario.cast_onto_stack("Lightning Helix", username="alice", targets=["alice"], auto=True)

    assert mountain.tapped is True
    assert foundry.tapped is True
    assert scenario.player("alice").mana_pool.floating == {}


# --------------------------------------------------------------------------
# A cost that cannot be paid
# --------------------------------------------------------------------------


def test_unpayable_cost_is_refused_with_a_clear_reason():
    """Two Forests cannot make {R}{W} - refused, not a crash, and the message
    reads like a sentence rather than quoting `[['W'], ['U']]`."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Helix", "alice", targets=["alice"])
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError as exc:
        raised = True
        message = str(exc)

    assert raised
    assert "{R}{W}" in message
    assert "[[" not in message


# --------------------------------------------------------------------------
# Spend restrictions (CR 106.6) - offered only when the restriction permits
# --------------------------------------------------------------------------


def test_eldrazi_temple_restricted_ability_is_not_auto_tapped():
    """Eldrazi Temple's `{T}: Add {C}{C}.` may only be spent to cast colorless
    Eldrazi spells or activate abilities of colorless Eldrazi (CR 106.6). Mind
    Stone is a colorless artifact and neither, so `auto_tap` is left with the
    unrestricted `{T}: Add {C}.` - one mana, not two - and the {2} cost is
    refused rather than silently paid with mana that cannot pay it."""
    scenario = (
        Scenario().player("alice", hand=["Mind Stone"], battlefield=["Eldrazi Temple"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (temple,) = scenario.untapped_sources("Eldrazi Temple")
    casting = scenario.cast("Mind Stone", "alice")
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert temple.tapped is False  # fail closed: nothing was tapped either


def test_eldrazi_temple_unrestricted_ability_still_pays_what_it_can():
    """The same land's free ability pays a cost it is actually enough for -
    Sol Ring's generic {1}, which colourless mana pays as well as any other."""
    scenario = Scenario().player("alice", hand=["Sol Ring"], battlefield=["Eldrazi Temple"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (temple,) = scenario.untapped_sources("Eldrazi Temple")

    scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)

    assert temple.tapped is True


def test_cavern_of_souls_restricted_colour_choice_is_not_auto_tapped():
    """Cavern of Souls's any-colour ability is restricted to casting a creature
    spell of the chosen type (CR 106.6). Shock is an instant, so that ability
    is not offered and only the unrestricted `{T}: Add {C}.` remains, which
    cannot pay a coloured cost."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Cavern of Souls"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (cavern,) = scenario.untapped_sources("Cavern of Souls")
    casting = scenario.cast("Shock", "alice", targets=["alice"])
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert cavern.tapped is False


# --------------------------------------------------------------------------
# Additional costs beyond {T} - never spent without the player's say-so
# --------------------------------------------------------------------------


def test_sunbaked_canyon_life_payment_is_not_auto_tapped():
    """Sunbaked Canyon's only mana ability costs `{T}, Pay 1 life`. Auto-tap
    never pays a cost the player did not agree to, so it leaves the land
    alone entirely - the life total is untouched and the cost is refused."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Sunbaked Canyon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (canyon,) = scenario.untapped_sources("Sunbaked Canyon")
    casting = scenario.cast("Shock", "alice", targets=["alice"])
    payment = casting.begin_paying()
    life_before = scenario.player("alice").life

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert canyon.tapped is False
    assert scenario.player("alice").life == life_before


def test_tinder_farm_uses_its_free_ability_not_the_sacrifice_one():
    """Tinder Farm has a plain `{T}: Add {G}.` and a `{T}, Sacrifice this
    land: Add {R}{W}.`. Auto-tap uses the free one and leaves the land on the
    battlefield - it never sacrifices a permanent the player did not ask it
    to."""
    scenario = (
        Scenario().player("alice", hand=["Elvish Mystic"], battlefield=["Tinder Farm"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (farm,) = scenario.untapped_sources("Tinder Farm")

    scenario.cast_onto_stack("Elvish Mystic", username="alice", auto=True)

    assert farm.tapped is True
    assert farm in scenario.game.battlefield  # still there - not sacrificed


def test_arena_of_glory_uses_its_free_ability_not_the_exert_one():
    """Arena of Glory has a plain `{T}: Add {R}.` and an exert ability that
    costs `{R}` and exerts the land. Auto-tap uses the free one and never
    exerts a permanent on the player's behalf."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Arena of Glory"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (arena,) = scenario.untapped_sources("Arena of Glory")

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    assert arena.tapped is True
    assert arena.exerted is False


# --------------------------------------------------------------------------
# Explicit choice still overrides
# --------------------------------------------------------------------------


def test_an_explicit_tap_still_overrides_what_auto_would_have_chosen():
    """A player who names a specific land and colour keeps that choice - the
    solver only runs when nobody picked for it. `Scenario.pay_with` (an
    explicit source list) is untouched by `auto_tap`'s existence."""

    scenario = (
        Scenario()
        .player("alice", hand=["Shock"], battlefield=["Mountain", "Sacred Foundry"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain, foundry) = scenario.untapped_sources("Mountain", "Sacred Foundry")
    casting = scenario.cast("Shock", "alice", targets=["alice"])
    payment = casting.begin_paying()

    payment.tap_for_mana(foundry, [Color.RED])  # the explicit choice
    payment.pay()

    assert foundry.tapped is True
    assert mountain.tapped is False


# --------------------------------------------------------------------------
# CR 605.1a conditional "add X instead" clauses - the regression this file's
# other tests did not catch: an earlier `auto_tap` read each source's output
# through `ManaAbility.produces()`, which ignores a conditional clause
# entirely. Full Tron (three colourless each, uncondtionally) auto-tapped for
# three total mana and refused every cost of four or more, even though full
# Tron out actually makes seven. `ManaAbility.effective` - the same
# board-aware resolution `Game.activate_ability` uses for a real activation,
# see `models/game.py`'s `_controlled_land_types` - is what the solver reads
# from now on, through `_auto_tap_candidates`'s `_mana_context`.
# --------------------------------------------------------------------------


def test_full_tron_auto_taps_karn_the_great_creator():
    """The exact reported regression: full Tron out, casting a `{4}` spell
    with nothing named. Two Tron pieces already make {C}{C}{C}{C} once all
    three are controlled (CR 205.3i: the condition is about what you
    *control*, not what else is tapped alongside it), so the minimal
    assignment is two lands, not three."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Karn, the Great Creator"],
            battlefield=["Urza's Mine", "Urza's Power Plant", "Urza's Tower"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant, tower = scenario.untapped_sources(
        "Urza's Mine", "Urza's Power Plant", "Urza's Tower"
    )

    scenario.cast_onto_stack("Karn, the Great Creator", username="alice", auto=True)

    tapped = [land for land in (mine, plant, tower) if land.tapped]
    assert len(tapped) == 2, "minimal: two boosted Tron pieces already make {C}{C}{C}{C}"
    assert tower not in tapped, "Tower's own {C}{C}{C} is not needed to reach four"
    assert scenario.player("alice").mana_pool.floating == {}


def test_full_tron_pays_a_seven_generic_cost():
    """All three Tron pieces, each boosted, make exactly seven - enough for
    All Is Dust's `{7}`, and only reachable by tapping every piece."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["All Is Dust"],
            battlefield=["Urza's Mine", "Urza's Power Plant", "Urza's Tower"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant, tower = scenario.untapped_sources(
        "Urza's Mine", "Urza's Power Plant", "Urza's Tower"
    )

    scenario.cast_onto_stack("All Is Dust", username="alice", auto=True)

    assert mine.tapped and plant.tapped and tower.tapped
    assert scenario.player("alice").mana_pool.floating == {}


def test_full_tron_paying_a_one_generic_cost_taps_exactly_one_land():
    """A cheap spell still taps only one Tron piece - `auto_tap` never spends
    more sources than the cost needs, even though every piece is boosted."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pithing Needle"],
            battlefield=["Urza's Mine", "Urza's Power Plant", "Urza's Tower"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant, tower = scenario.untapped_sources(
        "Urza's Mine", "Urza's Power Plant", "Urza's Tower"
    )

    scenario.cast_onto_stack("Pithing Needle", username="alice", auto=True)

    tapped = [land for land in (mine, plant, tower) if land.tapped]
    assert len(tapped) == 1


def test_two_tron_pieces_pay_their_base_amount_but_not_more():
    """Only two of the three pieces out: neither's condition holds (each
    names the *other two*, and one of those two is missing), so both make
    their base {C} - {C}{C} total, enough for Mind Stone's `{2}` and not for
    Trinisphere's `{3}`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Stone"],
            battlefield=["Urza's Mine", "Urza's Power Plant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant = scenario.untapped_sources("Urza's Mine", "Urza's Power Plant")

    scenario.cast_onto_stack("Mind Stone", username="alice", auto=True)

    assert mine.tapped and plant.tapped
    assert scenario.player("alice").mana_pool.floating == {}


def test_two_tron_pieces_cannot_pay_more_than_their_base_amount():
    """The same two pieces cannot stretch to Trinisphere's `{3}` - each is
    still only its base {C} with the third piece missing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Trinisphere"],
            battlefield=["Urza's Mine", "Urza's Power Plant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant = scenario.untapped_sources("Urza's Mine", "Urza's Power Plant")
    casting = scenario.cast("Trinisphere", "alice")
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError as exc:
        raised = True
        message = str(exc)

    assert raised
    assert "{3}" in message
    assert mine.tapped is False and plant.tapped is False  # fail closed


def test_ulamog_is_still_correctly_refused_by_full_tron_alone():
    """Full Tron's boosted maximum is seven, not ten - Ulamog's `{10}` stays
    refused even after the fix, proving the solver did not start overshooting
    in the other direction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ulamog, the Ceaseless Hunger"],
            battlefield=["Urza's Mine", "Urza's Power Plant", "Urza's Tower"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant, tower = scenario.untapped_sources(
        "Urza's Mine", "Urza's Power Plant", "Urza's Tower"
    )
    casting = scenario.cast("Ulamog, the Ceaseless Hunger", "alice")
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError as exc:
        raised = True
        message = str(exc)

    assert raised
    assert "{10}" in message
    assert not (mine.tapped or plant.tapped or tower.tapped)


def test_mixed_tron_and_a_basic_still_prefers_the_fixed_colour_source():
    """Full Tron plus a Mountain and a Sacred Foundry, casting a `{R}` spell:
    the Tron pieces cannot make red at all, so they are never a candidate
    assignment for this cost, and between the Mountain and the Foundry the
    solver still prefers the fixed, less flexible Mountain - the existing
    minimal/least-flexible preference is unaffected by resolving Tron's
    conditional clause."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=[
                "Urza's Mine",
                "Urza's Power Plant",
                "Urza's Tower",
                "Mountain",
                "Sacred Foundry",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine, plant, tower, mountain, foundry = scenario.untapped_sources(
        "Urza's Mine", "Urza's Power Plant", "Urza's Tower", "Mountain", "Sacred Foundry"
    )

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    assert mountain.tapped is True
    assert foundry.tapped is False
    assert not (mine.tapped or plant.tapped or tower.tapped)


def test_gemstone_caverns_without_its_luck_counter_cannot_pay_a_coloured_cost():
    """No luck counter: Gemstone Caverns' condition does not hold, so it only
    makes {C} - not enough for Shock's `{R}`, and it is not tapped for a cost
    it cannot help pay."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Gemstone Caverns"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (caverns,) = scenario.untapped_sources("Gemstone Caverns")
    casting = scenario.cast("Shock", "alice", targets=["alice"])
    payment = casting.begin_paying()

    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert caverns.tapped is False


def test_gemstone_caverns_with_its_luck_counter_auto_taps_for_the_needed_colour():
    """With a luck counter on it, Gemstone Caverns' condition holds and it
    adds one mana of any colour instead of {C} - the solver picks red to pay
    Shock, the same way it already does for a printed dual or an any-colour
    source such as Birds of Paradise."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Gemstone Caverns"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (caverns,) = scenario.untapped_sources("Gemstone Caverns")
    caverns.counters.add("luck")

    scenario.cast_onto_stack("Shock", username="alice", targets=["alice"], auto=True)

    assert caverns.tapped is True
    assert scenario.player("alice").mana_pool.floating == {}


@pytest.mark.xfail(
    reason=(
        "Ugin's Labyrinth's condition is 'if a card is exiled with this land' - "
        "tracking which permanent an exiled card was imprinted on is not modelled "
        "(see docs/engine-coverage.md and test_mana_abilities.py's "
        "test_ugins_labyrinth_imprint_condition_is_not_modelled), so auto_tap sees "
        "only the base {C} even with a card imprinted, and cannot solve a {2} cost "
        "off it alone."
    )
)
def test_ugins_labyrinth_auto_taps_for_its_imprint_bonus():
    scenario = (
        Scenario().player("alice", hand=["Mind Stone"], battlefield=["Ugin's Labyrinth"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (land,) = scenario.untapped_sources("Ugin's Labyrinth")

    scenario.cast_onto_stack("Mind Stone", username="alice", auto=True)

    # What CR 605.1a actually promises here, if imprint tracking existed:
    assert land.tapped is True
    assert scenario.player("alice").mana_pool.floating == {}

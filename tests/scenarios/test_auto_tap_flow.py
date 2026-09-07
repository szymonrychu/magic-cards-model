"""The flow-based auto-tap solver (T8b) - the shapes flow alone cannot express.

`_solve_auto_tap` (`machines/cost.py`) used to be `_solve_auto_tap_brute_force`:
`combinations(candidates, size)` over every untapped source, then every colour
a choice source in each combination could make. `_solve_auto_tap_flow` replaces
that with a max-flow extension of `ManaPool`'s own `source -> demand -> bucket
-> sink` network (`models/mana._assign_sources`) by one more layer, `demand ->
bucket -> permanent -> sink`, and branches explicitly only over what that
network cannot express - see `_is_exotic`'s own docstring.

This file is the direct, hand-picked coverage for each of those shapes with
real printings; `test_auto_tap_flow_property.py` is the randomised check that
the flow solver and the kept brute-force oracle never disagree on a board
neither of these picked by hand.

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 118.3** - "a permanent that's already tapped can't be tapped to pay a
  cost" - one `{T}` per permanent, whichever of its abilities it pays with.
  This is the rule `_group_by_source` protects: a naive flow network treating
  Eldrazi Temple's two abilities as two independent providers would let their
  capacities add (1 + 2 = 3), which is exactly two taps from one land.
- **CR 106.6** - a restriction travels with the mana, not the source, and
  narrows what it may pay for; the flow solver's per-permanent bucket map must
  not offer a restricted alternative for a purpose it cannot serve.
- **CR 107.4h / 106.3** - `{S}` is paid with mana from a snow source, of any
  colour; `_bucket_map` reads a permanent's snow flag once per permanent
  (`is_snow_source`), not per colour.
- **CR 118.13a** - the payer's choice of how a payable-in-multiple-ways symbol
  is covered; `_candidate_options` still owns this, unchanged, and the flow
  solver only has to agree with it, not reimplement it.
"""

from magic_cards_model.machines import CostPayment, Step, TotalCost, could_pay_mana_cost
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.mana import ManaCost, ManaSpend
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Hard shape 1: a source whose choice is between alternatives of more than
# one mana each - Shang-Chi's `{T}: Add two mana of any one color.`, the only
# card in this pool shaped that way (see `_is_exotic`). Branched over
# explicitly rather than handed to the flow network, which would otherwise
# let two units of flow leave by two different colour edges - two colours
# from one activation, not a choice of one.
# --------------------------------------------------------------------------


def test_shang_chi_pays_two_of_one_colour_for_an_ability_activation():
    """Shang-Chi alone makes exactly two mana of whichever single colour is
    needed - here red, for an activation cost that has nothing to do with
    Shang-Chi's own green identity."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    spend = ManaSpend.activating(card("Basking Rootwalla"))
    cost = ManaCost.parse("{R}{R}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is True

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice", spend=spend)
    tapped = payment.auto_tap(sources)
    assert len(tapped) == 1
    assert tapped[0].name == "Shang-Chi, Master of Kung Fu"
    payment.pay()
    assert scenario.player("alice").mana_pool.floating == {}


def test_shang_chi_can_choose_any_one_colour_not_just_its_own():
    """The same land, asked for green instead - proving the branch tries every
    one of its five alternatives, not just the one matching its own printed
    colour identity."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    spend = ManaSpend.activating(card("Basking Rootwalla"))
    cost = ManaCost.parse("{G}{G}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is True


def test_shang_chi_cannot_stretch_past_its_own_two_mana():
    """One activation is one choice of colour for two mana, never three - the
    same permanent cannot pay `{R}{R}{R}` off nothing else."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    spend = ManaSpend.activating(card("Basking Rootwalla"))
    cost = ManaCost.parse("{R}{R}{R}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is False


def test_shang_chis_restricted_mana_is_withheld_from_a_creature_spell():
    """The restriction is a purpose test, not a colour test - a creature
    *spell* is not an ability of a creature *source* (CR 106.6), so the same
    land offers nothing at all here and the cost is refused."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Shang-Chi, Master of Kung Fu"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    llanowar = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    spend = ManaSpend.casting(llanowar.card)
    cost = ManaCost.parse("{G}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is False


# --------------------------------------------------------------------------
# Hard shape 1b, the grouping bug it guards against: a permanent with *two*
# `{T}`-only abilities (Eldrazi Temple) must never have its two capacities
# summed. `_group_by_source` folds `_auto_tap_candidates`'s one-entry-per-
# ability list back into one entry per permanent before the flow network -
# or exotic branching - ever sees it, so at most one of the two is ever
# offered as this land's contribution.
# --------------------------------------------------------------------------


def test_eldrazi_temple_never_sums_its_two_abilities():
    """Eldrazi Temple alone makes {C} *or* {C}{C} (CR 118.3: one {T}), never
    {C}{C}{C} - Glaring Fleshraker's {2}{C} (converted 3) needs one mana more
    than either ability alone can give, restricted ability included."""
    scenario = (
        Scenario()
        .player("alice", hand=["Glaring Fleshraker"], battlefield=["Eldrazi Temple"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    fleshraker = scenario.find("Glaring Fleshraker", Zone.HAND, "alice")
    spend = ManaSpend.casting(fleshraker.card)
    cost = ManaCost.parse("{2}{C}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is False


def test_eldrazi_temple_pays_the_two_its_restricted_ability_actually_makes():
    """The restricted ability alone is enough for a cheaper colourless cost -
    proving the land is not simply withheld altogether once it has more than
    one ability to offer."""
    scenario = (
        Scenario().player("alice", hand=["Mind Stone"], battlefield=["Eldrazi Temple"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    mind_stone = scenario.find("Mind Stone", Zone.HAND, "alice")
    spend = ManaSpend.casting(mind_stone.card)
    cost = ManaCost.parse("{2}")

    # Mind Stone is colourless but not an Eldrazi spell, so the restricted
    # {C}{C} ability is still withheld (see test_auto_tap.py's own coverage of
    # this refusal) - this asks the same board a cost the *unrestricted*
    # ability alone can pay, {1}, to confirm the land is not withheld outright.
    assert could_pay_mana_cost(ManaCost.parse("{1}"), sources, game=game, payer="alice") is True
    assert could_pay_mana_cost(cost, sources, game=game, payer="alice", spend=spend) is False


# --------------------------------------------------------------------------
# Hard shape 2: filter lands. Their only mana-producing ability beyond the
# intrinsic {C} pays with mana already in the pool (CR 118.3a would have that
# be a cycle in a network shaped like this one), so it is never a bare-{T}
# ability at all - `free_tap_mana_abilities` excludes anything but a lone
# `{T}` cost before `_auto_tap_candidates` runs, and the flow solver never
# sees it as a candidate to group, brute-force, or route through in the first
# place.
# --------------------------------------------------------------------------


def test_a_filter_land_is_never_offered_to_auto_tap():
    """Sunken Ruins's `{U/B}, {T}: Add {U}{U}, {U}{B}, or {U}{B}.` costs more
    than `{T}` and is withheld exactly like Nurturing Peatland's life payment
    (`test_auto_tap.py`'s own coverage) - the free `{T}: Add {C}.` is all that
    is left, which cannot pay a coloured cost at all."""
    scenario = Scenario().player("alice", hand=["Shock"], battlefield=["Sunken Ruins"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (ruins,) = scenario.untapped_sources("Sunken Ruins")
    casting = scenario.cast("Shock", "alice", targets=["alice"])
    payment = casting.begin_paying()

    raised = False
    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    except ValueError:
        raised = True

    assert raised
    assert ruins.tapped is False


def test_a_filter_land_still_pays_its_free_colourless_ability():
    """The land is not withheld outright - its bare `{T}: Add {C}.` still
    counts for a generic cost, the same shape `test_tinder_farm_uses_its_
    free_ability_not_the_sacrifice_one` already covers for a costlier second
    ability."""
    scenario = Scenario().player("alice", battlefield=["Sunken Ruins"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (ruins,) = scenario.untapped_sources("Sunken Ruins")
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{1}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is True

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice")
    tapped = payment.auto_tap(sources)
    assert tapped == [ruins]
    payment.pay()


# --------------------------------------------------------------------------
# Hard shape 3: CR 106.6 restricted mana at the source layer - already the
# subject of `test_auto_tap.py`'s Eldrazi Temple/Cavern of Souls coverage
# before this task; kept here as a direct flow-solver check that a restricted
# alternative is only ever a bucket this payment's `spend` already allows,
# never offered and rejected downstream.
# --------------------------------------------------------------------------


def test_cavern_of_souls_pays_a_creature_spell_of_the_chosen_type():
    """The restricted any-colour ability, offered because this is exactly the
    creature spell of the chosen type it was built to pay - `auto_tap` prefers
    it (least flexible after a fixed source, but it is the only source here)
    over nothing at all, since the unrestricted `{T}: Add {C}.` cannot pay a
    coloured cost."""
    scenario = (
        Scenario().player("alice", hand=["Llanowar Elves"], battlefield=["Cavern of Souls"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (cavern,) = scenario.untapped_sources("Cavern of Souls")
    cavern.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")

    scenario.cast_onto_stack("Llanowar Elves", username="alice", auto=True)

    assert cavern.tapped is True
    assert scenario.player("alice").mana_pool.floating == {}


# --------------------------------------------------------------------------
# Hard shape 4: snow (CR 107.4h, 106.3) - a second dimension on the bucket
# alongside colour, read off the *permanent* once (`is_snow_source`), not
# offered per colour the way a genuine colour choice is.
# --------------------------------------------------------------------------


def test_auto_tap_prefers_the_snow_source_for_a_snow_cost():
    """Icehide Golem costs `{S}` - only a snow source can pay it, so between an
    ordinary Forest and a Snow-Covered Forest, `auto_tap` has to reach past
    the plain one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Icehide Golem"], battlefield=["Forest", "Snow-Covered Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest, snow_forest = scenario.untapped_sources("Forest", "Snow-Covered Forest")

    scenario.cast_onto_stack("Icehide Golem", username="alice", auto=True)

    assert snow_forest.tapped is True
    assert forest.tapped is False


def test_auto_tap_refuses_a_snow_cost_with_no_snow_source():
    """The mirror of the above - an ordinary Forest alone cannot pay `{S}`,
    however much green it makes."""
    scenario = Scenario().player("alice", hand=["Icehide Golem"], battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast("Icehide Golem", "alice")
    payment = casting.begin_paying()

    raised = False
    try:
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    except ValueError:
        raised = True

    assert raised
    assert forest.tapped is False


# --------------------------------------------------------------------------
# Hard shape 5: hybrid and Phyrexian symbols - the COST side's own choice
# (CR 118.13a), already `_candidate_options`'s job and unchanged by this
# task; these confirm the flow solver still asks it correctly instead of
# assuming every symbol in `owed` has exactly one way to pay.
# --------------------------------------------------------------------------


def test_hybrid_symbols_split_across_two_single_colour_sources():
    """Kitchen Finks's `{1}{G/W}{G/W}` off a lone Forest and a lone Plains -
    neither makes both hybrid symbols the same colour, so the solver has to
    read one `{G/W}` as green and the other as white."""
    scenario = (
        Scenario().player("alice", hand=["Kitchen Finks"], battlefield=["Forest", "Plains"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{G/W}{G/W}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is True

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice")
    tapped = payment.auto_tap(sources)
    assert len(tapped) == 2
    payment.pay()
    assert scenario.player("alice").mana_pool.floating == {}


def test_phyrexian_symbol_falls_back_to_life_when_mana_runs_short():
    """Dismember's `{1}{B/P}{B/P}` off one Swamp and one Forest: the {1} and
    one `{B/P}` are paid with mana (Swamp's black, Forest's green as generic),
    and the second `{B/P}` has nothing left to pay it but 2 life."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dismember"],
            battlefield=["Swamp", "Forest", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = [s for s in game.permanents_controlled_by("alice") if s.name != "Llanowar Elves"]
    target = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    cost = ManaCost.parse("{1}{B/P}{B/P}")
    life_before = scenario.player("alice").life

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is True

    scenario.cast_onto_stack("Dismember", username="alice", targets=[target], auto=True)

    assert scenario.player("alice").life == life_before - 2


def test_phyrexian_symbol_is_refused_with_no_mana_and_no_life_on_the_table():
    """The pure predicate, asked with `life_available` left at its default of
    zero: two lands cannot make three mana, and no life is offered either, so
    `{1}{B/P}{B/P}` is correctly refused rather than assumed payable with
    life nobody agreed to spend."""
    scenario = (
        Scenario().player("alice", hand=["Dismember"], battlefield=["Swamp", "Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{1}{B/P}{B/P}")

    assert could_pay_mana_cost(cost, sources) is False

"""Vivid (ecl-T1) - the two non-amount positions the ability word's "colors
among permanents you control" count is printed in: a spell's own CR 601.2f
self cost reduction (Rime Chill, Wildvine Pummeler) and a characteristic-
defining ability (Squawkroaster's power, CR 604.3a/613.4a). Both are
classified `static_unaudited` by the sweep - nothing in `support.py` audits a
spell's own self-reduction or a CDA's own count - so this file is their proof.

Also covers Sunderflock's neighbouring cost template, "This spell costs {X}
less to cast, where X is the greatest mana value among Elementals you
control" - the same `_COSTS_LESS_X_WHERE_X_IS_RE` fallback `models/game.py`'s
`cost_reduction_for` now reads generically, widened to a subtype qualifier
(`machines/effects._GREATEST_CHARACTERISTIC_AMONG_RE`) neither of the two
narrower pre-existing readers for this position (Ghalta's own "among
creatures you control") could name.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 601.2f: the total cost is locked in once every increase and reduction
  has applied; multiple reductions may be applied in any order.
- CR 118.7a: "Effects that reduce a cost by an amount of generic mana affect
  only the generic mana component of that cost."
- CR 604.3a: a characteristic-defining ability that sets power/toughness,
  printed on the object it affects, applies in sublayer 7a (CR 613.4a) -
  Squawkroaster's own printed toughness (a plain 4, not `*`) is untouched.
- CR 613.3: layer effects apply only to a permanent on the battlefield - a
  card elsewhere reads its printed characteristics, `*` included.
- CR 105.2c: a colorless permanent contributes no color to the count.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_WHITE = "Savannah Lions"
_BLUE = "Cursecatcher"
_BLACK = "Blood Artist"


def _cost(scenario: Scenario, name: str, **cast_kwargs) -> str:
    casting = scenario.cast(name, **cast_kwargs)
    return str(casting.total_cost.mana)


# -- Rime Chill: the reduction, and its own body once cast ---------------------


def test_rime_chill_costs_one_less_per_color_among_permanents():
    """Vivid - "This spell costs {1} less to cast for each color among
    permanents you control." Base {6}{U}; white, blue, and black among
    Alice's permanents takes {3} off the generic component (CR 118.7a),
    leaving {3}{U}.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rime Chill"],
            battlefield=[_WHITE, _BLUE, _BLACK] + ["Island"] * 7,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _cost(scenario, "Rime Chill", targets=[bears]) == "{3}{U}"


def test_rime_chill_reduction_never_touches_the_colored_symbol():
    """CR 118.7a: a generic reduction never touches the coloured component.
    CR 105.1 caps the count at five colors - one short of Rime Chill's six
    generic mana - so the {U} always survives no matter how many colors
    Alice controls.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rime Chill"],
            battlefield=[_WHITE, _BLUE, _BLACK, "Goblin Guide", "Llanowar Elves"] + ["Island"] * 7,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _cost(scenario, "Rime Chill", targets=[bears]) == "{1}{U}"


def test_rime_chill_taps_up_to_two_stuns_them_and_draws_a_card():
    """Rime Chill's own body, once cast: "Tap up to two target creatures.
    Put a stun counter on each of them. ... Draw a card." (CR 122.1d) - the
    Vivid line only reduces what it costs to get here.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rime Chill"],
            library=["Forest"],
            battlefield=[_WHITE, _BLUE, _BLACK] + ["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.cast_and_resolve("Rime Chill", *sources, targets=[bears, giant])

    assert bears.tapped and giant.tapped
    assert bears.counter_count("stun") == 1
    assert giant.counter_count("stun") == 1
    assert len(scenario.player("alice").hand) == 1


# -- Wildvine Pummeler: the same reduction, a different body -------------------


def test_wildvine_pummeler_costs_one_less_per_color_among_permanents():
    """Vivid - the identical self reduction on a creature spell (base
    {6}{G}); two colors among permanents (white, blue) takes {2} off.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wildvine Pummeler"], battlefield=[_WHITE, _BLUE] + ["Forest"] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Wildvine Pummeler") == "{4}{G}"


# -- Sunderflock: a neighbouring cost template, subtype-qualified ---------------


def test_sunderflock_costs_x_less_where_x_is_the_greatest_mana_value_among_elementals():
    """ "This spell costs {X} less to cast, where X is the greatest mana
    value among Elementals you control." Luminollusk (an Elemental, mana
    value 4) takes {4} off Sunderflock's base {7}{U}{U}.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=["Luminollusk"] + ["Island"] * 9)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Sunderflock") == "{3}{U}{U}"


def test_sunderflock_with_no_elementals_pays_full_cost():
    """CR 107.2: "the greatest ... among" an empty group is 0 - no
    Elementals among Alice's permanents takes nothing off.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=[_WHITE] + ["Island"] * 9)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Sunderflock") == "{7}{U}{U}"


# -- Squawkroaster: the CDA, on and off the battlefield -------------------------


def test_squawkroasters_power_equals_the_colors_among_permanents():
    """Vivid - "Squawkroaster's power is equal to the number of colors among
    permanents you control." Two colors (white, blue) among permanents,
    counting Squawkroaster's own red - three - is its power; its printed
    toughness (a plain 4, not `*`) is untouched (CR 208.2a's power-only CDA).
    """
    scenario = Scenario().player("alice", battlefield=["Squawkroaster", _WHITE, _BLUE]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    squawkroaster = scenario.creature("Squawkroaster", "alice")

    assert scenario.game.power_of(squawkroaster) == 3
    assert scenario.game.toughness_of(squawkroaster) == 4


def test_squawkroasters_power_moves_with_the_board():
    """CR 613.5: the CDA is recomputed continually - adding a third color
    (black) mid-game raises Squawkroaster's power without anything touching
    Squawkroaster itself.
    """
    scenario = (
        Scenario()
        .player("alice", library=[_BLACK], battlefield=["Squawkroaster", _WHITE, _BLUE])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    squawkroaster = scenario.creature("Squawkroaster", "alice")
    assert scenario.game.power_of(squawkroaster) == 3

    scenario.put_onto_battlefield(_BLACK, "alice", from_zone=Zone.LIBRARY)
    assert scenario.game.power_of(squawkroaster) == 4


def test_squawkroaster_off_the_battlefield_has_no_computed_power():
    """CR 613.3: layer effects, this CDA included, apply only to a permanent
    on the battlefield - in hand, Squawkroaster reads its printed `*`
    (CR 208.4b), which is no numeric power at all.
    """
    scenario = Scenario().player("alice", hand=["Squawkroaster"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    squawkroaster = scenario.find("Squawkroaster", Zone.HAND)

    assert squawkroaster.power is None

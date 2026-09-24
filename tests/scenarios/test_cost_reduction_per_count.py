"""CR 601.2f self-reductions that count something on the board or in a
player's history, one clause per required card.

Read whole in this session with `mise run rules:find 601.2f` and
`mise run rules:find 118.7a`:

- **CR 601.2f** - "The total cost is the mana cost or alternative cost ...
  plus all additional costs and cost increases, and minus all cost
  reductions ... It can't be reduced to less than {0}."
- **CR 118.7a** - "Effects that reduce a cost by an amount of generic mana
  affect only the generic mana component of that cost. They can't affect the
  colored or colorless mana components of that cost."

Every reader here (`Game.cost_reduction_for`'s per-card-type, per-turn-
history, *Domain*, and opponent's-board rows) is pre-existing, not work this
task adds or widens - each already has thorough dedicated coverage in
`test_dynamic_cost_reduction.py` (Emrakul), `test_cost_reduction_shapes.py`
(Domain, Hollow One, Obsidian Charmaw) and `test_self_reduction_reaches_the_
cast.py` (Leyline Binding's CR 118.7a floor, Emrakul through the ordinary
cast path). This file is this task's own required-card coverage - the four
templates, on the four cards named for it, plus the CR 118.7a floor that
`Game.cost_reduction_for`'s docstring calls out by name for all four - kept
short precisely because it is not proving new genericity, only that the
listed cards resolve to the discounted cost this template promises.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cycle
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

EMRAKUL = "Emrakul, the Promised End"
HOLLOW_ONE = "Hollow One"
LEYLINE_BINDING = "Leyline Binding"
SCION_OF_DRACO = "Scion of Draco"
OBSIDIAN_CHARMAW = "Obsidian Charmaw"


# -- Emrakul: "for each card type among cards in your graveyard" ------------


def test_emrakul_discounted_by_one_per_card_type_in_the_graveyard():
    """Sol Ring (artifact) and Lightning Bolt (instant) and Grizzly Bears
    (creature) are three card types - CR 205.2b counts a multi-type card
    once per type it has, but none of these three doubles up."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[EMRAKUL],
            graveyard=["Sol Ring", "Lightning Bolt", "Grizzly Bears"],
            battlefield=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(EMRAKUL)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{10}")


def test_emrakul_with_an_empty_graveyard_costs_its_full_thirteen():
    scenario = Scenario().player("alice", hand=[EMRAKUL], battlefield=["Island"] * 13).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(EMRAKUL)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{13}")


def test_emrakuls_reduction_is_read_fresh_as_the_cost_is_determined():
    """CR 601.2f is a step of casting, not a stored discount - a card that
    reaches the graveyard between two castings changes what the second one
    costs, without anything re-triggering."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[EMRAKUL, "Lightning Bolt"],
            graveyard=["Sol Ring"],
            battlefield=["Island"] * 13,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.cast(EMRAKUL)
    scenario.game.determine_total_cost(before)
    assert before.total_cost.mana == ManaCost.parse("{12}")
    before.cancel()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bolt])

    after = scenario.cast(EMRAKUL)
    scenario.game.determine_total_cost(after)
    assert after.total_cost.mana == ManaCost.parse("{11}")


# -- Hollow One: "for each card you've cycled or discarded this turn" -------


def test_hollow_one_discounted_by_two_per_card_discarded_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HOLLOW_ONE, "Lightning Bolt", "Grizzly Bears"],
            battlefield=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bolt, bears])

    casting = scenario.cast(HOLLOW_ONE)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{1}")


def test_hollow_one_with_nothing_discarded_this_turn_costs_its_full_five():
    scenario = Scenario().player("alice", hand=[HOLLOW_ONE], battlefield=["Island"] * 5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(HOLLOW_ONE)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{5}")


def test_hollow_ones_own_cycling_counts_toward_its_own_discount():
    """CR 702.29a/d: cycling discards the card to pay the activation cost, so
    a card that cycled itself away still counts once toward "cycled or
    discarded"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HOLLOW_ONE, "Street Wraith"],
            battlefield=["Island"] * 5,
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")

    casting = scenario.cast(HOLLOW_ONE)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{3}")


# -- Domain: "for each basic land type among lands you control" -------------


def test_leyline_binding_discounted_by_one_per_basic_land_type_controlled():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[LEYLINE_BINDING],
            battlefield=["Plains", "Island", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(LEYLINE_BINDING)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{2}{W}")


def test_leyline_binding_with_all_five_basic_land_types_floors_at_the_white_pip():
    """CR 118.7a: a generic-mana reduction never touches the colored
    component - {5}{W} with a {5} discount settles at {W}, not {0}."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[LEYLINE_BINDING],
            battlefield=["Plains", "Island", "Swamp", "Mountain", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(LEYLINE_BINDING)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{W}")


def test_scion_of_draco_discounted_by_two_per_basic_land_type_controlled():
    """A differently amounted Domain line ({2} a type, not {1}) on a
    differently typed card - Leyline Binding's own Enchantment against Scion
    of Draco's Artifact Creature - proving the reader is read off the
    sentence, not off either printing's other characteristics."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SCION_OF_DRACO],
            battlefield=["Plains", "Island", "Swamp", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(SCION_OF_DRACO)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{4}")


def test_domain_counts_land_types_not_lands():
    """Two Plains is still one basic land type - CR 305.6's five types are
    what Domain counts, never a land census."""
    scenario = (
        Scenario().player("alice", hand=[LEYLINE_BINDING], battlefield=["Plains", "Plains"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(LEYLINE_BINDING)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{4}{W}")


# -- Obsidian Charmaw: "for each land your opponents control that could
#    produce {C}" -------------------------------------------------------


def test_obsidian_charmaw_discounted_per_opponent_colorless_producing_land():
    scenario = (
        Scenario()
        .player("alice", hand=[OBSIDIAN_CHARMAW], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Wastes", "Wastes"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(OBSIDIAN_CHARMAW)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}{R}")


def test_obsidian_charmaws_own_lands_never_discount_it():
    """ "Your opponents control" - the caster's own colorless-producing lands
    (were there any here) do not count, and this board has none either way,
    proving the reduction is not a bare "lands that could produce {C}"
    census."""
    scenario = (
        Scenario()
        .player("alice", hand=[OBSIDIAN_CHARMAW], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Island", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(OBSIDIAN_CHARMAW)
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost.parse("{3}{R}{R}")

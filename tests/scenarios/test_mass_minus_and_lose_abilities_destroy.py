"""Two one-shot group effects whose affected set is fixed as they begin.

- Harvester of Misery: "When this creature enters, other creatures get -2/-2
  until end of turn." Shefet Archfiend (Standard/Pioneer/Modern, in no deck
  list) is the second printing: "... all other creatures get -2/-2 until end
  of turn."
- Day of Black Sun: "Each creature with mana value X or less loses all
  abilities until end of turn. Destroy those creatures." No other
  Modern/Pioneer/Standard printing carries the loses-all-abilities-then-
  destroy sentence pair (searched on Scryfall this session); its group is
  read by the same qualifier grammar the "Destroy each ..." sweepers use.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 611.2c** - a continuous effect from a resolving spell or ability fixes
  the set of objects it affects when it begins; a creature entering later is
  not affected.
- **CR 613.4c** - "-2/-2" is a sublayer 7c modification.
- **CR 613.1f** - "loses all abilities" is a layer 6 effect.
- **CR 608.2c** - instructions are followed in order; "those creatures" are
  exactly the creatures the first sentence affected.
- **CR 701.8a / 702.12b** - destroy moves a permanent to the graveyard; an
  indestructible one can't be destroyed - but Day of Black Sun has already
  taken indestructible away.
- **CR 603.10a** - a dies trigger looks back in time: a creature that had no
  abilities as it died has no dies trigger to fire.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- Harvester of Misery / Shefet Archfiend -----------------------------------


def _harvester_board(entering: str = "Harvester of Misery"):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[entering, "Grizzly Bears"],
            battlefield=["Serra Angel", "Llanowar Elves"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter(scenario, name: str):
    permanent = scenario.put_onto_battlefield(name, "alice")
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    scenario.state_based_actions()
    return permanent


def test_harvester_gives_every_other_creature_minus_two_minus_two():
    scenario = _harvester_board()
    angel = scenario.creature("Serra Angel", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    harvester = _enter(scenario, "Harvester of Misery")
    assert _pt(scenario, angel) == (2, 2)
    assert _pt(scenario, giant) == (1, 1)
    assert _pt(scenario, harvester) == (5, 4), "other: not itself"


def test_small_creatures_on_both_sides_die():
    scenario = _harvester_board()
    elves = scenario.creature("Llanowar Elves", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _enter(scenario, "Harvester of Misery")
    assert elves.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_a_creature_entering_afterwards_is_not_affected():
    """CR 611.2c: the set was fixed as the effect began."""
    scenario = _harvester_board()
    _enter(scenario, "Harvester of Misery")
    late = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    assert _pt(scenario, late) == (2, 2)
    assert late.zone is Zone.BATTLEFIELD


def test_the_shrink_ends_at_cleanup():
    scenario = _harvester_board()
    angel = scenario.creature("Serra Angel", "alice")
    _enter(scenario, "Harvester of Misery")
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert _pt(scenario, angel) == (4, 4)


def test_shefet_archfiend_is_the_same_effect_with_all():
    scenario = _harvester_board("Shefet Archfiend")
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    archfiend = _enter(scenario, "Shefet Archfiend")
    assert _pt(scenario, angel) == (2, 2)
    assert bears.zone is Zone.GRAVEYARD
    assert _pt(scenario, archfiend) == (5, 5)


def test_harvester_and_shefet_classify_as_handled():
    for name in ("Harvester of Misery", "Shefet Archfiend"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


# -- Day of Black Sun ---------------------------------------------------------


def _sun_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Day of Black Sun"],
            battlefield=["Grizzly Bears", *["Swamp"] * 6],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            battlefield=["Barbed Servitor", "Haywire Mite", "Serra Angel"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_sun(scenario, x: int):
    casting = scenario.cast("Day of Black Sun")
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * (x + 2)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_every_creature_with_mana_value_x_or_less_is_destroyed():
    scenario = _sun_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    mite = scenario.creature("Haywire Mite", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    _cast_sun(scenario, 2)
    assert bears.zone is Zone.GRAVEYARD
    assert mite.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD, "mana value 5 is more than 2"


def test_indestructible_is_lost_before_the_destroy():
    """CR 608.2c + 702.12b: the first sentence removes indestructible."""
    scenario = _sun_board()
    servitor = scenario.creature("Barbed Servitor", "bob")
    _cast_sun(scenario, 4)
    assert servitor.zone is Zone.GRAVEYARD


def test_a_creature_above_x_keeps_its_abilities():
    scenario = _sun_board()
    angel = scenario.creature("Serra Angel", "bob")
    servitor = scenario.creature("Barbed Servitor", "bob")
    _cast_sun(scenario, 3)
    assert servitor.zone is Zone.BATTLEFIELD, "mana value 4 is more than 3"
    assert scenario.game.computed_board().of(angel).has_ability("Flying")
    assert scenario.game.computed_board().of(servitor).has_ability("Indestructible")


def test_a_dies_trigger_does_not_fire_because_the_creature_had_no_abilities():
    """CR 603.10a: Haywire Mite's "you gain 2 life" looked back at nothing."""
    scenario = _sun_board()
    mite = scenario.creature("Haywire Mite", "bob")
    _cast_sun(scenario, 1)
    assert mite.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_x_of_zero_destroys_only_mana_value_zero_creatures():
    scenario = _sun_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    mite = scenario.creature("Haywire Mite", "bob")
    _cast_sun(scenario, 0)
    assert bears.zone is Zone.BATTLEFIELD
    assert mite.zone is Zone.BATTLEFIELD


def test_day_of_black_sun_classifies_as_handled():
    clauses = [c for c in classify_clauses(card("Day of Black Sun")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}

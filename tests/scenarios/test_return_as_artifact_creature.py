"""Returning a card from the graveyard as a creature it was not - Brilliance
Unleashed's second mode: "Choose target artifact card in your graveyard.
Return it to the battlefield if it's an artifact creature card. Otherwise,
return it to the battlefield and it's a 3/3 Robot artifact creature with
flying."

- CR 700.2 / CR 700.2a: "Choose one or both" - either mode alone, or both,
  resolved in printed order.
- The rider is a continuous effect from a resolving spell with no stated
  duration (CR 611.2a: it lasts until the end of the game - here, as long as
  that object stays on the battlefield, CR 400.7).
- CR 205.1b: "[creature type] artifact creature" keeps every prior card type
  and subtype other than creature types; layer 4 (CR 613.1d) adds the
  creature type and the Robot, layer 6 (CR 613.1f) flying, sublayer 7b
  (CR 613.4b) the 3/3.
- An artifact creature card comes back as itself, no rider.

Off-set proof (legal, in no deck list): Abuelo's Awakening - "Return target
artifact or non-Aura enchantment card from your graveyard to the battlefield
with X additional +1/+1 counters on it. It's a 1/1 Spirit creature with
flying in addition to its other types." - the rider as its own sentence,
"in addition to its other types", an enchantment as well as an artifact,
and counters on arrival.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone

from .harness import Scenario

BRILLIANCE = "Brilliance Unleashed"
LANDS = ["Island", "Island", "Mountain", "Mountain", "Mountain", "Mountain"]


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _brilliance_board(*, graveyard=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[BRILLIANCE],
            battlefield=LANDS,
            graveyard=list(graveyard),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def _cast_brilliance(scenario, modes, targets):
    casting = scenario.cast(BRILLIANCE, username="alice")
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*LANDS, username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_a_noncreature_artifact_returns_as_a_3_3_flying_robot():
    scenario = _brilliance_board(graveyard=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")

    _cast_brilliance(scenario, [2], [ring])

    assert ring.zone is Zone.BATTLEFIELD
    chars = _chars(scenario, ring)
    assert Type.ARTIFACT in chars.types
    assert Type.CREATURE in chars.types
    assert "Robot" in chars.subtypes
    assert (chars.power, chars.toughness) == (3, 3)
    assert "Flying" in chars.abilities


def test_the_returned_artifact_keeps_its_own_abilities():
    """Nothing removes Sol Ring's mana ability - it is still there."""
    scenario = _brilliance_board(graveyard=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")

    _cast_brilliance(scenario, [2], [ring])

    assert any("Add {C}{C}" in line for line in _chars(scenario, ring).abilities)


def test_an_artifact_creature_card_returns_as_itself():
    scenario = _brilliance_board(graveyard=["Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")

    _cast_brilliance(scenario, [2], [thopter])

    chars = _chars(scenario, thopter)
    assert thopter.zone is Zone.BATTLEFIELD
    assert (chars.power, chars.toughness) == (0, 2)
    assert "Robot" not in chars.subtypes
    assert "Thopter" in chars.subtypes


def test_the_rider_outlasts_the_turn():
    """No stated duration (CR 611.2a)."""
    scenario = _brilliance_board(graveyard=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    _cast_brilliance(scenario, [2], [ring])

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    chars = _chars(scenario, ring)
    assert Type.CREATURE in chars.types
    assert (chars.power, chars.toughness) == (3, 3)


def test_once_it_leaves_it_is_a_new_object_without_the_rider():
    """CR 400.7: destroyed and put back, it is a plain Sol Ring again."""
    scenario = _brilliance_board(graveyard=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    _cast_brilliance(scenario, [2], [ring])

    scenario.game.destroy(ring)
    assert ring.zone is Zone.GRAVEYARD
    scenario.game.put_onto_battlefield(ring, "alice")

    assert Type.CREATURE not in _chars(scenario, ring).types


def test_both_modes_damage_and_return():
    scenario = _brilliance_board(graveyard=["Sol Ring"], bob=["Craw Wurm"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_brilliance(scenario, [1, 2], [wurm, ring])
    scenario.state_based_actions()

    assert wurm.zone is Zone.GRAVEYARD
    assert Type.CREATURE in _chars(scenario, ring).types


def test_the_damage_mode_alone_returns_nothing():
    scenario = _brilliance_board(graveyard=["Sol Ring"], bob=["Craw Wurm"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_brilliance(scenario, [1], [wurm])

    assert ring.zone is Zone.GRAVEYARD


def test_a_target_gone_before_resolution_returns_nothing():
    """CR 608.2b: an illegal target is not returned."""
    scenario = _brilliance_board(graveyard=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    casting = scenario.cast(BRILLIANCE, username="alice")
    casting.choose_modes([2])
    casting.choose_targets([ring])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*LANDS, username="alice"))
    scenario.put_on_stack(casting)

    scenario.game.exile_permanent(ring)
    scenario.resolve_top()

    assert ring.zone is Zone.EXILE


# -- Abuelo's Awakening --------------------------------------------------------


def _cast_awakening(scenario, target, x):
    lands = ["Plains"] * (4 + x)
    casting = scenario.cast("Abuelo's Awakening", username="alice")
    casting.choose_targets([target])
    payment = casting.determine_cost(x_value=x)
    casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands, username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _awakening_board(card, x):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Abuelo's Awakening"],
            battlefield=["Plains"] * (4 + x),
            graveyard=[card],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def test_awakening_returns_an_artifact_as_a_1_1_flying_spirit_with_counters():
    scenario = _awakening_board("Sol Ring", 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")

    _cast_awakening(scenario, ring, 2)

    chars = _chars(scenario, ring)
    assert ring.zone is Zone.BATTLEFIELD
    assert Type.ARTIFACT in chars.types
    assert Type.CREATURE in chars.types
    assert "Spirit" in chars.subtypes
    assert "Flying" in chars.abilities
    # 1/1 in 7b, two +1/+1 counters in 7c.
    assert (chars.power, chars.toughness) == (3, 3)


def test_awakening_returns_an_enchantment_too():
    """Glorious Anthem comes back a 1/1 Spirit enchantment creature - and
    pumps itself, since it is now a creature alice controls."""
    scenario = _awakening_board("Glorious Anthem", 0)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anthem = scenario.find("Glorious Anthem", Zone.GRAVEYARD, "alice")

    _cast_awakening(scenario, anthem, 0)

    chars = _chars(scenario, anthem)
    assert Type.ENCHANTMENT in chars.types
    assert Type.CREATURE in chars.types
    assert (chars.power, chars.toughness) == (2, 2)


def test_awakening_keeps_an_artifact_creatures_own_types():
    """ "in addition to its other types": Ornithopter stays a Thopter, and its
    base P/T is set to 1/1."""
    scenario = _awakening_board("Ornithopter", 0)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")

    _cast_awakening(scenario, thopter, 0)

    chars = _chars(scenario, thopter)
    assert {"Thopter", "Spirit"} <= set(chars.subtypes)
    assert (chars.power, chars.toughness) == (1, 1)

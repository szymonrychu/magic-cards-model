"""Colour-setting effects in layer 5 and hexproof from a creature's own
colours in layer 6.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 613.1e** layer 5 colour-changing effects; **CR 613.1f** layer 6
  ability-adding effects - applied after layer 5, so "each of its colors" is
  read off the colours layer 5 left.
- **CR 105.3** a new colour replaces every previous one; **CR 105.2c** a
  colorless object has no colour; **CR 105.1** the five colours ("all
  colors").
- **CR 608.2d** a choice made as an ability resolves; **CR 614.12a** an
  "as ... enters" choice, made before it enters.
- **CR 611.2a** no duration stated - until the end of the game.
- **CR 702.11d** hexproof from [quality]: only spells and abilities the
  permanent's controller's *opponents* control from sources of that quality;
  **CR 702.11g** "hexproof from each [characteristic]" is one hexproof per
  value of it.

Reported cards: Puca's Eye ("When this artifact enters, draw a card, then
choose a color. This artifact becomes the chosen color."), Shimmerwilds
Growth ("Enchanted land is the chosen color."), Tam, Mindful First-Year
("Each other creature you control has hexproof from each of its colors." /
"{T}: Target creature you control becomes all colors until end of turn.").

Second printings (legal, in no deck list, Scryfall printing read
2026-09-27): Scrapbasket (Modern) - "{1}: This creature becomes all colors
until end of turn." - the all-colours reader on the ability's own source;
Distorting Lens (Modern) - "{T}: Target permanent becomes the color of your
choice until end of turn." - the chosen-colour reader Puca's Eye widens,
still read with its duration and its target; Breaker of Creation (Modern) -
"Hexproof from each color" - CR 702.11g's "each" shorthand the colour
expansion shares.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

PUCA = "Puca's Eye"
GROWTH = "Shimmerwilds Growth"
TAM = "Tam, Mindful First-Year"
#: CR 105.1: the five colours - `Color.COLORLESS` is not one (CR 105.2c).
FIVE_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}


def _colors(scenario: Scenario, permanent) -> set[Color]:
    return set(scenario.game.characteristics_of(permanent).colors)


def _abilities(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent).abilities


def _end_the_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()


# --------------------------------------------------------------------------
# Puca's Eye
# --------------------------------------------------------------------------


def _puca():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[PUCA], battlefield=["Island", "Island"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_puca(scenario, color: Color):
    scenario.will_choose(color.value, username="alice")
    eye = scenario.cast_and_resolve(PUCA, *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()
    return eye


def test_puca_draws_then_becomes_the_chosen_color():
    scenario = _puca()
    hand = len(scenario.player("alice").hand) - 1

    eye = _cast_puca(scenario, Color.GREEN)

    assert len(scenario.player("alice").hand) == hand + 1
    assert _colors(scenario, eye) == {Color.GREEN}


def test_puca_keeps_the_color_past_cleanup():
    """CR 611.2a: no duration, so it never ends."""
    scenario = _puca()
    eye = _cast_puca(scenario, Color.RED)

    _end_the_turn(scenario)

    assert _colors(scenario, eye) == {Color.RED}


def test_a_later_color_change_wins_until_it_ends():
    """CR 613.7b: Distorting Lens's later layer 5 effect wins; once it ends
    at cleanup, Puca's Eye's indefinite colour is what is left."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[PUCA],
            battlefield=["Island", "Island", "Distorting Lens"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eye = _cast_puca(scenario, Color.GREEN)
    lens = scenario.find("Distorting Lens", Zone.BATTLEFIELD, "alice")
    scenario.will_choose(Color.BLACK.value, username="alice")

    scenario.activate(lens, targets=[eye])
    scenario.resolve_top()
    assert _colors(scenario, eye) == {Color.BLACK}

    _end_the_turn(scenario)
    assert _colors(scenario, eye) == {Color.GREEN}


# --------------------------------------------------------------------------
# Shimmerwilds Growth
# --------------------------------------------------------------------------


def _growth():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GROWTH],
            battlefield=["Forest", "Forest", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enchant(scenario, land, color: Color):
    scenario.will_choose(color.value, username="alice", source=GROWTH)
    return scenario.cast_and_resolve(
        GROWTH, *scenario.untapped_sources("Forest", "Forest"), targets=[land]
    )


def test_the_enchanted_land_is_the_chosen_color():
    scenario = _growth()
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    assert _colors(scenario, island) == set()

    _enchant(scenario, island, Color.RED)

    assert _colors(scenario, island) == {Color.RED}


def test_the_color_goes_when_the_aura_does():
    scenario = _growth()
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    aura = _enchant(scenario, island, Color.WHITE)

    scenario.game.destroy(aura)

    assert _colors(scenario, island) == set()


def test_only_the_enchanted_land_changes():
    scenario = _growth()
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    forests = [p for p in scenario.game.battlefield if p.name == "Forest"]

    _enchant(scenario, island, Color.BLACK)

    assert all(_colors(scenario, forest) == set() for forest in forests)


# --------------------------------------------------------------------------
# Tam, Mindful First-Year
# --------------------------------------------------------------------------


def _tam(*, alice=("Grizzly Bears",), bob_hand=("Lightning Bolt",), bob=("Mountain",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[TAM, *alice], library=["Island"] * 5)
        .player("bob", hand=list(bob_hand), battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tam = scenario.creature(TAM, "alice")
    tam.summoning_sick = False
    return scenario, tam


def test_another_green_creature_has_hexproof_from_green():
    scenario, _ = _tam()
    bears = scenario.creature("Grizzly Bears", "alice")

    assert "Hexproof from green" in _abilities(scenario, bears)
    assert "Hexproof from red" not in _abilities(scenario, bears)


def test_tam_itself_does_not_have_it():
    """ "Each other creature"."""
    scenario, tam = _tam()

    assert not any(line.startswith("Hexproof from") for line in _abilities(scenario, tam))


def test_an_opponents_spell_of_another_color_can_still_target_it():
    """Red Lightning Bolt is not green: hexproof from green does not stop it."""
    scenario, _ = _tam()
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    casting.choose_targets([bears])


def test_a_colorless_creature_gets_nothing():
    """CR 105.2c: colorless is no colour - Ornithopter has nothing to have
    hexproof from."""
    scenario, _ = _tam(alice=("Ornithopter",))
    thopter = scenario.creature("Ornithopter", "alice")

    assert not any(line.startswith("Hexproof from") for line in _abilities(scenario, thopter))


def test_all_colors_then_hexproof_from_all_colors():
    """Tam's own ability makes the Bears every colour (layer 5), and Tam's
    static then reads those (layer 6): bob's red Lightning Bolt can no
    longer target it (CR 702.11d)."""
    scenario, tam = _tam()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(tam, index=0, targets=[bears])
    scenario.resolve_top()

    assert _colors(scenario, bears) == FIVE_COLORS
    assert "Hexproof from red" in _abilities(scenario, bears)
    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof from red"):
        casting.choose_targets([bears])


def test_all_colors_ends_at_cleanup():
    scenario, tam = _tam()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(tam, index=0, targets=[bears])
    scenario.resolve_top()

    _end_the_turn(scenario)

    assert _colors(scenario, bears) == {Color.GREEN}
    assert "Hexproof from red" not in _abilities(scenario, bears)


def test_the_controllers_own_spell_can_target_it():
    """CR 702.11d: "your opponents" - alice's own red spell still targets
    her all-colour Bears."""
    scenario, tam = _tam(bob_hand=())
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(tam, index=0, targets=[bears])
    scenario.resolve_top()

    refusal = scenario.game.hexproof_refusal(bears, "alice", bears)
    assert refusal is None


def test_when_tam_leaves_the_hexproof_goes():
    scenario, tam = _tam()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(tam)

    assert "Hexproof from green" not in _abilities(scenario, bears)


# --------------------------------------------------------------------------
# Second printings
# --------------------------------------------------------------------------


def test_scrapbasket_becomes_all_colors_until_end_of_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Scrapbasket", "Island"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    basket = scenario.creature("Scrapbasket", "alice")

    scenario.activate(basket, *scenario.untapped_sources("Island"))
    scenario.resolve_top()

    assert _colors(scenario, basket) == FIVE_COLORS
    _end_the_turn(scenario)
    assert _colors(scenario, basket) == set()


def test_distorting_lens_still_reads_through_the_widened_chosen_color_reader():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Distorting Lens"], library=["Island"] * 5)
        .player("bob", battlefield=["Sol Ring"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lens = scenario.find("Distorting Lens", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.will_choose(Color.GREEN.value, username="alice")

    scenario.activate(lens, targets=[ring])
    scenario.resolve_top()

    assert _colors(scenario, ring) == {Color.GREEN}
    _end_the_turn(scenario)
    assert _colors(scenario, ring) == set()


def test_breaker_of_creation_has_hexproof_from_each_color():
    """CR 702.11g: "hexproof from each color" is one per colour - bob's red
    Lightning Bolt cannot target it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Breaker of Creation"], library=["Island"] * 5)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    breaker = scenario.creature("Breaker of Creation", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof from"):
        casting.choose_targets([breaker])


def test_breaker_of_creations_cast_trigger_counts_colorless_permanents():
    """ "You gain 1 life for each colorless permanent you control" (CR
    105.2c): six Islands, Sol Ring and Ornithopter are eight - the spell
    itself is still on the stack, not a permanent."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Breaker of Creation"],
            battlefield=["Island"] * 6 + ["Sol Ring", "Ornithopter", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life = scenario.player("alice").life

    scenario.cast_onto_stack(
        "Breaker of Creation", *scenario.untapped_sources(*["Island"] * 6, "Sol Ring")
    )
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.player("alice").life == life + 8


@pytest.mark.parametrize("name", [PUCA, GROWTH, TAM, "Scrapbasket", "Breaker of Creation"])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail

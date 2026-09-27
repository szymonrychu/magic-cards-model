"""Cards gated on the comparison between a player's current life total and
their own starting life total (CR 103.4/119.1), one clause per test rather
than a single card-shaped test each - the mechanic, not the card, is what is
under test.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 103.4** - "Each player begins the game with a starting life total of
  20." - `Player.starting_life`, never assumed to be 20 by a reader (it is
  not, in a Two-Headed Giant/Vanguard/Commander/Brawl game), but every board
  here is an ordinary two-player game, so 20 is what every threshold below is
  measured against.
- **CR 119.3** - "If an effect causes a player to gain life or lose life,
  that player's life total is adjusted accordingly."
- **CR 606.2** - a loyalty ability is an activated ability with a loyalty
  symbol in its cost (Ajani, Strength of the Pride's own "0:").
- **CR 608.2f** - simultaneous actions on multiple objects, one instruction
  (Ajani's own self-exile and group sweep together).
- **CR 608.2c** - later text on a card may modify the meaning of earlier
  text; an "if" leading a loyalty ability's own effect is read the same
  plain-conditional way.
- **CR 508.1a** - declaring attackers; **CR 508.5** - the defending player an
  attacking creature's own ability refers to; **CR 500.7** - extra turns/
  combats, why "attacked this turn" has to be a per-creature record rather
  than a single "who did you attack" fact.
- **CR 104.3e** - "An effect may state that a player loses the game."
- **CR 120.2a** - combat damage, dealt during the combat damage step.
- **CR 122.1f** is not this file's concern; CR 613.4c (sublayer 7c pumps) and
  CR 613.1f (layer 6 grants) are, for the self- and group-static clauses.
- **CR 602.2b** - activating an ability follows the same process as casting a
  spell, which is why "Activate only if ..." is checked before the ability
  ever goes on the stack.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- Ajani, Strength of the Pride: the 0 loyalty ability ---------------------


def test_ajanis_zero_ability_clause_is_handled() -> None:
    (clause,) = [
        c for c in classify_clauses(card("Ajani, Strength of the Pride")) if c.text.startswith("0:")
    ]
    assert clause.category == HANDLED


def _ajani_board(alice_life: int) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Ajani, Strength of the Pride", "Grizzly Bears", "Mishra's Bauble"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Mishra's Bauble", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(scenario.player("alice"), alice_life - 20)
    ajani = scenario.creature("Ajani, Strength of the Pride", "alice")
    return scenario, ajani


def test_at_15_over_starting_it_exiles_itself_and_only_the_opponents_artifact_and_creature() -> (
    None
):
    """Alice starts at 20 (CR 103.4) and gains 15, landing exactly on "at
    least 15 life more than your starting life total". Bob's Plains is
    neither an artifact nor a creature and stays; alice's own Grizzly Bears
    and Mishra's Bauble are hers, not her opponents', and stay too."""
    scenario, ajani = _ajani_board(35)

    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert ajani.zone is Zone.EXILE
    assert scenario.find("Grizzly Bears", Zone.EXILE, "bob").zone is Zone.EXILE
    assert scenario.find("Mishra's Bauble", Zone.EXILE, "bob").zone is Zone.EXILE
    assert scenario.find("Plains", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_one_life_short_of_the_threshold_the_ability_does_nothing() -> None:
    """CR 606.2's loyalty ability is still legal to activate at any loyalty
    total that pays its cost - "0" costs nothing - but the intervening "if"
    inside its own effect (CR 608.2c) is a plain conditional instruction, not
    an activation restriction, so the ability still resolves and simply does
    nothing when it is false."""
    scenario, ajani = _ajani_board(34)

    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert ajani.zone is Zone.BATTLEFIELD
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD
    assert scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


# -- Angel of Destiny ---------------------------------------------------------


def test_angel_of_destinys_two_clauses_are_handled() -> None:
    clauses = classify_clauses(card("Angel of Destiny"))
    combat_damage_clause = next(c for c in clauses if c.text.startswith("Whenever a creature"))
    end_step_clause = next(c for c in clauses if c.text.startswith("At the beginning"))
    assert combat_damage_clause.category == HANDLED
    assert end_step_clause.category == HANDLED


def _drain_stack(scenario: Scenario) -> None:
    """Resolve everything currently on the stack - double strike (CR 702.4b,
    CR 510.4) puts one "deals combat damage to a player" trigger on the stack
    per damage instance, so a single `pass_until_resolved` is one instance
    short."""
    while scenario.stack_names():
        scenario.resolve_top()


def test_combat_damage_gains_both_players_life_equal_to_the_damage() -> None:
    """ "Whenever a creature you control deals combat damage to a player, you
    and that player each gain that much life." Flying, double strike (CR
    702.4b) deals the Angel's printed power (2) twice, so the total damage
    is 4 and the total lifegain from both triggers is 4 on each side."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Angel of Destiny"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Angel of Destiny", "alice")
    angel.summoning_sick = False
    scenario.attack_with(angel)
    scenario.no_blocks()
    scenario.combat_damage()
    _drain_stack(scenario)

    assert scenario.player("bob").life == 20 - 4 + 4
    assert scenario.player("alice").life == 20 + 4


def test_end_step_the_attacked_player_loses_at_15_over_starting() -> None:
    """CR 508.1a/CR 508.5: the player this creature attacked this turn - not
    merely "an opponent" - loses the game (CR 104.3e) once the controller's
    life stands 15 or more above their own CR 103.4 starting total."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Angel of Destiny"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Angel of Destiny", "alice")
    angel.summoning_sick = False
    scenario.attack_with(angel)
    scenario.no_blocks()
    scenario.combat_damage()
    _drain_stack(scenario)  # both double-strike lifegain triggers
    scenario.player("alice").life = 35

    for _ in range(5):  # declare blockers, damage, end of combat, main, end step
        scenario.advance()
        _drain_stack(scenario)
    assert scenario.step is Step.END_STEP

    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


def test_end_step_below_the_threshold_nobody_loses() -> None:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Angel of Destiny"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Angel of Destiny", "alice")
    angel.summoning_sick = False
    scenario.attack_with(angel)
    scenario.no_blocks()
    scenario.combat_damage()
    _drain_stack(scenario)

    for _ in range(5):
        scenario.advance()
        _drain_stack(scenario)
    assert scenario.step is Step.END_STEP

    assert scenario.game.is_in_game("bob")
    assert scenario.game.winner is None


def test_end_step_a_creature_that_did_not_attack_costs_nobody_the_game() -> None:
    """Even at 15 over starting, "each player this creature attacked this
    turn" is empty when the Angel never attacked - CR 508.1a's per-creature,
    per-turn record (`Game.attacked_players_this_turn`), not "each opponent"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Angel of Destiny"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").life = 35

    for _ in range(6):  # begin combat, attackers, blockers, damage, end of combat, main
        scenario.advance()
        _drain_stack(scenario)
    scenario.advance()  # end step
    _drain_stack(scenario)
    assert scenario.step is Step.END_STEP

    assert scenario.game.is_in_game("bob")
    assert scenario.game.winner is None


# -- Ayli, Eternal Pilgrim ----------------------------------------------------


def test_aylis_two_clauses_are_handled() -> None:
    clauses = classify_clauses(card("Ayli, Eternal Pilgrim"))
    sac_for_life = next(c for c in clauses if "gain life equal to" in c.text)
    exile_ability = next(c for c in clauses if "Exile target nonland" in c.text)
    assert sac_for_life.category == HANDLED
    assert exile_ability.category == HANDLED


def test_sacrificing_a_creature_gains_life_equal_to_its_toughness() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Ayli, Eternal Pilgrim", "Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ayli = scenario.creature("Ayli, Eternal Pilgrim", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(ayli, index=0, sacrificing=[bears], auto=True)
    scenario.resolve_top()

    assert scenario.player("alice").life == 22, "Grizzly Bears is a 2/2 (CR 208.1's toughness)"
    assert bears.zone is Zone.GRAVEYARD


def test_the_exile_ability_needs_10_life_more_than_starting_to_activate() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Ayli, Eternal Pilgrim", "Grizzly Bears", "Plains", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ayli = scenario.creature("Ayli, Eternal Pilgrim", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.why_cannot_activate(ayli, index=1) is not None

    scenario.game.gain_life(scenario.player("alice"), 10)
    assert scenario.why_cannot_activate(ayli, index=1) is None

    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "bob")
    scenario.activate(ayli, index=1, sacrificing=[bears], targets=[bauble], auto=True)
    scenario.resolve_top()

    assert bauble.zone is Zone.EXILE


def test_temple_of_aclazotzs_own_printing_of_the_same_sacrifice_ability_is_handled() -> None:
    """Generality proof, not the reported card: Arguel's Blood Fast //
    Temple of Aclazotz's own back face prints the identical "You gain life
    equal to the sacrificed creature's toughness." off a different cost
    shape - "{T}, Sacrifice a creature:" rather than Ayli's "{1}, Sacrifice
    another creature:" - which the same `_GAIN_LIFE_EQUAL_TO_SACRIFICED_
    CREATURE_RE` reads regardless."""
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Arguel's Blood Fast", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    front = scenario.creature("Arguel's Blood Fast", "alice")
    temple = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(front), "alice", transformed=True
    )
    assert temple.name == "Temple of Aclazotz"
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(temple, index=1, sacrificing=[bears])
    scenario.resolve_top()

    assert scenario.player("alice").life == 22
    assert bears.zone is Zone.GRAVEYARD


# -- Elenda, Saint of Dusk -----------------------------------------------------


def test_elendas_static_clause_is_handled() -> None:
    (clause,) = classify_clauses(card("Elenda, Saint of Dusk"))
    assert clause.category == HANDLED


def _elenda(life: int) -> tuple[Scenario, object]:
    scenario = Scenario().player("alice", life=20, battlefield=["Elenda, Saint of Dusk"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(scenario.player("alice"), life - 20)
    elenda = scenario.creature("Elenda, Saint of Dusk", "alice")
    return scenario, elenda


def _pt_and_menace(scenario: Scenario, elenda) -> tuple[int, int, bool]:
    chars = scenario.game.characteristics_of(elenda)
    return chars.power, chars.toughness, "Menace" in chars.abilities


def test_at_starting_life_elenda_is_unpumped() -> None:
    scenario, elenda = _elenda(20)
    assert _pt_and_menace(scenario, elenda) == (4, 4, False)


def test_above_starting_life_elenda_gets_plus_one_plus_one_and_menace() -> None:
    scenario, elenda = _elenda(21)
    assert _pt_and_menace(scenario, elenda) == (5, 5, True)


def test_at_least_10_over_starting_elenda_gets_the_additional_plus_five_plus_five_too() -> None:
    """CR 613.4c's sublayer 7c applies both of Elenda's own pumps
    independently: +1/+1 for being above starting life at all, plus another
    +5/+5 once the gap is 10 or more, both active at once at 30."""
    scenario, elenda = _elenda(30)
    assert _pt_and_menace(scenario, elenda) == (10, 10, True)


def test_9_over_starting_only_the_first_pump_applies() -> None:
    scenario, elenda = _elenda(29)
    assert _pt_and_menace(scenario, elenda) == (5, 5, True)


# -- Leyline of Hope -----------------------------------------------------------


def test_leyline_of_hopes_starting_life_clause_is_handled() -> None:
    (clause,) = [
        c for c in classify_clauses(card("Leyline of Hope")) if c.text.startswith("As long as")
    ]
    assert clause.category == HANDLED


def test_at_7_over_starting_creatures_you_control_get_plus_two_plus_two() -> None:
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Leyline of Hope", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Set the life total directly rather than through `Game.gain_life`:
    # Leyline of Hope's own second static ("If you would gain life, you gain
    # that much life plus 1 instead.") is a live replacement effect that
    # would add its own +1 on top of any amount gained here, one clause of
    # this same card interfering with isolating the other for this test.
    scenario.player("alice").life = 27
    bears = scenario.creature("Grizzly Bears", "alice")

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (4, 4)


def test_6_over_starting_creatures_are_unpumped() -> None:
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Leyline of Hope", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").life = 26
    bears = scenario.creature("Grizzly Bears", "alice")

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (2, 2)


# -- Righteous Valkyrie --------------------------------------------------------


def test_righteous_valkyries_two_clauses_are_handled() -> None:
    clauses = classify_clauses(card("Righteous Valkyrie"))
    trigger = next(c for c in clauses if c.text.startswith("Whenever another"))
    static = next(c for c in clauses if c.text.startswith("As long as"))
    assert trigger.category == HANDLED
    assert static.category == HANDLED


def test_another_angel_or_cleric_entering_gains_life_equal_to_its_toughness() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Righteous Valkyrie"],
            hand=["Speaker of the Heavens"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Speaker of the Heavens", "alice")
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21, "Speaker of the Heavens is a 1/1"


def test_righteous_valkyrie_pumps_creatures_at_7_over_starting() -> None:
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Righteous Valkyrie", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(scenario.player("alice"), 7)
    bears = scenario.creature("Grizzly Bears", "alice")

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (4, 4)

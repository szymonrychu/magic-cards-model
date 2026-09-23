""" "The Nth time this ability has resolved this turn", with several branches.

The template: "<effect> if this is the first time this ability has resolved
this turn. If it's the second time, <effect>. If it's the third time,
<effect>." - Omnath, Locus of Creation; Belladonna Took; Vito, Fanatic of
Aclazotz. The count is `Game.ability_resolutions_this_turn`, which already
includes the resolution in progress; exactly one branch (or none, from the
fourth resolution on) applies on each resolution.

- **CR 603.4** - the "if" is not an intervening "if": it does not immediately
  follow the trigger condition, so the ability always triggers and goes on
  the stack, and the "if" is read only as it resolves.
- **CR 400.7** - a permanent that changes zones is a new object with no
  memory of its previous existence, so its count starts over.
- **CR 701.6a** - a countered ability does not resolve, so it does not count.
- **CR 608.2b** - an ability whose every target has become illegal does not
  resolve, so it does not count either.
- **CR 605.1a / 605.1b** - a triggered ability that triggers on a land
  entering (and an activated ability with a target) is not a mana ability,
  even though it adds mana: it uses the stack. **CR 106.4** - the mana goes
  into its controller's mana pool.
- **CR 119.2 / 306.8** - damage to a player is life loss; damage to a
  planeswalker removes that many loyalty counters.
- **CR 109.5** - "you" is the ability's controller, so "each planeswalker you
  don't control" spares that player's own.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenState, create_predefined_tokens
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# --------------------------------------------------------------------------
# Omnath, Locus of Creation
# --------------------------------------------------------------------------


def _omnath_board(*, alice_battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Omnath, Locus of Creation"] + ["Forest"] * 6,
            battlefield=list(alice_battlefield),
            library=["Island"] * 10,
        )
        .player(
            "bob",
            hand=["Consign to Memory"],
            battlefield=["Island", *bob_battlefield],
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    omnath = scenario.put_onto_battlefield("Omnath, Locus of Creation", "alice")
    _resolve_stack(scenario)  # "When Omnath enters, draw a card."
    return scenario, omnath


def _landfall(scenario) -> None:
    scenario.put_onto_battlefield("Forest", "alice")
    _resolve_stack(scenario)


def _floating(scenario, username: str = "alice") -> dict:
    return {color: n for color, n in scenario.player(username).mana_pool.floating.items() if n}


def test_omnath_enters_and_draws_a_card():
    scenario, _omnath = _omnath_board()
    # Six Forests and the drawn Island.
    assert len(scenario.player("alice").hand) == 7


def test_omnath_first_landfall_gains_four_life_and_nothing_else():
    scenario, _omnath = _omnath_board()
    _landfall(scenario)
    assert scenario.player("alice").life == 24
    assert scenario.player("bob").life == 20
    assert _floating(scenario) == {}


def test_omnath_second_landfall_adds_rgwu_and_gains_no_life():
    scenario, _omnath = _omnath_board()
    _landfall(scenario)
    _landfall(scenario)
    assert scenario.player("alice").life == 24
    assert _floating(scenario) == {Color.RED: 1, Color.GREEN: 1, Color.WHITE: 1, Color.BLUE: 1}


def test_omnath_mana_trigger_uses_the_stack():
    """CR 605.1b: it triggers on a land entering, not on a mana ability, so
    it is not a mana ability - it goes on the stack and adds nothing until it
    resolves."""
    scenario, _omnath = _omnath_board()
    _landfall(scenario)
    scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    assert _floating(scenario) == {}
    scenario.resolve_top()
    assert _floating(scenario) == {Color.RED: 1, Color.GREEN: 1, Color.WHITE: 1, Color.BLUE: 1}


def test_omnath_third_landfall_hits_each_opponent_and_their_planeswalker():
    """ "Omnath deals 4 damage to each opponent and each planeswalker you
    don't control." Bob takes 4 and his Jace loses 4 loyalty (CR 306.8) -
    enough to put it into the graveyard; alice's own Jace, her life and her
    creatures are untouched."""
    scenario, omnath = _omnath_board(
        alice_battlefield=["Jace Beleren", "Grizzly Bears"],
        bob_battlefield=["Jace Beleren", "Grizzly Bears"],
    )
    alices_jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    bobs_jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    alices_loyalty = alices_jace.counters[Counter.LOYALTY]
    for _ in range(3):
        _landfall(scenario)

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 24, "only the first landfall gained life"
    assert bobs_jace.zone is Zone.GRAVEYARD
    assert alices_jace.zone is Zone.BATTLEFIELD
    assert alices_jace.counters[Counter.LOYALTY] == alices_loyalty
    assert scenario.creature("Grizzly Bears", "bob").damage == 0
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert omnath.damage == 0


def test_omnath_third_landfall_damages_a_surviving_planeswalker():
    """A planeswalker with more loyalty than the damage stays, 4 counters
    lighter."""
    scenario, _omnath = _omnath_board(bob_battlefield=["Jace Beleren"])
    bobs_jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    bobs_jace.add_counters(Counter.LOYALTY, 6 - bobs_jace.counters[Counter.LOYALTY])
    for _ in range(3):
        _landfall(scenario)
    assert bobs_jace.zone is Zone.BATTLEFIELD
    assert bobs_jace.counters[Counter.LOYALTY] == 2


def test_omnath_fourth_landfall_does_nothing():
    scenario, _omnath = _omnath_board()
    for _ in range(3):
        _landfall(scenario)
    scenario.player("alice").mana_pool.empty()
    _landfall(scenario)
    assert scenario.player("alice").life == 24
    assert scenario.player("bob").life == 16
    assert _floating(scenario) == {}


def test_omnath_count_resets_on_a_new_turn():
    """Two resolutions this turn and one the next is a first time again."""
    scenario, _omnath = _omnath_board()
    _landfall(scenario)
    _landfall(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    _landfall(scenario)
    assert scenario.player("alice").life == 28
    assert _floating(scenario) == {}


def test_omnath_that_left_and_came_back_is_a_new_object():
    """CR 400.7: the Omnath that returns has no memory of the old one's
    resolutions - its first landfall this turn gains 4 life again."""
    scenario, omnath = _omnath_board()
    _landfall(scenario)
    _landfall(scenario)
    scenario.player("alice").mana_pool.empty()
    scenario.game.return_to_hand(omnath)
    scenario.put_onto_battlefield("Omnath, Locus of Creation", "alice")
    _resolve_stack(scenario)
    _landfall(scenario)
    assert scenario.player("alice").life == 28
    assert _floating(scenario) == {}


def test_two_omnaths_count_apart():
    """The count is this ability's, on this object: a second Omnath's first
    landfall is a first time even though the first Omnath's has resolved."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"] * 3,
            battlefield=["Omnath, Locus of Creation", "Omnath, Locus of Creation"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _landfall(scenario)
    # Both triggered once; each is its own first time.
    assert scenario.player("alice").life == 28
    assert _floating(scenario) == {}


def test_a_countered_omnath_trigger_does_not_count():
    """CR 701.6a: Consign to Memory counters the first trigger, which never
    resolves - the next landfall is still the first time."""
    scenario, _omnath = _omnath_board()
    scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()
    trigger = scenario.game.stack[-1]
    scenario.pass_priority("alice")
    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.cast_and_resolve("Consign to Memory", island, username="bob", targets=[trigger])
    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20

    _landfall(scenario)
    assert scenario.player("alice").life == 24
    assert _floating(scenario) == {}


# --------------------------------------------------------------------------
# Belladonna Took
# --------------------------------------------------------------------------


def _belladonna_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Belladonna Took", "Grizzly Bears"],
            library=["Island"] * 10,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _token(scenario, username: str = "alice") -> None:
    create_predefined_tokens(scenario.game, "Treasure", username)
    _resolve_stack(scenario)


def test_belladonna_first_token_gains_one_life():
    scenario = _belladonna_board()
    hand = len(scenario.player("alice").hand)
    _token(scenario)
    assert scenario.player("alice").life == 21
    assert len(scenario.player("alice").hand) == hand


def test_belladonna_second_token_draws_a_card():
    scenario = _belladonna_board()
    hand = len(scenario.player("alice").hand)
    _token(scenario)
    _token(scenario)
    assert scenario.player("alice").life == 21
    assert len(scenario.player("alice").hand) == hand + 1


def test_belladonna_third_token_puts_a_counter_on_each_creature_you_control():
    scenario = _belladonna_board()
    for _ in range(3):
        _token(scenario)
    belladonna = scenario.creature("Belladonna Took", "alice")
    assert belladonna.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.creature("Grizzly Bears", "alice").counter_count(Counter.PLUS_ONE) == 1
    assert scenario.creature("Grizzly Bears", "bob").counter_count(Counter.PLUS_ONE) == 0


def test_belladonna_fourth_token_does_nothing():
    scenario = _belladonna_board()
    for _ in range(3):
        _token(scenario)
    hand = len(scenario.player("alice").hand)
    _token(scenario)
    assert scenario.player("alice").life == 21
    assert len(scenario.player("alice").hand) == hand
    belladonna = scenario.creature("Belladonna Took", "alice")
    assert belladonna.counter_count(Counter.PLUS_ONE) == 1


def test_an_opponents_token_does_not_trigger_belladonna():
    scenario = _belladonna_board()
    _token(scenario, "bob")
    _token(scenario)
    assert scenario.player("alice").life == 21, "alice's own token was the first resolution"


# --------------------------------------------------------------------------
# Vito, Fanatic of Aclazotz - the same template on a card outside the task
# --------------------------------------------------------------------------


def _vito_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Vito, Fanatic of Aclazotz"] + ["Memnite"] * 4,
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _sacrifice_a_memnite(scenario) -> None:
    memnite = next(p for p in scenario.game.battlefield if p.name == "Memnite")
    scenario.game.sacrifice(memnite)
    _resolve_stack(scenario)


def _vampire_demons(scenario) -> list:
    return [p for p in scenario.game.battlefield if isinstance(p, TokenState) and "Demon" in p.name]


def test_vito_branches_run_once_each_in_order():
    """ "Whenever you sacrifice another permanent, you gain 2 life if this is
    the first time this ability has resolved this turn. If it's the second
    time, each opponent loses 2 life. If it's the third time, create a 4/3
    white and black Vampire Demon creature token with flying." """
    scenario = _vito_board()
    _sacrifice_a_memnite(scenario)
    assert (scenario.player("alice").life, scenario.player("bob").life) == (22, 20)
    assert _vampire_demons(scenario) == []

    _sacrifice_a_memnite(scenario)
    assert (scenario.player("alice").life, scenario.player("bob").life) == (22, 18)
    assert _vampire_demons(scenario) == []

    _sacrifice_a_memnite(scenario)
    assert (scenario.player("alice").life, scenario.player("bob").life) == (22, 18)
    (demon,) = _vampire_demons(scenario)
    board = scenario.game.computed_board().of(demon)
    assert (board.power, board.toughness) == (4, 3)

    _sacrifice_a_memnite(scenario)
    assert (scenario.player("alice").life, scenario.player("bob").life) == (22, 18)
    assert len(_vampire_demons(scenario)) == 1


# --------------------------------------------------------------------------
# Soulbright Seeker - a targeted, mana-adding activated ability, and a
# fizzled resolution that does not count
# --------------------------------------------------------------------------


def _seeker_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Soulbright Seeker", "Grizzly Bears", "Memnite"] + ["Mountain"] * 5,
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_seeker(scenario, target) -> None:
    seeker = scenario.creature("Soulbright Seeker", "alice")
    mountain = scenario.untapped_sources("Mountain", username="alice")[0]
    scenario.activate(seeker, mountain, targets=[target])


def test_seeker_third_resolution_adds_rrrr():
    """ "{R}: Target creature you control gains trample until end of turn. If
    this is the third time this ability has resolved this turn, add
    {R}{R}{R}{R}." - a targeted ability, so not a mana ability (CR 605.1a);
    it resolves off the stack and the mana lands in the pool (CR 106.4)."""
    scenario = _seeker_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    for _ in range(2):
        _activate_seeker(scenario, bears)
        scenario.resolve_top()
    assert _floating(scenario) == {}
    _activate_seeker(scenario, bears)
    scenario.resolve_top()
    assert _floating(scenario) == {Color.RED: 4}


def test_a_fizzled_seeker_activation_does_not_count():
    """CR 608.2b: the second activation's only target is gone when it would
    resolve, so it does not resolve and is not counted - the third activation
    is only the second resolution, and the fourth is the third."""
    scenario = _seeker_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    _activate_seeker(scenario, bears)
    scenario.resolve_top()
    _activate_seeker(scenario, memnite)
    scenario.game.sacrifice(memnite)
    scenario.resolve_top()
    assert scenario.stack_names() == []

    _activate_seeker(scenario, bears)
    scenario.resolve_top()
    assert _floating(scenario) == {}

    _activate_seeker(scenario, bears)
    scenario.resolve_top()
    assert _floating(scenario) == {Color.RED: 4}


# --------------------------------------------------------------------------
# "each <type> you don't control" - Artistic Process, the same controller
# group Omnath's "each planeswalker you don't control" reads
# --------------------------------------------------------------------------


def _artistic_process(mode: int, *, bob_battlefield=("Grizzly Bears", "Memnite")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Artistic Process"],
            battlefield=["Grizzly Bears"] + ["Mountain"] * 5,
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Artistic Process")
    casting.choose_modes([mode])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()
    return scenario


def test_artistic_process_damages_only_creatures_you_dont_control():
    """ "Artistic Process deals 2 damage to each creature you don't control."
    Bob's creatures are dealt 2 and die; alice's own Bears is untouched, and
    no player is dealt damage."""
    scenario = _artistic_process(2)
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Memnite", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert (scenario.player("alice").life, scenario.player("bob").life) == (20, 20)


def test_artistic_process_you_dont_control_skips_planeswalkers():
    """The group is "creature": bob's Jace, a planeswalker he controls, is
    not a creature and keeps all its loyalty."""
    scenario = _artistic_process(2, bob_battlefield=("Jace Beleren",))
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    assert jace.counters[Counter.LOYALTY] == 3


def test_artistic_process_two_colour_token_is_one_clause():
    """ "Create a 3/3 blue and red Elemental creature token with flying. It
    gains haste until end of turn." - "blue and red" is one colour phrase
    (CR 105.1's colour words), not two instructions: one 3/3 flier that is
    both blue and red, with haste."""
    scenario = _artistic_process(3)
    (elemental,) = [
        p for p in scenario.game.battlefield if isinstance(p, TokenState) and "Elemental" in p.name
    ]
    board = scenario.game.computed_board().of(elemental)
    assert (board.power, board.toughness) == (3, 3)
    assert set(board.colors) == {Color.BLUE, Color.RED}
    assert has_keyword(elemental, "flying", scenario.game)
    assert has_keyword(elemental, "haste", scenario.game)

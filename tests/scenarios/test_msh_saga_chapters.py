"""Scenario: the chapter abilities of Marvel Super Heroes' Sagas.

A chapter ability is CR 714.2b's "When one or more lore counters are put onto
this Saga, if the number of lore counters on it was less than N and became at
least N, [effect]" - the trigger was already read; what is new here is each
chapter's *effect*, read off the printed text by the ordinary clause readers
so any card with the same words gets it. Oracle text from the Scryfall
printings in `data/printings`.

- **Armor Wars** - I "You may draw a card for each artifact you control. If
  you do, each opponent draws a card." / II "Artifact spells you cast this
  turn cost {1} less to cast." / III "This Saga deals X damage to target
  opponent, where X is the greatest mana value among artifacts you control."
- **Avengers: Under Siege** - II "This Saga deals 2 damage to each non-Villain
  creature and each opponent." / III "Create a Treasure token for each
  Villain you control."
- **Origin of the Avengers** - II "You may put a Hero creature card with mana
  value 3 or less from your hand onto the battlefield. If you don't, draw a
  card."
- **World War Hulk** - I "The next red or green creature spell you cast this
  turn can be cast without paying its mana cost." / III "Choose target
  creature you control. Until end of turn, double its power and toughness
  and it gains trample."

Off-msh proofs, each legal in Modern (and Pioneer where noted), none in an api
deck list:

- **Master of the Feast** (Pioneer) - "At the beginning of your upkeep, each
  opponent draws a card." - the each-opponent draw.
- **Ballad of the Black Flag** - IV "Historic spells you cast this turn cost
  {2} less to cast." - the this-turn spell discount (CR 700.6's historic);
  I-III "Mill three cards. You may put a historic card from among them into
  your hand." - historic read as a card group.
- **One with the Machine** (Pioneer) - "Draw cards equal to the greatest mana
  value among artifacts you control." - the greatest-mana-value amount.
- **Archangel Avacyn // Avacyn, the Purifier** (already in the pool) - "it
  deals 3 damage to each other creature and each opponent." - the same
  reader with "other" and no exclusion, still read after the widening.
- **Warren Instigator** - "you may put a Goblin creature card from your hand
  onto the battlefield." - the put-from-hand description (a subtype and a
  type); the mana value cap and "If you don't" are msh-only.
- **Grunn, the Lonely King** (Pioneer) - "Whenever Grunn attacks alone,
  double its power and toughness until end of turn." - doubling (CR 701.10).

The "non-`<Subtype>`" exclusion, the "If you don't" rider on a put-from-hand
and the "next ... spell ... can be cast without paying its mana cost"
permission are printed only on msh cards (MEMORY.md, 2026-09-24).

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 714.2b, CR 714.3a, CR 118.9, CR 601.2f, CR 601.2i, CR 700.6, CR 202.3,
CR 107.2, CR 120.2, CR 613.4c, CR 701.10a, CR 701.10b, CR 506.5, CR 110.2a,
CR 121.2c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _next_chapter(scenario, saga) -> None:
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)


def _enter(scenario, name: str, username: str = "alice"):
    saga = scenario.put_onto_battlefield(name, username)
    _resolve_everything(scenario)
    return saga


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _cost_of(scenario, name: str, username: str = "alice") -> ManaCost:
    """The total mana cost announcing `name` would come to (CR 601.2f), the
    announcement then rewound (CR 733.1) so nothing was cast."""
    casting = scenario.cast(name, username=username)
    cost = casting.total_cost.mana
    casting.cancel()
    return cost


# -- Armor Wars --------------------------------------------------------------


def _armor_board(*extra: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Armor Wars", "Mind Stone", "Grizzly Bears"],
            battlefield=["Sol Ring", "Memnite", "Forest", "Forest", *extra],
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_armor_wars_one_draws_per_artifact_and_each_opponent_draws_one():
    scenario = _armor_board()
    alice, bob = scenario.player("alice"), scenario.player("bob")
    hand, bob_hand = len(alice.hand), len(bob.hand)
    scenario.will_take_the_may(True)

    _enter(scenario, "Armor Wars")

    assert len(alice.hand) == hand - 1 + 2  # Armor Wars left; two artifacts
    assert len(bob.hand) == bob_hand + 1


def test_armor_wars_one_declined_draws_nobody_anything():
    scenario = _armor_board()
    alice, bob = scenario.player("alice"), scenario.player("bob")
    hand, bob_hand = len(alice.hand), len(bob.hand)
    scenario.will_take_the_may(False)

    _enter(scenario, "Armor Wars")

    assert len(alice.hand) == hand - 1
    assert len(bob.hand) == bob_hand


def test_off_msh_master_of_the_feast_makes_each_opponent_draw():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of the Feast"], library=["Swamp"] * 4)
        .player("bob", library=["Island"] * 4)
        .player("carol", library=["Island"] * 4)
        .build()
    )
    scenario.advance()  # untap -> upkeep: "at the beginning of your upkeep"
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 0
    assert len(scenario.player("bob").hand) == 1
    assert len(scenario.player("carol").hand) == 1


def test_armor_wars_two_makes_artifact_spells_cost_one_less_this_turn():
    scenario = _armor_board()
    scenario.will_take_the_may(False)
    saga = _enter(scenario, "Armor Wars")

    _next_chapter(scenario, saga)

    assert _cost_of(scenario, "Mind Stone") == ManaCost.parse("{1}")
    assert _cost_of(scenario, "Grizzly Bears") == ManaCost.parse("{1}{G}")


def test_armor_wars_two_is_gone_next_turn():
    scenario = _armor_board()
    scenario.will_take_the_may(False)
    saga = _enter(scenario, "Armor Wars")
    _next_chapter(scenario, saga)

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.turn.active_player == "alice"
    assert _cost_of(scenario, "Mind Stone") == ManaCost.parse("{2}")


def test_armor_wars_two_does_not_discount_an_opponents_artifact():
    scenario = (
        Scenario()
        .player("alice", hand=["Armor Wars"], library=["Island"] * 6)
        .player("bob", hand=["Mind Stone"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)
    saga = _enter(scenario, "Armor Wars")
    _next_chapter(scenario, saga)
    mind_stone = scenario.find("Mind Stone", Zone.HAND, "bob")

    _increases, decreases, _floor = scenario.game.static_cost_modifiers_for(mind_stone, "bob")

    assert decreases == []


def test_off_msh_ballad_four_discounts_historic_spells_by_two():
    """CR 700.6: legendary, artifact, or Saga. A plain creature is not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Stone", "Grunn, the Lonely King", "Grizzly Bears"],
            battlefield=["Ballad of the Black Flag"],
            library=["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballad = scenario.find("Ballad of the Black Flag", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, times=None)
    scenario.game.add_counters(ballad, Counter.LORE, 4)
    _resolve_everything(scenario)

    assert _cost_of(scenario, "Mind Stone") == ManaCost()
    assert _cost_of(scenario, "Grunn, the Lonely King") == ManaCost.parse("{2}{G}{G}")
    assert _cost_of(scenario, "Grizzly Bears") == ManaCost.parse("{1}{G}")


def test_armor_wars_three_deals_the_greatest_artifact_mana_value_to_target_opponent():
    """Sol Ring (1), Memnite (0), Mind Stone would be 2 - here Sol Ring and a
    Solemn Simulacrum (4) make X four."""
    scenario = _armor_board("Solemn Simulacrum")
    scenario.will_take_the_may(False)
    saga = _enter(scenario, "Armor Wars")
    _next_chapter(scenario, saga)
    scenario.will_choose_targets("bob")

    _next_chapter(scenario, saga)

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 20


def test_armor_wars_three_with_no_artifacts_deals_nothing():
    """CR 107.2: the greatest among nothing is 0."""
    scenario = (
        Scenario()
        .player("alice", hand=["Armor Wars"], library=["Island"] * 6)
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)
    saga = _enter(scenario, "Armor Wars")
    _next_chapter(scenario, saga)
    scenario.will_choose_targets("bob")

    _next_chapter(scenario, saga)

    assert scenario.player("bob").life == 20


def test_off_msh_one_with_the_machine_draws_the_greatest_artifact_mana_value():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["One with the Machine"],
            battlefield=["Solemn Simulacrum", "Sol Ring", "Island", "Island", "Island", "Island"],
            library=["Island"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("One with the Machine", auto=True)

    assert len(scenario.player("alice").hand) == 4


# -- Avengers: Under Siege ---------------------------------------------------


def _siege_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Avengers: Under Siege"],
            battlefield=["Grizzly Bears"],
            library=["Island"] * 6,
        )
        .player("bob", battlefield=["Savannah Lions"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_under_siege_two_spares_villains_and_hits_each_opponent():
    scenario = _siege_board()
    saga = _enter(scenario, "Avengers: Under Siege")  # I: two 2/1 Villains
    villains = [p for p in scenario.game.battlefield if getattr(p, "token", False)]
    assert len(villains) == 2

    _next_chapter(scenario, saga)

    assert all(villain.zone is Zone.BATTLEFIELD for villain in villains)
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.find("Savannah Lions", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_under_siege_three_makes_a_treasure_per_villain():
    scenario = _siege_board()
    saga = _enter(scenario, "Avengers: Under Siege")
    _next_chapter(scenario, saga)

    _next_chapter(scenario, saga)

    treasures = [p for p in scenario.game.battlefield if "Treasure" in _chars(scenario, p).subtypes]
    assert len(treasures) == 2


def test_avacyn_the_purifier_still_spares_itself_and_hits_each_opponent():
    """The widened reader's original shape: "each other creature"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Archangel Avacyn // Avacyn, the Purifier", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Savannah Lions"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    avacyn = scenario.creature("Archangel Avacyn", "alice")

    from magic_cards_model.machines.effects import transform_permanent

    transform_permanent(scenario.game, avacyn)
    _resolve_everything(scenario)

    assert avacyn.zone is Zone.BATTLEFIELD
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.find("Savannah Lions", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


# -- Origin of the Avengers --------------------------------------------------


def _origin_board(*hand: str):
    scenario = (
        Scenario()
        .player("alice", hand=["Origin of the Avengers", *hand], library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_origin_two_puts_a_small_hero_onto_the_battlefield():
    scenario = _origin_board("Brave Brawler")
    saga = _enter(scenario, "Origin of the Avengers")
    brawler = scenario.find("Brave Brawler", Zone.HAND, "alice")
    hand = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True)

    _next_chapter(scenario, saga)

    assert brawler.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == hand - 1


def test_origin_two_declined_draws_a_card():
    scenario = _origin_board("Brave Brawler")
    saga = _enter(scenario, "Origin of the Avengers")
    hand = len(scenario.player("alice").hand)
    scenario.will_take_the_may(False)

    _next_chapter(scenario, saga)

    assert scenario.find("Brave Brawler", Zone.HAND, "alice").zone is Zone.HAND
    assert len(scenario.player("alice").hand) == hand + 1


def test_origin_two_with_no_small_hero_draws_a_card():
    """Photon, Mighty Marvel is a Hero with mana value 4, and Grizzly Bears is
    no Hero - nothing qualifies, so "if you don't" draws."""
    scenario = _origin_board("Photon, Mighty Marvel", "Grizzly Bears")
    saga = _enter(scenario, "Origin of the Avengers")
    hand = len(scenario.player("alice").hand)

    _next_chapter(scenario, saga)

    assert scenario.find("Photon, Mighty Marvel", Zone.HAND, "alice").zone is Zone.HAND
    assert len(scenario.player("alice").hand) == hand + 1


def test_off_msh_warren_instigator_puts_a_goblin_creature_from_hand():
    """Warren Instigator: "Whenever this creature deals damage to an opponent,
    you may put a Goblin creature card from your hand onto the battlefield." -
    the same put-from-hand reader, a subtype and a type, no cap."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Warren Instigator"],
            hand=["Goblin Guide", "Grizzly Bears"],
            library=["Mountain"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    instigator = scenario.creature("Warren Instigator", "alice")
    scenario.will_take_the_may(True)

    scenario.game.deal_damage(scenario.player("bob"), 1, source=instigator)
    _resolve_everything(scenario)

    assert scenario.find("Goblin Guide", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice").zone is Zone.HAND


def test_off_msh_warren_instigator_offers_nothing_but_goblins():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Warren Instigator"],
            hand=["Grizzly Bears"],
            library=["Mountain"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    instigator = scenario.creature("Warren Instigator", "alice")

    scenario.game.deal_damage(scenario.player("bob"), 1, source=instigator)
    _resolve_everything(scenario)

    assert scenario.find("Grizzly Bears", Zone.HAND, "alice").zone is Zone.HAND
    assert not [q for q in scenario.questions_asked() if "Goblin" in (q.prompt or "")]


def test_off_msh_ballad_one_takes_a_historic_card_from_the_milled_three():
    """Ballad of the Black Flag's I - "Mill three cards. You may put a
    historic card from among them into your hand." - CR 700.6's historic
    read as a card group (Sol Ring is an artifact, Grizzly Bears is not)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ballad of the Black Flag"],
            library=["Grizzly Bears", "Sol Ring", "Island", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True)

    _enter(scenario, "Ballad of the Black Flag")

    assert sol_ring.zone is Zone.HAND
    assert bears.zone is Zone.GRAVEYARD


# -- World War Hulk ----------------------------------------------------------


def _hulk_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["World War Hulk", "Grizzly Bears", "Savannah Lions", "Llanowar Elves"],
            battlefield=["Forest", "Plains"],
            library=["Forest"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_free(scenario, name: str):
    casting = scenario.cast(name)
    casting.use_alternative_cost("World War Hulk")
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def test_hulk_one_makes_the_next_green_creature_free():
    scenario = _hulk_board()
    _enter(scenario, "World War Hulk")

    bears = _cast_free(scenario, "Grizzly Bears")

    assert bears.zone is Zone.BATTLEFIELD
    assert all(not land.tapped for land in scenario.untapped_sources("Forest", "Plains"))


def test_hulk_one_is_used_up_by_the_first_red_or_green_creature():
    scenario = _hulk_board()
    _enter(scenario, "World War Hulk")
    _cast_free(scenario, "Grizzly Bears")

    options = scenario.cast("Llanowar Elves").alternative_costs

    assert not any(option.source_name == "World War Hulk" for option in options)


def test_hulk_one_ignores_a_white_creature_and_keeps_waiting():
    """Savannah Lions is white: not "the next red or green creature spell"."""
    scenario = _hulk_board()
    _enter(scenario, "World War Hulk")

    lions = scenario.cast("Savannah Lions")
    assert not any(option.source_name == "World War Hulk" for option in lions.alternative_costs)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.pay_with(lions.begin_paying(), plains)
    scenario.put_on_stack(lions)
    _resolve_everything(scenario)

    assert _cast_free(scenario, "Grizzly Bears").zone is Zone.BATTLEFIELD


def test_hulk_one_ends_with_the_turn():
    scenario = _hulk_board()
    _enter(scenario, "World War Hulk")

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    options = scenario.cast("Grizzly Bears").alternative_costs
    assert not any(option.source_name == "World War Hulk" for option in options)


def test_hulk_three_doubles_power_and_toughness_and_grants_trample():
    scenario = (
        Scenario()
        .player("alice", battlefield=["World War Hulk", "Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("World War Hulk", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(saga, Counter.LORE, 2 - saga.counters[Counter.LORE])
    scenario.game.pending_triggers.clear()
    scenario.will_choose_targets(bears)

    _next_chapter(scenario, saga)

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Trample" in chars.abilities


def test_hulk_three_doubles_what_is_there_as_it_resolves():
    """CR 701.10b: +X/+X where X is the value as the ability resolves - two
    +1/+1 counters make a 4/4, doubled to 8/8."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["World War Hulk", "Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("World War Hulk", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.game.add_counters(saga, Counter.LORE, 2 - saga.counters[Counter.LORE])
    scenario.game.pending_triggers.clear()
    scenario.will_choose_targets(bears)

    _next_chapter(scenario, saga)

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (8, 8)


def test_off_msh_grunn_doubles_when_attacking_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grunn, the Lonely King"], library=["Forest"] * 6)
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    grunn = scenario.creature("Grunn, the Lonely King", "alice")

    scenario.attack_with(grunn)
    _resolve_everything(scenario)

    chars = _chars(scenario, grunn)
    assert (chars.power, chars.toughness) == (10, 10)

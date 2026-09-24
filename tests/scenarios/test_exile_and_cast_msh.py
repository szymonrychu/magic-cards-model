"""Exile-then-cast/play templates from the Marvel Super Heroes (msh) set
(task C02-T7): every card below exiles a card (or several), from a library or
a graveyard, and then may hand the exiled card's owner or controller CR
601.3's permission to cast or play it.

- **Black Widow, Super Spy** - "Whenever Black Widow deals combat damage to a
  player, that player exiles cards from the top of their library until they
  exile a nonland card. You may put a +1/+1 counter on Black Widow. If you
  don't, you may cast the exiled nonland card until end of turn and mana of
  any type can be spent to cast that spell." A CR 608.2d "may" (the counter)
  whose "if you don't" branch is itself a second, independent "may" (the
  cast permission) - read as one instruction by `_merge_exile_until_quality_
  then_counter_or_cast_clauses`.
- **Stolen Goods** (real Modern-legal Scryfall printing, added with
  `add_card.py`; not in any `magic-cards-model-api` deck list) - "Target
  opponent exiles cards from the top of their library until they exile a
  nonland card. Until end of turn, you may cast that card without paying its
  mana cost." Proves the shared exile-until-quality primitive generalizes
  past Black Widow's own third-person "that player" (CR 120.2a's damaged
  player) to a genuinely targeted opponent (CR 601.2c), through the ordinary
  `_parse_exile_then_play_permission_clauses` merge every other exile-then-
  permission card in the pool already shares.
- **Cosmic Cube** - "Whenever you attack, look at the top six cards of your
  library. You may cast a spell from among them with mana value less than or
  equal to the greatest power among attacking creatures you control without
  paying its mana cost. Put the rest on the bottom of your library in a
  random order."
- **Daredevil, Man Without Fear** - "Whenever you attack, you may exile the
  top card of your library. If that card is a Hero card, Daredevil gets
  +2/+1 until end of turn. You may play that card this turn."
- **Moonstone, Harsh Mistress** - "Whenever you discard a card, you may exile
  that card from your graveyard. If you do, until the end of your next turn,
  you may play that card."
- **Thor, God of Thunder** - "When Thor enters, exile target Equipment,
  instant, or sorcery card from your graveyard. Until the end of your next
  turn, you may play that card." Widens `_EXILE_TARGET_CARD_RE`'s quality
  group to accept an Oxford-comma type list, not only a single bare word.

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it and no rule or effect prohibits that player
  from casting it."
- **CR 120.2a** - damage "dealt as a result of combat" is what fires a "deals
  combat damage to a player" trigger and supplies its own "that player".
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written."
- **CR 608.2d** - a "may" question, answered as the ability resolves.
- **CR 118.9** - "without paying its mana cost" (Stolen Goods, Cosmic Cube).
- **CR 202.3** - mana value, read off a card even while it sits in a library
  or exile (Cosmic Cube's "mana value less than or equal to").
- **CR 401.2** - the library is one ordered pile; putting cards "in a random
  order" (Cosmic Cube) still keeps it that.
- **CR 603.6b** - an enters-the-battlefield trigger (Thor).
- **CR 603.2** - "attacks" triggers fire once combat begins (CR 508.1),
  before blockers, on the beginning-of-combat/declare-attackers window
  (Cosmic Cube, Daredevil - "whenever you attack").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


# -- Black Widow, Super Spy --------------------------------------------------


def _widow_board(*, bob_library: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Black Widow, Super Spy"])
        .player("bob", library=bob_library)
    )


def _widow_hit(scenario: Scenario):
    widow = scenario.creature("Black Widow, Super Spy", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(widow, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)
    return widow


def test_the_damaged_players_library_is_exiled_until_a_nonland_card():
    scenario = _widow_board(bob_library=["Island", "Forest", "Lightning Bolt", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _widow_hit(scenario)

    bob = scenario.player("bob")
    assert [state.name for state in bob.library] == ["Mountain"]
    exiled = [state for state in scenario.game.exile]
    assert [state.name for state in exiled] == ["Island", "Forest", "Lightning Bolt"]


def test_taking_the_counter_declines_the_cast_permission():
    scenario = _widow_board(bob_library=["Island", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)  # take the +1/+1 counter
    widow = _widow_hit(scenario)

    assert widow.counters.counts.get("+1/+1", 0) == 1
    bolt = next(state for state in scenario.game.exile if state.name == "Lightning Bolt")
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_declining_the_counter_then_taking_the_cast_grants_permission_with_any_type_mana():
    scenario = _widow_board(bob_library=["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)  # decline the counter
    scenario.will_take_the_may(True)  # take the cast permission
    widow = _widow_hit(scenario)

    assert widow.counters.counts.get("+1/+1", 0) == 0
    bolt = next(state for state in scenario.game.exile if state.name == "Lightning Bolt")
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.CAST
    assert permission.any_type_mana is True
    assert permission.until_end_of_turn is True


def test_declining_both_leaves_the_card_in_exile_with_no_permission():
    scenario = _widow_board(bob_library=["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)  # decline the counter
    scenario.will_take_the_may(False)  # decline the cast
    widow = _widow_hit(scenario)

    assert widow.counters.counts.get("+1/+1", 0) == 0
    bolt = next(state for state in scenario.game.exile if state.name == "Lightning Bolt")
    assert scenario.game.play_permission_for(bolt, "alice") is None
    assert bolt.zone is Zone.EXILE


def test_a_library_of_only_lands_exiles_everything_and_grants_nothing():
    """CR 609.3-style: the stop condition never fires, so there is no card to
    name for either "may" branch."""
    scenario = _widow_board(bob_library=["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    widow = _widow_hit(scenario)

    assert widow.counters.counts.get("+1/+1", 0) == 0
    bob = scenario.player("bob")
    assert bob.library == []
    assert {state.name for state in scenario.game.exile} == {"Forest", "Island"}


# -- Stolen Goods (second printing) ------------------------------------------


def test_stolen_goods_exiles_the_targeted_opponents_library_and_grants_free_cast():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stolen Goods"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", library=["Forest", "Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Stolen Goods")
    casting.choose_targets(["bob"])
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    bob = scenario.player("bob")
    assert [state.name for state in bob.library] == ["Island"]
    bolt = next(state for state in scenario.game.exile if state.name == "Lightning Bolt")
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.pays_mana_cost is False
    assert permission.until_end_of_turn is True


# -- Cosmic Cube --------------------------------------------------------


def test_cosmic_cube_casts_a_spell_at_or_under_the_greatest_attacking_power():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Cosmic Cube", "Grizzly Bears", "Craw Wurm"],
            library=["Lightning Bolt", "Forest", "Island", "Mountain", "Swamp", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    scenario.attack_with(bears, wurm, defending="bob")
    lightning_bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(lightning_bolt)
    scenario.will_choose_targets("bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.resolve_top()  # the Lightning Bolt cast during the trigger's resolution

    alice = scenario.player("alice")
    bolt = next((state for state in alice.graveyard if state.name == "Lightning Bolt"), None)
    assert bolt is not None, "Lightning Bolt (mv 1) is at or under Craw Wurm's power 6"
    assert len(alice.library) == 5  # 6 looked at, 1 cast, 5 bottomed in a random order
    assert scenario.player("bob").life == 17


def test_cosmic_cube_declines_or_finds_no_legal_spell_bottoms_everything():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Cosmic Cube", "Grizzly Bears"],
            library=["Forest", "Island", "Mountain", "Swamp", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert len(alice.library) == 6
    assert alice.graveyard == []


# -- Daredevil, Man Without Fear ----------------------------------------


def test_daredevils_exiled_hero_card_pumps_him_and_grants_a_this_turn_permission():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Daredevil, Man Without Fear"],
            library=["Black Widow, Super Spy", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    daredevil = scenario.creature("Daredevil, Man Without Fear", "alice")
    scenario.attack_with(daredevil, defending="bob")
    scenario.will_take_the_may(True)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert daredevil.power == 5  # 3 base + 2
    assert daredevil.toughness == 5  # 4 base + 1
    widow = next(state for state in scenario.game.exile if state.name == "Black Widow, Super Spy")
    permission = scenario.game.play_permission_for(widow, "alice")
    assert permission is not None
    assert permission.until_end_of_turn is True


def test_daredevils_exiled_non_hero_card_grants_permission_with_no_pump():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Daredevil, Man Without Fear"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    daredevil = scenario.creature("Daredevil, Man Without Fear", "alice")
    scenario.attack_with(daredevil, defending="bob")
    scenario.will_take_the_may(True)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert daredevil.power == 3
    forest = next(state for state in scenario.game.exile if state.name == "Forest")
    assert scenario.game.play_permission_for(forest, "alice") is not None


def test_declining_daredevils_exile_leaves_the_library_untouched():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Daredevil, Man Without Fear"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    daredevil = scenario.creature("Daredevil, Man Without Fear", "alice")
    scenario.attack_with(daredevil, defending="bob")
    scenario.will_take_the_may(False)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Forest"]
    assert scenario.game.exile == []


# -- Moonstone, Harsh Mistress -------------------------------------------


def test_moonstone_grants_a_next_turn_permission_over_the_discarded_card():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Moonstone, Harsh Mistress"], hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True)
    scenario.game.discard_cards("alice", [bolt])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.expires_end_of_next_turn is True


def test_containment_construct_second_printing_grants_a_this_turn_permission():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Containment Construct"], hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True)
    scenario.game.discard_cards("alice", [bolt])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.until_end_of_turn is True


# -- Thor, God of Thunder (enters trigger only; the cast-damage trigger is
# -- test_targeting_cast_triggers.py's business) --------------------------


def test_thor_exiles_a_chosen_equipment_instant_or_sorcery_from_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thor, God of Thunder"],
            graveyard=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt)
    mountains = scenario.untapped_sources(*(["Mountain"] * 5))
    casting = scenario.cast("Thor, God of Thunder")
    scenario.pay_with(casting.begin_paying(), *mountains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.expires_end_of_next_turn is True

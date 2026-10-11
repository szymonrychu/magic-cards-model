"""CR 716.2a, 508.3d, 701.9, 701.23: Cool but Rude's three levels.

- Level 1: "Whenever you attack, you may discard a card. If you do, draw a
  card." Once per attack declaration (CR 508.3d), only for the Class's
  controller, optional, and the draw only happens if a card was discarded.
- Level 2 ({1}{R}): "Whenever you discard a card, this Class deals 2 damage
  to each opponent." On any discard of the controller's own cards, whoever
  caused it, and not on an opponent's discard.
- Level 3 ({1}{R}): "When this Class becomes level 3, search your library for
  a card, put it into your hand, shuffle, then discard a card at random."
  The random discard (CR 701.9b) also feeds level 2's trigger.

Levels are gained in order, as a sorcery (CR 716.2a).

CR numbers used, read with `mise run rules:find` in this session: CR 716.2a,
CR 508.3d, CR 701.9a/b, CR 701.23a, CR 118.12.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CLASS = "Cool but Rude"


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _board(
    *,
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_hand: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand or [],
            battlefield=[CLASS, "Goblin Guide", "Grizzly Bears", *["Mountain"] * 6],
            library=library if library is not None else ["Island"] * 4,
        )
        .player("bob", hand=bob_hand or [], battlefield=["Llanowar Elves"], library=["Forest"] * 4)
    )


def _class(scenario):
    return scenario.find(CLASS, Zone.BATTLEFIELD, "alice")


def _attack(scenario, *names: str) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creatures = [scenario.creature(name, "alice") for name in names]
    scenario.attack_with(*creatures)
    settle(scenario)


def _hand(scenario, who: str = "alice") -> list[str]:
    return sorted(s.name for s in scenario.player(who).hand)


def _level_up(scenario, index: int, lands: int = 2) -> None:
    scenario.activate(
        _class(scenario), *scenario.untapped_sources(*["Mountain"] * lands), index=index
    )
    settle(scenario)


# -- level 1: attack trigger ---------------------------------------------------


def test_level_1_attack_lets_me_discard_a_card_and_draw_a_card():
    scenario = _board(hand=["Forest"], library=["Island", "Swamp"]).build()
    scenario.will_take_the_may(True, times=None)
    _attack(scenario, "Goblin Guide")

    assert _hand(scenario) == ["Island"]
    assert [s.name for s in scenario.player("alice").graveyard] == ["Forest"]


def test_level_1_declining_the_may_does_nothing():
    scenario = _board(hand=["Forest"], library=["Island"]).build()
    scenario.will_take_the_may(False, times=None)
    _attack(scenario, "Goblin Guide")

    assert _hand(scenario) == ["Forest"]
    assert scenario.player("alice").graveyard == []


def test_level_1_with_an_empty_hand_the_discard_cannot_be_chosen():
    """ "If you do": with no card to discard the yes option is illegal
    (CR 608.2d), so there is no discard and therefore no draw."""
    scenario = _board(hand=[], library=["Island"]).build()
    scenario.will_take_the_may(True, times=None)

    with pytest.raises(ValueError, match="illegal"):
        _attack(scenario, "Goblin Guide")

    assert _hand(scenario) == []


def test_level_1_with_an_empty_hand_declining_draws_nothing():
    scenario = _board(hand=[], library=["Island"]).build()
    scenario.will_take_the_may(False, times=None)
    _attack(scenario, "Goblin Guide")

    assert _hand(scenario) == []
    assert [s.name for s in scenario.player("alice").library][:1] == ["Island"]


def test_level_1_triggers_once_however_many_creatures_attack():
    """CR 508.3d: "Whenever you attack" is one trigger for the declaration."""
    scenario = _board(hand=["Forest", "Forest"], library=["Island", "Swamp"]).build()
    scenario.will_take_the_may(True, times=None)
    _attack(scenario, "Goblin Guide", "Grizzly Bears")

    assert len(scenario.player("alice").graveyard) == 1
    assert len(scenario.player("alice").hand) == 2


def test_level_1_does_not_trigger_on_the_opponents_attack():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 3)
        .player("alice", hand=["Forest"], battlefield=[CLASS], library=["Island"] * 3)
        .build()
    )
    scenario.will_take_the_may(True, times=None)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    settle(scenario)

    assert _hand(scenario) == ["Forest"]


def test_no_attack_no_trigger():
    scenario = _board(hand=["Forest"], library=["Island"]).build()
    scenario.will_take_the_may(True, times=None)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    settle(scenario)

    assert _hand(scenario) == ["Forest"]


# -- level bars: CR 716.2a -----------------------------------------------------


def test_levels_are_gained_in_order():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="is level 1, not level 2"):
        scenario.activate(_class(scenario), index=1)

    _level_up(scenario, 0)
    assert _class(scenario).class_level == 2
    _level_up(scenario, 1)
    assert _class(scenario).class_level == 3


def test_levels_are_sorcery_speed():
    scenario = _board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        scenario.activate(
            _class(scenario), *scenario.untapped_sources("Mountain", "Mountain"), index=0
        )


# -- level 2: discard damage -----------------------------------------------------


def test_level_2_deals_2_damage_to_each_opponent_when_i_discard():
    scenario = _board(hand=["Forest"], library=["Island"]).build()
    _class(scenario).class_level = 2
    scenario.will_take_the_may(True, times=None)
    _attack(scenario, "Goblin Guide")

    assert scenario.player("bob").life == 18


def test_level_2_is_not_live_at_level_1():
    scenario = _board(hand=["Forest"], library=["Island"]).build()
    scenario.will_take_the_may(True, times=None)
    _attack(scenario, "Goblin Guide")

    assert scenario.player("bob").life == 20


def test_level_2_triggers_for_a_discard_an_opponent_forces():
    """ "Whenever you discard a card" does not care who made me discard: one
    trigger per card (Mind Rot makes me discard two)."""
    scenario = (
        Scenario()
        .player("bob", hand=["Mind Rot"], battlefield=["Swamp"] * 3, library=["Forest"] * 3)
        .player("alice", hand=["Forest", "Island"], battlefield=[CLASS], library=["Island"] * 3)
        .build()
    )
    _class(scenario).class_level = 2
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_discard(*scenario.player("alice").hand, username="alice", times=None)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="bob")
    scenario.cast_onto_stack("Mind Rot", *swamps, username="bob", targets=["alice"])
    scenario.pass_until_resolved()
    settle(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.player("bob").life == 16  # 2 damage for each of the 2 cards
    assert scenario.player("alice").life == 20


def test_level_2_does_not_trigger_when_an_opponent_discards():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot"],
            battlefield=[CLASS, *["Swamp"] * 3],
            library=["Island"] * 3,
        )
        .player("bob", hand=["Forest", "Island"], library=["Forest"] * 3)
        .build()
    )
    _class(scenario).class_level = 2
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_discard(*scenario.player("bob").hand, username="bob", times=None)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_onto_stack("Mind Rot", *swamps, targets=["bob"])
    scenario.pass_until_resolved()
    settle(scenario)

    assert scenario.player("bob").hand == []
    assert scenario.player("bob").life == 20


def test_level_1_s_own_discard_feeds_level_2():
    """Both abilities are had at level 2 (CR 716.2a, "level N or greater")."""
    scenario = _board(hand=["Forest", "Forest"], library=["Island", "Swamp"]).build()
    _class(scenario).class_level = 2
    scenario.will_take_the_may(True, times=None)
    _attack(scenario, "Goblin Guide", "Grizzly Bears")

    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == 2


# -- level 3: tutor then random discard --------------------------------------------


def test_reaching_level_3_searches_puts_in_hand_and_discards_at_random():
    """With nothing else in hand the tutored card is the only candidate, so
    the random discard puts it in the graveyard - and, at level 3, the
    discard is also level 2's trigger."""
    scenario = _board(hand=[], library=["Island", "Lightning Bolt", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _class(scenario).class_level = 2
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bolt, username="alice", times=None)
    _level_up(scenario, 1)

    assert _class(scenario).class_level == 3
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_level_3_discard_is_at_random_among_the_whole_hand():
    """The discard is not the player's choice (CR 701.9b): across several
    shuffles both the tutored card and the card already in hand get discarded."""
    discarded = set()
    for seed in range(30):
        scenario = _board(hand=["Forest"], library=["Island", "Lightning Bolt"]).build()
        scenario.game.shuffle_seed = seed
        scenario.start_at(Step.PRECOMBAT_MAIN)
        _class(scenario).class_level = 2
        bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
        scenario.will_choose_cards(bolt, username="alice", times=None)
        _level_up(scenario, 1)
        assert len(scenario.player("alice").hand) == 1
        assert len(scenario.player("alice").graveyard) == 1
        discarded.add(scenario.player("alice").graveyard[0].name)
    assert discarded == {"Forest", "Lightning Bolt"}


def test_level_3_does_not_trigger_on_reaching_level_2():
    scenario = _board(hand=[], library=["Island", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _level_up(scenario, 0)

    assert _class(scenario).class_level == 2
    assert _hand(scenario) == []
    assert scenario.player("alice").graveyard == []

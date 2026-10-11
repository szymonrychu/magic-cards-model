"""Triggered instructions printed on EP-01 round 2 listed cards (T6), each
read as a template, never by name.

- "return a `<quality>` you control to its owner's hand" (Trusted Advisor's
  upkeep, "a blue creature") - CR 608.2d's controller choice, no target;
- "that player untaps a `<quality>` they control" (Hokori, Dust Drinker) -
  the player the triggering upkeep belongs to (CR 503.1) chooses;
- "draw an additional card and remove two hour counters from this
  enchantment" (Midnight Oil) - two instructions in order (CR 608.2c);
- "discard that many cards. Then if you have no cards in hand, you lose the
  game." (Marina Vendrell's Grimoire) and "put a judgment counter on this
  Aura. Then if there are three or more judgment counters on it, enchanted
  player loses the game." (Sinner's Judgment) - CR 104.3e;
- "create a token that's a copy of enchanted creature, except it's a Spirit
  in addition to its other types" (Ghastly Mimicry) - CR 707.9b;
- "you may search your library for a card named Tempest Hawk ..." - CR 201.5
  self-name, CR 701.23b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _build(alice: dict, bob: dict | None = None, step: Step = Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .player("alice", **{"library": ["Island"] * 10, **alice})
        .player("bob", **{"library": ["Island"] * 10, **(bob or {})})
        .build()
    )
    scenario.start_at(step)
    return scenario


def _resolve_triggers(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_upkeep_of(scenario, username):
    game = scenario.game
    start = game.turn.turns_taken
    while not (
        game.turn.active_player == username
        and game.turn.turns_taken > start
        and game.turn.step is Step.UPKEEP
    ):
        if game.turn.step is not Step.UNTAP:
            _resolve_triggers(scenario)
        scenario.advance()


def _disturb(scenario, name, *lands, targets):
    sources = scenario.untapped_sources(*lands)
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_trusted_advisor_returns_a_blue_creature_at_upkeep():
    scenario = _build({"battlefield": ["Trusted Advisor", "Grizzly Bears"]})
    _to_upkeep_of(scenario, "alice")
    _resolve_triggers(scenario)
    assert scenario.find("Trusted Advisor", Zone.HAND, "alice")
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")


def test_trusted_advisor_never_returns_a_non_blue_creature():
    scenario = _build({"battlefield": ["Trusted Advisor", "Grizzly Bears"]})
    advisor = scenario.find("Trusted Advisor", Zone.BATTLEFIELD, "alice")
    scenario.game.put_into_graveyard(advisor)
    _to_upkeep_of(scenario, "alice")
    _resolve_triggers(scenario)
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")


def test_hokori_lets_each_upkeep_player_untap_one_land():
    scenario = _build({"battlefield": ["Hokori, Dust Drinker"]}, {"battlefield": ["Island"] * 2})
    islands = [s for s in scenario.game.battlefield if s.name == "Island"]
    for island in islands:
        island.tapped = True
    _to_upkeep_of(scenario, "bob")
    _resolve_triggers(scenario)
    assert sorted(s.tapped for s in islands) == [False, True]


def test_midnight_oil_draws_and_spends_two_hour_counters():
    scenario = _build({"battlefield": ["Midnight Oil"]})
    oil = scenario.find("Midnight Oil", Zone.BATTLEFIELD, "alice")
    oil.add_counters("hour", 7)
    _to_upkeep_of(scenario, "alice")
    hand = len(scenario.player("alice").hand)
    while scenario.game.turn.step is not Step.PRECOMBAT_MAIN:
        _resolve_triggers(scenario)
        scenario.advance()
    assert oil.counters["hour"] == 5
    assert len(scenario.player("alice").hand) == hand + 2


def test_grimoire_discards_on_life_loss_and_an_empty_hand_loses():
    scenario = _build({"battlefield": ["Marina Vendrell's Grimoire"], "hand": ["Island"]})
    scenario.game.lose_life(scenario.player("alice"), 2)
    _resolve_triggers(scenario)
    assert not scenario.player("alice").hand
    assert not scenario.game.is_in_game("alice")


def test_grimoire_keeps_you_in_while_cards_remain():
    scenario = _build({"battlefield": ["Marina Vendrell's Grimoire"], "hand": ["Island"] * 3})
    scenario.game.lose_life(scenario.player("alice"), 1)
    _resolve_triggers(scenario)
    assert len(scenario.player("alice").hand) == 2
    assert scenario.game.is_in_game("alice")


def test_sinners_judgment_third_counter_makes_the_enchanted_player_lose():
    scenario = _build({"graveyard": ["Faithbound Judge"], "battlefield": ["Plains"] * 7})
    curse = _disturb(scenario, "Faithbound Judge", *["Plains"] * 7, targets=["bob"])
    assert curse.name == "Sinner's Judgment"
    curse.add_counters("judgment", 1)
    _to_upkeep_of(scenario, "alice")
    _resolve_triggers(scenario)
    assert curse.counters["judgment"] == 2
    assert scenario.game.is_in_game("bob")
    _to_upkeep_of(scenario, "alice")
    _resolve_triggers(scenario)
    assert not scenario.game.is_in_game("bob")


def test_ghastly_mimicry_copies_the_enchanted_creature_as_a_spirit():
    scenario = _build(
        {"graveyard": ["Mirrorhall Mimic"], "battlefield": ["Island"] * 5},
        {"battlefield": ["Grizzly Bears"]},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _disturb(scenario, "Mirrorhall Mimic", *["Island"] * 5, targets=[bears])
    _to_upkeep_of(scenario, "alice")
    _resolve_triggers(scenario)
    copies = [
        s
        for s in scenario.game.battlefield
        if s.name == "Grizzly Bears" and scenario.game.controller_of(s).username == "alice"
    ]
    assert len(copies) == 1
    assert "Spirit" in scenario.game.characteristics_of(copies[0]).subtypes


def test_tempest_hawk_fetches_another_tempest_hawk_on_combat_damage():
    scenario = _build(
        {"battlefield": ["Tempest Hawk"], "library": ["Island", "Tempest Hawk", "Island"]}
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Tempest Hawk"))
    scenario.no_blocks()
    scenario.will_take_the_may(True, username="alice")
    scenario.combat_damage()
    _resolve_triggers(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.find("Tempest Hawk", Zone.HAND, "alice")


def test_tempest_hawk_finds_nothing_with_another_name():
    scenario = _build({"battlefield": ["Tempest Hawk"], "library": ["Island"] * 3})
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Tempest Hawk"))
    scenario.no_blocks()
    scenario.will_take_the_may(True, username="alice")
    scenario.combat_damage()
    _resolve_triggers(scenario)
    assert not scenario.player("alice").hand


def test_every_listed_trigger_card_reads_handled():
    for name in (
        "Trusted Advisor",
        "Hokori, Dust Drinker",
        "Midnight Oil",
        "Marina Vendrell's Grimoire",
        "Faithbound Judge // Sinner's Judgment",
        "Mirrorhall Mimic // Ghastly Mimicry",
        "Tempest Hawk",
        "Malevolent Hermit // Benevolent Geist",
    ):
        support = card_support(card(name))
        assert support.status == "handled", (
            name,
            [c for c in support.clauses if c.status != "handled"],
        )

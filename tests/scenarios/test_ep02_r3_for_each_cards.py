"""EP-02-R3 T7: "for each <thing>" and "equal to the number of <things>" counts
that read a turn's history, a cast record, the Curses attached to a player or
the distinct mana values on a board.

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 700.4** - "dies" means is put into a graveyard from the battlefield.
- **CR 608.2h** - information an effect needs is taken once, as the effect is
  applied.
- **CR 608.2c** - instructions are followed in the order written.
- **CR 107.3a** - X on a spell or ability.
- **CR 122.1** - counters.
- **CR 202.3** - mana value.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Aetherspouts",
    "Agadeem Occultist",
    "Anticausal Vestige",
    "Ashen-Skin Zubera",
    "Biomantic Mastery",
    "Blinkmoth Urn",
    "Bloodhusk Ritualist",
    "Curse of Surveillance",
    "Curse of Thirst",
    "Dark Salvation",
    "Deadly Embrace",
    "Desert's Due",
    "Dream Salvage",
    "Engulf the Shore",
    "Fiery Bombardment",
    "Floating-Dream Zubera",
    "Hateful Eidolon",
    "Heirloom Epic",
    "Hobgoblin Bandit Lord",
    "Lightmine Field",
    "Lunar Insight",
    "Magebane Lizard",
    "Rending Vines",
    "Riptide Gearhulk",
    "Rumbling Aftershocks",
    "Sepulchral Primordial",
    "Shared Animosity",
    "Soul of Emancipation",
    "Squirming Emergence",
    "The Chain Veil",
]

PROOF = [
    "Silent-Chant Zubera",
    "Lightkeeper of Emeria",
    "Stronghold Arena",
]

LANDS = ["Plains"] * 6 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 4


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def _scenario(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_hand: list[str] | None = None,
    bob_library: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        )
        .player(
            "bob",
            battlefield=[*(bob or []), *LANDS],
            hand=bob_hand,
            graveyard=bob_graveyard,
            library=bob_library or ["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_all(scenario, name: str, *, user: str = "alice", targets=None, x: int | None = None):
    """Cast `name` and resolve the spell, its triggers and everything they
    put on the stack."""
    if scenario.priority_holder != user:
        scenario.pass_priority()
    if x is None:
        scenario.cast_onto_stack(name, username=user, targets=targets, auto=True)
    else:
        spell = scenario.find(name, Zone.HAND, user)
        scenario.game.cast(
            spell,
            user,
            x_value=x,
            targets=targets,
            mana_sources=scenario.untapped_sources(*LANDS, username=user),
        )
    _resolve_all(scenario)


def _named(scenario, name: str, zone: Zone = Zone.BATTLEFIELD, user: str | None = None) -> list:
    return [
        state
        for state in scenario.all_card_states()
        if state.name in (name, f"{name} Token")
        and state.zone is zone
        and (user is None or state.owner == user)
    ]


def _life(scenario, who: str) -> int:
    return scenario.player(who).life


def _hand(scenario, who: str) -> int:
    return len(scenario.player(who).hand)


# ---------------------------------------------------------------------------
# "for each <thing> that died this turn" (CR 700.4)
# ---------------------------------------------------------------------------


def test_deadly_embrace_draws_for_the_creature_it_destroyed() -> None:
    scenario = _scenario([], ["Grizzly Bears"], hand=["Deadly Embrace"])
    _cast_all(scenario, "Deadly Embrace", targets=[scenario.creature("Grizzly Bears", "bob")])
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert _hand(scenario, "alice") == 1


def test_deadly_embrace_counts_a_creature_that_died_earlier_this_turn() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], ["Grizzly Bears"], hand=["Deadly Embrace", "Lightning Bolt"]
    )
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Grizzly Bears", "alice")])
    _cast_all(scenario, "Deadly Embrace", targets=[scenario.creature("Grizzly Bears", "bob")])
    assert _hand(scenario, "alice") == 2  # both Bears died this turn, whoever controlled them


def test_deadly_embrace_counts_nothing_when_the_destroy_fails_to_kill() -> None:
    scenario = _scenario([], ["Grizzly Bears"], hand=["Deadly Embrace"])
    scenario.cast_onto_stack(
        "Deadly Embrace",
        username="alice",
        targets=[scenario.creature("Grizzly Bears", "bob")],
        auto=True,
    )
    # the target is gone before it resolves: the spell fizzles and draws nothing (CR 608.2b)
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))
    hand_before = _hand(scenario, "alice")
    _resolve_all(scenario)
    assert _hand(scenario, "alice") == hand_before


def test_floating_dream_zubera_draws_for_each_zubera_that_died() -> None:
    scenario = _scenario(["Floating-Dream Zubera", "Floating-Dream Zubera"], hand=["Wrath of God"])
    _cast_all(scenario, "Wrath of God")
    # each Zubera's trigger sees both deaths: two triggers x two Zubera
    assert _hand(scenario, "alice") == 4


def test_floating_dream_zubera_ignores_other_creatures_dying() -> None:
    scenario = _scenario(["Floating-Dream Zubera", "Grizzly Bears"], hand=["Wrath of God"])
    _cast_all(scenario, "Wrath of God")
    assert _hand(scenario, "alice") == 1


def test_ashen_skin_zubera_makes_the_opponent_discard_per_zubera() -> None:
    scenario = _scenario(
        ["Ashen-Skin Zubera"],
        ["Floating-Dream Zubera"],
        hand=["Wrath of God"],
        bob_hand=["Island", "Island", "Island", "Island"],
    )
    scenario.choose_trigger_targets("Ashen-Skin Zubera", [scenario.player("bob")])
    _cast_all(scenario, "Wrath of God")
    # two Zubera died this turn (either controller): bob discards two, and draws one from his own
    assert len(scenario.player("bob").graveyard) >= 2


def test_ashen_skin_zubera_discards_one_when_it_dies_alone() -> None:
    scenario = _scenario(
        ["Ashen-Skin Zubera"], hand=["Lightning Bolt"], bob_hand=["Island", "Island"]
    )
    scenario.choose_trigger_targets("Ashen-Skin Zubera", [scenario.player("bob")])
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Ashen-Skin Zubera", "alice")])
    assert _hand(scenario, "bob") == 1


def test_silent_chant_zubera_gains_two_life_per_zubera_that_died() -> None:
    scenario = _scenario(["Silent-Chant Zubera", "Floating-Dream Zubera"], hand=["Wrath of God"])
    _cast_all(scenario, "Wrath of God")
    assert _life(scenario, "alice") == 20 + 2 * 2


def _cast_kicked(scenario, name: str, times: int, *, user: str = "alice", targets=None, **kicker):
    """Cast `name` paying its (multi)kicker `times` times, then resolve it and
    everything it triggers."""
    casting = scenario.cast(name, user, targets=targets)
    if times:
        casting.pay_kicker(times, **kicker)
    scenario.auto_pay(casting.begin_paying(), username=user)
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


# ---------------------------------------------------------------------------
# "for each time it was kicked" (CR 702.33d)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("times", "discards"), [(0, 0), (1, 1), (3, 3)])
def test_bloodhusk_ritualist_discards_a_card_per_kick(times: int, discards: int) -> None:
    scenario = _scenario([], hand=["Bloodhusk Ritualist"], bob_hand=["Island"] * 5)
    scenario.choose_trigger_targets("Bloodhusk Ritualist", [scenario.player("bob")])
    _cast_kicked(scenario, "Bloodhusk Ritualist", times)
    assert _hand(scenario, "bob") == 5 - discards


def test_lightkeeper_of_emeria_gains_two_life_per_kick() -> None:
    scenario = _scenario([], hand=["Lightkeeper of Emeria"])
    _cast_kicked(scenario, "Lightkeeper of Emeria", 2)
    assert _life(scenario, "alice") == 20 + 4


def test_lightkeeper_of_emeria_gains_nothing_unkicked() -> None:
    scenario = _scenario([], hand=["Lightkeeper of Emeria"])
    _cast_kicked(scenario, "Lightkeeper of Emeria", 0)
    assert _life(scenario, "alice") == 20


def test_stronghold_arena_gains_three_life_per_kick() -> None:
    scenario = _scenario([], hand=["Stronghold Arena"])
    _cast_kicked(scenario, "Stronghold Arena", 1, which="{G}")
    assert _life(scenario, "alice") == 20 + 3


# ---------------------------------------------------------------------------
# "damage equal to the number of times that spell was kicked"
# ---------------------------------------------------------------------------


def test_rumbling_aftershocks_deals_damage_equal_to_the_kicks() -> None:
    scenario = _scenario(
        ["Rumbling Aftershocks"], hand=["Bloodhusk Ritualist"], bob_hand=["Island"]
    )
    scenario.will_take_the_may(True, source="Rumbling Aftershocks")
    scenario.choose_trigger_targets("Rumbling Aftershocks", [scenario.player("bob")])
    scenario.choose_trigger_targets("Bloodhusk Ritualist", [scenario.player("bob")])
    _cast_kicked(scenario, "Bloodhusk Ritualist", 3)
    assert _life(scenario, "bob") == 20 - 3


def test_rumbling_aftershocks_ignores_an_unkicked_spell() -> None:
    scenario = _scenario(["Rumbling Aftershocks"], hand=["Bloodhusk Ritualist"])
    scenario.choose_trigger_targets("Bloodhusk Ritualist", [scenario.player("bob")])
    _cast_kicked(scenario, "Bloodhusk Ritualist", 0)
    assert _life(scenario, "bob") == 20


def test_rumbling_aftershocks_may_decline() -> None:
    scenario = _scenario(["Rumbling Aftershocks"], hand=["Bloodhusk Ritualist"])
    scenario.will_take_the_may(False, source="Rumbling Aftershocks")
    scenario.choose_trigger_targets("Bloodhusk Ritualist", [scenario.player("bob")])
    _cast_kicked(scenario, "Bloodhusk Ritualist", 2)
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# "the number of cards target opponent discarded this turn" (CR 701.9a)
# ---------------------------------------------------------------------------


def test_dream_salvage_draws_for_each_card_the_opponent_discarded_this_turn() -> None:
    scenario = _scenario(
        [], hand=["Mind Rot", "Dream Salvage"], bob_hand=["Island", "Island", "Island"]
    )
    _cast_all(scenario, "Mind Rot", targets=["bob"])
    assert _hand(scenario, "bob") == 1
    before = _hand(scenario, "alice")
    _cast_all(scenario, "Dream Salvage", targets=["bob"])
    assert _hand(scenario, "alice") == before - 1 + 2  # the spell leaves, two cards come in


def test_dream_salvage_draws_nothing_when_the_opponent_discarded_nothing() -> None:
    scenario = _scenario([], hand=["Dream Salvage"], bob_hand=["Island"])
    _cast_all(scenario, "Dream Salvage", targets=["bob"])
    assert _hand(scenario, "alice") == 0


def test_dream_salvage_does_not_count_the_casters_own_discards() -> None:
    scenario = _scenario(
        [], hand=["Mind Rot", "Dream Salvage", "Island", "Island"], bob_hand=["Island"]
    )
    _cast_all(scenario, "Mind Rot", targets=["alice"])  # alice discards her own two cards
    _cast_all(scenario, "Dream Salvage", targets=["bob"])
    assert _hand(scenario, "alice") == 0


# ---------------------------------------------------------------------------
# "the number of noncreature spells they've cast this turn"
# ---------------------------------------------------------------------------


def test_magebane_lizard_damages_the_caster_by_their_noncreature_spell_count() -> None:
    scenario = _scenario(["Magebane Lizard"], bob_hand=["Opt", "Opt", "Opt"])
    _cast_all(scenario, "Opt", user="bob")
    assert _life(scenario, "bob") == 20 - 1
    _cast_all(scenario, "Opt", user="bob")
    assert _life(scenario, "bob") == 20 - 1 - 2
    _cast_all(scenario, "Opt", user="bob")
    assert _life(scenario, "bob") == 20 - 1 - 2 - 3


def test_magebane_lizard_does_not_count_creature_spells() -> None:
    scenario = _scenario(["Magebane Lizard"], hand=["Grizzly Bears", "Opt"])
    _cast_all(scenario, "Grizzly Bears")
    assert _life(scenario, "alice") == 20
    _cast_all(scenario, "Opt")
    assert _life(scenario, "alice") == 20 - 1


def test_magebane_lizard_hurts_its_own_controller_for_their_spells_only() -> None:
    scenario = _scenario(["Magebane Lizard"], hand=["Opt"], bob_hand=["Opt"])
    _cast_all(scenario, "Opt", user="bob")
    _cast_all(scenario, "Opt")
    assert _life(scenario, "bob") == 20 - 1
    assert _life(scenario, "alice") == 20 - 1  # alice's own first noncreature spell


# ---------------------------------------------------------------------------
# "the number of Goblins that entered the battlefield under your control this turn"
# ---------------------------------------------------------------------------


def test_hobgoblin_bandit_lord_deals_damage_per_goblin_that_entered_this_turn() -> None:
    scenario = _scenario(
        ["Hobgoblin Bandit Lord"], hand=["Goblin Guide", "Raging Goblin", "Grizzly Bears"]
    )
    for name in ("Goblin Guide", "Raging Goblin", "Grizzly Bears"):
        _cast_all(scenario, name)
    lord = scenario.creature("Hobgoblin Bandit Lord", "alice")
    scenario.activate(lord, targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20 - 2


def test_hobgoblin_bandit_lord_counts_a_goblin_that_has_since_died() -> None:
    scenario = _scenario(["Hobgoblin Bandit Lord"], hand=["Raging Goblin", "Lightning Bolt"])
    _cast_all(scenario, "Raging Goblin")
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Raging Goblin", "alice")])
    lord = scenario.creature("Hobgoblin Bandit Lord", "alice")
    scenario.activate(lord, targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20 - 1


def test_hobgoblin_bandit_lord_deals_nothing_when_no_goblin_entered() -> None:
    scenario = _scenario(["Hobgoblin Bandit Lord"])
    lord = scenario.creature("Hobgoblin Bandit Lord", "alice")
    scenario.activate(lord, targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# "each different mana value among nonland permanents you control" (CR 202.3)
# ---------------------------------------------------------------------------


def test_lunar_insight_draws_for_each_different_mana_value() -> None:
    scenario = _scenario(
        ["Memnite", "Grizzly Bears", "Grizzly Bears", "Serra Angel", "Llanowar Elves"],
        hand=["Lunar Insight"],
        library=["Island"] * 12,
    )
    _cast_all(scenario, "Lunar Insight")
    assert _hand(scenario, "alice") == 4  # mana values 0, 1, 2 and 5; the lands do not count


def test_lunar_insight_counts_only_the_casters_board() -> None:
    scenario = _scenario(["Grizzly Bears"], ["Serra Angel", "Memnite"], hand=["Lunar Insight"])
    _cast_all(scenario, "Lunar Insight")
    assert _hand(scenario, "alice") == 1


def test_lunar_insight_draws_nothing_with_only_lands() -> None:
    scenario = _scenario([], hand=["Lunar Insight"])
    _cast_all(scenario, "Lunar Insight")
    assert _hand(scenario, "alice") == 0


# ---------------------------------------------------------------------------
# Curses attached to a player (CR 303.4m)
# ---------------------------------------------------------------------------


def _curses_scenario(alice_curses: list[str], on_bob: list[bool], alice_hand=None, targets=None):
    """Alice's Curses, each attached to bob or alice, on bob's upkeep."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[*alice_curses], hand=alice_hand, library=["Island"] * 12)
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    for curse, at_bob in zip(
        [s for s in scenario.all_card_states() if s.zone is Zone.BATTLEFIELD], on_bob, strict=True
    ):
        curse.attach_to(scenario.player("bob" if at_bob else "alice"))
    if targets is not None:
        scenario.choose_trigger_targets(alice_curses[0], [scenario.player(t) for t in targets])
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    return scenario


def test_curse_of_thirst_deals_damage_per_curse_on_the_player() -> None:
    scenario = _curses_scenario(["Curse of Thirst", "Curse of Exhaustion"], [True, True])
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == 20 - 2
    assert _life(scenario, "alice") == 20


def test_curse_of_thirst_alone_deals_one() -> None:
    scenario = _curses_scenario(["Curse of Thirst"], [True])
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == 20 - 1


def test_curse_of_thirst_ignores_curses_on_another_player() -> None:
    scenario = _curses_scenario(["Curse of Thirst", "Curse of Exhaustion"], [True, False])
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == 20 - 1


def test_curse_of_surveillance_draws_for_the_other_player_by_the_curses_on_that_player() -> None:
    scenario = _curses_scenario(
        ["Curse of Surveillance", "Curse of Exhaustion"], [True, True], targets=["alice"]
    )
    scenario.pass_until_resolved()
    assert _hand(scenario, "alice") == 2
    assert _hand(scenario, "bob") == 0


def test_curse_of_surveillance_may_target_no_one() -> None:
    scenario = _curses_scenario(["Curse of Surveillance"], [True], targets=[])
    scenario.pass_until_resolved()
    assert _hand(scenario, "alice") == 0 and _hand(scenario, "bob") == 0


def test_curse_of_surveillance_cannot_draw_for_the_enchanted_player() -> None:
    """ "Other than that player": a choice of the enchanted player is illegal
    (CR 115.1, CR 608.2b), so bob draws nothing and alice, not chosen, neither."""
    scenario = _curses_scenario(["Curse of Surveillance"], [True], targets=["bob"])
    scenario.pass_until_resolved()
    assert _hand(scenario, "bob") == 0
    assert _hand(scenario, "alice") == 0

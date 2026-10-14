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
- **CR 202.3** - mana value (CR 202.3a: none is 0).
- **CR 702.33d** - kicked; **CR 303.4m** - "enchanted [object or player]";
  **CR 701.9a** - discard; **CR 603.10a** - leaves-the-battlefield look-back;
  **CR 400.7d** - an ability reads the spell that became its permanent;
  **CR 107.1c** - "any number" may be zero; **CR 115.1/115.3/115.6** - targets;
  **CR 608.2b** - targets rechecked; **CR 608.2d** - choices on resolution;
  **CR 608.2f** - simultaneous actions on a group.
- **CR 401.1** - libraries; **CR 609.3** - do as much as possible;
  **CR 110.2a / 111.2** - who controls a put or created object.
- **CR 606.3** - once per planeswalker per turn; **CR 602.1b / 602.2b / 601.2h** -
  activation instructions and paying the cost; **CR 107.4e** - hybrid symbols.
- **CR 613.4c** - layer 7c adds; **CR 702.73a** - changeling; **CR 508.3d** -
  batched attack triggers; **CR 120.1** - damage; **CR 701.8a** - destroy.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
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
    "Dripping-Tongue Zubera",
    "Canopy Stalker",
    "Gadrak, the Crown-Scourge",
    "Subtlety",
    "Aether Gust",
    "Tamiyo, the Moon Sage",
    "Growth Cycle",
    "Terastodon",
    "Hour of Need",
    "K'rrik, Son of Yawgmoth",
    "Ancestor Dragon",
    "Bushmeat Poacher",
    "Urza, Planeswalker",
    "Luminate Primordial",
    "Sylvan Primordial",
    "Lay Down Arms",
    "Bortuk Bonerattle",
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


# ---------------------------------------------------------------------------
# "if its mana value / toughness is less than or equal to the number of <things>"
# (CR 202.3, CR 608.2c: the comparison is made as the instruction is followed)
# ---------------------------------------------------------------------------


def _names(scenario, zone: Zone, user: str) -> list[str]:
    return sorted(s.name for s in scenario.all_card_states() if s.zone is zone and s.owner == user)


def test_rending_vines_destroys_a_permanent_within_the_hand_count_and_draws() -> None:
    scenario = _scenario(
        [], ["Sol Ring"], hand=["Rending Vines", "Island", "Island"], library=["Forest"] * 5
    )
    _cast_all(scenario, "Rending Vines", targets=[scenario.find("Sol Ring", Zone.BATTLEFIELD)])
    assert _names(scenario, Zone.GRAVEYARD, "bob") == ["Sol Ring"]
    assert _hand(scenario, "alice") == 3  # the two Islands and the card it drew


def test_rending_vines_spares_a_permanent_above_the_hand_count_but_still_draws() -> None:
    scenario = _scenario([], ["Wurmcoil Engine"], hand=["Rending Vines"], library=["Forest"] * 5)
    _cast_all(
        scenario, "Rending Vines", targets=[scenario.find("Wurmcoil Engine", Zone.BATTLEFIELD)]
    )
    assert _names(scenario, Zone.BATTLEFIELD, "bob").count("Wurmcoil Engine") == 1
    assert _hand(scenario, "alice") == 1


def test_agadeem_occultist_steals_a_creature_within_the_ally_count() -> None:
    scenario = _scenario(["Agadeem Occultist"], bob_graveyard=["Memnite", "Serra Angel"])
    occultist = scenario.creature("Agadeem Occultist", "alice")
    scenario.activate(
        occultist, targets=[scenario.find("Memnite", Zone.GRAVEYARD, "bob")], auto=True
    )
    _resolve_all(scenario)
    stolen = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    assert (stolen.owner, stolen.controller) == ("bob", "alice")


def test_agadeem_occultist_leaves_a_creature_above_the_ally_count() -> None:
    scenario = _scenario(["Agadeem Occultist"], bob_graveyard=["Memnite", "Serra Angel"])
    occultist = scenario.creature("Agadeem Occultist", "alice")
    scenario.activate(
        occultist, targets=[scenario.find("Serra Angel", Zone.GRAVEYARD, "bob")], auto=True
    )
    _resolve_all(scenario)
    assert "Serra Angel" in _names(scenario, Zone.GRAVEYARD, "bob")


def test_squirming_emergence_returns_a_permanent_card_within_the_graveyard_count() -> None:
    scenario = _scenario(
        [],
        hand=["Squirming Emergence"],
        graveyard=["Grizzly Bears", "Memnite", "Serra Angel", "Island", "Hill Giant"],
    )
    _cast_all(
        scenario, "Squirming Emergence", targets=[scenario.find("Serra Angel", Zone.GRAVEYARD)]
    )
    assert "Serra Angel" in _names(scenario, Zone.BATTLEFIELD, "alice")


def test_squirming_emergence_cannot_target_a_card_above_the_graveyard_count() -> None:
    scenario = _scenario([], hand=["Squirming Emergence"], graveyard=["Serra Angel", "Island"])
    with pytest.raises(Exception, match="(?i)mana value"):
        scenario.cast(
            "Squirming Emergence", "alice", targets=[scenario.find("Serra Angel", Zone.GRAVEYARD)]
        )


def test_engulf_the_shore_bounces_creatures_with_toughness_up_to_the_island_count() -> None:
    scenario = _scenario(
        ["Grizzly Bears", "Serra Angel"],
        ["Colossal Dreadmaw", "Memnite"],
        hand=["Engulf the Shore"],
    )
    _cast_all(scenario, "Engulf the Shore")
    assert _names(scenario, Zone.HAND, "alice") == ["Grizzly Bears", "Serra Angel"]
    assert _names(scenario, Zone.HAND, "bob") == ["Memnite"]
    assert _names(scenario, Zone.BATTLEFIELD, "bob").count("Colossal Dreadmaw") == 1


def test_anticausal_vestige_draws_then_puts_a_permanent_within_the_land_count() -> None:
    scenario = _scenario(
        ["Anticausal Vestige"],
        hand=["Serra Angel", "Wurmcoil Engine", "Go for the Throat"],
        library=["Forest"] * 5,
    )
    _cast_all(
        scenario,
        "Go for the Throat",
        targets=[scenario.creature("Anticausal Vestige", "alice")],
    )
    names = _names(scenario, Zone.BATTLEFIELD, "alice")
    # 21 lands: both permanent cards are within it; the vestige's trigger lets alice put one
    assert len([n for n in names if n in ("Serra Angel", "Wurmcoil Engine")]) == 1


# ---------------------------------------------------------------------------
# Per-count pumps and damage: Desert's Due, Dark Salvation, Shared Animosity,
# Lightmine Field, Fiery Bombardment (CR 608.2h: the count is taken once as the
# effect is applied; CR 613.4c: -N/-N effects add)
# ---------------------------------------------------------------------------


def _stats(scenario, name: str, user: str) -> tuple[int, int]:
    chars = scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, user))
    return chars.power, chars.toughness


@pytest.mark.parametrize(("deserts", "expected"), [(0, (4, 4)), (1, (3, 3)), (2, (2, 2))])
def test_deserts_due_shrinks_the_target_by_each_desert(deserts: int, expected) -> None:
    scenario = _scenario(["Desert"] * deserts, ["Colossal Dreadmaw"], hand=["Desert's Due"])
    _cast_all(
        scenario, "Desert's Due", targets=[scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD)]
    )
    assert _stats(scenario, "Colossal Dreadmaw", "bob") == expected


def test_deserts_due_does_not_count_the_opponents_deserts() -> None:
    scenario = _scenario([], ["Colossal Dreadmaw", "Desert"], hand=["Desert's Due"])
    _cast_all(
        scenario, "Desert's Due", targets=[scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD)]
    )
    assert _stats(scenario, "Colossal Dreadmaw", "bob") == (4, 4)


def test_dark_salvation_makes_zombies_for_the_player_and_shrinks_by_their_count() -> None:
    scenario = _scenario([], ["Colossal Dreadmaw"], hand=["Dark Salvation"])
    _cast_all(
        scenario,
        "Dark Salvation",
        targets=[scenario.player("alice"), scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD)],
        x=2,
    )
    assert len(_named(scenario, "Zombie", user="alice")) == 2
    assert _stats(scenario, "Colossal Dreadmaw", "bob") == (4, 4)


def test_dark_salvation_counts_the_zombies_of_the_targeted_player() -> None:
    scenario = _scenario(["Colossal Dreadmaw"], hand=["Dark Salvation"])
    _cast_all(
        scenario,
        "Dark Salvation",
        targets=[scenario.player("bob"), scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD)],
        x=3,
    )
    assert len(_named(scenario, "Zombie", user="bob")) == 3
    assert _stats(scenario, "Colossal Dreadmaw", "alice") == (3, 3)


def _attack(scenario, *creatures) -> None:
    """Declare `creatures` as attackers and resolve what that triggers."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*creatures)
    _resolve_all(scenario)


def test_shared_animosity_pumps_an_attacker_per_other_attacker_sharing_a_type() -> None:
    scenario = _scenario(
        ["Shared Animosity", "Goblin Guide", "Raging Goblin", "Grizzly Bears"], step=Step.UPKEEP
    )
    _attack(
        scenario,
        *scenario.creatures("Goblin Guide", "Raging Goblin", "Grizzly Bears", username="alice"),
    )
    assert _stats(scenario, "Goblin Guide", "alice")[0] == 2 + 1
    assert _stats(scenario, "Raging Goblin", "alice")[0] == 1 + 1
    assert _stats(scenario, "Grizzly Bears", "alice")[0] == 2


def test_shared_animosity_counts_a_changeling_as_sharing_every_type() -> None:
    scenario = _scenario(
        ["Shared Animosity", "Goblin Guide", "Changeling Outcast", "Grizzly Bears"],
        step=Step.UPKEEP,
    )
    _attack(
        scenario,
        *scenario.creatures(
            "Goblin Guide", "Changeling Outcast", "Grizzly Bears", username="alice"
        ),
    )
    assert _stats(scenario, "Goblin Guide", "alice")[0] == 2 + 1
    assert _stats(scenario, "Grizzly Bears", "alice")[0] == 2 + 1
    assert _stats(scenario, "Changeling Outcast", "alice")[0] == 1 + 2


def test_shared_animosity_gives_nothing_to_a_lone_attacker() -> None:
    scenario = _scenario(["Shared Animosity", "Goblin Guide", "Raging Goblin"], step=Step.UPKEEP)
    _attack(scenario, scenario.creature("Goblin Guide", "alice"))
    assert _stats(scenario, "Goblin Guide", "alice")[0] == 2


def test_lightmine_field_hurts_every_attacker_by_the_number_of_attackers() -> None:
    scenario = _scenario(
        ["Lightmine Field", "Grizzly Bears", "Memnite", "Colossal Dreadmaw"], step=Step.UPKEEP
    )
    _attack(
        scenario,
        *scenario.creatures("Grizzly Bears", "Memnite", "Colossal Dreadmaw", username="alice"),
    )
    assert _names(scenario, Zone.GRAVEYARD, "alice") == ["Grizzly Bears", "Memnite"]
    assert scenario.creature("Colossal Dreadmaw", "alice").damage == 3


def test_lightmine_field_deals_one_to_a_lone_attacker() -> None:
    scenario = _scenario(["Lightmine Field", "Grizzly Bears"], step=Step.UPKEEP)
    _attack(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert scenario.creature("Grizzly Bears", "alice").damage == 1


def test_fiery_bombardment_deals_damage_equal_to_the_red_symbols_sacrificed() -> None:
    scenario = _scenario(["Fiery Bombardment", "Hellrider"])
    hellrider = scenario.creature("Hellrider", "alice")
    scenario.activate(
        scenario.find("Fiery Bombardment", Zone.BATTLEFIELD, "alice"),
        sacrificing=[hellrider],
        targets=["bob"],
        auto=True,
    )
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20 - 2  # {2}{R}{R}


def test_fiery_bombardment_counts_a_single_red_symbol() -> None:
    scenario = _scenario(["Fiery Bombardment", "Goblin Guide", "Grizzly Bears"])
    scenario.activate(
        scenario.find("Fiery Bombardment", Zone.BATTLEFIELD, "alice"),
        sacrificing=[scenario.creature("Goblin Guide", "alice")],
        targets=["bob"],
        auto=True,
    )
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 19


def test_fiery_bombardment_deals_nothing_for_a_creature_without_red_symbols() -> None:
    scenario = _scenario(["Fiery Bombardment", "Grizzly Bears"])
    scenario.activate(
        scenario.find("Fiery Bombardment", Zone.BATTLEFIELD, "alice"),
        sacrificing=[scenario.creature("Grizzly Bears", "alice")],
        targets=["bob"],
        auto=True,
    )
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# Biomantic Mastery: "Draw a card for each creature target player controls, then
# draw a card for each creature another target player controls." (CR 608.2c)
# ---------------------------------------------------------------------------


def test_biomantic_mastery_draws_for_each_creature_both_players_control() -> None:
    scenario = _scenario(
        ["Grizzly Bears", "Memnite"],
        ["Serra Angel", "Hill Giant", "Llanowar Elves"],
        hand=["Biomantic Mastery"],
        library=["Forest"] * 12,
    )
    _cast_all(
        scenario, "Biomantic Mastery", targets=[scenario.player("alice"), scenario.player("bob")]
    )
    assert _hand(scenario, "alice") == 5


def test_biomantic_mastery_counts_the_chosen_players_not_the_casters() -> None:
    scenario = _scenario(
        ["Grizzly Bears"],
        ["Serra Angel", "Hill Giant"],
        hand=["Biomantic Mastery"],
        library=["Forest"] * 12,
    )
    _cast_all(
        scenario, "Biomantic Mastery", targets=[scenario.player("bob"), scenario.player("alice")]
    )
    assert _hand(scenario, "alice") == 3
    assert _hand(scenario, "bob") == 0


def test_biomantic_mastery_cannot_name_the_same_player_twice() -> None:
    scenario = _scenario(["Grizzly Bears"], hand=["Biomantic Mastery"])
    with pytest.raises(ValueError, match="CR 115.3"):
        scenario.cast(
            "Biomantic Mastery",
            "alice",
            targets=[scenario.player("alice"), scenario.player("alice")],
        )


# ---------------------------------------------------------------------------
# Blinkmoth Urn: "At the beginning of each player's first main phase, if this
# artifact is untapped, that player adds {C} for each artifact they control."
# ---------------------------------------------------------------------------


def _first_main_of(scenario, who: str) -> None:
    """Advance to `who`'s precombat main phase, resolving what triggers."""
    while not (scenario.step is Step.PRECOMBAT_MAIN and scenario.turn.active_player == who):
        scenario.advance()
        scenario.game.put_triggers_on_stack()
        _resolve_all(scenario)


def test_blinkmoth_urn_adds_mana_for_the_active_players_artifacts() -> None:
    scenario = _scenario(
        ["Blinkmoth Urn", "Sol Ring"], ["Ornithopter", "Memnite"], step=Step.UPKEEP
    )
    _first_main_of(scenario, "alice")
    assert scenario.player("alice").mana_pool.total == 2  # the urn and Sol Ring


def test_blinkmoth_urn_gives_the_mana_to_the_opponent_for_their_artifacts() -> None:
    scenario = _scenario(
        ["Blinkmoth Urn"], ["Ornithopter", "Sol Ring", "Wurmcoil Engine"], step=Step.UPKEEP
    )
    _first_main_of(scenario, "bob")
    assert scenario.player("bob").mana_pool.total == 3
    assert scenario.player("alice").mana_pool.total == 0


def test_blinkmoth_urn_adds_nothing_while_tapped() -> None:
    scenario = _scenario(["Blinkmoth Urn", "Sol Ring"], step=Step.UPKEEP)
    scenario.find("Blinkmoth Urn", Zone.BATTLEFIELD, "alice").tapped = True
    scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")  # Sol Ring stays untapped
    _first_main_of(scenario, "alice")
    assert scenario.player("alice").mana_pool.total == 0


# ---------------------------------------------------------------------------
# Aetherspouts: "For each attacking creature, its owner puts it on their choice of the
# top or bottom of their library." (CR 401.1, CR 608.2d)
# ---------------------------------------------------------------------------


def _aetherspouts(answers: list[bool]):
    scenario = _scenario(
        ["Grizzly Bears", "Memnite"],
        hand=["Aetherspouts"],
        library=["Forest"] * 6,
        step=Step.UPKEEP,
    )
    bears, memnite = scenario.creatures("Grizzly Bears", "Memnite", username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, memnite)
    for answer in answers:
        scenario.will_choose_top(answer, username="alice", times=1)
    _cast_all(scenario, "Aetherspouts")
    return scenario, [s.name for s in scenario.player("alice").library]


def test_aetherspouts_puts_every_attacker_on_top_when_the_owner_chooses_top() -> None:
    scenario, library = _aetherspouts([True, True])
    assert sorted(library[:2]) == ["Grizzly Bears", "Memnite"]
    assert scenario.attackers() == []


def test_aetherspouts_puts_every_attacker_on_the_bottom_when_the_owner_chooses_bottom() -> None:
    _scenario_, library = _aetherspouts([False, False])
    assert sorted(library[-2:]) == ["Grizzly Bears", "Memnite"]


def test_aetherspouts_asks_the_owner_once_per_attacker() -> None:
    _scenario_, library = _aetherspouts([True, False])
    assert library[0] in ("Grizzly Bears", "Memnite")
    assert library[-1] in ("Grizzly Bears", "Memnite")
    assert library[0] != library[-1]


def test_aetherspouts_leaves_non_attackers_alone() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], ["Serra Angel"], hand=["Aetherspouts"], step=Step.UPKEEP
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    _cast_all(scenario, "Aetherspouts")
    assert _names(scenario, Zone.BATTLEFIELD, "bob").count("Serra Angel") == 1


# ---------------------------------------------------------------------------
# Hateful Eidolon: "Whenever an enchanted creature dies, draw a card for each Aura
# you controlled that was attached to it." (CR 603.10a: leaves-the-battlefield
# abilities look back)
# ---------------------------------------------------------------------------


def _eidolon(my_auras: int, their_auras: int):
    scenario = _scenario(
        ["Hateful Eidolon", *["Pacifism"] * my_auras],
        ["Grizzly Bears", *["Pacifism"] * their_auras],
        hand=["Lightning Bolt"],
        library=["Forest"] * 8,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    for aura in [s for s in scenario.all_card_states() if s.name == "Pacifism"]:
        aura.attach_to(bears)
    return scenario, bears


def test_hateful_eidolon_draws_for_each_aura_you_controlled_on_the_dead_creature() -> None:
    scenario, bears = _eidolon(2, 0)
    _cast_all(scenario, "Lightning Bolt", targets=[bears])
    assert _hand(scenario, "alice") == 2


def test_hateful_eidolon_ignores_auras_an_opponent_controlled() -> None:
    scenario, bears = _eidolon(1, 2)
    _cast_all(scenario, "Lightning Bolt", targets=[bears])
    assert _hand(scenario, "alice") == 1


def test_hateful_eidolon_draws_nothing_when_an_unenchanted_creature_dies() -> None:
    scenario = _scenario(["Hateful Eidolon"], ["Grizzly Bears"], hand=["Lightning Bolt"])
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Grizzly Bears", "bob")])
    assert _hand(scenario, "alice") == 0


# ---------------------------------------------------------------------------
# "for each opponent, ..." enter triggers: Riptide Gearhulk, Sepulchral Primordial
# (CR 115.6 "up to one", CR 608.2d "may", CR 401.1 library placement)
# ---------------------------------------------------------------------------


def test_riptide_gearhulk_puts_the_opponents_permanent_third_from_the_top() -> None:
    scenario = _scenario(
        [],
        ["Serra Angel"],
        hand=["Riptide Gearhulk"],
        bob_library=["Forest", "Island", "Swamp", "Plains"],
    )
    scenario.choose_trigger_targets(
        "Riptide Gearhulk", [scenario.find("Serra Angel", Zone.BATTLEFIELD)]
    )
    _cast_all(scenario, "Riptide Gearhulk")
    assert [s.name for s in scenario.player("bob").library][:4] == [
        "Forest",
        "Island",
        "Serra Angel",
        "Swamp",
    ]
    assert "Serra Angel" not in _names(scenario, Zone.BATTLEFIELD, "bob")


def test_riptide_gearhulk_may_choose_no_target() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Riptide Gearhulk"])
    scenario.choose_trigger_targets("Riptide Gearhulk", [])
    _cast_all(scenario, "Riptide Gearhulk")
    assert "Serra Angel" in _names(scenario, Zone.BATTLEFIELD, "bob")


def test_riptide_gearhulk_cannot_target_a_land() -> None:
    scenario = _scenario([], [], hand=["Riptide Gearhulk"])
    land = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError, match="illegal target"):
        scenario.choose_trigger_targets("Riptide Gearhulk", [land])


def test_sepulchral_primordial_reanimates_the_opponents_creature_card() -> None:
    scenario = _scenario(
        [], hand=["Sepulchral Primordial"], bob_graveyard=["Serra Angel", "Island"]
    )
    scenario.choose_trigger_targets(
        "Sepulchral Primordial", [scenario.find("Serra Angel", Zone.GRAVEYARD, "bob")]
    )
    scenario.will_take_the_may(True)
    _cast_all(scenario, "Sepulchral Primordial")
    stolen = scenario.find("Serra Angel", Zone.BATTLEFIELD, "alice")
    assert (stolen.owner, stolen.controller) == ("bob", "alice")


def test_sepulchral_primordial_may_decline() -> None:
    scenario = _scenario([], hand=["Sepulchral Primordial"], bob_graveyard=["Serra Angel"])
    scenario.choose_trigger_targets(
        "Sepulchral Primordial", [scenario.find("Serra Angel", Zone.GRAVEYARD, "bob")]
    )
    scenario.will_take_the_may(False)
    _cast_all(scenario, "Sepulchral Primordial")
    assert _names(scenario, Zone.GRAVEYARD, "bob") == ["Serra Angel"]


def test_sepulchral_primordial_cannot_target_a_noncreature_card() -> None:
    scenario = _scenario([], hand=["Sepulchral Primordial"], bob_graveyard=["Island"])
    with pytest.raises(ValueError, match="illegal target"):
        scenario.choose_trigger_targets(
            "Sepulchral Primordial", [scenario.find("Island", Zone.GRAVEYARD, "bob")]
        )


# ---------------------------------------------------------------------------
# Soul of Emancipation: "destroy up to three other target nonland permanents. For each
# of those permanents, its controller creates a 3/3 white Angel creature token with flying."
# ---------------------------------------------------------------------------


def test_soul_of_emancipation_gives_each_permanents_controller_an_angel() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], ["Serra Angel", "Hill Giant"], hand=["Soul of Emancipation"]
    )
    scenario.choose_trigger_targets(
        "Soul of Emancipation",
        [
            scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"),
            scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob"),
            scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob"),
        ],
    )
    _cast_all(scenario, "Soul of Emancipation")
    assert len(_named(scenario, "Angel", user="alice")) == 1
    assert len(_named(scenario, "Angel", user="bob")) == 2
    assert _names(scenario, Zone.GRAVEYARD, "bob") == ["Hill Giant", "Serra Angel"]


def test_soul_of_emancipation_with_no_targets_makes_no_angels() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Soul of Emancipation"])
    scenario.choose_trigger_targets("Soul of Emancipation", [])
    _cast_all(scenario, "Soul of Emancipation")
    assert _named(scenario, "Angel") == []


# ---------------------------------------------------------------------------
# Heirloom Epic: "{4}, {T}: Draw a card. For each mana in this ability's activation
# cost, you may tap an untapped creature you control rather than pay that mana.
# Activate only as a sorcery." (CR 602.2b, CR 601.2h: costs are paid as the ability
# is activated; the taps replace mana of the cost)
# ---------------------------------------------------------------------------


def _epic(creatures: list[str]):
    scenario = _scenario(["Heirloom Epic", *creatures], library=["Forest"] * 6)
    return scenario, scenario.find("Heirloom Epic", Zone.BATTLEFIELD, "alice")


def _lands_tapped(scenario) -> int:
    return sum(
        1
        for s in scenario.game.battlefield
        if s.controller == "alice" and s.name in set(LANDS) and s.tapped
    )


def test_heirloom_epic_taps_creatures_instead_of_paying_mana() -> None:
    scenario, epic = _epic(["Grizzly Bears", "Memnite"])
    bears, memnite = scenario.creatures("Grizzly Bears", "Memnite", username="alice")
    scenario.activate(epic, tapping=[bears, memnite], auto=True)
    _resolve_all(scenario)
    assert bears.tapped and memnite.tapped
    assert _lands_tapped(scenario) == 2  # {4} less the two creatures
    assert _hand(scenario, "alice") == 1


def test_heirloom_epic_can_be_paid_by_creatures_alone() -> None:
    scenario, epic = _epic(["Grizzly Bears", "Memnite", "Serra Angel", "Hill Giant"])
    creatures = scenario.creatures(
        "Grizzly Bears", "Memnite", "Serra Angel", "Hill Giant", username="alice"
    )
    scenario.activate(epic, tapping=creatures, auto=True)
    _resolve_all(scenario)
    assert _lands_tapped(scenario) == 0
    assert _hand(scenario, "alice") == 1


def test_heirloom_epic_refuses_more_creatures_than_mana_in_the_cost() -> None:
    scenario, epic = _epic(["Grizzly Bears"] * 5)
    creatures = [
        s
        for s in scenario.game.battlefield
        if s.controller == "alice" and s.name == "Grizzly Bears"
    ]
    with pytest.raises(ValueError, match="has no \\{1\\} left to pay"):
        scenario.activate(epic, tapping=creatures, auto=True)


def test_heirloom_epic_refuses_a_tapped_creature() -> None:
    scenario, epic = _epic(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    with pytest.raises(ValueError, match="(?i)tapped"):
        scenario.activate(epic, tapping=[bears], auto=True)


def test_heirloom_epic_refuses_an_opponents_creature() -> None:
    scenario = _scenario(["Heirloom Epic"], ["Grizzly Bears"])
    epic = scenario.find("Heirloom Epic", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="(?i)control"):
        scenario.activate(epic, tapping=[scenario.creature("Grizzly Bears", "bob")], auto=True)


def _open_payment(cost: str, *, permitted: bool):
    from magic_cards_model.machines.cost import CostPayment, TotalCost

    scenario = _scenario(["Grizzly Bears"])
    payment = CostPayment.for_total(TotalCost.of(cost), game=scenario.game, payer="alice")
    payment.tap_creatures_for_mana = permitted
    return payment, scenario.creature("Grizzly Bears", "alice")


def test_a_creature_may_pay_a_coloured_symbol_of_the_cost() -> None:
    """The permission is "for each mana", coloured or generic - unlike convoke it
    does not ask for a creature of the symbol's colour."""
    from magic_cards_model.machines.objects_as_costs import tap_creature_for_mana
    from magic_cards_model.models.card import Color

    payment, bears = _open_payment("{2}{U}", permitted=True)
    substitution = tap_creature_for_mana(payment, bears, Color.BLUE)
    assert substitution.option.color is Color.BLUE


def test_tapping_a_creature_for_mana_needs_the_abilitys_permission() -> None:
    from magic_cards_model.machines.objects_as_costs import tap_creature_for_mana

    payment, bears = _open_payment("{2}", permitted=False)
    with pytest.raises(ValueError, match="(?i)does not let"):
        tap_creature_for_mana(payment, bears)


# ---------------------------------------------------------------------------
# The Chain Veil: "{4}, {T}: For each planeswalker you control, you may activate one
# of its loyalty abilities once this turn as though none of its loyalty abilities have
# been activated this turn." (CR 606.3) and the end-step gate "if you didn't activate a
# loyalty ability of a planeswalker this turn, you lose 2 life."
# ---------------------------------------------------------------------------


def _veil_board(*walkers: str):
    scenario = _scenario(["The Chain Veil", *walkers], library=["Forest"] * 6)
    return scenario, scenario.find("The Chain Veil", Zone.BATTLEFIELD, "alice")


def _mana_plus(scenario, walker: str):
    """Activate the walker's `+1: Add {R}{R}` (loyalty ability index 1)."""
    return scenario.activate(scenario.find(walker, Zone.BATTLEFIELD, "alice"), index=1, auto=True)


def _walker_refusal(scenario, walker: str) -> str | None:
    return scenario.why_cannot_activate(scenario.find(walker, Zone.BATTLEFIELD, "alice"), 1)


def test_chain_veil_lets_a_planeswalker_activate_a_second_loyalty_ability() -> None:
    scenario, veil = _veil_board("Chandra, Torch of Defiance")
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    assert "already been activated" in (
        _walker_refusal(scenario, "Chandra, Torch of Defiance") or ""
    )
    scenario.activate(veil, auto=True)
    _resolve_all(scenario)
    assert _walker_refusal(scenario, "Chandra, Torch of Defiance") is None
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    assert (
        scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "alice").counter_count(
            Counter.LOYALTY
        )
        == 6
    )


def test_chain_veil_gives_one_extra_activation_per_planeswalker_not_two() -> None:
    scenario, veil = _veil_board("Chandra, Torch of Defiance")
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    scenario.activate(veil, auto=True)
    _resolve_all(scenario)
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    assert "already been activated" in (
        _walker_refusal(scenario, "Chandra, Torch of Defiance") or ""
    )


def test_chain_veil_covers_every_planeswalker_the_controller_has() -> None:
    scenario, veil = _veil_board("Chandra, Torch of Defiance", "Nissa, Who Shakes the World")
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    scenario.activate(
        scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "alice"), index=0, auto=True
    )
    _resolve_all(scenario)
    scenario.activate(veil, auto=True)
    _resolve_all(scenario)
    assert _walker_refusal(scenario, "Chandra, Torch of Defiance") is None
    assert (
        scenario.why_cannot_activate(
            scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "alice"), 0
        )
        is None
    )


def test_chain_veil_does_nothing_for_an_opponents_planeswalker() -> None:
    scenario = _scenario(["The Chain Veil"], ["Chandra, Torch of Defiance"], library=["Forest"] * 4)
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    scenario.game.loyalty_activations[str(chandra.id)] = 1
    scenario.activate(scenario.find("The Chain Veil", Zone.BATTLEFIELD, "alice"), auto=True)
    _resolve_all(scenario)
    assert scenario.game.loyalty_activations[str(chandra.id)] == 1


def _to_end_step(scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()
        scenario.game.put_triggers_on_stack()
        _resolve_all(scenario)


def test_chain_veil_costs_two_life_at_the_end_step_without_a_loyalty_activation() -> None:
    scenario, _veil = _veil_board("Chandra, Torch of Defiance")
    _to_end_step(scenario)
    assert _life(scenario, "alice") == 18


def test_chain_veil_costs_nothing_after_a_loyalty_activation() -> None:
    scenario, _veil = _veil_board("Chandra, Torch of Defiance")
    _mana_plus(scenario, "Chandra, Torch of Defiance")
    _resolve_all(scenario)
    _to_end_step(scenario)
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# One reader per wording (the EP-02-R3 dedupe): every count is read by a single
# reader and applied exactly once (CR 608.2h: taken once, as the effect applies)
# ---------------------------------------------------------------------------


def test_once_a_twice_multikicked_creature_makes_two_wolves_not_four() -> None:
    """Times kicked (CR 702.33d), one cast-record reader: Wolfbriar Elemental
    multikicked twice makes exactly two Wolves."""
    scenario = (
        Scenario()
        .player("alice", hand=["Wolfbriar Elemental"], battlefield=["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_kicked(scenario, "Wolfbriar Elemental", 2)
    assert len(_named(scenario, "Wolf")) == 2


def test_once_the_greatest_toughness_among_other_creatures_is_one_value_not_a_sum() -> None:
    """Greatest stat among other creatures you control (CR 107.2, CR 208.5), one
    extremum reader: Hill Giant's 3 among the Hunter's companions - not their
    total 5, and never the opponent's Serra Angel."""
    scenario = _scenario(
        ["Grizzly Bears", "Hill Giant"], ["Serra Angel"], hand=["Flourishing Hunter"]
    )
    _cast_all(scenario, "Flourishing Hunter")
    assert _life(scenario, "alice") == 20 + 3


def test_once_a_lone_aura_attached_makes_one_elemental() -> None:
    """Auras/Equipment attached to it (CR 301.5a, CR 303.4b), one parse of the
    wording: Valduk with only Rancor attached makes exactly one Elemental, and an
    unattached Equipment counts for nothing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Valduk, Keeper of the Flame", "Rancor", "Bonesplitter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    valduk = scenario.creature("Valduk, Keeper of the Flame")
    (rancor,) = [p for p in scenario.game.battlefield if p.name == "Rancor"]
    rancor.attach_to(valduk)
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.resolve_top()
    assert len(_named(scenario, "Elemental")) == 1


def test_once_two_opponents_make_two_foods() -> None:
    """One amount-term entry: "the number of opponents you have" (CR 102.2) is read
    by one reader, so Gluttonous Troll in a three-player game makes exactly two Foods."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Gluttonous Troll"], battlefield=["Forest", "Forest", "Swamp", "Forest"]
        )
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Gluttonous Troll", *scenario.untapped_sources("Forest", "Forest", "Swamp", "Forest")
    )
    _resolve_all(scenario)
    assert len(_named(scenario, "Food")) == 2


def test_once_a_creature_that_died_alone_counts_itself_once() -> None:
    """Creatures that died this turn (CR 700.4), one turn-ledger reader: Canopy
    Stalker dying alone gains exactly 1 life."""
    scenario = _scenario(["Canopy Stalker"])
    scenario.game.destroy(scenario.creature("Canopy Stalker", "alice"))
    _resolve_all(scenario)
    assert _life(scenario, "alice") == 20 + 1


def test_once_that_player_is_the_damaged_player_only() -> None:
    """ "That player" (CR 603.2), one event-player helper: Emissary of Hope counts
    the one artifact the damaged player controls, never its controller's two."""
    scenario = _scenario(["Emissary of Hope", "Sol Ring", "Sol Ring"], ["Sol Ring"])
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(scenario.creature("Emissary of Hope", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_all(scenario)
    assert _life(scenario, "alice") == 20 + 1

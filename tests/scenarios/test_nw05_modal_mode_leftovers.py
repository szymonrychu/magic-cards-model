"""Three modal spells' last unread modes (NW-05, task T5).

- Lorehold Command's "Sacrifice a permanent, then draw two cards." - a bare
  "Sacrifice a <description>" instruction: the resolving controller
  sacrifices one permanent of their choice they control (CR 701.21a), then
  draws (CR 608.2c: the draw is its own instruction, so it happens even when
  nothing was sacrificed). Thalia and The Gitrog Monster's attack trigger
  ("sacrifice a creature or land, then draw a card") is the second printing.
- Wail of the Nim's "Regenerate each creature you control." - a regeneration
  shield on each such creature at resolution (CR 701.19a), and Entwine
  (CR 702.42a/702.42b): both modes, in the order written. Wrap in Vigor and
  Golgari Charm are the second printings.
- Clash of the Eikons' "Remove a lore counter from target Saga you control."
  - CR 714.2b: a chapter ability triggers only when lore counters are *put*
  on, so removing one triggers nothing; "choose one or more" modes keep their
  printed order (CR 608.2c) however they were announced. Chainbreaker's
  "{3}, {T}: Remove a -1/-1 counter from target creature." is the second
  printing of "remove a <kind> counter from target <object>".

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = ["Lorehold Command", "Wail of the Nim", "Clash of the Eikons"]
SECOND_PRINTINGS = [
    "Thalia and The Gitrog Monster",
    "Wrap in Vigor",
    "Golgari Charm",
    "Chainbreaker",
    "Decimator Beetle",
    "The First Eruption",
    "Bristlebud Farmer",
]


@pytest.mark.parametrize("name", LISTED + SECOND_PRINTINGS)
def test_every_printing_is_fully_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, (name, bad)


def _cast_modal(scenario, name, modes, *, targets=(), entwined=False):
    casting = scenario.cast(name)
    casting.choose_modes(list(modes), entwined=entwined)
    if targets:
        casting.choose_targets(list(targets))
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


# -- Lorehold Command: "Sacrifice a permanent, then draw two cards." ----------


def _lorehold(*, alice=(), library=("Plains", "Plains", "Plains")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lorehold Command"],
            battlefield=["Mountain", "Mountain", "Mountain", "Plains", "Plains", *alice],
            library=list(library),
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_lorehold_sacrifices_the_permanent_alice_chooses_then_draws_two():
    scenario = _lorehold(alice=["Ornithopter"])
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.will_choose_cards(thopter, username="alice")
    _cast_modal(scenario, "Lorehold Command", [1, 4])

    assert thopter.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 2
    spirits = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    assert len(spirits) == 1
    assert scenario.game.mode_notices == []


def test_lorehold_can_sacrifice_the_spirit_its_own_first_mode_made():
    """Printed order (CR 608.2c): the Spirit token exists by the time mode 4
    asks, so it is offered beside alice's five lands."""
    scenario = _lorehold()
    lands = {p.id for p in scenario.game.permanents_controlled_by("alice")}
    _cast_modal(scenario, "Lorehold Command", [1, 4])

    (question,) = [q for q in scenario.questions_asked() if q.cards and set(q.cards) & lands]
    extra = set(question.cards) - lands
    assert len(extra) == 1  # the Spirit
    assert len(question.cards) == 6
    assert len(scenario.player("alice").hand) == 2


def test_lorehold_offers_only_alices_own_permanents():
    """CR 701.21a: a player can't sacrifice a permanent they don't control -
    bob's Bears are never offered."""
    scenario = _lorehold(alice=["Ornithopter"])
    bears = scenario.creature("Grizzly Bears", "bob")
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.will_choose_cards(thopter, username="alice")
    _cast_modal(scenario, "Lorehold Command", [1, 4])

    question = next(q for q in scenario.questions_asked() if q.cards and thopter.id in q.cards)
    assert bears.id not in question.cards
    assert bears.zone is Zone.BATTLEFIELD


def test_lorehold_draws_two_with_any_permanent_given_up():
    """Alice gives up a tapped land: any permanent she controls will do."""
    scenario = _lorehold()
    _cast_modal(scenario, "Lorehold Command", [1, 4])

    lands_left = [
        p for p in scenario.game.permanents_controlled_by("alice") if not p.token and p.card.is_land
    ]
    gone = len(scenario.player("alice").graveyard) - 1  # less the Command itself
    tokens_left = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    assert gone + (1 - len(tokens_left)) == 1
    assert len(lands_left) + len(tokens_left) == 5
    assert len(scenario.player("alice").hand) == 2


# -- Thalia and The Gitrog Monster: the same instruction on a trigger --------


def test_thalia_and_the_gitrog_monster_sacrifices_a_creature_or_land_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thalia and The Gitrog Monster", "Forest", "Ornithopter"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Mind Stone"])
        .build()
    )
    thalia = scenario.creature("Thalia and The Gitrog Monster", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.will_choose_cards(forest, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(thalia)
    scenario.pass_until_resolved()

    question = next(q for q in scenario.questions_asked() if q.cards and forest.id in q.cards)
    assert set(question.cards) == {thalia.id, forest.id, thopter.id}
    assert forest.zone is Zone.GRAVEYARD
    assert thopter.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 1


def test_thalia_and_the_gitrog_monster_never_offers_a_noncreature_nonland():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thalia and The Gitrog Monster", "Mind Stone"],
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    thalia = scenario.creature("Thalia and The Gitrog Monster", "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(thalia)
    scenario.pass_until_resolved()

    assert stone.zone is Zone.BATTLEFIELD
    assert thalia.zone is Zone.GRAVEYARD  # the only creature or land she has
    assert len(scenario.player("alice").hand) == 1


# -- The First Eruption III: "Sacrifice a Mountain. If you do, ..." ----------


def _eruption_chapter_three(alice_lands):
    """Up to chapter II, then chapter III alone; the Wurm's damage before III
    is returned so III's own share can be told apart (CR 120.3)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The First Eruption", *alice_lands, "Craw Wurm"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "alice")

    def resolve_chapters():
        scenario.game.put_triggers_on_stack()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    resolve_chapters()
    scenario.game.saga_lore_step()
    resolve_chapters()
    giant = scenario.creature("Hill Giant", "bob")
    before = wurm.damage
    scenario.game.saga_lore_step()
    resolve_chapters()
    return scenario, giant, wurm, before


def test_first_eruption_sacrifices_a_mountain_and_then_deals_three():
    scenario, giant, wurm, before = _eruption_chapter_three(["Mountain", "Forest"])

    assert [c.name for c in scenario.player("alice").graveyard if c.name == "Mountain"]
    assert giant.zone is Zone.GRAVEYARD
    assert wurm.damage == before + 3


def test_first_eruption_without_a_mountain_deals_nothing():
    """ "If you do": nothing was sacrificed (CR 608.2d), so chapter III deals
    no damage."""
    scenario, giant, wurm, before = _eruption_chapter_three(["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    assert giant.zone is Zone.BATTLEFIELD
    assert wurm.damage == before
    assert forest.zone is Zone.BATTLEFIELD


# -- Bristlebud Farmer: "you may sacrifice a Food. If you do, ..." ----------


def _bristlebud(*, with_food: bool, take: bool = True):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bristlebud Farmer"],
            library=["Grizzly Bears", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farmer = scenario.put_onto_battlefield("Bristlebud Farmer", "alice")
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    foods = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    if not with_food:
        for food in foods:
            scenario.game.sacrifice(food)
    scenario.will_take_the_may(take, username="alice", source="Bristlebud Farmer")
    farmer.summoning_sick = False  # staged: it has been under alice's control since her turn began
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(farmer)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    return scenario


def _foods(scenario):
    return [p for p in scenario.game.permanents_controlled_by("alice") if p.token]


def test_bristlebud_sacrificing_a_food_mills_three():
    scenario = _bristlebud(with_food=True)

    assert len(_foods(scenario)) == 1
    milled_or_kept = len(scenario.player("alice").graveyard) + len(scenario.player("alice").hand)
    assert milled_or_kept >= 3
    assert len(scenario.player("alice").library) == 1


def test_bristlebud_declining_mills_nothing():
    scenario = _bristlebud(with_food=True, take=False)

    assert len(_foods(scenario)) == 2
    assert len(scenario.player("alice").library) == 4


def test_bristlebud_with_no_food_is_never_asked_and_mills_nothing():
    """ "If you do": with no Food there is nothing to sacrifice (CR 608.2d),
    so the consequence never runs."""
    scenario = _bristlebud(with_food=False)

    assert len(scenario.player("alice").library) == 4
    assert not [
        q
        for q in scenario.questions_asked()
        if q.source == "Bristlebud Farmer" and "sacrifice" in (q.prompt or "").lower()
    ]


# -- Wail of the Nim: regenerate each creature you control, and entwine -------


def _wail(*, alice=("Llanowar Elves", "Grizzly Bears"), bob=("Llanowar Elves",)):
    scenario = (
        Scenario()
        .player("alice", hand=["Wail of the Nim"], battlefield=["Swamp"] * 4 + list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_wail_mode_one_shields_each_creature_alice_controls_only():
    scenario = _wail()
    alice_elves = scenario.creature("Llanowar Elves", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bob_elves = scenario.creature("Llanowar Elves", "bob")
    _cast_modal(scenario, "Wail of the Nim", [1])

    assert alice_elves.regeneration_shields == 1
    assert bears.regeneration_shields == 1
    assert bob_elves.regeneration_shields == 0


def test_wail_mode_two_alone_kills_the_one_toughness_creatures():
    scenario = _wail()
    alice_elves = scenario.creature("Llanowar Elves", "alice")
    bob_elves = scenario.creature("Llanowar Elves", "bob")
    _cast_modal(scenario, "Wail of the Nim", [2])
    scenario.state_based_actions()

    assert alice_elves.zone is Zone.GRAVEYARD
    assert bob_elves.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 19


def test_entwined_wail_shields_first_then_deals_the_damage():
    """CR 702.42b: mode 1 then mode 2. Alice's Elves are shielded before the
    1 damage lands, so lethal damage's destruction (CR 704.5g) is replaced
    by regeneration (CR 701.19a: tapped, damage removed); bob's Elves die."""
    scenario = _wail()
    alice_elves = scenario.creature("Llanowar Elves", "alice")
    bob_elves = scenario.creature("Llanowar Elves", "bob")
    _cast_modal(scenario, "Wail of the Nim", [1, 2], entwined=True)
    scenario.state_based_actions()

    assert alice_elves.zone is Zone.BATTLEFIELD
    assert alice_elves.tapped
    assert alice_elves.damage == 0
    assert bob_elves.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 19


# -- Wrap in Vigor / Golgari Charm: the same group regeneration ---------------


def test_wrap_in_vigor_saves_alices_creatures_from_day_of_judgment():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wrap in Vigor", "Day of Judgment"],
            battlefield=["Forest", "Forest", "Plains", "Plains", "Plains", "Plains"]
            + ["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Wrap in Vigor", *scenario.untapped_sources("Forest", "Forest"))
    scenario.cast_and_resolve(
        "Day of Judgment", *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    )

    assert bears.zone is Zone.BATTLEFIELD and bears.tapped
    assert elves.zone is Zone.BATTLEFIELD and elves.tapped
    assert giant.zone is Zone.GRAVEYARD


def test_golgari_charm_regeneration_mode():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Golgari Charm"],
            battlefield=["Swamp", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast_modal(scenario, "Golgari Charm", [3])

    assert bears.regeneration_shields == 1
    assert giant.regeneration_shields == 0


# -- Clash of the Eikons: remove a lore counter from target Saga -------------


def _clash(*, bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Clash of the Eikons"],
            battlefield=["Forest", "History of Benalia"],
        )
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # History of Benalia's own chapter I, for its intrinsic first lore
    # counter (CR 714.3a), resolves first.
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    return scenario


def _knights(scenario, username="alice"):
    return [p for p in scenario.game.permanents_controlled_by(username) if p.token]


def test_removing_a_lore_counter_triggers_no_chapter():
    """CR 714.2b: chapters trigger on lore counters being put on, not off."""
    scenario = _clash()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD, "alice")
    assert saga.counters[Counter.LORE] == 1
    knights_before = len(_knights(scenario))
    _cast_modal(scenario, "Clash of the Eikons", [2], targets=[saga])
    scenario.game.put_triggers_on_stack()

    assert saga.counter_count("lore") == 0
    assert scenario.game.stack_is_empty
    assert len(_knights(scenario)) == knights_before
    assert saga.zone is Zone.BATTLEFIELD


def test_remove_then_put_in_printed_order_retriggers_chapter_one():
    """Modes 2 and 3 on the same Saga, announced 3 first: printed order
    removes the counter (1 -> 0), then puts one (0 -> 1), which crosses
    chapter I again (CR 714.2b) - so a second Knight."""
    scenario = _clash()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD, "alice")
    knights_before = len(_knights(scenario))
    _cast_modal(scenario, "Clash of the Eikons", [3, 2], targets=[saga, saga])
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert saga.counter_count("lore") == 1
    assert len(_knights(scenario)) == knights_before + 1


def test_the_saga_must_be_one_alice_controls():
    scenario = _clash(bob=["History of Benalia"])
    bobs = scenario.find("History of Benalia", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Clash of the Eikons")
    casting.choose_modes([2])
    with pytest.raises(ValueError):
        casting.choose_targets([bobs])


# -- Chainbreaker: remove a -1/-1 counter from target creature ---------------


def test_chainbreaker_removes_one_minus_one_counter():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chainbreaker", "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chainbreaker = scenario.creature("Chainbreaker", "alice")
    chainbreaker.add_counters("-1/-1", 2)
    scenario.activate(
        chainbreaker,
        *scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[chainbreaker],
    )
    scenario.resolve_top()

    assert chainbreaker.counter_count("-1/-1") == 1


def test_chainbreaker_on_a_creature_without_the_counter_does_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chainbreaker", "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chainbreaker = scenario.creature("Chainbreaker", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(
        chainbreaker,
        *scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[bears],
    )
    scenario.resolve_top()

    assert bears.counters == {} or not any(bears.counters.values())
    assert scenario.game.unmodeled_trigger_effect_notices == []


# -- Decimator Beetle: remove from one target, put on another ----------------


def test_decimator_beetle_moves_the_counter_from_its_first_target_to_its_second():
    """Each half acts on its own target (CR 115.1d: both chosen as the
    trigger goes on the stack, in printed order): the counter comes off
    alice's creature and one goes on bob's, never both on both."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Decimator Beetle", "Craw Wurm"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    beetle = scenario.creature("Decimator Beetle", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    wurm.add_counters("-1/-1", 1)
    scenario.will_choose_targets(wurm, giant, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(beetle)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert wurm.counter_count("-1/-1") == 0
    assert giant.counter_count("-1/-1") == 1


def test_decimator_beetle_with_no_second_target_only_removes():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Decimator Beetle", "Craw Wurm"])
        .player("bob")
        .build()
    )
    beetle = scenario.creature("Decimator Beetle", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    wurm.add_counters("-1/-1", 2)
    scenario.will_choose_targets(wurm, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(beetle)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert wurm.counter_count("-1/-1") == 1

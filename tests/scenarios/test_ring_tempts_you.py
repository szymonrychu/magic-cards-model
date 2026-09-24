"""Scenario: the Ring tempts you (CR 701.54), the keyword action Gollum,
Patient Plotter's leaves-the-battlefield trigger performs.

Read out of the Comprehensive Rules on disk this session with `mise run
rules:find 701.54`:

- **CR 701.54a** - "Each time the Ring tempts you, choose a creature you
  control. That creature becomes your Ring-bearer until another creature
  becomes your Ring-bearer or another player gains control of it."
- **CR 701.54b** - "Ring-bearer is a designation a permanent can have."
- **CR 701.54c** - "If a player doesn't have an emblem named The Ring at the
  time the Ring tempts them, they get an emblem named The Ring before choosing
  a creature to be their Ring-bearer. The Ring has 'Your Ring-bearer is
  legendary and can't be blocked by creatures with greater power.'" - and,
  as long as the Ring has tempted that player two, three, four or more times,
  the loot-on-attack, sacrifice-the-blocker and each-opponent-loses-3 abilities.
- **CR 701.54d** - "The Ring tempts a player whenever they complete the
  actions in 701.54a, even if some or all of those actions were impossible."
- **CR 701.54e** - "is your Ring-bearer" is true only for a creature "on the
  battlefield under your control" with the designation.

Around it: CR 114.2/114.4 (the emblem is in the command zone, owned and
controlled by that player, and its abilities function there), CR 400.7 (a
Ring-bearer that changes zones is a new object without the designation), CR
613.1d/613.1f (legendary is a layer 4 supertype change, the evasion a layer 6
ability), CR 509.3d ("becomes blocked by a creature" triggers once for each
blocker), CR 511.2 ("at end of combat"), CR 701.21a (the blocker's own
controller is the one who sacrifices it) and CR 608.2d (the Ring-bearer is
chosen while the effect is applied).

Gollum, Patient Plotter is the listed card. The template is proven on three
more printings, none in the api decks: Took Reaper ("When this creature dies,
the Ring tempts you."), Claim the Precious ("Destroy target creature. The Ring
tempts you.", the spell form) and Nazgul (the enters form, plus "Whenever the
Ring tempts you, ..."). Nazgul is also how the Ring's later levels are
reached: every copy put onto the battlefield tempts its controller once.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.card_state import CardState, Counter

from .harness import PlayedScenario, Scenario

NAZGUL = "Nazgûl"


def _is_legendary(scenario: PlayedScenario, permanent: CardState) -> bool:
    return Supertype.LEGENDARY in scenario.game.characteristics_of(permanent).supertypes


def _the_ring(scenario: PlayedScenario, username: str) -> CardState | None:
    rings = [emblem for emblem in scenario.game.emblems_of(username) if emblem.name == "The Ring"]
    assert len(rings) <= 1, "CR 701.54c: one emblem named The Ring, never a second"
    return rings[0] if rings else None


def _tempted(scenario: PlayedScenario, username: str) -> int:
    return scenario.player(username).ring_tempted_count


def _resolve_everything(scenario: PlayedScenario) -> None:
    """Put whatever has triggered on the stack (CR 603.3) and resolve it all,
    including anything those resolutions trigger in turn."""
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _nazgul_tempts(scenario: PlayedScenario, bearer: CardState, times: int) -> None:
    """Put `times` Nazgul from alice's hand onto the battlefield, one at a
    time, choosing `bearer` as the Ring-bearer each time the Ring tempts her
    (CR 608.2d) - the staging for the Ring's later levels."""
    for _ in range(times):
        scenario.will_choose_cards(bearer, username="alice")
        scenario.put_onto_battlefield(NAZGUL, "alice")
        _resolve_everything(scenario)


def walk_to(scenario: PlayedScenario, step: Step) -> None:
    """Advance - never jump - to `step`, resolving whatever fires on the way.
    `start_at` emits no step events, so a delayed "at end of combat" trigger
    is only proven by walking there (CR 511.2)."""
    while scenario.step is not step:
        scenario.advance()
        _resolve_everything(scenario)


# -- the keyword action itself ------------------------------------------------


def test_the_ring_tempts_you_is_reported_as_executed_by_the_pool_sweeper():
    """A CR 701 keyword action embedded in another ability's text, the same
    shape amass and investigate are: `scripts/sweep_pool.py` reads
    `machines/keywords.executes` and cannot tell "known" from "unknown"
    without being told."""
    assert executes("The Ring Tempts You") is True
    assert executes("the ring tempts you") is True


def test_gollum_leaving_the_battlefield_tempts_its_controller():
    """Gollum dies to Lightning Bolt; its leaves-the-battlefield trigger makes
    the Ring tempt alice. She gets the emblem (CR 701.54c, CR 114.2), her only
    creature becomes her Ring-bearer (CR 701.54a) and is legendary (layer 4)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Gollum, Patient Plotter", "Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter")
    bears = scenario.creature("Grizzly Bears")
    assert _the_ring(scenario, "alice") is None
    assert not _is_legendary(scenario, bears)

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[gollum])
    _resolve_everything(scenario)

    assert gollum.zone is Zone.GRAVEYARD
    ring = _the_ring(scenario, "alice")
    assert ring is not None
    assert ring.zone is Zone.COMMAND
    assert ring.owner == "alice" and ring.controller == "alice"
    assert _tempted(scenario, "alice") == 1
    assert scenario.game.ring_bearer_of("alice") is bears
    assert _is_legendary(scenario, bears)
    assert _the_ring(scenario, "bob") is None
    assert scenario.game.ring_bearer_of("bob") is None


def test_gollum_bounced_to_hand_still_tempts():
    """ "Leaves the battlefield" is every departure (CR 603.6c), not only a
    death: Gollum returned to hand by Unsummon tempts alice all the same."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unsummon"],
            battlefield=["Gollum, Patient Plotter", "Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter")
    bears = scenario.creature("Grizzly Bears")

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[gollum])
    _resolve_everything(scenario)

    assert gollum.zone is Zone.HAND
    assert _tempted(scenario, "alice") == 1
    assert scenario.game.ring_bearer_of("alice") is bears


def test_tempting_with_no_creature_still_levels_the_ring_up():
    """CR 701.54d: the Ring tempts a player "even if some or all of those
    actions were impossible". Gollum was alice's only creature, so there is
    nothing to choose - she still gets the emblem, the count still rises, and
    she simply has no Ring-bearer."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Gollum, Patient Plotter", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter")
    bobs_bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[gollum])
    _resolve_everything(scenario)

    assert _tempted(scenario, "alice") == 1
    assert _the_ring(scenario, "alice") is not None
    assert scenario.game.ring_bearer_of("alice") is None
    assert not _is_legendary(scenario, bobs_bears), "an opponent's creature is never chosen"


def test_the_levels_gained_with_no_creature_apply_to_the_next_ring_bearer():
    """The count is the player's, not the bearer's: a tempt with nothing to
    choose still counts, so the creature chosen at the second tempt gets the
    level 2 loot straight away."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            hand=["Lightning Bolt", NAZGUL],
            battlefield=["Gollum, Patient Plotter", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[gollum])
    _resolve_everything(scenario)
    assert scenario.game.ring_bearer_of("alice") is None

    nazgul = scenario.put_onto_battlefield(NAZGUL, "alice")
    _resolve_everything(scenario)

    assert _tempted(scenario, "alice") == 2
    assert scenario.game.ring_bearer_of("alice") is nazgul
    ring = _the_ring(scenario, "alice")
    assert ring is not None
    assert "draw a card, then discard a card" in ring.oracle_text


def test_the_ring_bearer_is_chosen_among_several_creatures():
    """CR 608.2d: with more than one creature the choice is asked, and the
    answer given is the one that becomes the Ring-bearer."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Gollum, Patient Plotter", "Grizzly Bears", "Runeclaw Bear", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter")
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear")

    scenario.will_choose_cards(runeclaw, username="alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[gollum])
    _resolve_everything(scenario)

    assert scenario.game.ring_bearer_of("alice") is runeclaw
    assert _is_legendary(scenario, runeclaw)
    assert not _is_legendary(scenario, bears)


def test_a_new_ring_bearer_replaces_the_old_one():
    """CR 701.54a: a creature is the Ring-bearer "until another creature
    becomes your Ring-bearer" - the old one stops being legendary, the new one
    starts, and the count is the sum of both tempts."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL, NAZGUL], battlefield=["Grizzly Bears", "Runeclaw Bear"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear")

    _nazgul_tempts(scenario, bears, 1)
    assert scenario.game.ring_bearer_of("alice") is bears
    assert _is_legendary(scenario, bears)

    _nazgul_tempts(scenario, runeclaw, 1)
    assert _tempted(scenario, "alice") == 2
    assert scenario.game.ring_bearer_of("alice") is runeclaw
    assert _is_legendary(scenario, runeclaw)
    assert not _is_legendary(scenario, bears)


def test_the_same_creature_may_be_chosen_again():
    """Nothing in CR 701.54a forbids choosing the current Ring-bearer again;
    it simply stays the Ring-bearer while the count rises."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL, NAZGUL], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    _nazgul_tempts(scenario, bears, 2)

    assert _tempted(scenario, "alice") == 2
    assert scenario.game.ring_bearer_of("alice") is bears


def test_a_ring_bearer_that_changes_zones_is_a_new_object_without_the_designation():
    """CR 400.7: bounced and replayed, the Grizzly Bears is a new object - not
    the Ring-bearer and not legendary - while the Ring itself keeps its count."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL, "Unsummon"], battlefield=["Grizzly Bears", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    _nazgul_tempts(scenario, bears, 1)
    assert scenario.game.ring_bearer_of("alice") is bears

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[bears])
    assert scenario.game.ring_bearer_of("alice") is None
    replayed = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert scenario.game.ring_bearer_of("alice") is None
    assert not _is_legendary(scenario, replayed)
    assert _tempted(scenario, "alice") == 1


def test_another_player_gaining_control_ends_the_designation_for_good():
    """CR 701.54a: the creature is the Ring-bearer "until ... another player
    gains control of it". Bob's Act of Treason takes the Ring-bearer: it is no
    longer alice's Ring-bearer, and not legendary under bob, who has no Ring.
    When control comes back at cleanup it is still not her Ring-bearer - the
    designation ended, it was not suspended."""
    scenario = (
        Scenario()
        .player("bob", hand=["Act of Treason"], battlefield=["Mountain"] * 3)
        .player("alice", hand=[NAZGUL], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 1)
    assert scenario.game.ring_bearer_of("alice") is bears

    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Act of Treason", *mountains, targets=[bears])

    assert scenario.game.controller_of(bears).username == "bob"
    assert scenario.game.ring_bearer_of("alice") is None
    assert scenario.game.ring_bearer_of("bob") is None
    assert not _is_legendary(scenario, bears)

    while scenario.turn.active_player != "alice":
        scenario.advance()
        _resolve_everything(scenario)

    assert scenario.game.controller_of(bears).username == "alice"
    assert scenario.game.ring_bearer_of("alice") is None
    assert not _is_legendary(scenario, bears)


def test_each_player_has_a_ring_of_their_own():
    """CR 701.54c's emblem is per player: bob's tempt gives bob his own Ring
    and his own count, and leaves alice's untouched."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL, NAZGUL], battlefield=["Grizzly Bears"])
        .player("bob", hand=[NAZGUL], battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    _nazgul_tempts(scenario, bears, 2)

    scenario.will_choose_cards(runeclaw, username="bob")
    scenario.put_onto_battlefield(NAZGUL, "bob")
    _resolve_everything(scenario)

    assert _tempted(scenario, "alice") == 2
    assert _tempted(scenario, "bob") == 1
    assert scenario.game.ring_bearer_of("alice") is bears
    assert scenario.game.ring_bearer_of("bob") is runeclaw
    assert _the_ring(scenario, "alice") is not _the_ring(scenario, "bob")


def test_the_ring_gains_its_abilities_one_level_at_a_time():
    """CR 701.54c: two, three and four tempts each add one ability, and
    tempts past four add nothing further."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL] * 5, battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    levels = [
        "can't be blocked by creatures with greater power",
        "draw a card, then discard a card",
        "sacrifices it at end of combat",
        "each opponent loses 3 life",
    ]
    for level in range(1, 6):
        _nazgul_tempts(scenario, bears, 1)
        ring = _the_ring(scenario, "alice")
        assert ring is not None
        text = ring.oracle_text
        for index, ability in enumerate(levels, start=1):
            assert (ability in text) is (index <= level), (level, ability)
        assert text.count("Your Ring-bearer is legendary") == 1
    assert _tempted(scenario, "alice") == 5


def test_a_ring_bearer_is_legendary_but_alone_does_not_trip_the_legend_rule():
    """Only the Ring-bearer becomes legendary (layer 4), so a second Grizzly
    Bears beside it is no second legendary permanent with that name and CR
    704.5j has nothing to do."""
    scenario = (
        Scenario()
        .player("alice", hand=[NAZGUL], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    _nazgul_tempts(scenario, first, 1)
    scenario.state_based_actions()

    assert first.zone is Zone.BATTLEFIELD and second.zone is Zone.BATTLEFIELD
    assert _is_legendary(scenario, first)
    assert not _is_legendary(scenario, second)


# -- level 1: can't be blocked by creatures with greater power --------------


def _ring_combat(alice_hand: list[str], bob_battlefield: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            hand=alice_hand,
            battlefield=["Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 4, battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _to_declare_attackers(scenario: PlayedScenario) -> None:
    walk_to(scenario, Step.DECLARE_ATTACKERS)


def test_level_one_a_greater_power_blocker_is_refused():
    scenario = _ring_combat([NAZGUL], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _nazgul_tempts(scenario, bears, 1)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    assert not scenario.game.can_block(giant, bears)
    with pytest.raises(ValueError, match="greater power"):
        scenario.block(bears, giant)
    assert scenario.game.evasion_notices == [], "read, not failed closed"


def test_level_one_an_equal_power_blocker_is_allowed():
    """ "Greater" is strictly greater: a 2-power blocker may block a 2-power
    Ring-bearer."""
    scenario = _ring_combat([NAZGUL], ["Runeclaw Bear"])
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    _nazgul_tempts(scenario, bears, 1)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    assert scenario.game.can_block(runeclaw, bears)
    scenario.block(bears, runeclaw)
    assert scenario.game.is_blocked(bears)
    assert scenario.game.evasion_notices == []


def test_the_greater_power_restriction_is_only_on_the_ring_bearer():
    """A creature that is not the Ring-bearer has no such restriction: once
    the designation moves on, the Hill Giant may block the old bearer."""
    scenario = _ring_combat([NAZGUL, NAZGUL], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _nazgul_tempts(scenario, bears, 1)
    first_nazgul = scenario.creature(NAZGUL, "alice")
    _nazgul_tempts(scenario, first_nazgul, 1)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    assert scenario.game.can_block(giant, bears)


def test_level_one_attacking_does_not_loot():
    scenario = _ring_combat([NAZGUL], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 1)
    _to_declare_attackers(scenario)
    hand = len(scenario.player("alice").hand)
    library = len(scenario.player("alice").library)

    scenario.attack_with(bears)
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == hand
    assert len(scenario.player("alice").library) == library


# -- level 2: loot on attack -------------------------------------------------


def test_level_two_the_ring_bearer_attacking_draws_then_discards():
    scenario = _ring_combat([NAZGUL, NAZGUL], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 2)
    _to_declare_attackers(scenario)
    alice = scenario.player("alice")
    hand, library, graveyard = len(alice.hand), len(alice.library), len(alice.graveyard)

    scenario.attack_with(bears)
    _resolve_everything(scenario)

    assert len(alice.library) == library - 1
    assert len(alice.hand) == hand
    assert len(alice.graveyard) == graveyard + 1


def test_level_two_another_attacker_does_not_loot():
    """ "Whenever your Ring-bearer attacks" - a Nazgul attacking beside a
    Ring-bearer that stays home draws nothing."""
    scenario = _ring_combat([NAZGUL, NAZGUL], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 2)
    walk_to(scenario, Step.CLEANUP)
    while scenario.turn.active_player != "alice" or scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
        _resolve_everything(scenario)
    nazgul = scenario.creatures(NAZGUL, username="alice")[0]
    alice = scenario.player("alice")
    library = len(alice.library)

    scenario.attack_with(nazgul)
    _resolve_everything(scenario)

    assert len(alice.library) == library


# -- level 3: the blocker is sacrificed at end of combat --------------------


def test_level_three_a_blocker_is_sacrificed_at_end_of_combat():
    """CR 509.3d / CR 511.2 / CR 701.21a: Giant Spider survives the Bears'
    2 damage, and is sacrificed by bob, its controller, as the end of combat
    step begins - not before."""
    scenario = _ring_combat([NAZGUL] * 3, ["Giant Spider"])
    bears = scenario.creature("Grizzly Bears", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    _nazgul_tempts(scenario, bears, 3)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)
    scenario.block(bears, spider)
    _resolve_everything(scenario)
    assert spider.zone is Zone.BATTLEFIELD, "waits for end of combat"

    walk_to(scenario, Step.COMBAT_DAMAGE)
    assert spider.zone is Zone.BATTLEFIELD
    assert spider.damage == 2

    walk_to(scenario, Step.END_OF_COMBAT)
    assert spider.zone is Zone.GRAVEYARD
    assert spider.owner == "bob"


def test_level_three_each_blocker_triggers_separately():
    """CR 509.3d: "becomes blocked by a creature" triggers once for each
    creature that blocks - two Giant Spiders, two sacrifices, even though the
    Ring-bearer itself dies to their damage first."""
    scenario = _ring_combat([NAZGUL] * 3, ["Giant Spider", "Giant Spider"])
    bears = scenario.creature("Grizzly Bears", "alice")
    spiders = scenario.creatures("Giant Spider", "Giant Spider", username="bob")
    _nazgul_tempts(scenario, bears, 3)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)
    scenario.block(bears, *spiders)
    _resolve_everything(scenario)

    walk_to(scenario, Step.END_OF_COMBAT)
    assert bears.zone is Zone.GRAVEYARD
    assert all(spider.zone is Zone.GRAVEYARD for spider in spiders)


def test_level_three_a_blocker_that_already_left_is_not_sacrificed():
    """CR 603.7c: the delayed ability refers to the blocking Giant Spider on
    the battlefield. Bounced by alice's Unsummon before end of combat, it is
    a new object in bob's hand, and nothing is sacrificed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            hand=[NAZGUL] * 3 + ["Unsummon"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob", library=["Island"] * 4, battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    _nazgul_tempts(scenario, bears, 3)
    _to_declare_attackers(scenario)
    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)
    scenario.block(bears, spider)
    _resolve_everything(scenario)

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[spider])
    assert spider.zone is Zone.HAND
    walk_to(scenario, Step.END_OF_COMBAT)

    assert spider.zone is Zone.HAND
    assert scenario.player("bob").graveyard == []


def test_level_two_a_blocker_is_not_sacrificed():
    scenario = _ring_combat([NAZGUL] * 2, ["Giant Spider"])
    bears = scenario.creature("Grizzly Bears", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    _nazgul_tempts(scenario, bears, 2)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)
    scenario.block(bears, spider)
    _resolve_everything(scenario)
    walk_to(scenario, Step.END_OF_COMBAT)

    assert spider.zone is Zone.BATTLEFIELD


# -- level 4: each opponent loses 3 life -------------------------------------


def test_level_four_combat_damage_to_a_player_costs_each_opponent_three_life():
    scenario = _ring_combat([NAZGUL] * 4, [])
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 4)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.END_OF_COMBAT)

    assert scenario.player("bob").life == 20 - 2 - 3
    assert scenario.player("alice").life == 20


def test_level_three_combat_damage_costs_nothing_extra():
    scenario = _ring_combat([NAZGUL] * 3, [])
    bears = scenario.creature("Grizzly Bears", "alice")
    _nazgul_tempts(scenario, bears, 3)
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)
    _resolve_everything(scenario)
    walk_to(scenario, Step.END_OF_COMBAT)

    assert scenario.player("bob").life == 20 - 2


# -- the template on other printings -----------------------------------------


def test_gollum_returns_from_the_graveyard_by_sacrificing_a_creature():
    """Gollum's other ability, "{B}, Sacrifice a creature: Return this card
    from your graveyard to your hand. Activate only as a sorcery." - the
    rest of the listed card, working from the graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice", graveyard=["Gollum, Patient Plotter"], battlefield=["Grizzly Bears", "Swamp"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.find("Gollum, Patient Plotter", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.activate(gollum, swamp, sacrificing=[bears])
    _resolve_everything(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Gollum, Patient Plotter", Zone.HAND, "alice") is not None


def test_took_reaper_dying_tempts_its_controller():
    """ "When this creature dies, the Ring tempts you." - the dies form."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Took Reaper", "Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reaper = scenario.creature("Took Reaper")
    bears = scenario.creature("Grizzly Bears")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[reaper])
    _resolve_everything(scenario)

    assert _tempted(scenario, "alice") == 1
    assert scenario.game.ring_bearer_of("alice") is bears


def test_claim_the_precious_destroys_then_tempts_its_caster():
    """A spell's own "The Ring tempts you." after a targeted clause: the
    target is destroyed and the caster - not the target's controller - is
    tempted."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Claim the Precious"],
            battlefield=["Grizzly Bears", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Claim the Precious", *swamps, targets=[runeclaw])

    assert runeclaw.zone is Zone.GRAVEYARD
    assert _tempted(scenario, "alice") == 1
    assert _tempted(scenario, "bob") == 0
    assert scenario.game.ring_bearer_of("alice") is bears


def test_nazgul_whenever_the_ring_tempts_you_grows_each_wraith():
    """ "Whenever the Ring tempts you, put a +1/+1 counter on each Wraith you
    control." - its own enters trigger tempts, and the tempt triggers it."""
    scenario = Scenario().player("alice", hand=[NAZGUL, NAZGUL]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = scenario.put_onto_battlefield(NAZGUL, "alice")
    _resolve_everything(scenario)
    assert first.counters[Counter.PLUS_ONE] == 1

    scenario.will_choose_cards(first, username="alice")
    second = scenario.put_onto_battlefield(NAZGUL, "alice")
    _resolve_everything(scenario)

    # Two Nazgul, two "whenever the Ring tempts you" triggers, each putting a
    # counter on each Wraith.
    assert first.counters[Counter.PLUS_ONE] == 1 + 2
    assert second.counters[Counter.PLUS_ONE] == 2
    assert _tempted(scenario, "alice") == 2


def test_nazgul_triggers_on_a_tempt_from_another_source():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=[NAZGUL, "Gollum, Patient Plotter", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nazgul = scenario.creature(NAZGUL)
    gollum = scenario.creature("Gollum, Patient Plotter")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[gollum])
    _resolve_everything(scenario)

    assert nazgul.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.ring_bearer_of("alice") is nazgul


def test_an_opponents_tempt_does_not_trigger_nazgul():
    """ "Whenever the Ring tempts **you**" - bob's Gollum tempts bob, and
    alice's Nazgul watches only alice. Bob is the active player, so the Bolt
    is his to cast."""
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Gollum, Patient Plotter", "Mountain"])
        .player("alice", battlefield=[NAZGUL])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nazgul = scenario.creature(NAZGUL, "alice")
    gollum = scenario.creature("Gollum, Patient Plotter", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[gollum])
    _resolve_everything(scenario)

    assert _tempted(scenario, "bob") == 1
    assert _tempted(scenario, "alice") == 0
    assert nazgul.counters[Counter.PLUS_ONE] == 0

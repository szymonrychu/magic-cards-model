"""Activating abilities "as though those creatures had haste" (CR 609.4, 702.10c).

Tyvar, Jubilant Brawler and Shang-Chi, Master of Kung Fu print the same static
sentence: "You may activate abilities of creatures you control as though those
creatures had haste."

The rules that decide what it does, looked up in the session that wrote this
file (`mise run rules:find`, against `.rules/MagicCompRules.txt`, "effective as
of August 7, 2026"):

- **CR 302.6** - "A creature's activated ability with the tap symbol or the
  untap symbol in its activation cost can't be activated unless the creature
  has been under its controller's control continuously since their most recent
  turn began. A creature can't attack unless it has been under its controller's
  control continuously since their most recent turn began. This rule is
  informally called the "summoning sickness" rule." Two restrictions, one name.
- **CR 702.10b** - "If a creature has haste, it can attack even if it hasn't
  been controlled by its controller continuously since their most recent turn
  began."
- **CR 702.10c** - "If a creature has haste, its controller can activate its
  activated abilities whose cost includes the tap symbol or the untap symbol
  even if that creature hasn't been controlled by that player continuously
  since their most recent turn began."
- **CR 609.4** - "Some effects state that a player may do something "as though"
  some condition were true or a creature can do something "as though" some
  condition were true. **This applies only to the stated effect.** For purposes
  of that effect, treat the game exactly as if the stated condition were true.
  For all other purposes, treat the game normally."

CR 609.4's second sentence is the whole shape of this file. The stated effect
is *activating abilities*, so only CR 702.10c's half of haste is borrowed;
CR 702.10b's attacking half is not, and a creature the grant reaches still
cannot attack the turn it arrives. Nor does the creature gain the haste
keyword - nothing else that reads haste sees anything.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.models.card import Card, Color
from magic_cards_model.models.game import (
    _HASTE_ACTIVATION_PERMISSION_RE,
    _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE,
)
from magic_cards_model.models.zone import Zone
from tests.cards import pool
from tests.scenarios.harness import Scenario

TYVAR = "Tyvar, Jubilant Brawler"
SHANG_CHI = "Shang-Chi, Master of Kung Fu"
DRUID = "Devoted Druid"


def all_printings() -> list[Card]:
    """Every real Scryfall printing the engine ships."""
    return sorted({card.id: card for card in pool().values()}.values(), key=lambda c: c.name)


def static_lines(card: Card) -> list[str]:
    return [
        (line.text or "").strip()
        for line in parse_abilities(card)
        if line.kind is AbilityKind.STATIC
    ]


def board(*battlefield: str, opponent: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=[DRUID], battlefield=list(battlefield), library=["Forest"] * 5)
        .player("bob", battlefield=list(opponent or []), library=["Forest"] * 5)
    )


def fresh_druid(scenario):
    """A Devoted Druid cast this turn - summoning sick by CR 302.6."""
    forests = scenario.untapped_sources("Forest", "Forest")
    druid = scenario.cast_and_resolve(DRUID, *forests)
    assert druid.summoning_sick, "it did arrive this turn"
    return druid


# -- the grant reaches a tap ability (CR 609.4 + CR 702.10c) ----------------


def test_tyvar_lets_a_summoning_sick_druid_activate_its_tap_ability():
    """The reported line: Tyvar out, Devoted Druid cast this turn, `{T}: Add {G}`."""
    scenario = board(TYVAR, "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    assert scenario.game.can_activate_tap_ability(druid)
    assert scenario.why_cannot_activate(druid, index=0) is None

    scenario.activate(druid, index=0)

    assert druid.tapped
    assert scenario.player("alice").mana_pool.floating


def test_the_devoted_druid_loop_runs_the_turn_the_druid_arrives():
    """Tap for {G}, then untap by paying a -1/-1 counter - the archetype's own
    line, on the turn the Druid lands, which is the whole point of Tyvar."""
    scenario = board(TYVAR, "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    scenario.activate(druid, index=0)
    assert druid.tapped
    scenario.activate(druid, index=1)
    scenario.pass_until_resolved()

    assert not druid.tapped, "CR 701.26b: the untap ability resolved"
    assert druid.toughness == 1, "one -1/-1 counter off a printed 0/2"


def test_the_grant_is_not_limited_to_mana_abilities():
    """Devoted Druid's untap ability costs a counter, not `{T}` - the grant is
    about CR 302.6's restriction, so an ability with no `{T}` was never gated."""
    scenario = board(TYVAR, "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    assert scenario.why_cannot_activate(druid, index=1) is None


def test_shang_chi_grants_it_to_itself():
    """ "Creatures you control" has no "other" in it, so the granting creature is
    inside its own subject and may activate its own `{T}` the turn it arrives."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SHANG_CHI],
            battlefield=["Forest", "Forest"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")
    shang_chi = scenario.cast_and_resolve(SHANG_CHI, *forests)
    assert shang_chi.summoning_sick

    assert scenario.game.can_activate_tap_ability(shang_chi)
    scenario.activate(shang_chi, index=0, color=Color.GREEN)

    assert shang_chi.tapped


# -- the inverse: summoning sickness still works (CR 302.6) -----------------


def test_without_the_grant_a_fresh_druid_is_still_refused():
    scenario = board("Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    assert not scenario.game.can_activate_tap_ability(druid)
    refusal = scenario.why_cannot_activate(druid, index=0)
    assert refusal is not None and "most recent turn began" in refusal


def test_an_opponents_tyvar_does_not_reach_your_creatures():
    """ "Creatures **you** control" - "you" is the static's own controller."""
    scenario = board("Forest", "Forest", opponent=[TYVAR]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    assert not scenario.game.can_activate_tap_ability(druid)


def test_the_grant_stops_when_its_source_leaves_the_battlefield():
    """CR 604.2 / CR 611.3a: a static ability's continuous effect is active
    only while its source is on the battlefield, and is not "locked in"."""
    scenario = board(TYVAR, "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)
    assert scenario.game.can_activate_tap_ability(druid)

    tyvar = scenario.find(TYVAR, Zone.BATTLEFIELD, "alice")
    scenario.game.put_into_graveyard(tyvar)

    assert not scenario.game.can_activate_tap_ability(druid)


# -- CR 609.4: only the stated effect ---------------------------------------


def test_the_grant_does_not_let_a_summoning_sick_creature_attack():
    """CR 609.4: "This applies only to the stated effect." The stated effect is
    activating abilities, so CR 702.10b's attacking permission is not borrowed
    and CR 302.6's second sentence still refuses."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=[TYVAR, "Forest", "Forest"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", *forests)

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers

    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError, match="summoning sickness"):
        scenario.attack_with(bears)


def test_the_grant_does_not_give_the_haste_keyword():
    """CR 609.4 again: the creature does not *have* haste, so nothing that
    reads the keyword off the computed board (CR 613.5) sees one."""
    scenario = board(TYVAR, "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = fresh_druid(scenario)

    computed = scenario.game.characteristics_of(druid)
    assert not any("haste" in ability.lower() for ability in computed.abilities)


# -- no regression on the permanents CR 302.6 never covered -----------------


def test_a_land_still_taps_the_turn_it_arrives_with_no_grant_in_play():
    """CR 302.6 restricts "a creature's" tap abilities; a land was never in it."""
    scenario = Scenario().player("alice", hand=["Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert scenario.game.can_activate_tap_ability(forest)


# -- the shape, and what it fails closed on ---------------------------------


def test_every_printing_carrying_this_sentence_is_read_by_the_strict_shape():
    """The whole card pool, not a name list: any static line that opens like
    this family must parse, or the engine is silently granting nothing while a
    card says otherwise. Two printings carry it today (Tyvar, Jubilant Brawler
    and Shang-Chi, Master of Kung Fu) and this is what notices a third."""
    looks_like = [
        (card.name, line)
        for card in all_printings()
        for line in static_lines(card)
        if _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE.match(line)
    ]

    assert {name for name, _ in looks_like} == {TYVAR, SHANG_CHI}
    unread = [
        (name, line) for name, line in looks_like if not _HASTE_ACTIVATION_PERMISSION_RE.match(line)
    ]
    assert unread == []


def test_a_subject_this_engine_cannot_read_fails_closed():
    """A qualified subject is caught by the loose shape and refused by the
    strict one, which is what puts a `LayerNotice` on the board instead of
    granting the permission to every creature its controller has. No printing
    in the pool is this shape - the assertion is about the readers, so that a
    future one is recorded rather than silently rounded up."""
    qualified = (
        "You may activate abilities of Elf creatures you control "
        "as though those creatures had haste."
    )

    assert _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE.match(qualified)
    assert _HASTE_ACTIVATION_PERMISSION_RE.match(qualified) is None


def test_an_attacking_permission_is_not_this_sentence():
    """ "as though it had haste" attached to attacking is a different effect
    (CR 702.10b), and this reader must not claim it - it opens with "may
    attack", not "may activate"."""
    attacking = "Creatures you control can attack as though they had haste."

    assert _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE.match(attacking) is None

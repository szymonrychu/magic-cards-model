"""SOS's damage riders: a targeted damage clause followed by a second
sentence that acts on the same target (CR 400.7 anaphora), or an optional
resolution-time cost that adds more.

- **Duel Tactics** - "Duel Tactics deals 1 damage to target creature. It
  can't block this turn." CR 509.1b's mirror of the already-handled "can't
  be blocked" rider (`machines/effects._RIDER_CANT_BE_BLOCKED_RE`), granted
  the identical way: the self line "This creature can't block."
  (`machines/combat.py`'s own blocker restriction) for the rest of the turn.
  No second Modern/Pioneer/Standard-legal printing of this exact "damage to
  target creature. It can't block this turn." template plays end to end:
  `card_search`/Scryfall turn up only Searing Barb (an "any target"
  antecedent gated by "If it's a creature," - and a real printing that is
  *itself* silent, CR 608.2c failing the whole spell closed because of its
  unrelated, unimplemented Incubate keyword action - not a card this reader
  can honestly claim as proof), Puppet Master, String Puller (not legal in
  any of the three formats) and Ydwen Efreet (a self-referential "it" inside
  one sentence, a different composition entirely). See MEMORY.md's dated
  line. Generality is instead proven within this file by exercising the
  reader across Duel Tactics' own two ways onto the stack - cast normally
  and cast again from the graveyard via flashback (CR 702.34a) - and by
  checking the grant does not survive past the turn it was made on (CR
  514.2).
- **Heated Argument** - "Heated Argument deals 6 damage to target creature.
  You may exile a card from your graveyard. If you do, Heated Argument also
  deals 2 damage to that creature's controller." CR 118.12's optional
  resolution-time cost (a graveyard card chosen and exiled, CR 608.2d)
  gating a second instance of damage to the first sentence's own target's
  controller, read before the first damage might remove that creature from
  the battlefield.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 509.1b** - a restriction against blocking makes a block declaring it
  illegal.
- **CR 400.7** - the pronoun/demonstrative anaphora naming the antecedent's
  own found object.
- **CR 702.34a** - Flashback: casting the card from the graveyard by paying
  its flashback cost, then exiling it instead of letting it go anywhere
  else when it leaves the stack.
- **CR 118.12** - "[a player] may [do something]. If [that player] does,
  [effect]" - the shape backing the graveyard-exile rider.
- **CR 608.2d** - the player announces choices (which card to exile) while
  applying a resolving effect.
- **CR 120.3a** - damage to a player causes that much life loss.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

DUEL_TACTICS = "Duel Tactics"
HEATED_ARGUMENT = "Heated Argument"


def test_duel_tactics_damages_the_target_and_it_cant_block():
    scenario = (
        Scenario()
        .player("alice", hand=[DUEL_TACTICS], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve(DUEL_TACTICS, mountain, targets=[bears])

    assert bears.damage == 1
    board = scenario.game.computed_board()
    assert "This creature can't block." in board.of(bears).abilities


def test_duel_tactics_grant_is_only_until_end_of_turn():
    scenario = (
        Scenario()
        .player("alice", hand=[DUEL_TACTICS], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve(DUEL_TACTICS, mountain, targets=[bears])
    board = scenario.game.computed_board()
    assert "This creature can't block." in board.of(bears).abilities

    scenario.game.cleanup_step()  # CR 514.2's own expiry, run directly
    board_after_cleanup = scenario.game.computed_board()
    assert "This creature can't block." not in board_after_cleanup.of(bears).abilities


def _flashback(scenario, name: str, targets=None):
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    if targets is not None:
        casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_duel_tactics_cast_from_the_graveyard_via_flashback_still_grants_cant_block():
    """The off-pool generality proof this reader actually has: no second
    real printing of the template plays end to end (see the module
    docstring and MEMORY.md's dated line), so generality is instead proven
    by driving the *same* reader through Duel Tactics' own second, distinct
    way onto the stack - CR 702.34a's flashback, an alternative cost and a
    different origin zone from a fresh cast, exercising the exact same
    `_parse_referent_object_clause` composition the front-face cast above
    already used."""
    scenario = (
        Scenario()
        .player("alice", graveyard=[DUEL_TACTICS], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _flashback(scenario, DUEL_TACTICS, targets=[bears])

    assert bears.damage == 1
    board = scenario.game.computed_board()
    assert "This creature can't block." in board.of(bears).abilities
    duel_tactics = scenario.find(DUEL_TACTICS, Zone.EXILE, "alice")
    assert duel_tactics.zone is Zone.EXILE  # CR 702.34a's own flashback exile, not the graveyard


BIG_CREATURE = "Atraxa, Grand Unifier"  # 7/7: survives the 6 damage, so `.damage`
# stays checkable afterward rather than being cleared by CR 400.7's own zone change.


def _heated_argument_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[HEATED_ARGUMENT],
            graveyard=["Mountain"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=[BIG_CREATURE])
    )


def test_heated_argument_exiling_a_card_deals_the_extra_damage_to_the_controller():
    scenario = _heated_argument_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    target = scenario.creature(BIG_CREATURE, "bob")
    life_before = bob.life
    mountain = alice.graveyard[0]
    scenario.will_take_the_may(True, source=HEATED_ARGUMENT)
    scenario.will_choose_cards(mountain, source=HEATED_ARGUMENT)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve(HEATED_ARGUMENT, *sources, targets=[target])

    assert target.damage == 6
    assert bob.life == life_before - 2
    assert mountain.zone is Zone.EXILE
    assert mountain not in alice.graveyard


def test_heated_argument_declining_the_exile_deals_no_extra_damage():
    scenario = _heated_argument_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    target = scenario.creature(BIG_CREATURE, "bob")
    life_before = bob.life
    scenario.will_take_the_may(False, source=HEATED_ARGUMENT)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve(HEATED_ARGUMENT, *sources, targets=[target])

    assert target.damage == 6
    assert bob.life == life_before


def test_heated_argument_with_an_empty_graveyard_offers_no_exile_and_deals_no_extra_damage():
    """CR 608.2d: "you may exile a card from your graveyard" is not offered
    at all when the graveyard is empty - there is no legal card to choose."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HEATED_ARGUMENT],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=[BIG_CREATURE])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    target = scenario.creature(BIG_CREATURE, "bob")
    life_before = bob.life
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve(HEATED_ARGUMENT, *sources, targets=[target])

    assert target.damage == 6
    assert bob.life == life_before
    assert scenario.questions_asked() == []


def test_heated_argument_still_damages_the_controller_even_though_the_target_died():
    """CR 400.7: "that creature's controller" is read off the target as it
    was found, before the first 6 damage puts it in the graveyard as a state-
    based action (CR 704.5g) - the second instance of damage still lands on
    the same player even though "that creature" is now gone."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HEATED_ARGUMENT],
            graveyard=["Mountain"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    life_before = bob.life
    scenario.will_take_the_may(True, source=HEATED_ARGUMENT)
    scenario.will_choose_cards(alice.graveyard[0], source=HEATED_ARGUMENT)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve(HEATED_ARGUMENT, *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD, "2/2 Grizzly Bears dies to 6 lethal damage"
    assert bob.life == life_before - 2

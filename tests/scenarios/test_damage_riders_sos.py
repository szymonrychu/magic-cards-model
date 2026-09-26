"""SOS's damage riders: a targeted damage clause followed by a second
sentence that acts on the same target (CR 400.7 anaphora), or an optional
resolution-time cost that adds more.

- **Duel Tactics** - "Duel Tactics deals 1 damage to target creature. It
  can't block this turn." CR 509.1b's mirror of the already-handled "can't
  be blocked" rider (`machines/effects._RIDER_CANT_BE_BLOCKED_RE`), granted
  the identical way: the self line "This creature can't block."
  (`machines/combat.py`'s own blocker restriction) for the rest of the turn.
- **Searing Barb** (off-pool, the generality proof - a real second printing,
  a *conditional* rider rather than Duel Tactics' unconditional one, and a
  "damage to any target" antecedent rather than "target creature") - "Searing
  Barb deals 2 damage to any target. If it's a creature, it can't block this
  turn." `machines/effects._REFERENT_IS_TYPE_CONDITION_RE` reads "if it's a
  `<type>`," as a characteristic check on the antecedent's own found object
  (CR 205.2a), filtering which referents the rider actually reaches - a
  player or planeswalker target simply never triggers the "can't block"
  half. (Its own "Incubate 1." clause is a different, unrelated mechanic
  this file does not touch or claim to cover.)
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
- **CR 205.2a** - the fifteen card types, including creature.
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
SEARING_BARB = "Searing Barb"
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


def _searing_barb_damage_and_cant_block_clause():
    """Searing Barb's own first two sentences, read the production way
    (`effects._spell_effect_or_notice`) - not its whole printed text.

    Searing Barb's third sentence, "Incubate 1.", is CR 701.51's Incubate
    keyword action - a real mechanic, but a wholly different one this task
    does not own or touch, and the engine does not implement it yet. Since
    `_parse_mixed_clauses` fails a card closed *as a whole* when even one of
    its clauses is unreadable (CR 608.2c has no notion of running half an
    effect), casting the real printed card end to end would resolve nothing
    at all and prove nothing about the conditional "can't block" rider this
    file is actually about. Reading just the two sentences that rider lives
    in, through the same dispatcher every whole card goes through, is what
    isolates the mechanic under test from the unrelated, unimplemented one
    sharing the card - not a hand-written substitute for either.
    """
    from magic_cards_model.machines import effects

    text = (
        "Searing Barb deals 2 damage to any target. If it's a creature, it can't block this turn."
    )
    effect = effects._spell_effect_or_notice(text)
    assert effect is not None and not effects._is_notice_only(effect)
    return effect


def test_searing_barb_a_creature_target_cant_block():
    scenario = (
        Scenario()
        .player("alice", hand=[SEARING_BARB], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_onto_stack(SEARING_BARB, *sources, targets=[bears])
    spell = scenario.game.stack[-1]

    with scenario.game._id_allocator_scope():  # noqa: SLF001 - deterministic ids, as every mutation in this engine mints them
        _searing_barb_damage_and_cant_block_clause()(scenario.game, spell)

    assert bears.damage == 2
    board = scenario.game.computed_board()
    assert "This creature can't block." in board.of(bears).abilities


def test_searing_barb_at_a_player_grants_no_cant_block():
    """CR 205.2a: a player is never a creature, so the conditional rider's
    own referent-type filter drops the referent, and nothing is granted -
    the damage to the player's life total still happens."""
    scenario = (
        Scenario()
        .player("alice", hand=[SEARING_BARB], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    life_before = bob.life
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_onto_stack(SEARING_BARB, *sources, targets=["bob"])
    spell = scenario.game.stack[-1]

    _searing_barb_damage_and_cant_block_clause()(scenario.game, spell)

    assert bob.life == life_before - 2


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

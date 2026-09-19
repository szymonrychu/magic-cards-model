"""Two closed gaps in Fblthp, Impossibly Lost's own body - "When one or more
of your opponents are dealt combat damage during your turn, draw two cards.
If your library has no cards in it, you win the game. Fblthp's owner
shuffles him into their library." The trigger itself already fired
(`test_damage_recipient_triggers.py`'s own "draws two" proof); the last two
instructions in the same resolution were unread, silently:

1. **"If `<condition>`, you win the game."** (CR 104.2b) - no primitive on
   `Game` even recorded a stated win before this, only `end_with_winner`,
   used solely by `Match` series scaffolding. `Game.player_wins_the_game` is
   the effect-side twin of `player_loses_the_game`, and `_parse_if_condition_
   you_win_the_game_clause` (`machines/effects.py`) reads the printed
   condition through the same general `Game.condition_holds` an activated
   ability's own "Activate only if ..." restriction already reads - a new
   `_CONDITION_LIBRARY_EMPTY_RE` branch there. This is deliberately *not*
   CR 603.4's intervening *if* (`intervening_if_holds`): Fblthp's own "If
   your library has no cards in it, ..." is a separate sentence following an
   earlier instruction in the same resolution, not a clause immediately
   gating the trigger the way Felidar Sovereign's "at the beginning of your
   upkeep, **if** you have 40 or more life, you win the game" is (one
   sentence, parsed as `TriggeredAbility.intervening_if`, a different
   mechanism entirely - not this file's own shape at all).

2. **"This permanent's owner shuffles it into their library."** - CR 201.5's
   own short-name self-reference ("Fblthp" -> "this permanent",
   `self_normalized_effect_text`), read the self-referential twin of
   `_parse_choose_target_owner_shuffles_it_clause`'s *targeted* shuffle.

Doctor Doom, Unrivaled and Cerulean Sphinx are the off-pool generality
proofs - an activated ability rather than a triggered one, "Then if ..."
rather than a bare "If ...", and "this creature" printed directly rather
than a name self-reference `self_normalized_effect_text` has to rewrite
first - so neither new parser is fitted to Fblthp's own exact sentence.

Verified this session with `mise run rules:find` (on-disk CR effective
2026-09-25):

- **CR 104.2b** - "An effect may state that a player wins the game."
- **CR 104.3c** - drawing more cards than are left in the library "loses the
  game the next time a player would receive priority" - a state-based
  action, which is why an explicit win stated *during* the same resolution,
  before any state-based check runs, pre-empts it (Fblthp's own reminder
  text: "If you draw from an empty library this way, you still win the
  game." - Doctor Doom, Unrivaled's own identical reminder: "You win even if
  you have 0 life or didn't draw a card.").
- **CR 608.2c** - printed instruction order; the shuffle still happens even
  though the game is already over by the time it runs.
- **CR 701.20a** - to shuffle a library is to put it in a random order;
  position never matters for a card shuffled in.
- **CR 603.4** - the intervening *if* this file's own shape is deliberately
  not: it gates whether a trigger even fires, checked twice, not a plain
  mid-resolution conditional instruction.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_fblthp_wins_the_game_and_shuffles_himself_in_from_an_empty_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fblthp, Impossibly Lost"], library=[])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.COMBAT_DAMAGE)
    fblthp = scenario.creature("Fblthp, Impossibly Lost", "alice")
    bob = scenario.player("bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bob, 3)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Fblthp, Impossibly Lost's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.game.winner == "alice"
    assert fblthp.zone is Zone.LIBRARY


def test_fblthp_does_not_win_when_the_library_is_not_empty():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fblthp, Impossibly Lost"],
            library=["Mountain", "Forest", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.COMBAT_DAMAGE)
    fblthp = scenario.creature("Fblthp, Impossibly Lost", "alice")
    bob = scenario.player("bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bob, 3)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.game.winner is None
    assert len(scenario.player("alice").hand) == 2, "the two cards drawn"
    assert fblthp.zone is Zone.LIBRARY, "the unconditional shuffle still happens"


def test_doctor_doom_wins_the_game_when_his_activated_draw_empties_the_library_off_pool():
    """Off-pool generality proof for the win-the-game action: an activated
    ability, not a triggered one, "Then if ..." (`split_effect_clauses`
    already strips the leading "Then") rather than a bare "If ...", and an
    extra life-loss clause ahead of it that has nothing to do with the win
    check at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Doctor Doom, Unrivaled"], library=[], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doom = scenario.creature("Doctor Doom, Unrivaled", "alice")

    scenario.activate(doom)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 19
    assert scenario.game.winner == "alice"


def test_doctor_doom_does_not_win_with_cards_still_in_the_library():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Doctor Doom, Unrivaled"], library=["Mountain", "Forest"], life=20
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doom = scenario.creature("Doctor Doom, Unrivaled", "alice")

    scenario.activate(doom)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 19
    assert scenario.game.winner is None


def test_cerulean_sphinx_shuffles_itself_into_its_owners_library_off_pool():
    """Off-pool generality proof for the self-shuffle: an activated ability,
    not a triggered one, and "this creature" printed directly rather than a
    name self-reference `self_normalized_effect_text` has to rewrite first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Cerulean Sphinx",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sphinx = scenario.creature("Cerulean Sphinx", "alice")
    (island,) = scenario.untapped_sources("Island")

    scenario.activate(sphinx, island)
    scenario.pass_until_resolved()

    assert sphinx.zone is Zone.LIBRARY
    assert sphinx.owner == "alice"

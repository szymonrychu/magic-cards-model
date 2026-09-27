"""Scenario: "chooses a card name, then reveals the top card [of a
library] ... If that card has the chosen name, [it goes to hand]. [If it
does not, some other consequence.]" - CR 608.2c's resolving ability doing
exactly what it is printed to do, CR 701.20a's reveal, and CR 201.1's plain
name comparison.

Vexing Arcanix: "{3}, {T}: Target player chooses a card name, then reveals
the top card of their library. If that card has the chosen name, that
player puts it into their hand. Otherwise, they put it into their graveyard
and this artifact deals 2 damage to them." Before this file, `machines/
effects.py`'s own `_DAMAGE_THAT_PLAYER_RE` (a bare `.*` in front of "deals N
damage to that player") matched the *tail* of this whole paragraph and
reported the card `handled` while silently discarding the naming choice,
the reveal, and the hand branch outright - `scripts/sweep_pool.py --card
"Vexing Arcanix"` said `handled` for a card that could not actually put
anything into anyone's hand.

Conundrum Sphinx (a second, real, Modern-legal printing of the same core
mechanic - not the reported card): "Whenever this creature attacks, each
player chooses a card name. Then each player reveals the top card of their
library. If the card a player revealed has the name they chose, that player
puts it into their hand. If it doesn't, that player puts it on the bottom of
their library." Same choose/reveal/compare core
(`machines.effects._ask_name_reveal_top_and_branch`), a group subject and a
different miss action instead of Vexing Arcanix's single target and damage
rider.

Every CR number here was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 608.2c** - the controller of a resolving ability follows its
  instructions in the order written.
- **CR 701.20a** - revealing a card.
- **CR 201.1** - a card's name is printed on its upper left corner, so
  comparing a revealed card's own name to the chosen one is comparing what
  is actually printed there.
- **CR 201.4** - "If an effect instructs a player to choose a card name, the
  player must choose the name of a card in the Oracle card reference" - the
  name itself has to be a real card, not merely a non-empty string.
- **CR 609.3** / **CR 101.3** - an effect that attempts something
  impossible (nothing to reveal) does only as much as possible.
- **CR 101.4** - APNAP order for simultaneous choices among several
  players: every player names a card, in turn order, *before* anyone's
  library is revealed - not name-then-reveal one player at a time, which
  would let a later player's choice follow an earlier reveal.

`test_every_player_names_before_any_reveal` proves CR 101.4's ordering
directly: it wraps `Game.reveal` at the one seam `_ask_name_reveal_top_and_
branch`/`_parse_each_player_name_reveal_branch_clause` call it through, the
same spy-not-stand-in technique `test_mulligans.py`'s own `test_every_
declaration_is_collected_before_any_mulligan_is_taken` uses for CR 103.5's
identical "collect every choice before acting on any of them" shape -
recording, at the instant each card is revealed, how many card-name
decisions have been asked so far, then calling straight through to the real
`reveal`. Every answer it returns, and every card it moves, is still the
engine's own.

`test_an_invalid_name_is_refused` and `test_a_differently_worded_miss_
branch_is_read_the_same_way` cover findings 1.6 and 3: the chosen name must
be a real card (CR 201.4), and `_EACH_PLAYER_NAME_REVEAL_BRANCH_RE` reads
its miss branch generically rather than pinned to Conundrum Sphinx's own
"puts it on the bottom of their library" - proved directly against Vexing
Arcanix's own differently-worded "puts it into their graveyard" miss,
since no second real printing of the *group* "each player" shape exists
(Petra Sphinx prints the closest cousin, and it is not legal in Modern,
Pioneer, or Standard).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.scenarios.harness import Scenario

ARCANIX = "Vexing Arcanix"
SPHINX = "Conundrum Sphinx"


def _activate_arcanix(scenario: Scenario, *, targets):
    arcanix = scenario.find(ARCANIX, Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    return scenario.activate(arcanix, *sources, targets=targets)


# --------------------------------------------------------------------------
# Vexing Arcanix
# --------------------------------------------------------------------------


def test_a_matching_name_goes_to_the_targets_hand_with_no_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ARCANIX, "Forest", "Forest", "Forest"],
            library=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top = alice.library[0]
    life_before = alice.life

    scenario.will_choose("Lightning Bolt", source=ARCANIX)
    _activate_arcanix(scenario, targets=["alice"])
    scenario.resolve_top()

    assert top.zone is Zone.HAND
    assert alice.life == life_before


def test_an_unmatched_name_goes_to_the_graveyard_and_deals_2_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ARCANIX, "Forest", "Forest", "Forest"])
        .player("bob", library=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    top = bob.library[0]
    life_before = bob.life

    scenario.will_choose("Counterspell", source=ARCANIX)
    _activate_arcanix(scenario, targets=["bob"])
    scenario.resolve_top()

    assert top.zone is Zone.GRAVEYARD
    assert bob.life == life_before - 2


def test_an_empty_library_leaves_the_ability_with_nothing_to_do():
    """CR 609.3/CR 101.3: no top card to reveal means the whole instruction
    does as much as possible, which here is nothing at all - not even the
    naming question, since nothing could ever be compared against it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[ARCANIX, "Forest", "Forest", "Forest"], library=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life

    _activate_arcanix(scenario, targets=["alice"])
    scenario.resolve_top()

    assert alice.life == life_before
    assert scenario.game.decisions.asked == []


# --------------------------------------------------------------------------
# Conundrum Sphinx: the second, differently-shaped real printing
# --------------------------------------------------------------------------


def test_each_attacking_players_own_library_is_named_and_revealed_independently():
    """Alice's own chosen name matches her own top card (Lightning Bolt goes
    to her hand); bob's chosen name does not match his own top card (Forest
    goes to the bottom of his library) - each player names and reveals only
    their own library, never the other's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[SPHINX],
            library=["Lightning Bolt"],
        )
        .player("bob", library=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sphinx = scenario.creature(SPHINX)
    alice_top = scenario.player("alice").library[0]
    bob_top = scenario.player("bob").library[0]

    scenario.will_choose("Lightning Bolt", username="alice", source=SPHINX)
    scenario.will_choose("Counterspell", username="bob", source=SPHINX)
    scenario.attack_with(sphinx)
    scenario.resolve_top()

    assert alice_top.zone is Zone.HAND
    assert bob_top.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bob_top


def test_every_player_names_before_any_reveal(monkeypatch):
    """CR 101.4: "each player chooses a card name" happens for every player,
    in APNAP order, before "then each player reveals the top card" - never
    name-then-reveal one player at a time, which would let bob's own naming
    choice follow alice's already-revealed card. Wraps `Game.reveal` at the
    one seam this reader calls it through, recording how many card-name
    decisions have already been asked at the instant each card is revealed,
    then calling straight through to the real `reveal` - a spy, not a
    stand-in."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[SPHINX], library=["Lightning Bolt"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sphinx = scenario.creature(SPHINX)
    scenario.will_choose("Lightning Bolt", username="alice", source=SPHINX)
    scenario.will_choose("Forest", username="bob", source=SPHINX)

    naming_counts_at_reveal: list[int] = []
    real_reveal = Game.reveal

    def watching_reveal(self, card_state, source=None):
        naming_counts_at_reveal.append(
            len([q for q in self.decisions.asked if q.kind is DecisionKind.CHOOSE_A_QUALITY])
        )
        return real_reveal(self, card_state, source=source)

    monkeypatch.setattr(Game, "reveal", watching_reveal)

    scenario.attack_with(sphinx)
    scenario.resolve_top()

    assert naming_counts_at_reveal == [2, 2], (
        "both players' names were already chosen before either card was revealed"
    )


def test_an_invalid_name_is_refused():
    """CR 201.4: "the player must choose the name of a card in the Oracle
    card reference" - a string that names no real card is not a legal
    answer, and `Game.ask` refuses it with a reason rather than silently
    treating it as a guaranteed miss."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ARCANIX, "Forest", "Forest", "Forest"],
            library=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Not A Real Magic Card Xyzzyx", source=ARCANIX)
    _activate_arcanix(scenario, targets=["alice"])

    with pytest.raises(ValueError, match="CR 201.4"):
        scenario.resolve_top()


def test_a_real_but_unbundled_card_name_is_also_refused():
    """The engine validates against `data.printing_pool` - every Scryfall
    printing this build has ever added with `scripts/add_card.py` - not the
    full Oracle card reference (CR 108.1), which this engine does not ship.
    A genuinely real Magic card this pool has simply never bundled reads
    the same as an invented one; documented as a known limitation in
    `docs/engine-coverage.md` rather than silently accepted."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ARCANIX, "Forest", "Forest", "Forest"],
            library=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # A real Magic card (Scryfall-verified: Ice Age's Erosion), just never
    # added to this repo's bundled printing pool.
    scenario.will_choose("Erosion", source=ARCANIX)
    _activate_arcanix(scenario, targets=["alice"])

    with pytest.raises(ValueError, match="CR 201.4"):
        scenario.resolve_top()


def test_generalises_off_a_differently_worded_miss_branch():
    """`_EACH_PLAYER_NAME_REVEAL_BRANCH_RE` is not fitted to Conundrum
    Sphinx's own literal "puts it on the bottom of their library" - proved
    directly (no second real printing of the *group* "each player" shape
    exists - Petra Sphinx is the closest cousin and is not legal in Modern,
    Pioneer, or Standard) against Vexing Arcanix's own differently-worded
    miss, "puts it into their graveyard", the identical direct-parse proof
    `test_cast_trigger_half_x_life_and_draw.py`'s own generalises-off-a-
    differently-named-halved-quantity test already uses for the same
    reason."""
    from magic_cards_model.machines.effects import _parse_each_player_name_reveal_branch_clause

    assert (
        _parse_each_player_name_reveal_branch_clause(
            "Each player chooses a card name. Then each player reveals the top "
            "card of their library. If the card a player revealed has the name "
            "they chose, that player puts it into their hand. If it doesn't, "
            "that player puts it into their graveyard."
        )
        is not None
    )

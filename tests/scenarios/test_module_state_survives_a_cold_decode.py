"""The engine as a stateless library (T7): a game decoded cold must reconcile
and answer exactly as one played continuously does. Three module-scoped
pieces of state were quietly the odd ones out - each is CR-correct only for
as long as the process that ran the game keeps running:

- `machines/layers.py`'s `sync_granted_ability_texts` (CR 604.2, CR 613.1f)
  used to remember which quoted ability texts it had ever seen a permanent's
  static ability offer to grant in a process-global set, so a cold-decoded
  game - which has never populated that set - skipped reconciliation
  entirely and left a stale grant on an unequipped creature. It now reads a
  departed source's own text back out of wherever else in the game that
  source still is (a graveyard, most often), needing no memory of its own.
- `CardState.bind_to_game` (CR 613.5) is what makes `power`/`toughness` ask
  the layer engine instead of falling back to the printed value plus
  counters. `Game.put_onto_battlefield` is its only production call site, so
  a permanent already on the battlefield the moment a `Game` is decoded from
  a dict never gets bound at all. `card_state.bind_all_to_game` is the loop
  that closes the gap - see the T7 report for why it could not be wired into
  `Game.model_post_init` itself in this task.
- `TokenState` (CR 111.1) used to lose its own class on a round trip, because
  every field that stores one is typed plainly as `CardState` and a `dict`
  carries no Python type information. `CardState` now reads its own subclass
  back off the `token` flag already in the data.

`targeting._CACHE`'s equivalent fix (a `Card` instance leaking between
games) is `tests/test_targeting.py`'s
`test_mutating_a_card_in_one_game_is_not_observed_through_another_games_profile`,
and `Match.card_resolver`'s is
`tests/scenarios/test_match_card_resolver_round_trip.py` - both live in their
own files because neither needs a played game to demonstrate.
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card_state import bind_all_to_game
from magic_cards_model.models.game import Game
from magic_cards_model.models.token import TREASURE, TokenState, create_tokens
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# 1. `sync_granted_ability_texts` reconciles a cold decode identically
#    (CR 604.2, CR 613.1f)
# --------------------------------------------------------------------------

MANTLE_ABILITY = "{3}, {Q}: This creature gets +2/+2 until end of turn."


def test_an_unequip_after_a_cold_decode_still_takes_the_grant_back_off():
    """Umbral Mantle: `Equipped creature has "{3}, {Q}: This creature gets
    +2/+2 until end of turn."` (CR 113.10a).

    Attach it live, dump and reload the whole game - a cold decode, with no
    history in this process for a leftover global to lean on - then unattach
    on the *decoded* copy and reconcile again. CR 604.2's "as long as ... has
    the ability" must take the grant back off the decoded creature exactly as
    it would the live one.
    """
    scenario = Scenario().player("alice", battlefield=["Umbral Mantle", "Grizzly Bears"]).build()
    mantle = scenario.find("Umbral Mantle", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mantle.attach_to(bears)
    compute_board(scenario.game.battlefield, static_effects(scenario.game.battlefield))
    assert bears.granted_ability_texts == (MANTLE_ABILITY,)

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    decoded_mantle = next(s for s in decoded.battlefield if s.name == "Umbral Mantle")
    decoded_bears = next(s for s in decoded.battlefield if s.name == "Grizzly Bears")
    assert decoded_bears.granted_ability_texts == (MANTLE_ABILITY,), (
        "the stale-looking grant is only stale once the Equipment lets go - "
        "it must still be there right after the decode"
    )

    decoded_mantle.unattach()
    board = compute_board(decoded.battlefield, static_effects(decoded.battlefield))

    assert decoded_bears.granted_ability_texts == ()
    assert not board.of(decoded_bears).has_ability(MANTLE_ABILITY)
    assert decoded.activated_abilities(decoded_bears) == []


# --------------------------------------------------------------------------
# 3. `bind_to_game` (CR 613.5) - the helper `Game.model_post_init` needs
# --------------------------------------------------------------------------


def _every_card_state(game: Game):
    for cards in game.shared_zones.values():
        yield from (state for state in cards if hasattr(state, "bind_to_game"))
    for player in game.players:
        for cards in player.zones.values():
            yield from cards


def test_bind_all_to_game_gives_a_decoded_creature_its_layer_computed_power():
    """Glorious Anthem: "Creatures you control get +1/+1" (CR 613.4c).

    Live, `Scenario.build` already binds a staged battlefield permanent, so
    the Bears reads 3/3. A cold decode has no such binding at all yet -
    `Game.model_post_init` (models/game.py) does not call this helper, and
    that file is out of scope for this task: it is held by a concurrent agent
    working on machines/triggers.py and models/game.py, so the one-loop
    change it still needs (iterate `self.shared_zones.values()` and each
    player's `.zones.values()`, exactly as `_every_card_state` above does,
    calling `state.bind_to_game(self)` on each) is reported rather than made
    here. What this test proves instead: `bind_all_to_game` (`models/
    card_state.py`), applied to a decoded game by hand, produces exactly the
    live game's answer - the fix is correct and ready for that one-loop wire.
    """
    scenario = Scenario().player("alice", battlefield=["Glorious Anthem", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert (bears.power, bears.toughness) == (3, 3), "bound live, as before this task"

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    decoded_bears = next(s for s in decoded.battlefield if s.name == "Grizzly Bears")
    assert (decoded_bears.power, decoded_bears.toughness) == (2, 2), (
        "unbound: a fresh decode has not asked the layer engine yet"
    )

    bind_all_to_game(_every_card_state(decoded), decoded)

    assert (decoded_bears.power, decoded_bears.toughness) == (3, 3), (
        "bound, the decoded creature now answers exactly as the live one does"
    )


# --------------------------------------------------------------------------
# 4. A token keeps its class - and `move_to`'s CR 111.8 override - across a
#    round trip
# --------------------------------------------------------------------------


def test_a_token_survives_a_cold_decode_as_a_tokenstate_with_its_override_intact():
    """CR 111.10a's Treasure, created by the game rather than hand-written.

    Every field that stores a permanent is typed plainly as `CardState`
    (`Player.zones`, `Game`'s shared zones), so nothing here changes to make
    this pass - `CardState` itself now reads a `TokenState` back out of a
    dict that says `token: true`, wherever that dict is sitting.
    """
    scenario = Scenario().player("alice", battlefield=["Forest"]).build()
    (treasure,) = create_tokens(scenario.game, TREASURE, "alice")
    assert isinstance(treasure, TokenState)
    assert Type.ARTIFACT in treasure.card.types

    # CR 111.7/111.8: the token leaves the battlefield once. `TokenState.
    # move_to`'s own override is what remembers that a second move must be
    # refused.
    treasure.move_to(Zone.GRAVEYARD)
    assert treasure.left_the_battlefield

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    decoded_treasure = next(
        state
        for cards in decoded.shared_zones.values()
        for state in cards
        if state.name == treasure.name
    )

    assert isinstance(decoded_treasure, TokenState), "the class itself must survive the round trip"
    assert decoded_treasure.left_the_battlefield

    # And the override still refuses a further move (CR 111.8) - a plain
    # `CardState` has no such refusal and would simply reassign `zone`.
    decoded_treasure.move_to(Zone.HAND)
    assert decoded_treasure.zone is Zone.GRAVEYARD

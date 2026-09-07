"""T1 of the stateless-library plan: a `Game` decoded from one snapshot, then
replayed through the same sequence of commands, must dump byte-identically
both times - and two independently built games must never mint the same id.

A `Game` already round-trips byte-identically through `model_dump(mode="json")`
/ `model_validate` with no decision provider attached. The gap this covers is
what happens *after* the round trip: replaying the same commands from the same
decoded state used to mint a fresh `uuid4()` every time a card changed zones
(`CardState.zone_change_stamp`, set by `move_to`) and every time some other
object (a triggered ability instance, a delayed trigger, a continuous effect,
a token's underlying `Card`) was newly created - live, unseeded randomness,
different on every run.

`ids.new_id()` is what every one of those sites calls instead of a bare
`uuid4()`, and `Game._id_allocator_scope` is what makes it deterministic:
every mutating public method - `advance`, `pass_priority`, `resolve_top`,
`play_land`, `activate_ability`, `declare_attackers`, `declare_blockers`, the
pregame moves, `put_on_stack`, `Casting`'s own construction and `cast()`, and
`CostPayment.pay()` - opens that context manager for the span of its own call,
installing `Game._allocate_id` (`uuid5` of the game's own `game_uid` and its
`objects_created` counter) as `new_id`'s allocator. Two replays of the same
snapshot, driven by the same sequence of calls, therefore mint the same ids in
the same order every time.

`game_uid` is what keeps that replay-identity guarantee from colliding with a
different one: two independently built games must never share an id, even
when both default to `shuffle_seed=0` (which is correct for *shuffling* -
CR 701.24a wants a replay to reshuffle identically at a shared seed - and wrong
for *identity*, which must never repeat). `game_uid` is a plain serialised
field precisely so a decoded snapshot carries it back unchanged (replay
identity) while a freshly built `Game` gets a fresh one via `uuid4`'s own
randomness (game identity).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.scenarios.harness import PlayedScenario, Scenario


def _advance(game: Game, times: int) -> None:
    """Walk `game.advance()` forward, always as the current active player's
    own decision (or their CR 723.5 controller's) - `PlayedScenario.advance`'s
    own default, reproduced here because this test drives a bare `Game`
    decoded straight from a snapshot rather than a `PlayedScenario`.
    """
    for _ in range(times):
        decider = game.controller_of_player(game.turn.active_player)
        game.advance(decider)


def _minted_ids(dumped: object, key: str = "zone_change_stamp") -> set[str]:
    """Every value of `key` anywhere in a `model_dump(mode="json")` tree.

    `zone_change_stamp` is minted on every zone change (`CardState.move_to`),
    which is the id every card in the game carries, so walking the whole dump
    for it is a cheap, general way to collect "every id this game has minted
    that is still visible on some object" without naming every zone by hand.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for field, value in node.items():
                if field == key and isinstance(value, str):
                    found.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(dumped)
    return found


def _play_a_full_turn(scenario: Scenario) -> "PlayedScenario":
    """Build the board T1's acceptance test replays: a hand that can cast a
    spell, put a trigger on the stack, resolve it, and create a token -
    exercising every converted `default_factory=new_id` site, not just
    `CardState.move_to`'s.
    """
    return (
        scenario.player(
            "alice",
            library=["Forest"] * 5,
            hand=["Ranger-Captain of Eos", "Ephemerate", "Giant Growth", "Spectral Procession"],
            battlefield=["Grizzly Bears"] + ["Plains"] * 9 + ["Forest"] * 2,
        )
        .player(
            "bob",
            library=["Plains"] * 5,
            hand=["Grizzly Bears"],
            battlefield=["Plains"],
        )
        .build()
    )


def _replay_cast_trigger_and_token_sequence(game: Game) -> None:
    """Cast Ranger-Captain of Eos (an `AbilityOnStack` ETB trigger, resolved),
    Ephemerate targeting a creature already on the battlefield (CR 702.88's
    Rebound leaves a `DelayedTrigger` behind), Giant Growth (a
    `ContinuousEffect`), Ranger-Captain's own sacrifice ability (a
    `CastingRuleEffect`, CR 611.1), and Spectral Procession (three token
    `Card`s, CR 111.3) - one real printing per site, from
    `tests/fixtures/cards`.

    Driven directly against `game` through `PlayedScenario`'s convenience
    methods, which are thin wrappers over the same `Game`/`Casting`/
    `CostPayment` calls a real caller makes - not through a decision
    provider, so calling this twice against two independently decoded copies
    of the same snapshot takes the identical sequence of engine calls both
    times.
    """
    for _ in range(3):  # CR 500.1: UNTAP -> UPKEEP -> DRAW -> PRECOMBAT_MAIN
        decider = game.controller_of_player(game.turn.active_player)
        game.advance(decider)
    played = PlayedScenario(game)
    bears = played.creature("Grizzly Bears", "alice")

    ranger_sources = played.untapped_sources("Plains", "Plains", "Plains")
    played.cast_and_resolve("Ranger-Captain of Eos", *ranger_sources)
    played.resolve_top()  # the ETB trigger itself (declines the search)

    ranger = played.creature("Ranger-Captain of Eos", "alice")

    (ephemerate_source,) = played.untapped_sources("Plains")
    played.cast_and_resolve("Ephemerate", ephemerate_source, targets=[bears])

    (growth_source,) = played.untapped_sources("Forest")
    played.cast_and_resolve("Giant Growth", growth_source, targets=[bears])

    played.activate(ranger, sacrificing=[ranger])
    played.resolve_top()  # the sacrifice ability itself

    procession_sources = played.untapped_sources(
        "Plains", "Plains", "Plains", "Plains", "Plains", "Forest"
    )
    played.cast_and_resolve("Spectral Procession", *procession_sources)

    _advance(game, 9)  # finish the turn and start the next one


def test_replaying_the_same_snapshot_twice_is_byte_identical():
    scenario = _play_a_full_turn(Scenario())
    snapshot = scenario.game.model_dump(mode="json")

    replay_a = Game.model_validate(snapshot)
    _replay_cast_trigger_and_token_sequence(replay_a)

    replay_b = Game.model_validate(snapshot)
    _replay_cast_trigger_and_token_sequence(replay_b)

    # Sanity: the sequence actually did something, so this is not vacuously
    # true of two untouched games.
    assert replay_a.turn.turns_taken >= 1
    assert replay_a.model_dump(mode="json") != snapshot
    # Thinness guard (finding 4): a replay that minted only `CardState.
    # move_to`'s own id would still pass the dump-equality check below by
    # accident if turn state alone diverged for some other reason - this
    # fails loud if the sequence above stops minting ids at all.
    assert replay_a.objects_created >= 1
    # Finding 5: if some other code drained this game's counter (or the
    # counter silently stopped advancing), the two replays would still often
    # produce equal dumps by coincidence - state that never got compared
    # rather than state that matched. Comparing the counter itself catches
    # that a fresh mid-sequence `id()` collision cannot.
    assert replay_a.objects_created == replay_b.objects_created
    assert replay_a.model_dump(mode="json") == replay_b.model_dump(mode="json")


def test_replaying_play_land_twice_is_byte_identical():
    """Finding 2's worst case named directly: `play_land` is a special action
    (CR 116.2a) that never goes through `advance`, so before `_id_allocator_
    scope` wrapped it too, replaying it from one decoded snapshot minted a
    fresh `uuid4()` for the land's own `zone_change_stamp` and for its
    enters-the-battlefield trigger every time.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Plains"])
        .player("bob", battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    snapshot = scenario.game.model_dump(mode="json")

    replay_a = Game.model_validate(snapshot)
    land_a = next(card for card in replay_a.player("alice").hand if card.name == "Forest")
    replay_a.play_land(land_a, "alice")

    replay_b = Game.model_validate(snapshot)
    land_b = next(card for card in replay_b.player("alice").hand if card.name == "Forest")
    replay_b.play_land(land_b, "alice")

    assert replay_a.objects_created >= 1
    assert replay_a.model_dump(mode="json") == replay_b.model_dump(mode="json")


def test_independently_built_games_never_share_an_id():
    """Finding 1: identity, not just replay-of-the-same-snapshot, is the
    guarantee `game_uid` exists for. Two games built moments apart both
    default `shuffle_seed` to 0 - correctly, since CR 701.24a's shuffle seed
    is about reproducing *randomness*, not minting identity - so an allocator
    keyed on `shuffle_seed` alone mints the identical sequence of ids for
    both. Reproduced before the fix: both games below contained
    `uuid5(NAMESPACE_OID, "0:0")` = `6cf21c37-2e20-5914-b798-ab32d941ca91`.

    `game_uid` (a fresh `uuid4` per construction, unlike `shuffle_seed`) is
    what makes the two disjoint instead.
    """

    def built_and_advanced() -> Game:
        scenario = (
            Scenario()
            .player("alice", library=["Forest"] * 5, hand=["Grizzly Bears"], battlefield=["Forest"])
            .player("bob", library=["Plains"] * 5, hand=["Grizzly Bears"], battlefield=["Plains"])
            .build()
        )
        _advance(scenario.game, 12)
        return scenario.game

    game_one = built_and_advanced()
    game_two = built_and_advanced()

    assert game_one.game_uid != game_two.game_uid
    ids_one = _minted_ids(game_one.model_dump(mode="json"))
    ids_two = _minted_ids(game_two.model_dump(mode="json"))
    assert ids_one, "the sequence above should have minted at least one id"
    assert ids_one.isdisjoint(ids_two)


def test_replaying_a_refused_cast_twice_is_byte_identical():
    """`Casting.cancel()`'s own gap, closed: CR 601.6 rewinds a proposal that
    turns out illegal, and CR 733.1 makes that rewind itself a real zone
    change - `cancel`'s own docstring is why. Putting the card back in
    `origin_zone` mints a fresh `zone_change_stamp`, and `_undo_the_move_to_
    the_stack` mints another restoring the CR 400.7 identity the card had
    before the cast was ever proposed - both immediately overwritten by that
    same identity restore, so neither survives into the final dump either
    way. What the fix actually changes is `objects_created`, the count
    `Game._allocate_id` advances on every mint it serves: before the fix,
    `cancel`'s two moves fell to a bare `uuid4()` with no allocator
    installed, which never touches that counter at all, so a rewound cast
    was free. After it, `cancel` opens its own `_id_allocator_scope` the same
    as `cast()` does, and both moves are charged to it like any other mint.

    Swords to Plowshares targeting a player is illegal (it wants a creature),
    so `choose_targets` raises and the engine's own `_refusing` wrapper calls
    `cancel()` before the `ValueError` ever reaches the caller - the same
    path `rewind_unfinished` exercises for every refused or dry-run
    `cast_card` request in the api.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    snapshot = scenario.game.model_dump(mode="json")

    def attempt_the_illegal_cast(game: Game) -> int:
        """Propose, then have the proposal refused and rewound. Returns
        `objects_created` as it stood the moment before `cancel()` ran, so
        the caller can check exactly how much `cancel()` itself charged."""
        swords = next(
            card for card in game.player("alice").hand if card.name == "Swords to Plowshares"
        )
        casting = Casting(spell=swords, caster="alice", origin_zone=Zone.HAND, game=game)
        before_cancel = game.objects_created
        with pytest.raises(ValueError, match="cannot target the player"):
            casting.choose_targets(["bob"])
        return before_cancel

    replay_a = Game.model_validate(snapshot)
    before_a = attempt_the_illegal_cast(replay_a)

    replay_b = Game.model_validate(snapshot)
    before_b = attempt_the_illegal_cast(replay_b)

    # `cancel`'s own two moves, and nothing else, each charged to the
    # allocator - the precise regression check a looser `> 0` would miss,
    # since both replays would still agree with each other (just on the
    # wrong, unwrapped count) without it.
    assert replay_a.objects_created == before_a + 2
    assert replay_b.objects_created == before_b + 2
    assert replay_a.objects_created == replay_b.objects_created
    assert replay_a.model_dump(mode="json") == replay_b.model_dump(mode="json")

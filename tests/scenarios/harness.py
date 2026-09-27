"""Harness for scenario tests: build a board state, then play it out.

See docs/scenario-tests.md for how to write one. The short version:

    scenario = (
        Scenario()
        .player("alice", library=["Questing Beast"], battlefield=["Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    scenario.draw()
    ...

Every card is a real Scryfall printing loaded from tests/fixtures/cards. To use
a card the pool does not have yet, add its Scryfall json there - do not hand-write
card data, since the point of these tests is that they run against real cards.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from magic_cards_model.machines import Casting, CostPayment, PriorityOutcome, Step, TurnMachine
from magic_cards_model.machines.abilities import granted_mana_abilities, parse_mana_abilities
from magic_cards_model.machines.conditions.history import note_exile_arrivals
from magic_cards_model.machines.decisions import (
    CardSplit,
    Decision,
    DecisionKind,
    ScriptedAnswer,
)
from magic_cards_model.machines.objects_as_costs import waterbend
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import CardState, Color, Game, Match, Player, Zone
from magic_cards_model.models.card_state import TargetRef
from tests.cards import card_state

#: What a scenario may hand to `targets=`: a permanent, a player, or a
#: username. `TargetRef.coerce` works out which was meant, so a test can write
#: `targets=[bears]` or `targets=["bob"]` and mean the obvious thing.
Target = CardState | Player | str | TargetRef


# ---------------------------------------------------------------------------
# The round-trip / replay invariant (T10).
#
# `tests/scenarios/conftest.py`'s `pytest_pyfunc_call` runs every scenario
# test function once for real, then - if it built at least one `Game` - a
# second time with every `Game` construction this file funnels through
# swapped for a decode of what the first run built at that same point. Two
# runs of the exact same literal test code is what "replay of a scenario's
# own commands" means here: nothing has to be recorded call-by-call, because
# the test function's own body already *is* that command sequence, and
# `ids.py`'s per-`game_uid` deterministic id allocator is what makes a second
# run from a decoded snapshot mint the same ids in the same order the first
# run did - see its own docstring. The conftest hook does the round-trip
# check (dump, decode, re-dump, compare) after the first run regardless, and
# the replay comparison after the second.
#
# `checkpoint` is the one seam every path that hands a scenario test a
# playable `Game` has to cross: `Scenario.build` below, `Match.start_game`
# (wrapped once, just below, since roughly a fifth of `tests/scenarios/`
# reaches `Match` directly rather than through `Scenario`), and the two
# scenario files that construct a bare `Game` themselves call it explicitly.
# A file that never calls it never hands the conftest hook a `Game` to check,
# which is how the ~24 files with no board at all - a registry-minimality
# guard, a `Deck` construction test - stay correctly uncovered rather than
# silently failing.
#
# Warming: `Game.computed_board`'s own docstring (and `machines/legal_
# actions.py`'s) records that the CR 613.7 timestamp registry
# (`continuous_effects.entered`/`.clock`) is lazily populated on a cold
# game's first call, so a game dumped before that call and one dumped after
# differ. `checkpoint` calls `computed_board()` itself, every time, before
# ever taking a snapshot - the same "warm before you trust a graveyard-
# reading CDA" rule `computed_board`'s own docstring already states, not a
# special case invented for this invariant. That is legitimate rather than a
# quiet exclusion because the registry is real CR 613.7 state a live game
# would populate the same way on its own first legality check; forcing that
# to happen at the moment a scenario's board is ready, rather than whenever a
# test happens to first ask a question, changes *when* the clock starts, not
# *what* it means once it has.
#
# Ids: `ids.py`'s own docstring names a specific, short list of `Game`
# methods that install its deterministic `uuid5(game_uid, objects_created)`
# allocator for the span of their own call - `advance`, `destroy`,
# `check_state_based_actions`, `resolve_top`, and a dozen more - and says nothing
# else mints one. That list turned out not to be exhaustive: `Game.sacrifice`,
# `Game.draw_cards`, and a long tail of other public methods also reach
# `CardState.move_to`, `ContinuousEffectStore.create`, `DelayedTriggers.
# create`, or a bare `CardState`/`AbilityOnStack` construction, all of which
# mint an id through the *same* `ids.new_id`, but with no scope open around
# them - so they fall back to plain `uuid4()`. A live game never notices,
# because it never compares itself to another run of itself; this invariant
# does exactly that, and it is the dominant class of finding this task
# reported - see `MEMORY.md` and the T10 report for the full account and
# which methods are fixed versus still open.
#
# A harness-level fix was tried and reverted: installing `game._allocate_id`
# as the process-wide default for the rest of a checkpointed test, so every
# uncovered method's `new_id()` found it instead of `uuid4`. It made
# `objects_created` advance for ids that were never supposed to be counted at
# all - `machines/legal_actions.py` builds throwaway `Casting`/`CostPayment`
# objects to judge affordability without ever touching the real game, and
# with the default installed those mints became persisted state, breaking
# `test_legal_actions_mutates_nothing`'s own guarantee on the very first,
# non-replayed run. Determinism has to be scoped to the specific methods
# whose ids are actually kept, which only `Game._id_allocator_scope()` -
# opened per method, in `game.py` - can tell apart from a query that discards
# what it built. The fix belongs there, not here; this file only detects the
# gap and reports it.
# ---------------------------------------------------------------------------

_MODE: str = "off"  # "off" | "record" | "replay"
_INITIAL_DUMPS: list[dict[str, Any]] = []
_LIVE_GAMES: list[Game] = []
_REPLAY_QUEUE: list[dict[str, Any]] = []


def checkpoint(game: Game) -> Game:
    """Warm `game`, then - outside a tracked test - hand it back unchanged.

    Inside `tests/scenarios/conftest.py`'s hook this is where a `Game` a
    scenario is about to start playing either gets recorded (first run) or
    swapped for a decode of what the first run recorded at this same call
    (second run, replaying). Every other caller - a script, a one-off REPL
    session, `mise run` tooling - sees a plain pass-through, because `_MODE`
    defaults to `"off"` and only the conftest hook ever changes it.

    This does *not* install `game._allocate_id` as a process-wide default the
    way an earlier draft of this function did - that draft made every id
    minted for the rest of the test deterministic, including the throwaway
    `Casting`/`CostPayment` objects `machines/legal_actions.py` builds to
    judge affordability without ever mutating the real game, and that made
    `objects_created` advance on a supposedly pure query -
    `test_legal_actions_mutates_nothing`'s own guarantee - breaking it on the
    very first (non-replayed) run. Determinism has to be scoped to the
    specific `Game` methods whose ids are actually persisted, which is
    `Game._id_allocator_scope()`'s own job; the fix for the gaps this
    invariant found belongs there (`game.py`), not here.
    """
    game.computed_board()
    if _MODE == "record":
        _INITIAL_DUMPS.append(game.model_dump(mode="json"))
        _LIVE_GAMES.append(game)
        return game
    if _MODE == "replay":
        if not _REPLAY_QUEUE:
            raise AssertionError(
                "replay ran out of recorded checkpoints: this scenario built a "
                "game on its second run that it did not build on its first, "
                "so it is not deterministic enough for the round-trip/replay "
                "invariant to judge"
            )
        replayed = Game.model_validate(_REPLAY_QUEUE.pop(0))
        _LIVE_GAMES.append(replayed)
        return replayed
    return game


def begin_recording() -> None:
    """Start tracking every `Game` a scenario's first run checkpoints."""
    global _MODE
    _MODE = "record"
    _INITIAL_DUMPS.clear()
    _LIVE_GAMES.clear()
    _REPLAY_QUEUE.clear()


def end_recording() -> tuple[list[Game], list[dict[str, Any]]]:
    """Stop tracking and return `(games, initial_dumps)`, in checkpoint order."""
    global _MODE
    games, dumps = list(_LIVE_GAMES), list(_INITIAL_DUMPS)
    _MODE = "off"
    _LIVE_GAMES.clear()
    _INITIAL_DUMPS.clear()
    return games, dumps


def begin_replaying(initial_dumps: list[dict[str, Any]]) -> None:
    """Start the scenario's second run: each checkpoint call now decodes the
    matching entry of `initial_dumps` instead of using the game it built."""
    global _MODE
    _MODE = "replay"
    _REPLAY_QUEUE.clear()
    _REPLAY_QUEUE.extend(initial_dumps)
    _LIVE_GAMES.clear()


def end_replaying() -> list[Game]:
    """Stop replaying and return the decoded games, in checkpoint order."""
    global _MODE
    games = list(_LIVE_GAMES)
    _MODE = "off"
    _LIVE_GAMES.clear()
    return games


def diff_json(left: Any, right: Any, path: str = "$") -> str | None:
    """The path to the first place two `model_dump(mode="json")` trees
    differ, or `None` when they do not - `assert left == right` on a whole
    game's dump is true or false with no clue which of thousands of fields
    was the one that moved."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left:
                return f"{path}.{key}: missing on the left, {right[key]!r} on the right"
            if key not in right:
                return f"{path}.{key}: {left[key]!r} on the left, missing on the right"
            found = diff_json(left[key], right[key], f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return f"{path}: {len(left)} item(s) on the left, {len(right)} on the right"
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            found = diff_json(left_item, right_item, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


#: Top-level `Game` fields that move whenever *anything* resolves, whatever
#: it did: the stack and priority themselves (CR 608.2n removes the resolved
#: object), the id counter, the decision log (counted separately by
#: `ResolutionEffect.questions`), the per-turn resolution tally, and the
#: scratch fields a resolution fills and empties. A resolution that changed
#: only these did nothing a player could see.
_RESOLUTION_BOOKKEEPING = frozenset(
    {
        "stack",
        "priority",
        "decisions",
        "objects_created",
        "ability_resolutions_this_turn",
        "pending_triggers",
        "trigger_targets",
        "resolving",
        "fizzled",
    }
)


def _notice_counts(dump: dict[str, Any]) -> dict[str, int]:
    return {key: len(value) for key, value in dump.items() if key.endswith("_notices")}


class ResolutionEffect:
    """What resolving one stack object did (CR 608.2): which parts of the game
    moved, which questions it put to a player (CR 608.2d), and which notices
    it raised - the engine's own admission that it failed closed on a clause
    instead of performing it.

    `did_something` is the behavioural sweep's bar: the game changed or a
    player was asked something, and no notice was raised on the way.
    """

    def __init__(self, before: dict[str, Any], after: dict[str, Any], questions: int) -> None:
        self.changed = sorted(
            key
            for key in set(before) | set(after)
            if key not in _RESOLUTION_BOOKKEEPING
            and not key.endswith("_notices")
            and before.get(key) != after.get(key)
        )
        self.questions = questions
        before_notices, after_notices = _notice_counts(before), _notice_counts(after)
        raised = {
            key: [
                notice
                for notice in after[key][before_notices.get(key, 0) :]
                # CR 603.3d's "no legal choices" is the game working, not
                # the engine failing closed: a trigger the resolution caused
                # with nothing to target is simply removed.
                if notice.get("kind") != "no_legal_targets"
            ]
            for key, count in after_notices.items()
            if count > before_notices.get(key, 0)
        }
        self.notices = {key: found for key, found in raised.items() if found}

    @property
    def did_something(self) -> bool:
        return bool(self.changed or self.questions) and not self.notices

    def __repr__(self) -> str:
        return (
            f"ResolutionEffect(changed={self.changed}, questions={self.questions}, "
            f"notices={self.notices})"
        )


def _checkpoint_start_game(original: Any) -> Any:
    """Wrap `Match.start_game` so a deck-loading scenario that never touches
    `Scenario`/`PlayedScenario` still hands its `Game` through `checkpoint`.

    `Match.games` keeps its own reference to the game `start_game` built, so
    a replay swap has to overwrite that slot too - otherwise `match.
    current_game` and the caller's own local would disagree about which
    `Game` is being played, one the freshly-built original and the other the
    decoded replacement.
    """

    def wrapped(self: Match, *args: Any, **kwargs: Any) -> Game:
        game = original(self, *args, **kwargs)
        checked = checkpoint(game)
        if checked is not game and self.games and self.games[-1] is game:
            self.games[-1] = checked
        return checked

    return wrapped


Match.start_game = _checkpoint_start_game(Match.start_game)


def mana_from(source: CardState, color: Color | None = None) -> list[Color]:
    """What tapping this source adds to the pool.

    Read off the card's own `{T}: Add ...` text by the ability parser, so Sol
    Ring correctly makes two and a dual land insists the scenario says which
    colour it chose. Filtered to `source.up_face_name` (CR 712.8d/712.8e/
    712.8f): an MDFC on the battlefield only has the mana ability of the face
    that's up, so Witch Enchanter sitting front face up (a creature) must not
    read Witch-Blessed Meadow's `{T}: Add {W}.` off the card's other half.
    """
    # Plus `CardState.granted_ability_texts`'s own `{T}: Add ...` lines - see
    # `granted_mana_abilities`'s own docstring; Urza's Saga's chapter I grant
    # is the pool's only source of these.
    abilities = parse_mana_abilities(source.card, source.up_face_name) + granted_mana_abilities(
        source.granted_ability_texts
    )
    if not abilities:
        raise ValueError(f"{source.card.name} has no mana ability")

    if color is not None:
        for ability in abilities:
            try:
                return ability.produces(color)
            except ValueError:
                continue
        raise ValueError(f"{source.card.name} cannot add {color.value}")

    return abilities[0].produces()


class Scenario:
    """Builds a game with a known board state."""

    def __init__(self) -> None:
        self._players: list[Player] = []
        self._battlefield: list[tuple[str, list[str]]] = []
        self._exiled: list[tuple[str, list[str]]] = []
        self._automatic_turn_based_actions = True

    def automatic_turn_based_actions(self) -> "Scenario":
        """Explicitly ask for the turn-based actions. They are on by default."""
        self._automatic_turn_based_actions = True
        return self

    def manual_turn_based_actions(self) -> "Scenario":
        """Stop `advance()` performing each step's turn-based actions (CR 703.3).

        The engine does them by default, because the rules say they happen on
        their own. Turn them off for a scenario that drives one mechanic by
        hand - typically one whose board has a short or empty library, where an
        automatic draw would lose the game at the first `advance()` into the
        draw step (CR 704.5b) and drown the mechanic under test.
        """
        self._automatic_turn_based_actions = False
        return self

    def player(
        self,
        username: str,
        *,
        life: int = 20,
        library: list[str] | None = None,
        hand: list[str] | None = None,
        battlefield: list[str] | None = None,
        graveyard: list[str] | None = None,
        exile: list[str] | None = None,
        sideboard: list[str] | None = None,
        companion: str | None = None,
    ) -> "Scenario":
        """Add a player, with the cards they start the scenario holding.

        Library order is top-first, so `library=["Questing Beast", "Forest"]`
        draws Questing Beast first.

        `sideboard` is the group of cards this player has **outside the game**
        (CR 400.11a) - the cards CR 103.2a set aside before the game began, and
        the only place a "from outside the game" ability may reach. See
        `models/zone.py` for why that is not an eighth zone.

        `companion` names a card to place outside the game and stamp as this
        player's chosen companion (`Player.companion_id`, CR 702.139a) -
        bypassing `Deck.companion_problems`'s own condition check, the same
        way a scenario's `battlefield=` bypasses actually casting anything.
        `tests/scenarios/test_companion.py` covers the condition check itself
        directly against a `Deck`.
        """
        player = Player(username=username, life=life)
        for zone, names in (
            (Zone.LIBRARY, library),
            (Zone.HAND, hand),
            (Zone.GRAVEYARD, graveyard),
            (Zone.SIDEBOARD, sideboard),
        ):
            for name in names or []:
                # CR 108.3's owner is stamped by `Player.add` now, which is
                # where a real deck becomes a library too, so a scenario board
                # and a loaded decklist agree about who owns what.
                player.add(card_state(name), zone)
        if companion is not None:
            companion_state = card_state(companion)
            player.add(companion_state, Zone.SIDEBOARD)
            player.companion_id = companion_state.id

        self._players.append(player)
        self._battlefield.append((username, list(battlefield or [])))
        self._exiled.append((username, list(exile or [])))
        return self

    def build(self) -> "PlayedScenario":
        if not self._players:
            raise ValueError("a scenario needs at least one player")

        game = Game(
            players=self._players,
            automatic_turn_based_actions=self._automatic_turn_based_actions,
            schema_version=Game.CURRENT_SCHEMA_VERSION,
        )
        for username, names in self._battlefield:
            for name in names:
                state = card_state(name, Zone.BATTLEFIELD, controller=username, owner=username)
                # A staged board skips `Game.enter_the_battlefield` - nothing here
                # entered, it is just already there - so it has to do that method's
                # binding itself. Without it a scenario permanent would be the one
                # object in the engine reporting the printed value plus counters
                # (CR 122.1a) where a played one reports the characteristics the
                # layer system computes (CR 613.5), and every scenario asserting on
                # `CardState.power`/`.toughness` would pass or fail for a reason no
                # real game shares.
                state.bind_to_game(game)
                game.battlefield.append(state)
        for username, names in getattr(self, "_exiled", []):
            for name in names:
                game.exile.append(card_state(name, Zone.EXILE, controller=username, owner=username))
        # A staged exile was already there when the scenario began, like a
        # staged battlefield - nothing was put into exile this turn yet
        # ("if one or more cards were put into exile this turn").
        note_exile_arrivals(game, count=False)
        return PlayedScenario(checkpoint(game))


class PlayedScenario:
    """A built game, with the moves a scenario needs to drive it."""

    def __init__(self, game: Game) -> None:
        self.game = game

    # -- state ------------------------------------------------------------

    @property
    def turn(self) -> TurnMachine:
        assert self.game.turn is not None
        return self.game.turn

    @property
    def step(self) -> Step:
        return self.turn.step

    def player(self, username: str | None = None) -> Player:
        """A player by name, defaulting to whoever's turn it is."""
        return self.game.player(username) if username else self.game.active_player

    def battlefield_names(self) -> list[str]:
        return [state.name for state in self.game.battlefield]

    def find(self, name: str, zone: Zone, username: str | None = None) -> CardState:
        """The first copy of `name` in `zone`, narrowed to `username` when
        given. Raises if it is not there.

        A shared zone (battlefield, stack, exile, ...) holds every player's
        objects in one list (CR 110.1), so `username` has to filter it the
        same way `player(username).cards_in(zone)` already does for a
        per-player zone below - CR 108.4a's `controller_or_owner` fallback
        (the controller where CR 109.4 gives an object one, the owner
        otherwise) is what "whose" means there. Without this, `username` was
        silently ignored for every shared zone: `find("Mountain", Zone.
        BATTLEFIELD, username="bob")` on a board where alice also controls a
        Mountain returned whichever of the two the shared list happened to
        list first - alice's, tapped or not, never necessarily bob's own
        untapped one - a wrong-object bug a caller had no way to see short of
        checking identity by hand.
        """
        if zone in self.game.shared_zones:
            candidates = self.game.shared_zones[zone]
            if username is not None:
                candidates = [
                    state
                    for state in candidates
                    if getattr(state, "controller_or_owner", getattr(state, "controller", None))
                    == username
                ]
        else:
            candidates = self.player(username).cards_in(zone)

        for state in candidates:
            if state.name == name or state.name.startswith(f"{name} //"):
                return state
        raise AssertionError(
            f"{name} is not in {zone.value}; it holds {[s.name for s in candidates]}"
        )

    def zones_containing(self, card_state: CardState) -> list[str]:
        """Every zone in the whole game state that currently holds this object.

        A zone move that only checks the destination passes even when the
        object was left behind in its old zone too - `Game.put_on_stack` once
        had that exact bug for a card cast from a shared zone (an Adventure's
        exiled half, a foretold or plotted card). This is the assertion that
        catches duplication: after any move, `len(zones_containing(x)) == 1`
        should hold, naming shared zones as `"shared:<zone>"` and per-player
        ones as `"<username>:<zone>"` so a duplicate that spans a player zone
        and a shared zone is not mistaken for one hit.
        """
        found = []
        for zone, cards in self.game.shared_zones.items():
            if card_state in cards:
                found.append(f"shared:{zone.value}")
        for player in self.game.players:
            for zone, cards in player.zones.items():
                if card_state in cards:
                    found.append(f"{player.username}:{zone.value}")
        return found

    def all_card_states(self) -> list[CardState]:
        """Every `CardState` the game currently holds, in every zone, once each.

        Deduplicated by object identity, not just id: `zones_containing`
        already proves a single card is or isn't doubly listed, but a scenario
        that wants to snapshot the whole game - "these are the cards that
        exist right now" - and compare against a later snapshot needs the
        whole set at once. `Scenario.assert_in_exactly_one_zone` is the
        assertion that walks a snapshot like this one.
        """
        seen: dict[object, CardState] = {}
        for cards in self.game.shared_zones.values():
            for card in cards:
                seen[id(card)] = card
        for player in self.game.players:
            for cards in player.zones.values():
                for card in cards:
                    seen[id(card)] = card
        return list(seen.values())

    def assert_in_exactly_one_zone(self, *cards: CardState) -> None:
        """CR 400.1: every object is in a zone, and never in two at once.

        The assertion form of `zones_containing` - for any card a test wants
        to hold accountable, not just one at a time. Written so a scenario
        that just resolved something with a mid-resolution decision (CR
        608.2d) can assert the whole board is still consistent - no card
        counted zero times (vanished, as Malevolent Rumble once did when an
        illegal `choose_cards` answer unwound its resolution) or twice
        (duplicated).
        """
        for card in cards:
            found = self.zones_containing(card)
            assert len(found) == 1, (
                f"{card.name} ({card.id}) is in {len(found)} zone(s), expected "
                f"exactly 1 (CR 400.1): {found}"
            )

    def creature(self, name: str, username: str | None = None) -> CardState:
        """A creature on the battlefield by name, narrowed to one controller.

        `find(name, Zone.BATTLEFIELD)` searches the shared battlefield, so it
        cannot tell alice's Grizzly Bears from bob's. Combat scenarios almost
        always need to.
        """
        controller = username or self.player().username
        for state in self.game.permanents_controlled_by(controller):
            if state.name == name:
                return state
        raise AssertionError(
            f"{controller} controls no {name}; they control "
            f"{[s.name for s in self.game.permanents_controlled_by(controller)]}"
        )

    def creatures(self, *names: str, username: str | None = None) -> list[CardState]:
        """Distinct creatures matching `names`, in order - two Bears are two objects."""
        controller = username or self.player().username
        available = self.game.permanents_controlled_by(controller)

        picked: list[CardState] = []
        for name in names:
            match = next((s for s in available if s.name == name and s not in picked), None)
            if match is None:
                raise AssertionError(
                    f"{controller} has no spare {name}; "
                    f"remaining: {[s.name for s in available if s not in picked]}"
                )
            picked.append(match)
        return picked

    def untapped_sources(self, *names: str, username: str | None = None) -> list[CardState]:
        """Untapped permanents matching `names`, in the order given.

        Repeating a name picks a different copy each time, so
        `untapped_sources("Forest", "Forest")` returns two distinct Forests.
        """
        controller = username or self.player().username
        available = [
            state for state in self.game.permanents_controlled_by(controller) if state.untapped
        ]

        picked: list[CardState] = []
        for name in names:
            match = next((s for s in available if s.name == name and s not in picked), None)
            if match is None:
                raise AssertionError(
                    f"no untapped {name} available; "
                    f"untapped: {[s.name for s in available if s not in picked]}"
                )
            picked.append(match)
        return picked

    # -- moves ------------------------------------------------------------

    def start_at(self, step: Step) -> Step:
        """Advance to `step`, running the untap step on the way if it is passed."""
        if self.step is Step.UNTAP and step is not Step.UNTAP:
            self.game.untap_step()
        reached = self.turn.advance_to(step)
        # The raw pointer moved, so priority has to be told (CR 502.4, 514.3) -
        # a scenario that starts in a step granting priority must have some,
        # and one that stays in untap must have none.
        self.game.sync_priority_with_step()
        return reached

    def advance(self, username: str | None = None) -> Step:
        """Advance the turn, as `username`'s own decision (or their controller's).

        Defaults to whoever is actually authorized right now - the active
        player, or the player controlling them under a CR 723 effect - so a
        scenario driving its own turn forward needs no boilerplate. Pass an
        explicit `username` to test the refusal `Game.advance` gives a player
        who is not that authorized decider.
        """
        player = username or self.game.controller_of_player(self.turn.active_player)
        return self.game.advance(player)

    def draw(self, count: int = 1, username: str | None = None) -> list[CardState]:
        """Draw through the game, not straight off the `Player` (CR 121.2).

        `Player.draw` moves the cards and nothing else: no draw replacement
        gets a look (CR 121.6), no draw event is raised for anything watching,
        and the per-turn draw record is never incremented. A scenario driving
        the draw step by hand was therefore proving that nothing triggers on a
        draw *because the draw never happened as an event* - which is a test
        agreeing with itself. `Game.draw_cards` is the real door.
        """
        return self.game.draw_cards(self.player(username), count)

    def turn_based_actions(self) -> None:
        """Run the current step's turn-based actions by hand (CR 703.3).

        For a scenario that wants one step's automatic action without turning
        the whole thing on for the game.
        """
        self.game.turn_based_actions()

    # -- decisions made during resolution (CR 608.2d) -----------------------
    #
    # A resolving spell can ask its controller a question, and there is no
    # player agent to answer it. A scenario answers instead, in advance: the
    # answers queue up on the game and each is matched to the next question of
    # its kind. Nothing here fakes an effect - the engine performs the whole
    # consequence itself - so a scripted answer is staging in exactly the sense
    # a rigged library is.
    #
    # An answer left unqueued falls through to the documented default in
    # `machines/decisions.py`. A scenario that cares says so.

    def _queue(
        self,
        kind: DecisionKind,
        value: object,
        username: str | None,
        source: str | None,
        times: int | None,
    ) -> None:
        self.game.decisions.add(
            ScriptedAnswer(
                kind=kind,
                value=value,
                player=username,
                source=source,
                uses=times,
            )
        )

    def will_take_the_may(
        self,
        taken: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next plain "you may" (CR 608.2d).

        `times=None` answers every one of them for the rest of the game, which
        is what a scenario about a repeated optional trigger wants.
        """
        self._queue(DecisionKind.MAY, taken, username, source, times)

    def will_dredge(
        self,
        card: CardState | str | None,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next dredge offer (CR 702.52a): replace the draw by
        dredging `card`, or decline with `None` to draw normally.

        `card` is a graveyard `CardState`, or its name - resolved off the
        dredger's own graveyard, the way `will_choose_mode` resolves a mode by
        its printed text rather than an id nobody outside the engine has yet.
        """
        value: tuple[UUID, ...]
        if card is None:
            value = ()
        elif isinstance(card, str):
            owner = self.player(username)
            (state,) = [c for c in owner.cards_in(Zone.GRAVEYARD) if c.name == card]
            value = (state.id,)
        else:
            value = (card.id,)
        self._queue(DecisionKind.DREDGE, value, username, source, times)

    def will_pay_the_life(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "you may pay N life" (CR 119.4, CR 608.2d).

        Refusing is always legal; paying is not, below the life total, and a
        scenario that asks to pay anyway gets a `ValueError` naming CR 608.2d
        rather than a silent life total going negative.
        """
        self._queue(DecisionKind.PAY_LIFE, paid, username, source, times)

    def will_pay_life_amount(
        self,
        amount: int,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "you may pay any amount of life" (CR 119.4,
        CR 608.2d) - Necrodominance's own end-step trigger."""
        self._queue(DecisionKind.PAY_LIFE_AMOUNT, amount, username, source, times)

    def will_choose_mode(
        self,
        text: str,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next modal *triggered* ability's "choose one" (CR
        603.3c, 700.2a) by naming the mode's own printed text - Elder
        Gargaroth's own attack/block trigger."""
        self._queue(DecisionKind.CHOOSE_A_MODE, text, username, source, times)

    def will_choose_top(
        self,
        top: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "puts it on their choice of the top or bottom of
        their library" (CR 401.2, CR 608.2d) - Subtlety's own choice. `top`
        names the answer: `True` for the top (the documented default,
        `DecisionKind.PUT_ON_TOP_OR_BOTTOM`'s own least-destructive choice),
        `False` for the bottom.
        """
        self._queue(DecisionKind.PUT_ON_TOP_OR_BOTTOM, top, username, source, times)

    def will_choose_hand_or_graveyard(
        self,
        hand: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "put it into your hand or graveyard" (CR 608.2d) -
        Dina's Guidance's own choice. `hand` names the answer: `True` for the
        hand (the documented default, `DecisionKind.PUT_INTO_HAND_OR_
        GRAVEYARD`'s own least-destructive choice), `False` for the
        graveyard.
        """
        self._queue(DecisionKind.PUT_INTO_HAND_OR_GRAVEYARD, hand, username, source, times)

    def will_choose_pile(
        self,
        pile_one: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next CR 700.3 pile choice (Liliana of the Veil's own
        `-6`, Do or Die) - the *second* of the mechanic's two questions, put
        to whichever player the card names for it (the ability's own
        target), not to the ability's controller who divided the piles.
        `pile_one` names the answer: `True` for pile one
        (`Decision.cards`, the dividing player's own choice of what to put
        there), `False` for its complement.
        """
        self._queue(DecisionKind.CHOOSE_PILE, pile_one, username, source, times)

    def will_pay_the_energy(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next fixed-amount "you may pay {E}..."/"...unless you
        pay {E}" (CR 107.14, CR 118.3, CR 608.2d).

        Refusing is always legal; paying is not, below the energy needed, and
        a scenario that asks to pay anyway gets a `ValueError` naming CR 608.2d,
        the same shape `will_pay_the_life` already holds for CR 119.4.
        """
        self._queue(DecisionKind.PAY_ENERGY, paid, username, source, times)

    def will_pay_the_mana_cost(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
        sources: Sequence[CardState] | None = None,
    ) -> None:
        """Answer the next "unless its controller pays {N}" (CR 118.12a, CR
        608.2d) - Censor's and Mystical Dispute's shape.

        Refusing is always legal; paying is not when the floating mana plus
        the payer's untapped mana sources cannot cover it (CR 118.3, CR
        608.2g). `sources` names which mana sources to activate while paying;
        left out, the engine chooses them the way `CostPayment.auto_tap` does.
        """
        value: object = paid if sources is None else tuple(state.id for state in sources)
        self._queue(DecisionKind.PAY_MANA, value, username, source, times)

    def will_pay_energy_amount(
        self,
        amount: int,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "you may pay any amount of {E}" (CR 107.14, CR
        118.3, CR 608.2d) with exactly `amount`.

        `amount` is validated against however much energy the player actually
        has when asked, not against whatever a scenario expects up front - a
        scripted amount greater than that gets `Game.ask`'s `ValueError`
        naming CR 118.3, the same way an out-of-range `will_pay_the_life`
        would.
        """
        self._queue(DecisionKind.PAY_ENERGY_AMOUNT, amount, username, source, times)

    def will_choose(
        self,
        value: str,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "as [this] enters, choose a color/card name/creature
        type" question (CR 614.1c, CR 614.12a) with `value`.

        A color is its letter code (`Color.BLUE.value`, i.e. `"U"`); a card
        name or creature type is the plain string. `source` is the card
        asking, which is how a scenario with several such choices in flight
        tells them apart - the same convention `will_take_the_may` and
        `will_pay_the_life` already use.
        """
        self._queue(DecisionKind.CHOOSE_A_QUALITY, value, username, source, times)

    def will_discard(
        self,
        *cards: CardState,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_CARDS` question - the cleanup discard is the
        first one - with exactly these cards (CR 514.1, CR 701.9b).

        `Game.ask` still checks the answer is the right size and drawn from the
        cards actually offered, so a scenario naming the wrong count or a card
        not in the zone gets `Game.ask`'s `ValueError`, not a silent mismatch.
        """
        self._queue(DecisionKind.CHOOSE_CARDS, tuple(c.id for c in cards), username, None, times)

    def will_choose_cards(
        self,
        *cards: CardState,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_CARDS` question with exactly these cards.

        `will_discard` is the same question asked by the cleanup step; this is
        the general one, for a "choose N of these cards" put by a card's own
        text - Karn, the Great Creator's `−2` choosing among the artifact cards
        its controller owns outside the game and face up in exile. `source`
        narrows the answer to the card asking, the way `will_take_the_may`
        already does.
        """
        self._queue(DecisionKind.CHOOSE_CARDS, tuple(c.id for c in cards), username, source, times)

    def will_choose_players(
        self,
        *players: Player | str,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_PLAYERS` question with exactly these
        players - `will_choose_cards`' own twin, for CR 701.34a's own
        proliferate ("choose any number of ... players ...") and any future
        card sharing the same CR 608.2d player-choice shape."""
        self._queue(
            DecisionKind.CHOOSE_PLAYERS,
            tuple(p if isinstance(p, str) else p.username for p in players),
            username,
            source,
            times,
        )

    def will_choose_targets(
        self,
        *targets: Target,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_TARGETS` question with exactly these targets.

        The vocabulary is `targets=`'s own: a `CardState` is an object target
        and a `str` a player target, both coerced to a `TargetRef` the way
        CR 115.1 makes them one kind of thing. `Game.ask` still checks the
        answer against the legal candidates it offered, so naming something
        illegal raises rather than being silently accepted.
        """
        self._queue(
            DecisionKind.CHOOSE_TARGETS,
            tuple(TargetRef.coerce(target) for target in targets),
            username,
            source,
            times,
        )

    def will_assign_combat_damage(
        self,
        *assignment: tuple[Target, int],
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `ASSIGN_COMBAT_DAMAGE` question (CR 510.1c, 702.19b).

        Each entry is `(recipient, amount)`: a blocking creature, or a player
        by username (trample). `Game.ask` checks the whole assignment
        (CR 510.1e), so an illegal one raises naming the rule it breaks.
        """
        self._queue(
            DecisionKind.ASSIGN_COMBAT_DAMAGE,
            tuple((TargetRef.coerce(target), amount) for target, amount in assignment),
            username,
            source,
            times,
        )

    def will_order_triggers(
        self,
        *source_names: str,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `ORDER_TRIGGERS` question (CR 603.3b) by naming the
        source of each of that player's own waiting triggers, **bottom of the
        stack first**.

        "First, each player, in APNAP order, puts each triggered ability they
        control on the stack in any order they choose." The last name given is
        therefore the trigger that goes on *top* and so resolves *first* -
        which is the way round DDR#983's trick needs.

        Named by printed source rather than by ability id for the same reason
        `choose_trigger_targets` is: the abilities do not exist until the event
        fires, so there is no id for a scenario to name in advance.
        `machines/decisions._resolve_trigger_order` refuses a name that does
        not match exactly one of the abilities actually offered, so a
        misspelling raises rather than being quietly ignored.
        """
        self._queue(DecisionKind.ORDER_TRIGGERS, tuple(source_names), username, None, times)

    def scry_keeping_everything_on_top(
        self, *, username: str | None = None, times: int | None = 1
    ) -> None:
        """Bottom nothing on the next scry (CR 701.22a).

        "Put any number of them on the bottom" - none is a number, so this is a
        real answer and not a refusal to answer.
        """
        self._queue(DecisionKind.SCRY, CardSplit(), username, None, times)

    def scry_bottoming(
        self,
        *cards: CardState,
        top_order: list[CardState] | None = None,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Put these cards on the bottom on the next scry (CR 701.22a).

        The cards are named by identity, so a scenario says "bottom *this*
        Island" rather than "bottom the second card". Anything not named stays
        on top, in the order it was looked at unless `top_order` says otherwise
        - "the rest on top of your library in any order".

        Naming a card that is not among the ones looked at is refused, because
        CR 701.22a only lets a player move the cards they looked at.
        """
        self._queue(
            DecisionKind.SCRY,
            CardSplit(
                moved=tuple(state.id for state in cards),
                top_order=None if top_order is None else tuple(state.id for state in top_order),
            ),
            username,
            None,
            times,
        )

    def surveil_to_graveyard(
        self,
        *cards: CardState,
        top_order: list[CardState] | None = None,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Put these cards into the graveyard on the next surveil (CR 701.25a)."""
        self._queue(
            DecisionKind.SURVEIL,
            CardSplit(
                moved=tuple(state.id for state in cards),
                top_order=None if top_order is None else tuple(state.id for state in top_order),
            ),
            username,
            None,
            times,
        )

    def surveil_keeping_everything_on_top(
        self, *, username: str | None = None, times: int | None = 1
    ) -> None:
        """Put nothing into the graveyard on the next surveil (CR 701.25a)."""
        self._queue(DecisionKind.SURVEIL, CardSplit(), username, None, times)

    def top_of_library(self, count: int = 1, username: str | None = None) -> list[CardState]:
        """The top `count` cards, without looking at them through an effect.

        For asserting where a scry or a surveil left things, and for naming the
        cards a scenario is about to answer a question about.
        """
        return list(self.player(username).library[:count])

    def questions_asked(self) -> list[Decision]:
        """Every question the engine has put to a player, in order.

        The only way to assert that a card asked *nothing*: CR 701.22b's
        "instructed to scry 0, no scry event occurs" and CR 701.25c's surveil
        equivalent are both about a question that was never put.
        """
        return list(self.game.decisions.asked)

    # -- priority ---------------------------------------------------------

    @property
    def priority_holder(self) -> str | None:
        """Who has priority, or None if nobody does (CR 502.4, 514.3)."""
        return self.game.priority_holder

    def pass_priority(self, username: str | None = None) -> PriorityOutcome:
        """Pass priority for one player. Defaults to whoever holds it.

        With no `username` in a step where nobody holds priority, the pass is
        made in the name of the active player, so the refusal a scenario is
        testing is CR 502.4's and not "you did not say who".
        """
        holder = self.priority_holder
        if username is None and holder is None:
            username = self.game.controller_of_player(self.turn.active_player)
        return self.game.pass_priority(username or holder or "")

    def pass_until_resolved(self) -> PriorityOutcome:
        """Every player still in the game passes in turn, resolving the top of the stack."""
        outcome = PriorityOutcome.PASSED
        for _ in range(len(self.game.players_in_game)):
            outcome = self.pass_priority()
            if outcome is not PriorityOutcome.PASSED:
                break
        return outcome

    # -- special actions --------------------------------------------------

    def play_land(
        self, name: str, username: str | None = None, from_zone: Zone = Zone.HAND
    ) -> CardState:
        """Play a land. A special action: no stack, no priority pass.

        `from_zone` is CR 701.18a's "from the zone it's in (usually the hand)":
        an effect can hand out permission to play a land from somewhere else
        (`Game.grant_play_permission` with `PlayAction.PLAY`), and `play_land`
        refuses any other zone without one.
        """
        player = self.player(username)
        # A shared zone can hold a land the player neither owns nor controls
        # (Dauthi Voidwalker's void card) - the same reason `cast` drops the
        # owner filter there.
        find_username = None if from_zone in self.game.shared_zones else player.username
        land = self.find(name, from_zone, find_username)
        return self.game.play_land(land, player.username)

    # -- combat -----------------------------------------------------------

    def _default_defender(self) -> str:
        """The one opponent of the active player, when a scenario does not say."""
        active = self.player().username
        opponents = [p.username for p in self.game.players_in_game if p.username != active]
        if len(opponents) != 1:
            raise AssertionError(f"say who is being attacked; opponents are {opponents}")
        return opponents[0]

    def attack_with(
        self, *creatures: CardState, defending: CardState | Player | str | None = None
    ) -> None:
        """Declare these creatures as attackers (CR 508.1).

        `defending` is a player, a username, or a planeswalker or battle; it
        defaults to the active player's only opponent. Raises `ValueError` with
        the rule's reason when a declaration is illegal, so a scenario about an
        illegal attack asserts on that message.
        """
        defender = defending if defending is not None else self._default_defender()
        self.game.declare_attackers([(creature, defender) for creature in creatures])

    def can_attack(
        self, creature: CardState, defending: CardState | Player | str | None = None
    ) -> bool:
        defender = defending if defending is not None else self._default_defender()
        return self.game.can_attack(creature, defender)

    def block(self, attacker: CardState, *blockers: CardState) -> None:
        """Block one attacker with these creatures, in declaration order.

        Combines with earlier `block` calls, and the whole declaration is
        rechecked each time (CR 509.1), which is what makes a lone blocker on a
        creature with menace illegal.
        """
        pairs = [
            (blocker, attacker_state)
            for attacker_state in self.game.attacking_creatures()
            for blocker in self._blockers_on(attacker_state)
        ]
        pairs += [(blocker, attacker) for blocker in blockers]
        self.game.declare_blockers(pairs)

    def _blockers_on(self, attacker: CardState) -> list[CardState]:
        attack = self.game.combat.attack_by(attacker.id)
        if attack is None:
            return []
        found = (self.game.find_by_id(card_id) for card_id in attack.blockers)
        return [state for state in found if state is not None]

    def no_blocks(self) -> None:
        """The defending player declares no blockers (CR 509.1)."""
        self.game.declare_blockers([])

    def combat_damage(self) -> list[tuple[CardState | Player, int]]:
        """Deal combat damage, first-strike step included (CR 510).

        Returns the assignment as `(target, amount)` pairs, so a scenario can
        assert on how the damage was split rather than only on what died.
        """
        return self.game.combat_damage()

    def attackers(self) -> list[CardState]:
        return self.game.attacking_creatures()

    def blockers(self) -> list[CardState]:
        return self.game.blocking_creatures()

    # -- casting ----------------------------------------------------------

    def pay_with(self, payment: CostPayment, *sources: CardState) -> CostPayment:
        """Tap each source for mana and pay. Returns the settled payment.

        The overflow is left on the payment as `payment.overflow`.
        """
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))
        payment.pay()
        return payment

    def auto_pay(self, payment: CostPayment, username: str | None = None) -> CostPayment:
        """Let the payment solve its own mana, from every permanent `username`
        controls (`CostPayment.auto_tap`), then pay. This is the same
        auto-tap the API uses by default when a player gives no `--sources`.
        """
        controller = username or payment.payer or self.player().username
        payment.auto_tap(self.game.permanents_controlled_by(controller))
        payment.pay()
        return payment

    def put_on_stack(self, casting: Casting) -> CardState:
        """Finish casting and put the spell onto the stack.

        The caster keeps priority afterwards, as the rules give it back to
        whoever just cast something.
        """
        spell = casting.cast()
        on_stack = self.game.put_on_stack(spell, casting.caster)
        self.game.retain_priority(casting.caster)
        return on_stack

    def resolve_top(self):
        """Resolve the top of the stack. Returns a `CardState` or an `AbilityOnStack`."""
        return self.game.resolve_top()

    def resolve_top_measured(self) -> ResolutionEffect:
        """Resolve the top of the stack and report what that resolution did -
        see `ResolutionEffect`. Measured straight after CR 608.2's resolution,
        before any state-based action, so a creature the resolution damaged
        still counts as changed even if CR 704.5g later kills it."""
        before = self.game.model_dump(mode="json")
        asked = len(self.game.decisions.asked)
        self.game.resolve_top()
        after = self.game.model_dump(mode="json")
        return ResolutionEffect(before, after, len(self.game.decisions.asked) - asked)

    # -- abilities --------------------------------------------------------

    def stack_names(self) -> list[str]:
        """What is on the stack, bottom first. An ability names its source."""
        return [item.name for item in self.game.stack]

    @property
    def pending_triggers(self) -> list[AbilityOnStack]:
        """Abilities that have triggered but are not on the stack yet (CR 603.3)."""
        return self.game.pending_triggers

    def choose_trigger_targets(self, card_name: str, targets: list[Target]) -> None:
        """Say what a card's triggered ability aims at when it goes on the stack."""
        self.game.choose_trigger_targets(card_name, list(targets))

    def put_onto_battlefield(
        self,
        name: str,
        username: str | None = None,
        from_zone: Zone = Zone.HAND,
        *,
        tapped: bool = False,
    ) -> CardState:
        """Put a card straight onto the battlefield without casting it.

        The Tooth and Nail path: no stack, no cost, no casting event.
        """
        player = self.player(username)
        card = self.find(name, from_zone, player.username)
        return self.game.put_onto_battlefield(card, player.username, tapped=tapped)

    def activate(
        self,
        source: CardState,
        *mana_sources: CardState,
        index: int = 0,
        username: str | None = None,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        tapping_for_cost: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
        targets: list[Target] | None = None,
        color: Color | Sequence[Color] | str | None = None,
        auto: bool = False,
        x_value: int = 0,
        division: list[int] | None = None,
    ) -> AbilityOnStack | None:
        """Activate one of `source`'s abilities, paying with `mana_sources`.

        `division` is CR 601.2d's announced split of a divided effect among
        `targets`, one share per target (CR 602.2b imports it for abilities).

        Returns the ability now on the stack, or None for a mana ability, which
        never goes on the stack at all (CR 605.3b). The activator keeps priority
        afterwards (CR 117.3c), as they do after casting a spell.

        `color` is the colour chosen for a mana ability that offers one - a
        dual land or an "any color" source. That is `game.activate_ability`'s
        own choice of what *this* ability produces, not the mana payment - it
        stays a plain argument even when `auto=True` lets `auto_pay` solve the
        cost of activating it.

        `x_value` is CR 107.3a's X (Fiend Artisan's `{X}{B/G}`), announced
        once here and threaded through both `begin_activating` and
        `activate_ability` - the same value has to reach both, exactly the
        way a spell's `x_value` reaches both `determine_cost` and `cast`.

        `tapping` is CR 701.67a's waterbend payment: each untapped artifact or
        creature listed there is tapped to pay one generic mana of the cost
        instead of mana being spent on it. Like convoke (CR 702.51b) it applies
        only after the total cost has been determined, so it lands on the open
        `CostPayment` rather than on the cost - which is why it is applied here
        and not passed to `begin_activating`.

        `tapping_for_cost` is a different thing with an unavoidably similar
        name: the permanents chosen to pay a printed "Tap `<count>` untapped
        `<quality>` you control" additional cost (Persistent Petitioners'
        "Tap four untapped Advisors you control", Merchant's Dockhand's "Tap
        X untapped artifacts you control") - CR 601.2b's own choice, made as
        the activation is announced, the same moment `sacrificing`/
        `discarding`/`exiling` are. Passed straight to `begin_activating`,
        never to an open `CostPayment` the way `tapping` is.
        """
        controller = username or self.game.controller_of(source).username
        payment = self.game.begin_activating(
            source,
            index,
            controller,
            sacrificing=sacrificing,
            discarding=discarding,
            exiling=exiling,
            revealing=revealing,
            tapping=tapping_for_cost,
            x_value=x_value,
            targets=targets,
            division=division,
        )
        if tapping:
            waterbend(payment, *tapping)
        if auto:
            payment.auto_tap(self.game.permanents_controlled_by(controller))
        else:
            for mana_source in mana_sources:
                payment.tap_for_mana(mana_source, mana_from(mana_source))
        payment.pay()
        ability = self.game.activate_ability(
            source,
            index,
            controller,
            color=color,
            x_value=x_value,
            exiled_for_cost=exiling[0] if exiling else None,
            sacrificed_for_cost=sacrificing,
            division=division,
        )
        self.game.retain_priority(controller)
        return ability

    def why_cannot_activate(
        self, source: CardState, index: int = 0, username: str | None = None
    ) -> str | None:
        return self.game.why_cannot_activate(source, index, username)

    def cycle(
        self,
        card_state: CardState,
        *mana_sources: CardState,
        username: str | None = None,
        index: int = 0,
    ) -> object:
        """Cycle a card out of its owner's hand (CR 702.29a).

        "Cycling is an activated ability that functions only while the card
        with cycling is in a player's hand. 'Cycling [cost]' means '[Cost],
        Discard this card: Draw a card.'" CR 702.29b adds that the ability
        "continues to exist while the object is on the battlefield and in all
        other zones", which is why the *zone* is what gates it, not the card.

        `activate` is deliberately not the door: it goes through
        `Game.begin_activating`, which only reaches abilities of battlefield
        permanents, so a card in hand has "no activated ability number 0"
        there - correctly, for the abilities `Game` reads off a permanent.
        Cycling is built by `machines/keywords.py` out of the keyword line
        instead, discard and all, so this delegates to its own driver rather
        than widening the permanent path.

        `mana_sources` pay a cycling cost that needs mana; Street Wraith's
        "Cycling—Pay 2 life" needs none.
        """
        from magic_cards_model.machines import keywords

        player = username or self.game.controller_of(card_state).username

        def pay(payment: CostPayment) -> None:
            for mana_source in mana_sources:
                payment.tap_for_mana(mana_source, mana_from(mana_source))

        return keywords.cycle(self.game, card_state, player, pay, index)

    def bring_companion_to_hand(
        self, *mana_sources: CardState, username: str | None = None
    ) -> CardState:
        """CR 116.2g: pay `{3}` and put `username`'s chosen companion into
        their hand, paying with `mana_sources`."""
        player = username or self.game.active_player.username
        payment = self.game.begin_bringing_companion_to_hand(player)
        for mana_source in mana_sources:
            payment.tap_for_mana(mana_source, mana_from(mana_source))
        payment.pay()
        return self.game.bring_companion_to_hand(player)

    def turn_face_up(
        self,
        permanent: CardState,
        *mana_sources: CardState,
        username: str | None = None,
        procedure: str | None = None,
    ) -> CardState:
        """CR 702.37e: pay the morph cost and turn a face-down permanent
        face up, paying with `mana_sources`.

        `procedure` ("morph" or "manifest") picks CR 701.40c-d's alternative
        for a permanent that is manifested *and* has morph or disguise;
        `None` keeps the engine's own default preference.
        """
        controller = username or self.game.controller_of(permanent).username
        payment = self.game.begin_turning_face_up(permanent, controller, procedure=procedure)
        for mana_source in mana_sources:
            payment.tap_for_mana(mana_source, mana_from(mana_source))
        payment.pay()
        turned = self.game.turn_face_up(permanent, controller, procedure=procedure)
        self.game.retain_priority(controller)
        return turned

    def cast(
        self,
        name: str,
        username: str | None = None,
        from_zone: Zone = Zone.HAND,
        targets: list[Target] | None = None,
        *,
        division: list[int] | None = None,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        beholding: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
    ) -> Casting:
        """Begin casting a card, returning the casting machine mid-announcement.

        Targets may be permanents, players, or usernames, mixed freely - a
        Bolt aimed at a face is `targets=["bob"]`.

        `sacrificing`, `discarding`, `exiling`, `tapping` and `beholding` are
        the objects chosen to pay the card's own printed "As an additional
        cost to cast this spell, ..." sentence (CR 601.2b, CR 118.8a) - the
        creature Fling throws, the two cards Cathartic Reunion discards, the
        creature Swallow Whole taps, the hand card or battlefield permanent
        Countersculpt beholds. `Casting` reads the sentence itself at
        CR 601.2f and takes the objects from these lists in the order the
        sentences print; the same vocabulary `Game.activation_cost` uses for
        an activated ability's object costs.
        """
        player = self.player(username)
        # A shared zone (exile chief among them) can hold a card the caster
        # neither owns nor controls - Ragavan's own steal-and-cast, Dire
        # Fleet Daredevil's, Null Summoner's Threshold grant - so `find`'s
        # own owner/controller filter is the wrong question to ask it here;
        # only a per-player zone (hand, graveyard, library) is scoped to the
        # caster at all.
        find_username = None if from_zone in self.game.shared_zones else player.username
        spell = self.find(name, from_zone, find_username)
        casting = Casting(
            spell=spell,
            caster=player.username,
            origin_zone=from_zone,
            game=self.game,
            sacrificing=list(sacrificing or []),
            discarding=list(discarding or []),
            exiling=list(exiling or []),
            tapping=list(tapping or []),
            beholding=list(beholding or []),
            revealing=None if revealing is None else list(revealing),
        )
        if targets is not None:
            casting.choose_targets(targets)
        if division is not None:
            # CR 601.2d: the division is announced *after* the targets, in the
            # same CR 601.2 announcement, and each of those targets must
            # receive at least one of whatever is divided.
            casting.announce_division(division)
        return casting

    def cast_onto_stack(
        self,
        name: str,
        *sources: CardState,
        username: str | None = None,
        targets: list[Target] | None = None,
        auto: bool = False,
        division: list[int] | None = None,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        beholding: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
    ) -> CardState:
        """Cast a spell and leave it on the stack, unresolved.

        Use this when the scenario is about what happens while it sits there -
        responses, counterspells, resolution order.

        `auto=True` pays with `auto_pay` instead of `sources` - the same
        auto-tap path the API takes when a player gives no `--sources`.

        `sacrificing`/`discarding`/`exiling`/`tapping`/`beholding` pay the
        card's printed additional cost - see `cast`.
        """
        casting = self.cast(
            name,
            username,
            targets=targets,
            division=division,
            sacrificing=sacrificing,
            discarding=discarding,
            exiling=exiling,
            tapping=tapping,
            beholding=beholding,
            revealing=revealing,
        )
        payment = casting.begin_paying()
        if auto:
            self.auto_pay(payment, username=casting.caster)
        else:
            self.pay_with(payment, *sources)
        return self.put_on_stack(casting)

    # -- state-based actions ----------------------------------------------

    def state_based_actions(self) -> list[CardState]:
        """Check state-based actions (CR 704.3) - a plain alias for `Game.
        check_state_based_actions`.

        `Game` now performs the whole CR 704.5 sweep itself, counters
        included: annihilation (CR 704.5q, via `models.card_state.
        annihilate_counters_on`, called from `Game._state_based_actions_once`)
        and a planeswalker at zero loyalty (CR 704.5i) both live there. This
        method used to duplicate the annihilation half here - directly, with
        no priority round and no exemption check - which is exactly the
        workaround `tests/scenarios/test_zero_loyalty_exemption.py` warns
        against for the loyalty half; it exists now only because every other
        scenario file in this pool already calls it by this name.
        """
        return self.game.check_state_based_actions()

    def cast_and_resolve(
        self,
        name: str,
        *sources: CardState,
        username: str | None = None,
        targets: list[Target] | None = None,
        auto: bool = False,
        division: list[int] | None = None,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        beholding: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
    ) -> CardState:
        """The whole path for a spell nobody responds to.

        Announce it, pay with `sources`, put it on the stack, resolve it.
        Scenarios that care about a step in the middle should drive the parts
        themselves rather than call this. `auto=True` pays with `auto_pay`
        instead - see `cast_onto_stack`.

        `sacrificing`/`discarding`/`exiling`/`tapping`/`beholding` pay the
        card's printed additional cost - see `cast`.
        """
        self.cast_onto_stack(
            name,
            *sources,
            username=username,
            targets=targets,
            auto=auto,
            division=division,
            sacrificing=sacrificing,
            discarding=discarding,
            exiling=exiling,
            tapping=tapping,
            beholding=beholding,
            revealing=revealing,
        )
        return self.resolve_top()

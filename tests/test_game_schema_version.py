"""T9 of the stateless-library plan: `Game.schema_version`.

Engine behaviour is a function of (state, engine version), not of state
alone - effects resolve through name-keyed registries and text parsers
(`machines/effects.py`, `machines/abilities.py`, `machines/delayed.py`,
`machines/layers.py`), so a state written by one engine build and decoded by
another can resolve differently with no signal at all. `Game.schema_version`
is the signal: written on every dump, checked on every decode, and refused -
loudly, per `memory/silent-default-dispatch-tables.md` - rather than defaulted
whenever it does not match, or is missing entirely. See `Game.schema_version`
and `Game.CURRENT_SCHEMA_VERSION`'s own docstrings in `models/game.py` for the
full policy and the bump rule this module exercises rather than restates.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Match, Player
from magic_cards_model.models.card import Color
from magic_cards_model.models.game import Game, SchemaVersionMismatch
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _bears(game: Game, username: str) -> CardState:
    """The one Grizzly Bears `username` controls, without a `PlayedScenario`
    wrapper - needed for the decoded copy in the round-trip test below, which
    is a bare `Game.model_validate` result rather than something `Scenario`
    built."""
    (found,) = [
        state for state in game.permanents_controlled_by(username) if state.name == "Grizzly Bears"
    ]
    return found


def _a_played_game() -> Game:
    """A real board, played a step forward, not just built - the round trip
    this module cares about is of a `Game` that has actually done something,
    not an inert one still sitting at its defaults."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 3,
            hand=["Giant Growth"],
            battlefield=["Forest", "Grizzly Bears"],
        )
        .player("bob", library=["Plains"] * 3, battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    return scenario.game


def test_a_fresh_game_is_stamped_with_the_current_schema_version() -> None:
    """`Game.__init__` (via the scenario harness's own `Game(...)` call) -
    fresh construction, not a decode - carries the current version with no
    caller needing to think about it beyond the one explicit keyword the
    harness passes."""
    game = _a_played_game()
    assert game.schema_version == Game.CURRENT_SCHEMA_VERSION


def test_round_trip_at_the_current_version_is_unaffected() -> None:
    """`model_dump(mode="json")` / `model_validate` at a matching version
    round-trips exactly as it did before this field existed - real cards, a
    resolved spell, a pumped creature, all still there and still playable."""
    game = _a_played_game()
    dumped = game.model_dump(mode="json")
    assert dumped["schema_version"] == Game.CURRENT_SCHEMA_VERSION

    decoded = Game.model_validate(dumped)
    assert decoded.schema_version == Game.CURRENT_SCHEMA_VERSION
    assert decoded.model_dump(mode="json") == dumped

    # And it is still a live, playable game, not just a static blob: the
    # pumped Grizzly Bears is still on the battlefield at 5/5 for the decoded
    # copy exactly as it was for the original.
    original_bears = _bears(game, "alice")
    decoded_bears = _bears(decoded, "alice")
    assert (original_bears.power, original_bears.toughness) == (5, 5)
    assert (decoded_bears.power, decoded_bears.toughness) == (5, 5)


def test_decode_refuses_a_mismatched_schema_version() -> None:
    """A snapshot written at a different schema version is refused, not
    silently accepted as current - the documented policy for a real version
    disagreement, since a name-keyed registry or parser change between the
    two versions could make this exact state resolve differently."""
    game = _a_played_game()
    dumped = game.model_dump(mode="json")
    dumped["schema_version"] = Game.CURRENT_SCHEMA_VERSION + 1

    with pytest.raises(
        SchemaVersionMismatch, match=f"decodes schema_version={Game.CURRENT_SCHEMA_VERSION}"
    ):
        Game.model_validate(dumped)


def test_decode_refuses_a_snapshot_with_no_schema_version_at_all() -> None:
    """A snapshot with no `schema_version` key - every state written before
    this field existed - is refused exactly like a mismatched one, per the
    documented migration policy: there is no real pre-versioning data this
    engine persists anywhere yet (`GameStore` in magic-cards-model-api is
    in-memory only), so there is nothing to migrate forward, and a decoded
    snapshot's *behaviour*, not merely its shape, is what a missing version
    cannot vouch for. Refuse rather than assume current."""
    game = _a_played_game()
    dumped = game.model_dump(mode="json")
    del dumped["schema_version"]

    with pytest.raises(SchemaVersionMismatch, match="no schema_version field"):
        Game.model_validate(dumped)


def test_construction_with_no_schema_version_is_refused_too() -> None:
    """The refusal is not limited to `model_validate` - it is a `mode="before"`
    validator, so a bare `Game(...)` call that forgets to stamp a version is
    refused the same way a decode is. Nothing builds a `Game` without saying,
    out loud, what engine version it is built at."""
    with pytest.raises(SchemaVersionMismatch, match="no schema_version field"):
        Game(players=[Player(username="alice"), Player(username="bob")])


def test_a_mismatched_game_nested_inside_a_match_is_also_refused() -> None:
    """The check fires uniformly regardless of entry point: a `Game` reached
    as an element of `Match.games` (the shape a decoded match-in-progress
    actually carries) is checked exactly like a bare `Game.model_validate`
    call, because the validator is compiled into `Game`'s own core schema
    rather than being a classmethod override some entry points could route
    around."""
    game = _a_played_game()
    match = Match(players=[Player(username="alice"), Player(username="bob")])
    match.games.append(game)
    dumped = match.model_dump(mode="json")
    dumped["games"][0]["schema_version"] = Game.CURRENT_SCHEMA_VERSION + 1

    with pytest.raises(
        SchemaVersionMismatch, match=f"decodes schema_version={Game.CURRENT_SCHEMA_VERSION}"
    ):
        Match.model_validate(dumped)


#: The version this engine build's predecessor stamped: the last one written
#: before `SpendClause` gained its zone dimension and before
#: `machines/abilities.py` learned to read "Add two mana in any combination of
#: colors". Named here rather than written as `CURRENT_SCHEMA_VERSION - 1` so
#: the test keeps asserting something after the next bump moves the current
#: value further away from it.
_SCHEMA_VERSION_BEFORE_ZONE_CLAUSES = 5


def _a_game_with_restricted_mana_floating() -> Game:
    """A real board whose mana pool holds a CR 106.6-restricted mana with a
    zone clause on it - Interdimensional Web Watch's "Spend this mana only to
    cast spells from exile", tapped for real rather than hand-built.

    This is the state a version-5 snapshot could already be carrying, and the
    reason the version has to move: `Player.mana_pool` is a serialised field,
    so a `RestrictedMana`'s `ManaRestriction` and its `SpendClause`s are all
    reachable from `Game.model_dump()`.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Interdimensional Web Watch"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watch = scenario.find("Interdimensional Web Watch", Zone.BATTLEFIELD, "alice")
    watch.summoning_sick = False
    scenario.game.activate_ability(watch, 0, "alice", color=Color.RED)
    return scenario.game


def test_a_snapshot_written_before_the_zone_clause_existed_is_refused() -> None:
    """The bump rule's own two bullets, both tripped by this change, so a
    version-5 snapshot must not decode here.

    A `SpendClause` gained `zone` - a field added to something reachable from
    `Game.model_dump()`, via `Player.mana_pool.restricted[].restriction.
    clauses[]` - and a version-5 dump has no `zone` key on any clause it
    holds. Decoded at the current version that missing key reads as "this
    clause asks nothing about the origin zone", which is the Web Watch's mana
    quietly paying for a spell cast from the hand: a recorded state resolving
    differently with no signal, the exact failure `schema_version` exists to
    catch.

    The same snapshot is wrong for the second reason too - `machines/
    abilities.py` now parses "Add two mana in any combination of colors",
    a mana-ability parse change on a printing that was already in the pool -
    which is the bump rule's second bullet by name.
    """
    dumped = _a_game_with_restricted_mana_floating().model_dump(mode="json")

    clauses = [
        clause
        for player in dumped["players"]
        for entry in player["mana_pool"]["restricted"]
        for clause in entry["restriction"]["clauses"]
    ]
    assert clauses, "the board is supposed to hold restricted mana with a clause on it"
    for clause in clauses:
        # What a version-5 dump of this pool actually looked like: the field
        # did not exist yet, so the key is absent rather than null.
        del clause["zone"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ZONE_CLAUSES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ZONE_CLAUSES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `Reveal` learned who saw it and against which
#: object and library order (`viewers`, `zone_change_stamp`, `turn`,
#: `library_epoch`), before `Player.library_epoch` and before
#: `Game.known_carries`.
_SCHEMA_VERSION_BEFORE_KNOWN_INFORMATION = 7


def test_the_known_information_bump_moved_the_version_past_seven() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_KNOWN_INFORMATION


def test_a_snapshot_written_before_known_information_is_refused() -> None:
    """A version-7 dump has reveals with no stamp or epoch and players with no
    library epoch; decoded as current, every record would read as an
    unrecognised shape and silently know nothing. Refused instead."""
    dumped = _a_played_game().model_dump(mode="json")
    for player in dumped["players"]:
        del player["library_epoch"]
    del dumped["known_carries"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_KNOWN_INFORMATION

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_KNOWN_INFORMATION}",
    ):
        Game.model_validate(dumped)


#: The version both the known-information change and `Decision.source_id`
#: stamped independently, each without the other's fields.
_SCHEMA_VERSION_OF_EITHER_HALF = 8


def test_a_version_eight_snapshot_is_refused() -> None:
    """A version-8 dump was written by a build with known information and no
    `Decision.source_id`, or with `source_id` and no reveal stamps or epochs.
    Either one decoded as current says the wrong thing, so neither decodes."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_OF_EITHER_HALF
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_OF_EITHER_HALF

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_OF_EITHER_HALF}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `Game.library_orders_kept` recorded which
#: library cards kept their order through a put onto the bottom.
_SCHEMA_VERSION_BEFORE_LIBRARY_ORDERS_KEPT = 10


def test_a_snapshot_written_before_library_orders_kept_is_refused() -> None:
    """A version-10 dump has no `library_orders_kept`; decoded as current, every
    library record a bottom put had kept would silently end."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_LIBRARY_ORDERS_KEPT
    dumped = _a_played_game().model_dump(mode="json")
    del dumped["library_orders_kept"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_LIBRARY_ORDERS_KEPT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_LIBRARY_ORDERS_KEPT}",
    ):
        Game.model_validate(dumped)

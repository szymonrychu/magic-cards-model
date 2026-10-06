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

from magic_cards_model.machines import PriorityOutcome, Step
from magic_cards_model.machines.casting_restrictions import create_spells_cant_be_countered_grant
from magic_cards_model.machines.triggers import AbilityOnStack
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


#: The version stamped before `Decision.quality`, token ownership at creation,
#: and Malevolent Rumble's parsed reveal-to-hand.
_SCHEMA_VERSION_BEFORE_BATTLE_THREE = 11


def test_a_snapshot_written_before_battle_three_is_refused() -> None:
    """A version-11 dump has decisions with no `quality` and tokens with no
    owner; decoded as current, both would read as a different game."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BATTLE_THREE
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BATTLE_THREE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BATTLE_THREE}",
    ):
        Game.model_validate(dumped)


#: The version stamped before battle 5's persisted shapes: a modal triggered
#: ability's chosen modes (`AbilityOnStack.modes`/`.mode_targets`),
#: `Game.announced_reveal_counts`, `Game.search_description_notices`,
#: `CostComponent.variable_count`/`.source`, and `ExileMarker.LINKED`.
_SCHEMA_VERSION_BEFORE_TRIGGER_MODES_AND_REVEAL_COSTS = 12


def test_a_snapshot_written_before_trigger_modes_and_reveal_costs_is_refused() -> None:
    """A version-12 dump has no `announced_reveal_counts` and no
    `search_description_notices`, and a modal trigger in it carries no chosen
    mode; decoded as current, that trigger would be asked for its mode again at
    resolution, which CR 603.3c places at the moment it went on the stack."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_TRIGGER_MODES_AND_REVEAL_COSTS
    dumped = _a_played_game().model_dump(mode="json")
    assert "announced_reveal_counts" in dumped
    assert "search_description_notices" in dumped
    del dumped["announced_reveal_counts"]
    del dumped["search_description_notices"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_TRIGGER_MODES_AND_REVEAL_COSTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_TRIGGER_MODES_AND_REVEAL_COSTS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `CastRecord.keyword_cost_paid` (warp's delayed
#: exile, CR 702.185a) and `Decision.mana_sources` (paying an "unless" by
#: activating mana abilities, CR 608.2g). Battle 6 was stamped 12 -> 13 on its
#: own line of development, beside battle 5's 12 -> 13, so it landed as 14.
_SCHEMA_VERSION_BEFORE_BATTLE_SIX = 13


def test_a_snapshot_written_before_battle_six_is_refused() -> None:
    """A version-13 dump has cast records with no `keyword_cost_paid`; decoded
    as current, a warp card cast for its warp cost would read as cast for its
    mana cost and never be exiled at end step."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BATTLE_SIX
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BATTLE_SIX

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BATTLE_SIX}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `Answer.damage` (the `ASSIGN_COMBAT_DAMAGE` tape
#: field) and `Game.unreadable_counter_amount_notices` existed.
_SCHEMA_VERSION_BEFORE_DAMAGE_ASSIGNMENT = 14


def test_a_snapshot_written_before_damage_assignment_is_refused() -> None:
    """A version-14 dump has no `unreadable_counter_amount_notices`, and its tape
    cannot hold a combat damage assignment; decoded as current, a paused combat
    would replay against a question that build never asked. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_DAMAGE_ASSIGNMENT
    dumped = _a_played_game().model_dump(mode="json")
    del dumped["unreadable_counter_amount_notices"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_DAMAGE_ASSIGNMENT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_DAMAGE_ASSIGNMENT}",
    ):
        Game.model_validate(dumped)


#: The version stamped before battle 7, U1 (PR #21) and battle 8, which share
#: one bump because none was deployed on its own: a triggered mana ability (CR
#: 605.1b) resolving off the stack (CR 605.4a), scry asking CR 401.4's bottom
#: order and the attack requirement (CR 508.1d); `AbilityOnStack.source_last_known`
#: (CR 113.7a); cast records keyed per object (CR 400.7) and
#: `AbilityOnStack.source_stamp`.
_SCHEMA_VERSION_BEFORE_BATTLES_SEVEN_AND_EIGHT = 15


def test_a_snapshot_written_before_battles_seven_and_eight_is_refused() -> None:
    """A version-15 dump can hold Leyline of Abundance's trigger on the stack,
    a tape one scry-order question short, and cast records keyed by card id
    that would read as no record at all; decoded as current, it would replay
    into a game no version-16 engine could have produced."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BATTLES_SEVEN_AND_EIGHT
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BATTLES_SEVEN_AND_EIGHT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BATTLES_SEVEN_AND_EIGHT}",
    ):
        Game.model_validate(dumped)


#: The version stamped before flow 3's integration wave fixed three
#: already-reachable dispatch bugs: `machines.combat.block_refusal` never
#: read a blocker's own "can't block" text (CR 509.1b, Bloodghast blocking
#: illegally), `declare_blockers_step` skipped `Combat.declare_blockers`
#: entirely on a fully unblocked attack (`Combat.blockers_declared` staying
#: falsely `False` for CR 509.1h's "unblocked creature" checks), and
#: `Game._state_based_actions_once` never called
#: `annihilate_counters_on` at all (CR 704.5q's pairwise +1/+1/-1/-1 removal
#: sat unreachable in `models/card_state.py`, exercised only by the scenario
#: harness). No field was added - the bump rule's second bullet, like
#: "Bumped 44 -> 45" above.
_SCHEMA_VERSION_BEFORE_FLOW_THREE_BLOCK_TAP_AND_ANNIHILATE_FIXES = 50


def test_a_snapshot_written_before_flow_three_integration_is_refused() -> None:
    """A version-50 dump can hold Bloodghast mid-combat with an illegal block
    already nodded through, a fully unblocked attack whose
    `Combat.blockers_declared` never got set, or a permanent already carrying
    both +1/+1 and -1/-1 counters that the engine's own state-based-action
    loop had never annihilated; decoded as current, each of those reads a
    board CR 509.1b/509.1h/704.5q say cannot exist. Refused instead."""
    assert (
        Game.CURRENT_SCHEMA_VERSION
        > _SCHEMA_VERSION_BEFORE_FLOW_THREE_BLOCK_TAP_AND_ANNIHILATE_FIXES
    )
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_FLOW_THREE_BLOCK_TAP_AND_ANNIHILATE_FIXES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_FLOW_THREE_BLOCK_TAP_AND_ANNIHILATE_FIXES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before the F1T11 integration bump: `Game.player_
#: subject_split_notices` (T5) and `CastingRuleEffect.excluded_source_id`
#: (T5) landed without a bump, and the dead-object-to-library dies readers
#: (T9/G6) closed Murderous Rider et al. against a `GameEvent.zone_change_
#: stamp` bumped separately (46 -> 47, still true and unrepeated here); this
#: is the integration wave's own bump for what stayed unbumped after it.
_SCHEMA_VERSION_BEFORE_F1T11_INTEGRATION = 51


def test_the_f1t11_integration_bump_moved_the_version_past_fifty_one() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_F1T11_INTEGRATION


def test_a_snapshot_written_before_the_f1t11_integration_bump_is_refused() -> None:
    """A version-51 dump is refused rather than decoded as current: Smuggler's
    Copter's crew-and-attack/block "you may draw a card. If you do, discard a
    card." went from `<none>` (a silent no-op) to a real merged reader
    (f1-t8/G5) on a printing that was already in the pool, the bump rule's
    second bullet by name - a version-51 game holding a crewed, attacking
    Copter would resolve that trigger differently decoded here."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_F1T11_INTEGRATION

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_F1T11_INTEGRATION}",
    ):
        Game.model_validate(dumped)


#: The version stamped before S03 gave `Player` its "no maximum hand size for
#: the rest of the game" field (Sea Gate Restoration, CR 613.11) and taught
#: `has_no_maximum_hand_size` and annihilator (CR 702.86a) to act where they
#: did nothing.
_SCHEMA_VERSION_BEFORE_S03_NO_MAXIMUM_HAND_SIZE = 53


def test_a_snapshot_written_before_s03_is_refused() -> None:
    """A version-53 dump cannot say whether a player's maximum hand size was
    removed for the rest of the game, and a version-53 board with Reliquary
    Tower or an annihilator attacker would play differently decoded here."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_S03_NO_MAXIMUM_HAND_SIZE
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_S03_NO_MAXIMUM_HAND_SIZE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_S03_NO_MAXIMUM_HAND_SIZE}",
    ):
        Game.model_validate(dumped)


#: The version stamped before S05 (putting creature cards onto the
#: battlefield): `CardState.last_known_mana_value`/`times_transformed`,
#: `CastRecord.additional_cost_mana_values`, `AbilityOnStack.cost_sacrificed_
#: mana_values` and `DelayedEffectSpec`'s `transform_subject` kind are new
#: persisted fields.
_SCHEMA_VERSION_BEFORE_S05_PUT_ONTO_BATTLEFIELD = 54


def test_the_s05_bump_moved_the_version_past_fifty_four() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_S05_PUT_ONTO_BATTLEFIELD


def test_a_snapshot_written_before_the_s05_bump_is_refused() -> None:
    """A version-54 dump has no mana value recorded for a sacrificed cost
    and no transform count, so an Eldritch Evolution or a pending Aang delayed
    trigger in it would resolve differently decoded here - refused instead."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_S05_PUT_ONTO_BATTLEFIELD

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_S05_PUT_ONTO_BATTLEFIELD}",
    ):
        Game.model_validate(dumped)


#: The last version before S09's linked-exile fields: `ExileAnnotation.
#: linked_permanent_stamp` (CR 400.7's "which object" for a CR 607.2a link),
#: `GameEvent.origin_exile_annotation` (the pile a played card came out of),
#: and an activated `AbilityOnStack` now carrying `source_stamp`.
_SCHEMA_VERSION_BEFORE_LINKED_EXILE_STAMPS = 55


def test_the_linked_exile_bump_moved_the_version_past_fifty_five() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_LINKED_EXILE_STAMPS


def test_a_snapshot_written_before_the_linked_exile_stamps_is_refused() -> None:
    """A version-55 dump is refused rather than decoded as current: its
    linked exile piles carry no object stamp, so a Keen-Eyed Curator that
    left and came back would count its earlier self's pile again, and a
    pending Voltaic Visionary trigger would have no pile to read."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_LINKED_EXILE_STAMPS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_LINKED_EXILE_STAMPS}",
    ):
        Game.model_validate(dumped)


#: The last version before S15's resolution-created replacements:
#: `Game.draw_redirections` became `Game.created_replacements`, and
#: `DelayedEffectSpec` gained `CreatedTriggeredAbility`.
_SCHEMA_VERSION_BEFORE_CREATED_REPLACEMENTS = 57


def test_the_created_replacements_bump_moved_the_version_past_fifty_seven() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CREATED_REPLACEMENTS


def test_a_snapshot_written_before_created_replacements_is_refused() -> None:
    """A version-57 dump is refused rather than decoded as current: a
    pending Plagiarize in it sits on `draw_redirections`, a field this build
    no longer has, and would silently stop replacing anything."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CREATED_REPLACEMENTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CREATED_REPLACEMENTS}",
    ):
        Game.model_validate(dumped)


#: The last version before S18's `CardState.last_known_attached_to`.
_SCHEMA_VERSION_BEFORE_LAST_KNOWN_ATTACHMENT = 58


def test_the_last_known_attachment_bump_moved_the_version_past_fifty_eight() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_LAST_KNOWN_ATTACHMENT


def test_a_snapshot_written_before_the_last_known_attachment_is_refused() -> None:
    """A version-58 dump is refused rather than decoded as current: an Aura
    that left the battlefield in it carries no `last_known_attached_to`, so
    its pending enters trigger would find nothing to act on."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_LAST_KNOWN_ATTACHMENT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_LAST_KNOWN_ATTACHMENT}",
    ):
        Game.model_validate(dumped)


#: The last version before S23's static anthems: `QualifiedCreatures` gained
#: its supertype, nontoken and chosen-colour fields and `Count` gained
#: `CountOtherCreaturesLikeThatOne`.
_SCHEMA_VERSION_BEFORE_STATIC_ANTHEM_QUALIFIERS = 59


def test_the_static_anthem_bump_moved_the_version_past_fifty_nine() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_STATIC_ANTHEM_QUALIFIERS


def test_a_snapshot_written_before_static_anthem_qualifiers_is_refused() -> None:
    """A version-59 dump is refused rather than decoded as current: a board
    holding Caged Sun or Mirror Box computed no anthem there and computes one
    here, and a stored `QualifiedCreatures` has no chosen-colour field."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_STATIC_ANTHEM_QUALIFIERS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_STATIC_ANTHEM_QUALIFIERS}",
    ):
        Game.model_validate(dumped)


#: The last version before S30's Ring: `Player` gained the Ring's count and
#: Ring-bearer designation (CR 701.54).
_SCHEMA_VERSION_BEFORE_THE_RING = 61


def test_the_ring_bump_moved_the_version_past_sixty_one() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_THE_RING


def test_a_snapshot_written_before_the_ring_is_refused() -> None:
    """A version-61 dump is refused rather than decoded as current: its
    players have no Ring count or Ring-bearer, and a pending Gollum trigger
    resolved as a no-op there and tempts here."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_THE_RING

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_THE_RING}",
    ):
        Game.model_validate(dumped)


def _a_game_with_a_pending_dies_trigger_and_a_cant_be_countered_grant() -> Game:
    """A real board carrying both of T5's/T9's own reachable-but-unbumped
    state at once, played to the point that matters rather than hand-built:
    Murderous Rider's dies trigger sitting on the stack, still holding the
    `GameEvent.zone_change_stamp` (T9/G6) that lets it find its own graveyard
    incarnation when it resolves, and a Veil-of-Summer-shaped `CastingRule
    Effect` (T5/G2b) granting alice's spells protection from countering this
    turn, recorded on `Game.casting_rule_effects`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Murderous Rider"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rider = scenario.creature("Murderous Rider", "alice")

    scenario.game.destroy(rider)
    scenario.game.put_triggers_on_stack()
    scenario.game.casting_rule_effects.append(
        create_spells_cant_be_countered_grant("alice", "Veil of Summer")
    )
    return scenario.game


def test_round_trip_preserves_a_pending_dies_trigger_and_the_cant_be_countered_grant() -> None:
    """Extends the module's own round-trip coverage (`test_round_trip_at_the_
    current_version_is_unaffected` only ever plays a pump spell) to the two
    kinds of state this integration bump exists for: a pending trigger
    carrying a `GameEvent.zone_change_stamp`, and a `Game.casting_rule_
    effects` entry - both reachable from `Game.model_dump()` and both able to
    resolve differently if a decode ever silently lost either one."""
    game = _a_game_with_a_pending_dies_trigger_and_a_cant_be_countered_grant()

    (rider_trigger,) = [
        ability
        for ability in game.stack
        if isinstance(ability, AbilityOnStack) and ability.source_name == "Murderous Rider"
    ]
    assert rider_trigger.event is not None
    assert rider_trigger.event.zone_change_stamp is not None
    assert len(game.casting_rule_effects) == 1

    dumped = game.model_dump(mode="json")
    assert dumped["schema_version"] == Game.CURRENT_SCHEMA_VERSION

    decoded = Game.model_validate(dumped)
    assert decoded.model_dump(mode="json") == dumped

    (decoded_trigger,) = [
        ability
        for ability in decoded.stack
        if isinstance(ability, AbilityOnStack) and ability.source_name == "Murderous Rider"
    ]
    assert decoded_trigger.event is not None
    assert decoded_trigger.event.zone_change_stamp == rider_trigger.event.zone_change_stamp
    assert len(decoded.casting_rule_effects) == 1
    assert decoded.casting_rule_effects[0].kind == game.casting_rule_effects[0].kind

    # And it is still live: the dies trigger still resolves and still finds
    # its own graveyard incarnation to move, exactly as the un-decoded game
    # would have.
    for _ in range(len(decoded.players_in_game)):
        holder = decoded.priority_holder or decoded.controller_of_player(decoded.turn.active_player)
        outcome = decoded.pass_priority(holder)
        if outcome is not PriorityOutcome.PASSED:
            break
    decoded_rider = [
        state for state in decoded.player("alice").library if state.name == "Murderous Rider"
    ]
    assert decoded_rider, "the decoded trigger must still find and move its own dead incarnation"


#: The version stamped before `PlayPermission` gained `until_next_end_step_of`
#: ("until your next end step", Riveteers Charm's second mode).
_SCHEMA_VERSION_BEFORE_NEXT_END_STEP_PERMISSIONS = 56


def _a_game_with_a_next_end_step_permission() -> Game:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Riveteers Charm"],
            battlefield=["Swamp", "Mountain", "Forest"],
            library=["Forest", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Riveteers Charm")
    casting.choose_modes([2])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Swamp", "Mountain", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario.game


def test_a_next_end_step_permission_round_trips_at_the_current_version() -> None:
    game = _a_game_with_a_next_end_step_permission()
    assert {p.until_next_end_step_of for p in game.play_permissions} == {"alice"}

    dumped = game.model_dump(mode="json")
    decoded = Game.model_validate(dumped)

    assert decoded.model_dump(mode="json") == dumped
    assert {p.until_next_end_step_of for p in decoded.play_permissions} == {"alice"}


def test_a_snapshot_written_before_next_end_step_permissions_is_refused() -> None:
    """A version-56 dump has no `until_next_end_step_of` on any permission;
    decoded as current it would read as a permission with no end-step bound
    at all - one that silently outlives its own printed duration."""
    dumped = _a_game_with_a_next_end_step_permission().model_dump(mode="json")
    for permission in dumped["play_permissions"]:
        del permission["until_next_end_step_of"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NEXT_END_STEP_PERMISSIONS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NEXT_END_STEP_PERMISSIONS}",
    ):
        Game.model_validate(dumped)


#: The last version before S29's day and night (CR 731): `Game` gained
#: `day_night` and `previous_turn_active_player`.
_SCHEMA_VERSION_BEFORE_DAY_AND_NIGHT = 60


def test_the_day_night_bump_moved_the_version_past_sixty() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_DAY_AND_NIGHT


def test_a_snapshot_written_before_day_and_night_is_refused() -> None:
    """A version-60 dump has no `day_night`; decoded as current it would read
    as "neither" even for a game whose Gavony Dawnguard had already made it
    day, and no daybound permanent would ever transform."""
    dumped = _a_played_game().model_dump(mode="json")
    del dumped["day_night"]
    del dumped["previous_turn_active_player"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_DAY_AND_NIGHT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_DAY_AND_NIGHT}",
    ):
        Game.model_validate(dumped)


#: The last version before S31's phasing: `CardState` had no
#: `phased_out_under`/`phased_out_indirectly` and `Game` no `phased_out`.
_SCHEMA_VERSION_BEFORE_PHASING = 62


def test_the_phasing_bump_moved_the_version_past_sixty_two() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_PHASING


def test_a_snapshot_written_before_phasing_is_refused() -> None:
    """A version-62 dump is refused rather than decoded as current: it has no
    `phased_out` list, and Teferi, Master of Time's -3 resolved nothing there
    and phases a creature out here (CR 702.26b)."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_PHASING

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_PHASING}",
    ):
        Game.model_validate(dumped)


#: The last version before S33's `AbilityOnStack.source_times_transformed`.
_SCHEMA_VERSION_BEFORE_SOURCE_TIMES_TRANSFORMED = 63


def test_the_source_times_transformed_bump_moved_the_version_past_sixty_three() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SOURCE_TIMES_TRANSFORMED


def test_a_snapshot_written_before_source_times_transformed_is_refused() -> None:
    """A version-63 dump is refused rather than decoded as current: a pending
    trigger in it carries no `source_times_transformed`, so CR 701.27f could
    not tell whether its source had transformed since."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SOURCE_TIMES_TRANSFORMED

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SOURCE_TIMES_TRANSFORMED}",
    ):
        Game.model_validate(dumped)


#: The last version before S26's graveyard cast permissions.
_SCHEMA_VERSION_BEFORE_GRAVEYARD_CAST_PERMISSIONS = 64


def test_the_graveyard_cast_permission_bump_moved_the_version_past_sixty_four() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_GRAVEYARD_CAST_PERMISSIONS


def test_a_snapshot_written_before_graveyard_cast_permissions_is_refused() -> None:
    """A version-64 dump is refused rather than decoded as current: it has no
    `once_per_turn_cast_permissions_used`, so a Rivaz of the Claw already used
    this turn would decode as unused."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_GRAVEYARD_CAST_PERMISSIONS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_GRAVEYARD_CAST_PERMISSIONS}",
    ):
        Game.model_validate(dumped)


#: The last version before C00-T1's `ManaSpend.any_color` (CR 609.4b).
_SCHEMA_VERSION_BEFORE_SPEND_AS_ANY_COLOR = 65


def test_the_spend_as_any_color_bump_moved_the_version_past_sixty_five() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SPEND_AS_ANY_COLOR


def test_a_snapshot_written_before_spend_as_any_color_is_refused() -> None:
    """A version-65 dump is refused rather than decoded as current: an open
    activation payment in it carries no `ManaSpend.any_color`, so CR 609.4b's
    "as though it were mana of any color" would silently stop applying."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SPEND_AS_ANY_COLOR

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SPEND_AS_ANY_COLOR}",
    ):
        Game.model_validate(dumped)


#: The last version before C00-T5's `CostComponent.link_to_permanent_id`.
_SCHEMA_VERSION_BEFORE_DELVE_EXILE_LINK = 66


def test_the_delve_exile_link_bump_moved_the_version_past_sixty_six() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_DELVE_EXILE_LINK


def test_a_snapshot_written_before_the_delve_exile_link_is_refused() -> None:
    """A version-66 dump is refused rather than decoded as current: a pending
    `AbilityOnStack.keyword_activation`/`.unless_payment`'s own exile
    component in it carries no `link_to_permanent_id`, so CR 607.2q's own
    "exiled with it" read would find nothing linked at all."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_DELVE_EXILE_LINK

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_DELVE_EXILE_LINK}",
    ):
        Game.model_validate(dumped)


#: The last version before C01-T1's `Player.has_enduring_story`.
_SCHEMA_VERSION_BEFORE_ENDURING_STORY = 67


def test_the_enduring_story_bump_moved_the_version_past_sixty_seven() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ENDURING_STORY


def test_a_snapshot_written_before_the_enduring_story_is_refused() -> None:
    """A version-67 dump is refused rather than decoded as current: its
    players carry no `has_enduring_story`, so a player who had already met
    CR 702.195a's count would decode without the designation every "as long
    as you have an enduring story" static reads."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ENDURING_STORY

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ENDURING_STORY}",
    ):
        Game.model_validate(dumped)


#: The last version before C01-T3's `PlayPermission.pays_life_for_mana_value`
#: and `PlayPermission.choice_group`.
_SCHEMA_VERSION_BEFORE_PAY_LIFE_PERMISSION = 68


def test_the_pay_life_permission_bump_moved_the_version_past_sixty_eight() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_PAY_LIFE_PERMISSION


def test_a_snapshot_written_before_the_pay_life_permission_is_refused() -> None:
    """A version-68 dump is refused rather than decoded as current: a live
    `PlayPermission` in it carries no `pays_life_for_mana_value`, so an
    Inside Information grant would decode as a free cast (CR 118.9b), and no
    `choice_group`, so "one of those cards" would decode as all of them."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_PAY_LIFE_PERMISSION

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_PAY_LIFE_PERMISSION}",
    ):
        Game.model_validate(dumped)


#: The last version before C01-T6's `CardState.chosen_modal_options`
#: (Gollum, Riddle Master's own "choose one that hasn't been chosen -").
_SCHEMA_VERSION_BEFORE_CHOSEN_MODAL_OPTIONS = 69


def test_the_chosen_modal_options_bump_moved_the_version_past_sixty_nine() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CHOSEN_MODAL_OPTIONS


def test_a_snapshot_written_before_chosen_modal_options_is_refused() -> None:
    """A version-69 dump is refused rather than decoded as current: a
    permanent on the battlefield in it carries no `chosen_modal_options`, so
    a "choose one that hasn't been chosen -" trigger would forget every mode
    it had already picked and offer them all again."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CHOSEN_MODAL_OPTIONS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CHOSEN_MODAL_OPTIONS}",
    ):
        Game.model_validate(dumped)


#: The last version before C01-T7's `PreventionShield.source_stamp`/
#: `.lasts_while` and `GraveyardArrival.card_id`.
_SCHEMA_VERSION_BEFORE_SOURCE_KEYED_PREVENTION = 70


def test_the_source_keyed_prevention_bump_moved_the_version_past_seventy() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SOURCE_KEYED_PREVENTION


def test_a_snapshot_written_before_source_keyed_prevention_is_refused() -> None:
    """A version-70 dump is refused rather than decoded as current: a
    prevention shield in it has no `source_stamp`/`lasts_while`, so CR 400.7's
    new object and CR 611.2b's "for as long as" would both be lost, and its
    graveyard ledger has no `card_id` to answer "put there from the
    battlefield this turn"."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SOURCE_KEYED_PREVENTION

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SOURCE_KEYED_PREVENTION}",
    ):
        Game.model_validate(dumped)


#: The last version before `CombatMachine.declared_attacking_power`.
_SCHEMA_VERSION_BEFORE_DECLARED_ATTACKING_POWER = 71


def test_the_declared_attacking_power_bump_moved_the_version_past_seventy_one() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_DECLARED_ATTACKING_POWER


def test_a_snapshot_written_before_declared_attacking_power_is_refused() -> None:
    """A version-71 dump is refused rather than decoded as current: its
    combat carries no `declared_attacking_power`, so a pack tactics trigger
    on the stack would resolve as though nothing had attacked."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_DECLARED_ATTACKING_POWER

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_DECLARED_ATTACKING_POWER}",
    ):
        Game.model_validate(dumped)


#: The last version before `ManaPool.treasure`/`CastRecord.treasure_mana_spent`.
_SCHEMA_VERSION_BEFORE_TREASURE_MANA = 72


def test_the_treasure_mana_bump_moved_the_version_past_seventy_two() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_TREASURE_MANA


def test_a_snapshot_written_before_treasure_mana_is_refused() -> None:
    """A version-72 dump is refused rather than decoded as current: its pools
    and cast records carry no Treasure provenance, so "if mana from a Treasure
    was spent to cast it" would read false for a spell that was."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_TREASURE_MANA

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_TREASURE_MANA}",
    ):
        Game.model_validate(dumped)


#: The last version before `CastRecord.cast_using_teamwork`/`Game.
#: became_tapped_count_this_turn` (C02-T2, Teamwork).
_SCHEMA_VERSION_BEFORE_TEAMWORK = 73


def test_the_teamwork_bump_moved_the_version_past_seventy_three() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_TEAMWORK


def test_a_snapshot_written_before_teamwork_is_refused() -> None:
    """A version-73 dump is refused rather than decoded as current: its cast
    records carry no `cast_using_teamwork`, so "if this spell was cast using
    teamwork" would read false for a spell that was, and it has no per-turn
    tap count for Captain America, Living Legend's own "first time ... this
    turn" intervening if to read at all."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_TEAMWORK

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_TEAMWORK}",
    ):
        Game.model_validate(dumped)


#: The last version before `Game.harnessed`/`Game.power_up_restricted_turns`.
_SCHEMA_VERSION_BEFORE_HARNESS_AND_POWER_UP_RESTRICTION = 74


def test_the_harness_and_power_up_restriction_bump_moved_the_version_past_seventy_four() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_HARNESS_AND_POWER_UP_RESTRICTION


def test_a_snapshot_written_before_harness_and_power_up_restriction_is_refused() -> None:
    """A version-74 dump is refused rather than decoded as current: it
    carries no `harnessed`/`power_up_restricted_turns` fields at all, which
    would silently read as "nothing is harnessed" and "no turn is power-up-
    restricted" for a game that actually recorded one of either."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_HARNESS_AND_POWER_UP_RESTRICTION

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_HARNESS_AND_POWER_UP_RESTRICTION}",
    ):
        Game.model_validate(dumped)


#: The last version before `Game.counters_put_this_turn` (C02-T4).
_SCHEMA_VERSION_BEFORE_COUNTERS_PUT_HISTORY = 75


def test_the_counters_put_history_bump_moved_the_version_past_seventy_five() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_COUNTERS_PUT_HISTORY


def test_a_snapshot_written_before_counters_put_history_is_refused() -> None:
    """A version-75 dump is refused rather than decoded as current: it
    carries no record of the counters put this turn, so Kid Loki's hexproof
    and Beast's flying would read as though none had been put."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_COUNTERS_PUT_HISTORY

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_COUNTERS_PUT_HISTORY}",
    ):
        Game.model_validate(dumped)


#: The version stamped before C02-T5's "one or more" batch bookkeeping
#: (`tapped_since_last_batch`, `graveyard_arrivals_announced`) and this-turn
#: spell grants (`next_spell_free_cast_grants`, `spell_cost_reduction_grants`).
_SCHEMA_VERSION_BEFORE_BATCHED_EVENTS = 76


def test_the_batched_events_bump_moved_the_version_past_seventy_six() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BATCHED_EVENTS


def test_a_snapshot_written_before_batched_events_is_refused() -> None:
    """A version-76 dump has no `graveyard_arrivals_announced`; decoded as
    current, every graveyard arrival already this turn would read as not yet
    announced and be raised again as one fresh batch. Refused instead."""
    dumped = _a_played_game().model_dump(mode="json")
    for field in (
        "tapped_since_last_batch",
        "graveyard_arrivals_announced",
        "next_spell_free_cast_grants",
        "spell_cost_reduction_grants",
    ):
        del dumped[field]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BATCHED_EVENTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BATCHED_EVENTS}",
    ):
        Game.model_validate(dumped)


#: The last version before C02-T7's `CardState.chosen_modal_options_this_turn`
#: (The Vision's own per-turn "choose one that hasn't been chosen this turn
#: -", reset every cleanup step, a sibling of C01-T6's never-reset
#: `chosen_modal_options`) and `machines.delayed.StaticPrisonReturn.
#: return_zone` (Cloak and Dagger, Entwined's CR 610.3 delayed return from a
#: hand rather than only from the battlefield).
_SCHEMA_VERSION_BEFORE_PER_TURN_MODAL_OPTIONS_AND_RETURN_ZONE = 77


def test_the_per_turn_modal_options_bump_moved_the_version_past_seventy_seven() -> None:
    assert (
        Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_PER_TURN_MODAL_OPTIONS_AND_RETURN_ZONE
    )


def test_a_snapshot_written_before_per_turn_modal_options_and_return_zone_is_refused() -> None:
    """A version-77 dump is refused rather than decoded as current: a
    permanent in it carries no `chosen_modal_options_this_turn`, so The
    Vision's per-turn "choose one that hasn't been chosen this turn -" would
    read every prior turn's choices as still exclusive; and a pending
    `StaticPrisonReturn` in it carries no `return_zone`, so Cloak and Dagger,
    Entwined's CR 610.3 return of a card exiled from a hand would default to
    the battlefield instead."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_PER_TURN_MODAL_OPTIONS_AND_RETURN_ZONE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_PER_TURN_MODAL_OPTIONS_AND_RETURN_ZONE}",
    ):
        Game.model_validate(dumped)


#: The last version before the self-pump counts' `excludes_self` (C02-T8).
_SCHEMA_VERSION_BEFORE_EXCLUDES_SELF_COUNTS = 78


def test_the_excludes_self_count_bump_moved_the_version_past_seventy_eight() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_EXCLUDES_SELF_COUNTS


def test_a_snapshot_written_before_excludes_self_counts_is_refused() -> None:
    """A version-78 dump is refused rather than decoded as current: a stored
    "for each other artifact you control" count from before carried no
    `excludes_self`, so it would count the pumped creature itself."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_EXCLUDES_SELF_COUNTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_EXCLUDES_SELF_COUNTS}",
    ):
        Game.model_validate(dumped)


#: The last version before `SpendClause.min_mana_value`/`requires_x_in_cost`
#: (C02 integration, Helga, Skittish Seer's spend restriction).
_SCHEMA_VERSION_BEFORE_SPEND_MANA_VALUE = 79


def test_the_spend_mana_value_bump_moved_the_version_past_seventy_nine() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SPEND_MANA_VALUE


def test_a_snapshot_written_before_spend_mana_value_is_refused() -> None:
    """A version-79 dump is refused: mana it holds from a restriction that
    was unread then (and so permitted nothing) would decode as unread now."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SPEND_MANA_VALUE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SPEND_MANA_VALUE}",
    ):
        Game.model_validate(dumped)


#: The last version before EC2's condition reader: `Game.turn_counts`/
#: `turn_counts_last_turn`/`damage_dealt_this_turn`, `CastRecord.cast_step`/
#: `cast_during_turn_of` and `GameEvent.declared_attacker`.
_SCHEMA_VERSION_BEFORE_CONDITION_READER = 80


def test_the_condition_reader_bump_moved_the_version_past_eighty() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CONDITION_READER


def test_a_snapshot_written_before_the_condition_reader_is_refused() -> None:
    """A version-80 dump is refused rather than decoded as current: it has no
    per-turn count ledger, so "it's the first combat phase of the turn" would
    read an additional combat as the first, and its cast records carry no step
    for "if you cast it during your main phase"."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CONDITION_READER

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CONDITION_READER}",
    ):
        Game.model_validate(dumped)


#: The last version before EC3's cast-record reader: `CastRecord.kicker_costs_paid`/
#: `bargained`/`evidence_collected`/`revealed_for_cost`/
#: `controlled_subtypes_as_cast`/`creature_mana_spent`/`snow_mana_spent`.
_SCHEMA_VERSION_BEFORE_CAST_RECORD_READER = 81


def test_the_cast_record_reader_bump_moved_the_version_past_eighty_one() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CAST_RECORD_READER


def test_a_snapshot_written_before_the_cast_record_reader_is_refused() -> None:
    """A version-81 dump is refused rather than decoded as current: its cast
    records carry no kicker costs, bargain, collected evidence or creature/snow
    mana spent, so "if it was bargained" or "if it was kicked twice" would read
    a spell cast that way as one that was not."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CAST_RECORD_READER

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CAST_RECORD_READER}",
    ):
        Game.model_validate(dumped)


#: The last version before EC4's turn-history readers: `Game.turn_history`/
#: `turn_history_last_turn`, `exile_residents_seen`,
#: `dealt_combat_damage_since_their_turn` and `DamageDealt`'s source and
#: recipient facts.
_SCHEMA_VERSION_BEFORE_TURN_HISTORY = 82


def test_the_turn_history_bump_moved_the_version_past_eighty_two() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_TURN_HISTORY


def test_a_snapshot_written_before_the_turn_history_is_refused() -> None:
    """A version-82 dump has no turn history: decoded as current, "if a
    non-Skeleton creature died under your control this turn" would read a
    turn whose deaths were never recorded as a turn where nothing died."""
    dumped = _a_played_game().model_dump(mode="json")
    for field in (
        "turn_history",
        "turn_history_last_turn",
        "exile_residents_seen",
        "dealt_combat_damage_since_their_turn",
    ):
        del dumped[field]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_TURN_HISTORY

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_TURN_HISTORY}",
    ):
        Game.model_validate(dumped)


#: The last version before EC5's player-state readers: `Player.starting_life`.
_SCHEMA_VERSION_BEFORE_STARTING_LIFE = 83


def test_the_starting_life_bump_moved_the_version_past_eighty_three() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_STARTING_LIFE


def test_a_snapshot_written_before_the_starting_life_is_refused() -> None:
    """A version-83 dump has no `starting_life`: decoded as current, the
    player's validator would record the life they have now as the life they
    began with (CR 103.4), so "if your life total is less than your starting
    life total" would read a player at 12 life as never having lost any."""
    dumped = _a_played_game().model_dump(mode="json")
    for player in dumped["players"]:
        del player["starting_life"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_STARTING_LIFE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_STARTING_LIFE}",
    ):
        Game.model_validate(dumped)


#: The last version before EC6's object-state readers: `CardState.saddled`/
#: `saddled_by`/`suspected`/`renowned`/`venture_room`/`dungeon_completions`/
#: `last_known_attachments`.
_SCHEMA_VERSION_BEFORE_OBJECT_STATE = 84


def test_the_object_state_bump_moved_the_version_past_eighty_four() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_OBJECT_STATE


def test_a_snapshot_written_before_the_object_state_is_refused() -> None:
    """A version-84 dump has no renowned, suspected or saddled designation:
    decoded as current, a renowned creature (CR 702.112b) would read as never
    having become renowned, and "if it's saddled" as false."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_OBJECT_STATE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_OBJECT_STATE}",
    ):
        Game.model_validate(dumped)


#: The last version before Forecast's own once-each-turn tracking:
#: `Game.forecast_activations` (CR 702.57b).
_SCHEMA_VERSION_BEFORE_FORECAST = 85


def test_the_forecast_bump_moved_the_version_past_eighty_five() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_FORECAST


def test_a_snapshot_written_before_forecast_is_refused() -> None:
    """A version-85 dump has no `forecast_activations`: decoded as current, a
    forecast ability activated earlier that turn (CR 702.57b) would read as
    never having been, and a second activation the same upkeep would be
    wrongly allowed."""
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_FORECAST

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_FORECAST}",
    ):
        Game.model_validate(dumped)


#: The last version before Mana Sculpt's own delayed mana trigger:
#: `machines/delayed.DelayedTrigger.any_main_phase`.
_SCHEMA_VERSION_BEFORE_ANY_MAIN_PHASE_DELAYED_MANA = 86


def test_the_any_main_phase_delayed_mana_bump_moved_the_version_past_eighty_six() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ANY_MAIN_PHASE_DELAYED_MANA


def test_a_snapshot_written_before_any_main_phase_delayed_mana_is_refused() -> None:
    """A version-86 pending `DelayedTrigger` has no `any_main_phase`: decoded
    as current, Mana Sculpt's own "at the beginning of your next main phase"
    trigger would read as `False` (the pre-existing single-`step` gate),
    matching neither of the controller's own main phases at all - a mana
    grant that was waiting to fire silently never does."""
    game = _a_played_game()
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.delayed import AddManaAmountForController, DelayedTrigger
    from magic_cards_model.models.card import Color

    game.delayed_triggers.triggers.append(
        DelayedTrigger(
            text="At the beginning of your next main phase, add {C}.",
            effect=AddManaAmountForController(amount=1, color=Color.COLORLESS),
            event=TriggerEvent.BEGINNING_OF_STEP,
            any_main_phase=True,
            controller="alice",
            source_name="Mana Sculpt",
            only_when_active="alice",
        )
    )
    dumped = game.model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ANY_MAIN_PHASE_DELAYED_MANA

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ANY_MAIN_PHASE_DELAYED_MANA}",
    ):
        Game.model_validate(dumped)


#: The last version before CR 614.10's skip-turn counter:
#: `machines.turn.TurnMachine.skipped_turns`.
_SCHEMA_VERSION_BEFORE_SKIPPED_TURNS = 87


def test_the_skipped_turns_bump_moved_the_version_past_eighty_seven() -> None:
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SKIPPED_TURNS


def test_a_snapshot_written_before_skipped_turns_is_refused() -> None:
    """A version-87 dump has no `turn.skipped_turns`: decoded as current, a
    player Ral Zarek's own "-7" made skip their next turns would read as
    having none pending, and CR 614.10's skip would silently not happen on
    their next turn."""
    dumped = _a_played_game().model_dump(mode="json")
    del dumped["turn"]["skipped_turns"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SKIPPED_TURNS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SKIPPED_TURNS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `CastRecord` gained `enters_with_counters` (a
#: cast permission's CR 614.1c "enters with a counter" rider) and `Game`
#: gained `next_spell_keyword_grants` ("the next noncreature spell you cast
#: this turn has affinity for artifacts", CR 702.41a) - tmt T6.
_SCHEMA_VERSION_BEFORE_CAST_PERMISSION_RIDERS = 90


def test_a_snapshot_written_before_cast_permission_riders_is_refused() -> None:
    """A version-90 dump has no next-spell keyword grants and cast records
    with no rider: decoded as current, a Leonardo-cast creature on the stack
    would enter without its finality counter. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CAST_PERMISSION_RIDERS
    dumped = _a_played_game().model_dump(mode="json")
    assert dumped["next_spell_keyword_grants"] == []
    del dumped["next_spell_keyword_grants"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CAST_PERMISSION_RIDERS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CAST_PERMISSION_RIDERS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `machines/cost.CostComponent` gained
#: `exile_after` (Champion of the Clachan's own "behold a Kithkin and exile
#: it", CR 118.8/601.2f) - ecl T4.
_SCHEMA_VERSION_BEFORE_BEHOLD_AND_EXILE = 91


def test_a_snapshot_written_before_behold_and_exile_is_refused() -> None:
    """A version-91 dump's own `CostComponent` rows have no `exile_after`
    flag at all: decoded as current, a pending Champion of the Clachan cast
    whose behold cost was mid-payment would forget that beholding also
    exiles, and CR 607.2q's own link would never be written. Refused
    instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BEHOLD_AND_EXILE
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BEHOLD_AND_EXILE

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BEHOLD_AND_EXILE}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `ContinuousEffects` gained
#: `keyword_counter_stamps` (CR 613.7c's timestamp for each keyword counter,
#: ordered against "loses all abilities" in layer 6, CR 613.1f) and
#: `GameEvent` gained `entered_together` (CR 603.6a's one enters event for
#: several permanents) - ecl T5.
_SCHEMA_VERSION_BEFORE_KEYWORD_COUNTER_STAMPS = 92


def test_a_snapshot_written_before_keyword_counter_stamps_is_refused() -> None:
    """A version-92 dump has no keyword counter timestamps: decoded as
    current, a flying counter put on after a "loses all abilities" effect
    would read as older than it and grant nothing. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_KEYWORD_COUNTER_STAMPS
    dumped = _a_played_game().model_dump(mode="json")
    assert dumped["continuous_effects"]["keyword_counter_stamps"] == {}
    del dumped["continuous_effects"]["keyword_counter_stamps"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_KEYWORD_COUNTER_STAMPS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_KEYWORD_COUNTER_STAMPS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before ecl T7's persisted additions: `CastRecord.
#: conspire_paid` (CR 702.78a), `CostComponent.from_among`, `PlayPermission.
#: while_controlling` (CR 611.2b) and the `that_creature_dies_consequence`
#: delayed effect kind.
_SCHEMA_VERSION_BEFORE_CONSPIRE_AND_WHILE_CONTROLLING = 93


def test_a_snapshot_written_before_conspire_and_while_controlling_is_refused() -> None:
    """A version-93 dump has no `conspire_paid` on its cast records and no
    `while_controlling` on its play permissions: decoded as current, a
    conspired spell would read as never conspired (no copy) and a Taster of
    Wares permission would read as unconditional. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CONSPIRE_AND_WHILE_CONTROLLING
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CONSPIRE_AND_WHILE_CONTROLLING

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CONSPIRE_AND_WHILE_CONTROLLING}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `machines/delayed.ReturnSubjectToBattlefieldUnderOwner`/
#: `ReturnEachExiledToBattlefieldUnderOwner` gained `tapped` and
#: `PreventionShield` gained `until_next_turn_of` (Morningtide's Light's own
#: "return those cards to the battlefield tapped ..." and "Until your next
#: turn, prevent all damage that would be dealt to you.", CR 611.2a) - ecl T8.
_SCHEMA_VERSION_BEFORE_ECL_T8_ZONE_RESETS = 94


def test_a_snapshot_written_before_ecl_t8_zone_resets_is_refused() -> None:
    """A version-94 dump's own `PreventionShield` (if any) has no
    `until_next_turn_of`: decoded as current, one created for Morningtide's
    Light's own "until your next turn" duration would default to `None` and
    never expire on `begin_turn_for` at all, silently outliving the turn it
    was supposed to end on. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ECL_T8_ZONE_RESETS
    dumped = _a_played_game().model_dump(mode="json")
    assert dumped["prevention_shields"] == []
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ECL_T8_ZONE_RESETS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ECL_T8_ZONE_RESETS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `CardState` gained `protector` (CR 310.9).
_SCHEMA_VERSION_BEFORE_BATTLE_PROTECTOR = 95


def test_a_snapshot_written_before_battle_protectors_is_refused() -> None:
    """A version-95 dump's battles carry no `protector`: decoded as current,
    each would default to `None`, and a battle nobody attacks would then be
    handed a protector chosen afresh by CR 704.5x - possibly a different
    opponent than the one chosen as it entered. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_BATTLE_PROTECTOR
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_BATTLE_PROTECTOR

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_BATTLE_PROTECTOR}",
    ):
        Game.model_validate(dumped)


def test_a_battle_protector_survives_a_dump_and_reload() -> None:
    """CR 310.9: carol's Siege keeps bob - the opponent she chose - as its
    protector across a save and load."""
    scenario = (
        Scenario()
        .player("alice")
        .player("bob")
        .player("carol", hand=["Invasion of Zendikar"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("bob", username="carol", source="Invasion of Zendikar")
    scenario.put_onto_battlefield("Invasion of Zendikar", "carol")

    reloaded = Game.model_validate(scenario.game.model_dump(mode="json"))

    (siege,) = [state for state in reloaded.battlefield if state.name == "Invasion of Zendikar"]
    assert siege.protector == "bob"


#: The version stamped before entering loyalty/defense/lore counters went
#: through counter replacements, and `CounterAmountReplacement` /
#: `CastingRuleEffect` gained their putter, player, halving and
#: "for as long as" fields.
_SCHEMA_VERSION_BEFORE_ENTERING_COUNTER_REPLACEMENTS = 96


def test_a_snapshot_written_before_entering_counter_replacements_is_refused() -> None:
    """A version-96 game with Doubling Season out would put a planeswalker's
    loyalty on undoubled (CR 306.5b, CR 122.6) where this build doubles it -
    the same state resolving differently, so it is refused."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ENTERING_COUNTER_REPLACEMENTS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ENTERING_COUNTER_REPLACEMENTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ENTERING_COUNTER_REPLACEMENTS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `AbilityOnStack` gained `mana_spent` and
#: `treasure_mana_spent` (CR 601.2h via CR 602.2b, ec7-instead).
_SCHEMA_VERSION_BEFORE_ABILITY_MANA_SPENT = 101


def test_a_snapshot_written_before_ability_mana_spent_is_refused() -> None:
    """A version-101 dump's activated abilities on the stack carry no record
    of what paid their cost: decoded as current, each would default to
    nothing spent, and Paragon of Modernity's "If `<mana condition>`, put a
    +1/+1 counter on it instead" would silently take the ordinary branch for
    an activation that really was paid that way. Refused instead."""
    assert {"mana_spent", "treasure_mana_spent"} <= set(AbilityOnStack.model_fields)
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ABILITY_MANA_SPENT
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ABILITY_MANA_SPENT

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ABILITY_MANA_SPENT}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `layers.CreaturesControlledByQuality` existed.
_SCHEMA_VERSION_BEFORE_GROUP_EVASION_GRANTS = 97


def test_a_snapshot_written_before_group_evasion_grants_is_refused() -> None:
    """A version-97 dump predates the `CreaturesControlledByQuality` selector
    kind a group "can't be blocked" grant (CR 509.1b) is stored under, so a
    continuous effect written by an older engine for the same printing would
    carry a different selector shape. Refused instead of decoded as current."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_GROUP_EVASION_GRANTS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_GROUP_EVASION_GRANTS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_GROUP_EVASION_GRANTS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `Game` gained `monarch` and `TriggeredAbility`
#: gained `monarch_inherent` (CR 725, ec7-monarch).
_SCHEMA_VERSION_BEFORE_MONARCH = 102


def test_a_snapshot_written_before_the_monarch_is_refused() -> None:
    """A version-102 dump has no monarch: decoded as current it would default
    to nobody, and a game where a player really was the monarch would stop
    drawing them the end-step card (CR 725.2) with no signal. Refused
    instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_MONARCH
    dumped = _a_played_game().model_dump(mode="json")
    assert "monarch" in dumped
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_MONARCH

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_MONARCH}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `GraveyardArrival` gained `card_types`
#: (Raphael, Fiendish Savior's and Macabre Reconstruction's "a creature card
#: was put into your graveyard from anywhere this turn", EC7).
_SCHEMA_VERSION_BEFORE_GRAVEYARD_ARRIVAL_CARD_TYPES = 103


def test_a_snapshot_written_before_graveyard_arrival_card_types_is_refused() -> None:
    """A version-103 dump's own `GraveyardArrival` entries have no
    `card_types`: decoded as current, each would default to `()`, which
    reads as "no printed types" - a creature card that already reached a
    graveyard this turn would silently stop counting for "a creature card
    was put into your graveyard from anywhere this turn", the same way a
    version-70 `is_permanent_card`-less dump would misstate CR 700.11's
    Descend. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_GRAVEYARD_ARRIVAL_CARD_TYPES
    dumped = _a_played_game().model_dump(mode="json")
    # Giant Growth itself, resolved off the stack into the graveyard.
    (arrival,) = dumped["graveyard_arrivals_this_turn"]
    assert arrival["card_types"] == ["instant"]
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_GRAVEYARD_ARRIVAL_CARD_TYPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_GRAVEYARD_ARRIVAL_CARD_TYPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `CardState` gained `solved` (CR 719.3b, R0a-T5).
_SCHEMA_VERSION_BEFORE_R0A_T5_SOLVED = 98


def test_a_snapshot_written_before_the_solved_designation_is_refused() -> None:
    """A version-98 dump has no `CardState.solved`: decoded as current, a Case
    would read unsolved forever (CR 719.3b). Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_R0A_T5_SOLVED
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_R0A_T5_SOLVED

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_R0A_T5_SOLVED}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `CardState` gained `unlocked_doors` (CR
#: 709.5c's Room designations - Unholy Annex // Ritual Chamber) - R0a-T6.
_SCHEMA_VERSION_BEFORE_ROOM_UNLOCKED_DOORS = 99


def test_a_snapshot_written_before_room_unlocked_doors_is_refused() -> None:
    """A version-99 dump has no `unlocked_doors` on its card states: decoded
    as current, a Room permanent would read as having neither door
    unlocked, and "when you unlock this door" would never trigger again for
    a game resumed from that snapshot. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_ROOM_UNLOCKED_DOORS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_ROOM_UNLOCKED_DOORS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_ROOM_UNLOCKED_DOORS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `models/player.Player` gained `speed` and
#: `speed_increased_on_turn` (CR 702.179a-f: Speed, and Perilous Snare's
#: "Start your engines!") - R0a T8.
_SCHEMA_VERSION_BEFORE_SPEED = 100


def test_a_snapshot_written_before_speed_is_refused() -> None:
    """A version-100 dump's own players have no `speed` field at all: decoded
    as current, `Player.speed` would default to `None` regardless of
    whatever speed the player actually had, and `speed_increased_on_turn`
    likewise - a mid-game snapshot would silently lose whether "Start your
    engines!" had already fired for that player. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_SPEED
    dumped = _a_played_game().model_dump(mode="json")
    for player in dumped["players"]:
        assert player["speed"] is None
        assert player["speed_increased_on_turn"] is None
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_SPEED

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_SPEED}",
    ):
        Game.model_validate(dumped)


#: The version stamped before `Game` gained
#: `nontoken_creatures_died_under_control_this_turn` (Vile Redeemer's cast
#: trigger, "for each nontoken creature that died under your control this
#: turn").
_SCHEMA_VERSION_BEFORE_NONTOKEN_DEATHS_UNDER_CONTROL = 104


def test_a_snapshot_written_before_nontoken_deaths_under_control_is_refused() -> None:
    """A version-104 dump has no per-player count of nontoken creatures that
    died under their control this turn: decoded as current it would default
    to none, and a Vile Redeemer cast later that same turn would make no
    Scions for deaths that really happened. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NONTOKEN_DEATHS_UNDER_CONTROL
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NONTOKEN_DEATHS_UNDER_CONTROL

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NONTOKEN_DEATHS_UNDER_CONTROL}",
    ):
        Game.model_validate(dumped)


def _a_game_with_a_pending_cast_trigger() -> Game:
    """Hydroid Krasis cast for X=2, its own cast trigger still pending on the
    stack above it (CR 603.3) - the one live shape whose dump actually
    carries a `GameEvent.subject_stamp` (EC7-rv-rules)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hydroid Krasis"],
            battlefield=["Forest", "Forest", "Forest", "Island"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Hydroid Krasis", "alice")
    payment = casting.determine_cost(x_value=2)
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", "Forest", "Island"))
    scenario.put_on_stack(casting)
    return scenario.game


#: The version stamped before `GameEvent` gained `subject_stamp` (EC7-rv-rules:
#: a cast trigger's own X - Hydroid Krasis, Genesis Hydra, Old Stickfingers,
#: Geometer's Arthropod - lost the moment its own spell left the stack).
_SCHEMA_VERSION_BEFORE_CAST_TRIGGER_SUBJECT_STAMP = 105


def test_a_snapshot_written_before_cast_trigger_subject_stamp_is_refused() -> None:
    """A version-105 dump's own cast-triggered `AbilityOnStack.event` carries
    no `subject_stamp`: decoded as current it would default to `None`, and a
    cast trigger resolving after its own spell was countered in response
    would read no cast X at all (`Game.cast_record_of` keyed by the spell's
    *current*, post-counter `zone_change_stamp` finds nothing) instead of
    the Oracle-ruled cast X - the exact regression `_cast_trigger_x_value`
    and `_cast_trigger_mana_spent_x_value` fix by reading `Game.cast_record_
    as_last_known(event.subject_stamp)` instead. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_CAST_TRIGGER_SUBJECT_STAMP
    game = _a_game_with_a_pending_cast_trigger()
    dumped = game.model_dump(mode="json")
    (trigger,) = [
        item
        for item in dumped["shared_zones"]["stack"]
        if item.get("state_class") == "AbilityOnStack" and item.get("event") is not None
    ]
    assert trigger["event"]["subject_stamp"] is not None
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_CAST_TRIGGER_SUBJECT_STAMP

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_CAST_TRIGGER_SUBJECT_STAMP}",
    ):
        Game.model_validate(dumped)


#: The version stamped before the life-total and combat-damage-history shapes
#: (fix-archangel-beckett): `Game.attacked_players_this_turn`,
#: `Game.attacks_unblocked_triggered`,
#: `CardState.assigns_no_combat_damage_this_combat`,
#: `TriggerEvent.ATTACKS_UNBLOCKED`, `DamageLifeFloorReplacement`, and the
#: `EventKind.LOSE_THE_GAME`/`LOSE_LIFE` replacement event kinds.
_SCHEMA_VERSION_BEFORE_LIFE_TOTAL_SHAPES = 106


def test_a_snapshot_written_before_life_total_shapes_is_refused() -> None:
    """A version-106 dump has no record of which players were attacked this
    turn or which attacks-and-unblocked triggers already fired: decoded as
    current both would default to empty, and a "deals combat damage to a
    player who was attacked this turn" reader or a CR 508.3f trigger could
    fire again, or not at all, with no signal. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_LIFE_TOTAL_SHAPES
    dumped = _a_played_game().model_dump(mode="json")
    assert "attacked_players_this_turn" in dumped
    assert "attacks_unblocked_triggered" in dumped
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_LIFE_TOTAL_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_LIFE_TOTAL_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before stream s7c's one shared bump: `CardState`
#: gained `last_known_copiable` (Ochre Jelly's Split, CR 707.2),
#: `AbilityOnStack` gained `cost_sacrificed_powers`/`cost_sacrificed_toughnesses`
#: (CR 608.2h), `machines/delayed` gained `create_token_copy_of_last_known` and
#: `CreatedReplacementSpec` gained `LeaveBattlefieldExile` (CR 614.1a).
_SCHEMA_VERSION_BEFORE_S7C_LAST_KNOWN_SHAPES = 107


def test_a_snapshot_written_before_the_s7c_last_known_shapes_is_refused() -> None:
    """A version-107 dump's card states carry no `last_known_copiable`:
    decoded as current each would default to none, and an Ochre Jelly copy
    that died before the snapshot would make its delayed token copy from
    nothing instead of the copiable values it last had. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_S7C_LAST_KNOWN_SHAPES
    game = _a_played_game()
    dumped = game.model_dump(mode="json")
    assert dumped["shared_zones"]["battlefield"]
    assert all("last_known_copiable" in state for state in dumped["shared_zones"]["battlefield"])
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_S7C_LAST_KNOWN_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_S7C_LAST_KNOWN_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before stream E5's one shared bump: the turn-history
#: record gained `cast_mana_spent` and the "left_battlefield"/"spell_warped"
#: kinds (intervening ifs, CR 603.4), `CreatedReplacementSpec` gained
#: `DieToExileReplacement` (CR 614.1a), `CardState` gained `flipped` (CR 710),
#: `TargetRequirement` gained `object_dealt_damage_clause` and
#: `ThatCreatureDiesConsequence` gained `source_stamp` (CR 400.7).
_SCHEMA_VERSION_BEFORE_E5_SHAPES = 108


def test_a_snapshot_written_before_the_e5_shapes_is_refused() -> None:
    """A version-108 dump's card states carry no `flipped`: decoded as
    current a flipped Goka the Unjust would default to its unflipped top half
    and lose the bottom half's ability with no signal. Refused instead."""
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_E5_SHAPES
    dumped = _a_played_game().model_dump(mode="json")
    assert dumped["shared_zones"]["battlefield"]
    assert all("flipped" in state for state in dumped["shared_zones"]["battlefield"])
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_E5_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_E5_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before round 293-fra: `GameEvent` gained
#: `loyalty_removed` (how many loyalty counters a loyalty ability's cost
#: removed, CR 606.4), read by "if you removed two or more loyalty counters to
#: activate it" on the trigger and again on resolution (CR 603.4).
_SCHEMA_VERSION_BEFORE_293_FRA_SHAPES = 109


def test_a_snapshot_written_before_the_293_fra_shapes_is_refused() -> None:
    """A version-109 dump's pending loyalty-activation events carry no
    `loyalty_removed`: decoded as current, Way of the Mind Sculptor's trigger
    would recheck its intervening if against `None` and silently not draw.
    Refused instead."""
    from magic_cards_model.machines.triggers import GameEvent

    assert "loyalty_removed" in GameEvent.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_293_FRA_SHAPES
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_293_FRA_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_293_FRA_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before NW01-T2: `CastRecord` gained
#: `additional_cost_kinds`/`additional_cost_powers` and `CostComponent`
#: gained `every_matching`, read back by a resolving spell's "creatures tapped
#: this way" and "the total power of the sacrificed creatures" (CR 608.2h).
_SCHEMA_VERSION_BEFORE_NW01_T2_SHAPES = 113


def test_a_snapshot_written_before_the_nw01_t2_shapes_is_refused() -> None:
    """A version-113 dump's cast records carry no `additional_cost_kinds`:
    decoded as current, a Burn at the Stake on the stack would count no
    creature as tapped and deal 0. Refused instead."""
    from magic_cards_model.models.game.records import CastRecord

    assert "additional_cost_kinds" in CastRecord.model_fields
    assert "additional_cost_powers" in CastRecord.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NW01_T2_SHAPES
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NW01_T2_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NW01_T2_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before NW02-T2: `PreventionShield` gained
#: `source_filter`, `players_only`, `and_permanents_of` and `reflects` (CR
#: 609.7b's rechecked source filter, CR 615.5's damage rider).
_SCHEMA_VERSION_BEFORE_NW02_T2_SHIELDS = 115


def test_a_snapshot_written_before_the_nw02_t2_shields_is_refused() -> None:
    """A version-115 dump's shields carry no `source_filter`: decoded as
    current, a Hunter's Ambush shield would prevent every creature's combat
    damage, green or not. Refused instead."""
    from magic_cards_model.models.game.records import PreventionShield

    for name in ("source_filter", "players_only", "and_permanents_of", "reflects"):
        assert name in PreventionShield.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NW02_T2_SHIELDS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NW02_T2_SHIELDS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NW02_T2_SHIELDS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before NW02-T3: `CastRecord` gained
#: `controlled_modified_creature_as_cast`, read back by Flame Discharge's "If
#: you controlled a modified creature as you cast this spell" (CR 700.9, CR
#: 601.2i). 116 is held by another NW-02 task, so the last shape without the
#: field is 115.
_SCHEMA_VERSION_BEFORE_NW02_T3_SHAPES = 115


def test_a_snapshot_written_before_the_nw02_t3_shapes_is_refused() -> None:
    """A version-115 dump's cast records carry no
    `controlled_modified_creature_as_cast`: decoded as current, a Flame
    Discharge on the stack would read "no modified creature" and deal X.
    Refused instead."""
    from magic_cards_model.models.game.records import CastRecord

    assert "controlled_modified_creature_as_cast" in CastRecord.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NW02_T3_SHAPES
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NW02_T3_SHAPES

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NW02_T3_SHAPES}",
    ):
        Game.model_validate(dumped)


#: The version stamped before NW03-T1: `PreventionShield` gained
#: `recipient_types` and `recipient_controller`, `ShieldSourceFilter` gained
#: `creatures`, `colors_any`, `colorless` and `not_controlled_by`, and
#: `ReflectedDamage` gained `optional`, and `CardState` gained
#: `last_known_attacking`.
_SCHEMA_VERSION_BEFORE_NW03_T1_SHIELDS = 117


def test_a_snapshot_written_before_the_nw03_t1_shields_is_refused() -> None:
    """A version-117 dump's shields carry no `recipient_types`: decoded as
    current, a Forfend shield would prevent damage to players too. Refused
    instead."""
    from magic_cards_model.models.game.records import (
        PreventionShield,
        ReflectedDamage,
        ShieldSourceFilter,
    )

    for name in ("recipient_types", "recipient_controller"):
        assert name in PreventionShield.model_fields
    for name in ("creatures", "colors_any", "colorless", "not_controlled_by"):
        assert name in ShieldSourceFilter.model_fields
    assert "optional" in ReflectedDamage.model_fields
    assert "last_known_attacking" in CardState.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NW03_T1_SHIELDS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NW03_T1_SHIELDS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NW03_T1_SHIELDS}",
    ):
        Game.model_validate(dumped)


#: The version stamped before NW03-T7: `PreventionShield` gained
#: `counters_when_prevented` (CR 615.5's "For each 1 damage prevented this
#: way, put a +1/+1 counter on that creature"). 119-123 are held by the other
#: NW-03 tasks, so the last shape without the field is 118.
_SCHEMA_VERSION_BEFORE_NW03_T7_SHIELDS = 118


def test_a_snapshot_written_before_the_nw03_t7_shields_is_refused() -> None:
    """A version-118 dump's shields carry no `counters_when_prevented`:
    decoded as current, a Test of Faith shield would prevent the damage and
    put no counters. Refused instead."""
    from magic_cards_model.models.game.records import PreventionShield

    assert "counters_when_prevented" in PreventionShield.model_fields
    assert Game.CURRENT_SCHEMA_VERSION > _SCHEMA_VERSION_BEFORE_NW03_T7_SHIELDS
    dumped = _a_played_game().model_dump(mode="json")
    dumped["schema_version"] = _SCHEMA_VERSION_BEFORE_NW03_T7_SHIELDS

    with pytest.raises(
        SchemaVersionMismatch,
        match=f"schema_version={_SCHEMA_VERSION_BEFORE_NW03_T7_SHIELDS}",
    ):
        Game.model_validate(dumped)

"""A target that changed zones since it was chosen is illegal (CR 608.2b).

The reported case: a permanent was exiled and returned by Ephemerate while a
single-target removal spell aimed at it sat on the stack. The removal
resolved anyway and killed it - confirmed directly against live game state
that the card now in the graveyard carried the *same object id* it had
before the blink, which is exactly the shape CR 400.7 forbids treating as
one continuous object once a spell targeting it checks it back on
resolution.

Every rule cited here was looked up with `mise run rules:find` in this
session, against `.rules/MagicCompRules.txt` (2026-08-19 release):

- **CR 400.7** - "An object that moves from one zone to another becomes a
  new object with no memory of, or relation to, its previous existence."
  None of the 400.7a-m exceptions preserve target legality; they are about
  an effect *finding* the new object or spell-to-permanent continuity.
- **CR 608.2b** - "If the spell or ability specifies targets, it checks
  whether the targets are still legal. A target that's no longer in the
  zone it was in when it was targeted is illegal. ... If all its targets,
  for every instance of the word 'target,' are now illegal, the spell or
  ability doesn't resolve. It's removed from the stack and, if it's a
  spell, put into its owner's graveyard. Otherwise, the spell or ability
  will resolve normally. Illegal targets, if any, won't be affected by
  parts of a resolving spell's effect for which they're illegal."

Before the fix, `TargetRef` carried only `kind`/`card_id`/`username` - no
record of which incarnation (CR 400.7) it was chosen against - so
`Game.legal_target` accepted any card still findable by id, blink included.
`CardState.zone_change_stamp` (re-minted by `move_to` on every zone change)
is what the engine already uses to answer "is this the same object" for a
continuous effect's own selector; `TargetRef.zone_change_stamp`, filled at
announcement (CR 601.2c/603.3d) from the live `CardState`, is the same idiom
applied to targeting.

Erode is the reported card: "Destroy target creature or planeswalker. Its
controller may search their library for a basic land card, put it onto the
battlefield tapped, then shuffle." (verified with `resolve_cards`). The
second sentence is CR 400.7 anaphora on the *same* target ("its controller"),
not a second target - `machines/effects.py`'s `_parse_anaphoric_clause_pair`
docstring is explicit that re-resolving it would reproduce a past bug, so
this file never re-checks that half.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario


def test_erode_fizzles_when_its_target_is_blinked_in_response():
    """The reported case. erin's Erode targets bob's Grizzly Bears; bob
    responds with Ephemerate on his own Bears (CR 601.2c: "target creature
    you control" is satisfied - the caster controls the object exiled).
    Ephemerate resolves first (LIFO), making Bears a new object with the
    same id (CR 400.7); Erode then checks its sole target back (CR 608.2b),
    finds it illegal, and the whole spell fizzles - Bears is never
    destroyed, and Erode goes to erin's graveyard unresolved rather than
    silently doing nothing *or* silently doing what it used to do.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("erin", hand=["Erode"], battlefield=["Plains"])
        .player(
            "bob",
            hand=["Ephemerate"],
            battlefield=["Grizzly Bears", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    same_id = bears.id
    stamp_before = bears.zone_change_stamp
    erode = scenario.find("Erode", Zone.HAND, username="erin")

    (erin_plains,) = scenario.untapped_sources("Plains", username="erin")
    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")

    scenario.cast_onto_stack("Erode", erin_plains, username="erin", targets=[bears])
    scenario.pass_priority("erin")
    scenario.cast_onto_stack("Ephemerate", bob_plains, username="bob", targets=[bears])

    ephemerate = scenario.resolve_top()  # top of stack: Ephemerate, CR 608.2c
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.id == same_id  # this engine mutates in place
    assert bears.zone_change_stamp != stamp_before  # CR 400.7: a new object
    assert ephemerate.zone in (Zone.EXILE, Zone.GRAVEYARD)

    scenario.resolve_top()  # Erode: its sole target is now illegal

    # CR 608.2b: fizzled, never destroyed, put into its owner's graveyard.
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert erode.zone is Zone.GRAVEYARD
    assert erode.controller == "erin"


def test_erode_still_destroys_a_target_that_never_moved():
    """Control: with no blink in the way, Erode works exactly as printed -
    proves the fizzle above is about the zone change, not a general Erode
    regression.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("erin", hand=["Erode"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    (erin_plains,) = scenario.untapped_sources("Plains", username="erin")

    scenario.cast_and_resolve("Erode", erin_plains, username="erin", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_electrolyze_still_resolves_when_only_one_of_two_targets_blinks():
    """CR 608.2b's fizzle is all-or-nothing across every target: with two
    targets and only one blinked away, the spell still resolves and affects
    the target that is still legal - `Game.spell_fizzles`'s `all(...)` is
    correct here and must not become "fizzle on any stale target".

    alice's Electrolyze splits its 2 damage 1/1 between bob's Grizzly Bears
    (2/2, will be blinked away by bob's own Ephemerate in response) and his
    Memnite (0/1, will die to its 1 damage) - and still draws alice a card,
    proving the spell resolved rather than fizzling outright.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electrolyze"],
            library=["Forest"],
            battlefield=["Island", "Island", "Mountain"],
        )
        .player(
            "bob",
            hand=["Ephemerate"],
            battlefield=["Grizzly Bears", "Memnite", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    memnite = scenario.creature("Memnite", username="bob")
    # `hand_before` still counts Electrolyze itself, which is about to leave
    # the hand to be cast - the draw replaces it, netting no change, which is
    # the point: the spell resolved (it drew a card) rather than fizzling.
    hand_before = len(scenario.player("alice").cards_in(Zone.HAND))

    sources = scenario.untapped_sources("Island", "Island", "Mountain", username="alice")
    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")

    scenario.cast_onto_stack(
        "Electrolyze", *sources, username="alice", targets=[bears, memnite], division=[1, 1]
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Ephemerate", bob_plains, username="bob", targets=[bears])

    scenario.resolve_top()  # Ephemerate: Bears becomes a new object
    scenario.resolve_top()  # Electrolyze: Bears is illegal, Memnite is not
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0  # CR 608.2b: not affected by the illegal part
    assert memnite.zone is Zone.GRAVEYARD  # the legal target still took its damage
    assert len(scenario.player("alice").cards_in(Zone.HAND)) == hand_before  # cast, then drew


def test_a_bare_id_answer_still_fizzles_against_a_blinked_target():
    """The fix must not be a no-op over `magic_cards_model_api`: its own
    `decisions.targets_answer` builds a `CHOOSE_TARGETS` answer as
    `TargetRef.to_card(UUID(token))` from a client-supplied token string -
    never a live `CardState`, so it carries no `zone_change_stamp` of its
    own. `ScriptedAnswer` below is built the identical way, on purpose, to
    stand in for that api call without importing the sibling package.

    Two things have to both hold for the reported case to actually reach a
    seat sitting behind that API, not just a scenario driving `Casting`
    directly:

    1. `Game._validate_answer`'s `CHOOSE_TARGETS` branch must still *accept*
       a bare, unstamped reference naming a legal candidate - `TargetRef.
       __eq__` ignores the stamp precisely so this is not refused as "not a
       legal target" (it would be, if the stamp were compared like every
       other field: `decision.targets`' own entries are already stamped,
       and an unstamped answer would never equal one).
    2. The reference the trigger actually resolves with must still end up
       *stamped* - swapped for its canonical, already-stamped counterpart
       from `decision.targets` - or `Game.legal_target`'s zone-change check
       has nothing to compare and silently no-ops for every answer that
       reached the engine this way.

    Devourer of Destiny's own cast trigger (CR 603.3d) is the vehicle: alice
    targets bob's Grizzly Bears by bare id; bob responds by blinking it with
    his own Ephemerate before the trigger resolves.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring"] + ["Forest"] * 5,
        )
        .player(
            "bob",
            hand=["Ephemerate"],
            battlefield=["Grizzly Bears", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    bare_answer = TargetRef.to_card(bears.id)  # exactly `targets_answer`'s shape
    assert bare_answer.zone_change_stamp is None
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(bare_answer,), player="alice")
    )

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5, username="alice")
    scenario.cast_onto_stack("Devourer of Destiny", *sources, username="alice")

    (trigger,) = [item for item in scenario.game.stack if item is not scenario.game.stack[0]]
    assert trigger.targets[0].card_id == bears.id  # the bare answer was accepted
    assert trigger.targets[0].zone_change_stamp == bears.zone_change_stamp  # and stamped

    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Ephemerate", bob_plains, username="bob", targets=[bears])

    scenario.resolve_top()  # the exile trigger: its bare-id target is now stale

    assert bears.zone is Zone.BATTLEFIELD  # CR 608.2b: fizzled, not exiled

"""What resolves when "deals combat damage to a player"/"to an opponent"
triggers (CR 120.2a), for the three real printings in the pool that print it:
Ragavan, Nimble Pilferer, Nashi, Searcher in the Dark, and Questing Beast.

The trigger *firing* is not this file's business - `test_trigger_events.py`
already proves `TriggerEvent.DEALS_DAMAGE` and `machines/triggers.
condition_matches` read "deals combat damage to a player"/"to an opponent"
generically off any card's own printed text (CR 603.2), so a card with this
shape and no code written for it specifically still triggers correctly. What
was missing before this file existed was everything downstream: what actually
happens when the ability resolves.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote the file:

- **CR 120.2a** - "Damage may be dealt as a result of combat."
- **CR 111.10a** - a Treasure token's fixed characteristics.
- **CR 510.4** / **CR 702.4b** - double strike's extra combat damage step, so
  an unblocked double striker deals two separate instances of combat damage to
  the defending player, not one instance of double the number.
- **CR 608.2n** - an ability whose source has left the battlefield still
  resolves; CR 113.7a is why an `AbilityOnStack` keeps its source's id and
  name rather than the source itself.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - the sibling rule that makes "you may cast that card" an
  optional action rather than a forced one, which is why leaving it
  unmodelled (see `UnmodeledTriggerEffectNotice`) still leaves a legal board:
  a controller offered the cast and declining it looks identical.

Ragavan's own two sentences run in full except the time-boxed cast permission,
which this engine has no primitive for; Nashi's and Questing Beast's whole
resolution clauses are left unmodelled for reasons specific to each - see
`machines/effects.UnmodeledTriggerEffectNotice`'s own docstring.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def ragavan_board(bob_library: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer"])
        .player("bob", library=bob_library if bob_library is not None else ["Forest", "Island"])
    )


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


# -- Ragavan, Nimble Pilferer ------------------------------------------------


def test_ragavan_creates_a_treasure_and_exiles_the_top_card_when_unblocked():
    """The happy path: both readable sentences run.

    A Treasure enters the battlefield under Ragavan's controller (CR 111.10a),
    and the top card of the damaged player's library - bob's - is exiled
    (CR 400.6). This is the test that fails on the unfixed engine: see the
    module-level note in the git history / report for the before/after.
    """
    scenario = ragavan_board(["Forest", "Island"]).build()
    top_of_library = scenario.player("bob").library[0]
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    treasures = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasures) == 1
    assert treasures[0].controller == "alice"
    assert top_of_library.zone is Zone.EXILE
    assert top_of_library in scenario.game.exile


def test_ragavan_does_nothing_when_his_combat_damage_is_blocked():
    """Damage to a blocking creature is not damage "to a player" (CR 120.2a).

    No trigger, so no Treasure and the library is untouched - the effect
    function is simply never called, which this asserts on the board rather
    than only on `pending_triggers` the way `test_trigger_events.py` does.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer"])
        .player("bob", library=["Forest", "Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    library_before = list(scenario.player("bob").library)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.block(ragavan, bears)
    scenario.combat_damage()
    resolve_all(scenario)

    assert not any(state.name == "Treasure Token" for state in scenario.game.battlefield)
    assert scenario.player("bob").library == library_before


def test_ragavan_fires_once_per_combat_damage_step_under_double_strike():
    """CR 510.4/702.4b: an unblocked double striker deals two separate
    instances of combat damage to the defending player, and CR 603.2 fires a
    triggered ability once per event - so Ragavan's trigger goes on the stack
    twice, once after each step, and each resolution is a full run of the
    effect: two Treasures, and the top *two* cards of bob's library exiled.

    Assault Strobe is a real instant that grants double strike (verified
    oracle text, `tests/fixtures/cards/assault_strobe.json`); nothing about
    Ragavan's own printing grants it, so this is the double-strike interaction
    rather than a printed keyword.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Assault Strobe"],
            battlefield=["Mountain", "Ragavan, Nimble Pilferer"],
        )
        .player("bob", library=["Forest", "Island", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Assault Strobe", mountain, targets=[ragavan])
    top_two = list(scenario.player("bob").library[:2])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    treasures = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasures) == 2
    assert all(state in scenario.game.exile for state in top_two)


def test_ragavans_effect_still_runs_in_full_once_ragavan_is_gone():
    """CR 608.2n: an ability with no card behind it any more still resolves.

    Ragavan connects, the trigger goes on the stack, and then - with priority
    still to be had before it resolves - alice's Ragavan is removed from the
    game entirely (state-based action for 0 toughness, forced here by direct
    damage rather than a hand-written mock). The ability still has
    `ability.event.player` and `ability.controller` from when it triggered
    (CR 113.7a), so the Treasure and the exile both still happen with no
    living source to look up.
    """
    scenario = ragavan_board(["Forest"]).build()
    top_of_library = scenario.player("bob").library[0]
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Ragavan, Nimble Pilferer's triggered ability"]
    # Ragavan is a 2/1: one point of marked damage is lethal, and the ability
    # is still sitting on the stack underneath the state-based action that
    # kills him.
    scenario.game.deal_damage(ragavan, 1)
    scenario.game.check_state_based_actions()
    assert ragavan.zone is Zone.GRAVEYARD

    resolve_all(scenario)

    assert any(state.name == "Treasure Token" for state in scenario.game.battlefield)
    assert top_of_library.zone is Zone.EXILE


def test_a_notice_is_recorded_for_the_unmodelled_cast_permission():
    """ "Until end of turn, you may cast that card" is not modelled (see
    `UnmodeledTriggerEffectNotice`), and this is the "unreadable is not the
    same as no effect" record for it - every resolution leaves one, not only
    a resolution that happens to run into some other gap.
    """
    scenario = ragavan_board(["Forest"]).build()
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    notices = scenario.game.unmodeled_trigger_effect_notices
    assert len(notices) == 1
    assert notices[0].source_name == "Ragavan, Nimble Pilferer"
    assert "you may cast that card" in notices[0].text


def test_ragavan_still_creates_a_treasure_off_an_empty_library():
    """CR 120.2a's trigger does not care whether "exile the top card" has a
    card to act on - an empty library exiles nothing (there is no CR 704
    state-based loss for an empty library by itself, only for a draw from
    one), and the Treasure sentence is unaffected by the other one having
    nothing to do.
    """
    scenario = ragavan_board([]).build()
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    assert any(state.name == "Treasure Token" for state in scenario.game.battlefield)


# -- Nashi, Searcher in the Dark and Questing Beast: fail-closed -------------


def test_nashi_triggers_but_its_resolution_is_left_unmodelled():
    """Nashi: "you mill that many cards. You may put any number of legendary
    and/or enchantment cards from among them into your hand. If you put no
    cards into your hand this way, put a +1/+1 counter on Nashi."

    The trigger fires (proven generically in `test_trigger_events.py`) and the
    mill amount is even readable now (`GameEvent.amount`, off `Game.
    deal_damage`'s own event) - what stops this running end to end is that
    `DecisionKind.CHOOSE_CARDS` (`machines/decisions.py`) can only ask for an
    exact count, never "any number of", so there is no decision shape to
    offer the "put some subset into your hand" choice with. Running the mill
    alone and skipping the choice would be a half-executed instruction
    (CR 608.2c gives no license to run part of one sentence), so nothing runs
    and a notice is recorded instead: the library is untouched and Nashi gets
    no counter.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nashi, Searcher in the Dark"])
        .player("bob", library=["Forest", "Island"])
        .build()
    )
    nashi = scenario.creature("Nashi, Searcher in the Dark", "alice")
    library_before = list(scenario.player("alice").library)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(nashi, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    assert scenario.player("alice").library == library_before
    assert nashi.counters["+1/+1"] == 0
    notices = scenario.game.unmodeled_trigger_effect_notices
    assert len(notices) == 1
    assert notices[0].source_name == "Nashi, Searcher in the Dark"


def test_questing_beast_triggers_but_its_resolution_is_left_unmodelled():
    """Questing Beast: "it deals that much damage to target planeswalker that
    player controls."

    The trigger fires on "to an opponent" (proven in `test_trigger_events.py`)
    and the damage amount is readable (`GameEvent.amount`), but "target
    planeswalker **that player** controls" needs a target restricted by the
    trigger's own event rather than by the ability's static printed text -
    `machines/targeting.profile_for_text` only reads the latter - so no target
    is chosen and nothing runs; a notice is recorded instead of a phantom
    damage instance with nowhere to land.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Questing Beast"])
        .player("bob", battlefield=[])
        .build()
    )
    beast = scenario.creature("Questing Beast", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(beast, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    notices = scenario.game.unmodeled_trigger_effect_notices
    assert len(notices) == 1
    assert notices[0].source_name == "Questing Beast"

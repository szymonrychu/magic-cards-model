"""What resolves when "deals combat damage to a player"/"to an opponent"
triggers (CR 120.2a), for the three real printings in the pool that print it:
Ragavan, Nimble Pilferer, Nashi, Searcher in the Dark, and Questing Beast.

The trigger *firing* is not this file's business - `test_trigger_events.py`
already proves `TriggerEvent.DEALS_DAMAGE` and `machines/triggers.
condition_matches` read "deals combat damage to a player"/"to an opponent"
generically off any card's own printed text (CR 603.2), so a card with this
shape and no code written for it specifically still triggers correctly. What
this file is about is what happens once the ability resolves.

**Ragavan's whole paragraph now runs**: Treasure, exile, and the "until end of
turn, you may cast that card" permission (CR 601.3) that used to void the
ability, now built as `machines/casting.PlayPermission` and granted by
`Game.grant_play_permission`. The permission's own rules - who may cast it,
when it stops, what it does not allow - are `test_play_from_exile.py`'s
business, not this file's. **Nashi and Questing Beast still fail closed**, each
for its own missing primitive, and the notice paragraphs below are about them.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote the file:

- **CR 120.2a** - "Damage may be dealt as a result of combat."
- **CR 510.4** / **CR 702.4b** - double strike's extra combat damage step, so
  an unblocked double striker deals two separate instances of combat damage to
  the defending player, not one instance of double the number, and CR 603.2
  fires the trigger once per instance.
- **CR 608.2n** - an ability whose source has left the battlefield still
  resolves; CR 113.7a is why an `AbilityOnStack` keeps its source's id and
  name rather than the source itself.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - which this codebase already reads as
  giving no license to run *part* of a multi-clause ability and stop
  (`_parse_mixed_clauses`'s own docstring: "CR 608.2c has no notion of running
  half an effect"). Nashi's and Questing Beast's abilities are still read that
  way: each has a clause naming a primitive that does not exist, so the whole
  ability leaves a notice rather than a half-built board - consistent with how
  `AnaphoricClauseNotice`, `DelayedClauseNotice`, and `ConditionalClauseNotice`
  already treat an unreadable trailing clause on an otherwise-readable ability.
  Ragavan was the third such card until the play-from-exile wave built the
  primitive his third sentence names; his whole paragraph runs now.
- **CR 607.1** - the within-one-ability link that makes "that card" in
  Ragavan's third sentence mean whatever his second sentence just exiled, and
  "that player" in his second mean whoever his trigger's damage landed on.
- CR 101.3 / CR 609.3 ("any part of an instruction that's impossible to
  perform is ignored"/"does only as much as possible") do not apply here:
  those rules are for something the *game itself* recognises as impossible at
  resolution (too few cards to discard) with the rest of the instruction
  still carried out around it. A clause this *engine* has no code for is a
  different thing - the ability is not impossible to resolve, this wave is
  simply not able to read all of what it says - and the established
  convention in this codebase for exactly that gap is the fail-closed notice,
  not a partial run.

All three cards below fire for real and go on the stack. Ragavan's resolves in
full; Nashi's and Questing Beast's each leave an `UnmodeledTriggerEffectNotice`
instead of a partial board.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.cards import card
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


# -- "that player" is an anaphor, never a target (CR 601.2c) -----------------


def test_ragavans_that_player_is_never_a_targeting_requirement():
    """ "That player" in "exile the top card of **that player's** library" is
    CR 607.1's within-one-ability anaphora back to the trigger's own event -
    the player the combat damage landed on - not a target CR 601.2c ever asks
    the controller to announce. Getting this backwards (treating "that
    player" as a target and asking who the exile should hit) would happen to
    look correct in a two-player game, where "that player" and "an opponent"
    pick out the same person by elimination - so this is checked directly
    against the parser rather than only against a two-player board.

    `profile_for_text` is what `Game.why_cannot_target_with_trigger` and
    `Game._ask_trigger_targets` both read to decide whether an ability needs
    an announced target at all (CR 603.3d); an empty `requirements` tuple
    means neither of those paths is ever reached for this ability - not that
    they were asked and found nothing to restrict.
    """
    ragavan_text = card("Ragavan, Nimble Pilferer").oracle_text
    condition_and_effect = ragavan_text.split("\n")[0]
    assert "that player" in condition_and_effect

    profile = profile_for_text(condition_and_effect)
    assert profile.understood is True
    assert profile.requirements == ()


def test_ragavans_trigger_goes_on_the_stack_with_no_targets_and_no_targeting_notice():
    """The runtime half of the check above, in a three-player game so "that
    player" (whoever combat damage lands on) cannot be silently confused with
    "an opponent" (anyone but the controller) the way it could with only one
    opponent to pick from.

    Ragavan is alice's; carol takes the hit, not bob. Nothing on the stack
    ever asks for a target (CR 603.3d never runs for this ability), and no
    `TargetingNotice` is recorded either - that notice exists for an ability
    that *does* need a target this wave could not work out, which is a
    different gap from needing none at all.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer"])
        .player("bob")
        .player("carol", library=["Forest"])
        .build()
    )
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="carol")
    scenario.no_blocks()
    scenario.combat_damage()

    on_stack = scenario.game.put_triggers_on_stack()

    assert len(on_stack) == 1
    assert on_stack[0].targets == []
    assert on_stack[0].event is not None
    assert on_stack[0].event.player == "carol"
    assert scenario.game.targeting_notices == []


# -- Ragavan, Nimble Pilferer ------------------------------------------------


def test_ragavan_makes_a_treasure_and_exiles_the_top_card_with_a_cast_permission():
    """All three clauses now run, in printed order (CR 608.2c).

    "Create a Treasure token" (CR 111.10a), "exile the top card of that
    player's library" (CR 607.1's anaphora back to the trigger's own damaged
    player) and "Until end of turn, you may cast that card" (CR 601.3's
    permission, `machines/casting.PlayPermission`) are one paragraph and
    resolve as one. Nothing is left unread, so no notice is recorded any more -
    the ability used to void itself with an `UnmodeledTriggerEffectNotice`
    because the third clause named a primitive that did not exist.

    The permission goes to **alice**, who controls Ragavan, while CR 108.3
    leaves the card owned by bob, whose library it came off.
    """
    scenario = ragavan_board(["Forest", "Island"]).build()
    top_of_library = scenario.player("bob").library[0]
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    assert any(state.name == "Treasure Token" for state in scenario.game.battlefield)
    assert top_of_library.zone is Zone.EXILE
    assert top_of_library.owner == "bob"

    permission = scenario.game.play_permission_for(top_of_library, "alice")
    assert permission is not None, "CR 601.3: alice may cast it"
    assert permission.pays_mana_cost, "Ragavan says nothing about paying nothing"
    assert scenario.game.play_permission_for(top_of_library, "bob") is None
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_ragavan_does_not_trigger_at_all_when_his_combat_damage_is_blocked():
    """Damage to a blocking creature is not damage "to a player" (CR 120.2a).

    No trigger at all here, which is a different thing from the trigger
    firing and resolving to nothing above: `pending_triggers` stays empty and
    no notice is recorded, since the ability never goes on the stack to leave
    one.
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

    assert scenario.player("bob").library == library_before
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_ragavan_resolves_once_per_combat_damage_step_under_double_strike():
    """CR 510.4/702.4b: an unblocked double striker deals two separate
    instances of combat damage to the defending player, and CR 603.2 fires a
    triggered ability once per event - so Ragavan's trigger goes on the stack
    twice, once after each step, and each resolution exiles its own card and
    hands out its own permission rather than the two collapsing into one.

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
    library_before = list(scenario.player("bob").library)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    resolve_all(scenario)

    treasures = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasures) == 2
    assert scenario.player("bob").library == library_before[2:]
    exiled = [state for state in library_before[:2] if state.zone is Zone.EXILE]
    assert len(exiled) == 2
    assert all(scenario.game.play_permission_for(state, "alice") is not None for state in exiled), (
        "each resolution grants its own permission, over its own card"
    )
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_ragavans_ability_still_resolves_once_ragavan_is_gone():
    """CR 608.2n: an ability with no card behind it any more still resolves.

    Ragavan connects, the trigger goes on the stack, and then - with priority
    still to be had before it resolves - alice's Ragavan is removed from the
    game entirely (state-based action for 0 toughness, forced here by direct
    damage rather than a hand-written mock). The ability still has its
    `source_id`/`source_name` from when it triggered (CR 113.7a), and the
    whole paragraph still runs: the Treasure is made, the card is exiled, and
    the permission is granted to alice, who no longer controls the creature
    that granted it. CR 608.2 does not consult the source for any of that.
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
    assert scenario.game.play_permission_for(top_of_library, "alice") is not None
    assert scenario.game.unmodeled_trigger_effect_notices == []


# -- Nashi, Searcher in the Dark and Questing Beast: fail-closed -------------


def test_nashi_triggers_but_its_resolution_is_left_unmodelled():
    """Nashi: "you mill that many cards. You may put any number of legendary
    and/or enchantment cards from among them into your hand. If you put no
    cards into your hand this way, put a +1/+1 counter on Nashi."

    The trigger fires (proven generically in `test_trigger_events.py`), and
    "you may put any number of ... into your hand" has no `DecisionKind.
    CHOOSE_CARDS` shape to ask with - that decision only ever asks for an
    exact count (`Game.ask`'s own check: "needs {amount} card(s) chosen"),
    never "as many as you like". Running the mill alone and skipping the
    choice (and the counter that depends on its outcome) would be a
    half-executed instruction, so nothing runs and a notice is recorded
    instead: the library is untouched and Nashi gets no counter.
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
    assert "any number of" in notices[0].text


def test_questing_beast_triggers_but_its_resolution_is_left_unmodelled():
    """Questing Beast: "it deals that much damage to target planeswalker that
    player controls."

    The trigger fires on "to an opponent" (proven in `test_trigger_events.py`),
    but "target planeswalker **that player** controls" needs a target
    restricted by the trigger's own event rather than by the ability's static
    printed text - `machines/targeting.profile_for_text` only ever reads the
    latter ("you control"/"an opponent controls" against the ability's
    *controller*, never against whoever the triggering damage happened to
    land on) - so no target is chosen and nothing runs; a notice is recorded
    instead of a phantom damage instance with nowhere to land.
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
    assert "that player controls" in notices[0].text

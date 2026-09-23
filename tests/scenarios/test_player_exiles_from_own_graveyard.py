"""G3: "target player" (or another player-anaphora subject) exiles N cards of
their own choice from their own graveyard - Relic of Progenitus's first
ability ("{T}: Target player exiles a card from their graveyard."), Curse of
Oblivion's own upkeep trigger ("that player exiles two cards from their
graveyard"), and Merrow Bonegnawer's identically-worded tap ability, proving
this reads off the sentence rather than off Relic's own name.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 608.2d** - "If an effect of a spell or ability offers any choices
  other than choices already made as part of casting the spell, activating
  the ability, or otherwise putting the spell or ability on the stack, the
  player announces these while applying the effect." There is no CR 701.9b-
  style subrule naming who chooses for an *exile*, unlike discard's own
  explicit one - this is the general rule the choice comes from, and "the
  player" applying the instruction is the one the sentence's subject names
  (the target player, or "that player"), never the resolving ability's own
  controller.
- **CR 609.3** - "If an effect attempts to do something impossible, it does
  only as much as possible." A graveyard shorter than the printed count
  exiles everything it has rather than raising or asking a bigger question
  than the graveyard can answer.
- **CR 607.1** - within-one-ability anaphora: Curse of Oblivion's "that
  player" refers back to whichever specific player its own "at the beginning
  of enchanted player's upkeep" trigger condition just fired for
  (`GameEvent.player`), never the Aura's own controller - the same anaphora
  `_parse_that_player_sacrifices_of_their_choice_clause` (Sheoldred,
  Whispering One's "that player sacrifices...") and
  `_parse_they_gain_or_lose_life_clause` already read for a sibling verb,
  widened here with a generic delegator so a verb neither of those two
  readers know (exile) is not left another one-off table row away.
- **CR 406.2** - to exile an object is to put it into the exile zone from
  whatever zone it is currently in; a graveyard card is exiled the same way
  a permanent is.

Relic of Progenitus is the reported card. Merrow Bonegnawer prints the exact
same tap-ability sentence on a different, unrelated creature - proof this is
read off the words, not off Relic's own name. Curse of Oblivion is a
genuinely different sentence shape (a trigger's own "that player" anaphora,
a count of two, no target announcement at all) that exercises the same
reader through a different subject-resolution path.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import activated_effect_for
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_relic_of_progenitus_asks_the_targeted_player_not_the_controller():
    """Alice controls and activates Relic of Progenitus, targeting bob.
    CR 608.2d's choice belongs to bob - the acting/targeted player - never
    to alice, the ability's own controller."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relic of Progenitus"])
        .player("bob", graveyard=["Mountain", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Relic of Progenitus", Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")

    scenario.will_choose_cards(mountain, username="bob")
    scenario.activate(relic, targets=["bob"])
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.EXILE
    assert forest.zone is Zone.GRAVEYARD
    assert bob.graveyard == [forest]


def test_relic_of_progenitus_targeting_an_empty_graveyard_does_nothing():
    """CR 609.3: nothing to exile is nothing done - no `CHOOSE_CARDS`
    question is asked (an unqueued one would raise), and nothing exiles."""
    scenario = Scenario().player("alice", battlefield=["Relic of Progenitus"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Relic of Progenitus", Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")

    scenario.activate(relic, targets=["bob"])
    scenario.pass_until_resolved()

    assert bob.graveyard == []
    assert scenario.game.exile == []


def test_merrow_bonegnawer_reads_the_same_sentence_off_a_different_card():
    """Merrow Bonegnawer prints the identical "{T}: Target player exiles a
    card from their graveyard." tap ability on an unrelated Merfolk Rogue -
    proof the reader is keyed to the sentence, not to Relic's own name."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Merrow Bonegnawer"])
        .player("bob", graveyard=["Swamp", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    merrow = scenario.find("Merrow Bonegnawer", Zone.BATTLEFIELD, "alice")
    swamp = scenario.find("Swamp", Zone.GRAVEYARD, "bob")
    island = scenario.find("Island", Zone.GRAVEYARD, "bob")

    scenario.will_choose_cards(island, username="bob")
    scenario.activate(merrow, targets=["bob"])
    scenario.pass_until_resolved()

    assert island.zone is Zone.EXILE
    assert swamp.zone is Zone.GRAVEYARD


def test_curse_of_oblivion_asks_the_enchanted_player_to_choose_two_of_three():
    """Curse of Oblivion's own upkeep trigger: "that player exiles two cards
    from their graveyard." Bob, the enchanted player, chooses 2 of his own
    3 - never alice, who cast and controls the Aura."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Curse of Oblivion"])
        .player("bob", graveyard=["Mountain", "Forest", "Plains"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    curse = scenario.find("Curse of Oblivion", Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    curse.attach_to(bob)
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")
    plains = scenario.find("Plains", Zone.GRAVEYARD, "bob")

    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Curse of Oblivion's triggered ability"]

    scenario.will_choose_cards(mountain, forest, username="bob")
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.EXILE
    assert forest.zone is Zone.EXILE
    assert plains.zone is Zone.GRAVEYARD


def test_curse_of_oblivion_with_only_one_card_exiles_that_one():
    """CR 609.3 again, from the trigger side: bob's graveyard holds only one
    card, so the "exile two" instruction does only as much as it can - that
    one card goes, with no bigger question asked than the graveyard can
    answer."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Curse of Oblivion"])
        .player("bob", graveyard=["Mountain"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    curse = scenario.find("Curse of Oblivion", Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    curse.attach_to(bob)
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")

    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Curse of Oblivion's triggered ability"]

    scenario.will_choose_cards(mountain, username="bob")
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.EXILE
    assert bob.graveyard == []


def test_relics_second_ability_is_unchanged():
    """Relic of Progenitus's own second ability - "{1}, Exile this artifact:
    Exile all graveyards. Draw a card." - is a different ability entirely
    (no player-choice clause at all) and is undisturbed by this wave's new
    reader.

    Reached directly through `activated_effect_for`, the same technique
    `test_counters_that_many_trigger.py`'s own "no triggering event" proof
    uses for an ability the harness has no way to drive through the ordinary
    cost-payment path: the bare "Exile this artifact" cost phrasing is an
    unrelated, pre-existing gap (`test_legal_actions.py`'s own "Finding 1" -
    `_PHRASE_EXILE` reads only "exile this card", never "this `<type>`"),
    nothing this wave's `parse_clause_effect` reader touches, and orthogonal
    to what this test is actually proving."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Relic of Progenitus"], graveyard=["Forest"], library=["Plains"]
        )
        .player("bob", graveyard=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Relic of Progenitus", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    swamp = scenario.find("Swamp", Zone.GRAVEYARD, "bob")
    hand_size_before = len(alice.hand)

    second = scenario.game.activated_abilities(relic)[1]
    effect = activated_effect_for("Relic of Progenitus", 1, second.effect)
    assert effect is not None
    ability = AbilityOnStack(
        kind=AbilityKind.ACTIVATED,
        ability=second,
        source_id=relic.id,
        source_name="Relic of Progenitus",
        controller="alice",
    )

    effect(scenario.game, ability)

    assert forest.zone is Zone.EXILE
    assert swamp.zone is Zone.EXILE
    assert alice.graveyard == []
    assert bob.graveyard == []
    assert len(alice.hand) == hand_size_before + 1

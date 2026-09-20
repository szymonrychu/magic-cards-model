"""Scenario: "Untap all <qualifier> you control." - a filtered group untap
with no named target, generalised past Jiang Yanggu, Never Alone's own end
step trigger.

`machines/effects.py` had a reader for "Untap this creature." (Devoted
Druid's own cost-paid untap) and "Untap it." (Amulet of Vigor's trigger
naming a single subject) before this file, but nothing for a *filtered
group* with no subject at all:

- **Jiang Yanggu, Never Alone** (Reality Fracture), "At the beginning of
  your end step, untap all tokens you control." - the token filter.
- **Dramatic Reversal** (off-set, a real and well-known card), "Untap all
  nonland permanents you control." - a different filter ("nonland
  permanents", not "tokens") on a spell rather than a triggered ability,
  proving the reader is not keyed to Jiang Yanggu's name or to a triggered
  ability's own machinery (`_parse_untap_all_qualifier_clause` is reached
  from `_ability_effect_or_notice`, which both a resolving spell's
  triggered-ability-shaped clause and an ordinary triggered ability's own
  effect clause share).

The rule this rests on:

- **CR 701.26b** - untapping is unconditional here (`exert_applies=False`),
  the same choice `_parse_untap_trigger_subject_clause` already makes:
  CR 701.43a's exert only withholds the untap *step's own* untap, never one
  a resolving ability performs.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario

SOLDIER = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)


def test_jiang_yanggu_untaps_tokens_at_the_beginning_of_the_end_step():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Jiang Yanggu, Never Alone", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")
    bears.tapped = True
    soldier.tapped = True

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert not soldier.tapped, "a token you control"
    assert bears.tapped, "not a token - the printed card stays tapped"


def test_jiang_yanggu_leaves_an_opponents_token_alone():
    scenario = (
        Scenario().player("alice", battlefield=["Jiang Yanggu, Never Alone"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (theirs,) = create_tokens(scenario.game, SOLDIER, "bob")
    theirs.tapped = True

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert theirs.tapped


def test_dramatic_reversal_untaps_nonland_permanents_off_set():
    """Off-set proof: a real card, a different filter ("nonland
    permanents"), and a spell rather than a triggered ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dramatic Reversal"],
            battlefield=["Grizzly Bears", "Sol Ring", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    bears.tapped = True
    ring.tapped = True

    forest, island = scenario.untapped_sources("Forest", "Island", username="alice")
    scenario.cast_and_resolve("Dramatic Reversal", forest, island, username="alice")

    assert not bears.tapped
    assert not ring.tapped
    assert forest.tapped, "a land - untouched by 'nonland permanents', and spent on the cost"
    assert island.tapped, "a land - untouched by 'nonland permanents', and spent on the cost"

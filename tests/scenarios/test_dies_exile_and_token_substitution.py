"""Scenario: FRA S9's remaining replacement effects - "would die" as its own
event shape, and a token-creation event replaced by an entirely different
token rather than augmented.

`machines/replacement.py` had readers for "would be put into a graveyard"
and for "those tokens **plus** ..." before this file, and neither covered
either of these two real shapes:

- **Garruk, Veiled Butcher** (Reality Fracture), "If a creature an opponent
  controls would die, exile it instead." - CR 700.4's "dies" ("is put into a
  graveyard from the battlefield") is narrower than `_GRAVEYARD_EVENT_RE`'s
  "would be put into a graveyard [from anywhere]", so a card milled or
  discarded must not trip this reader the way a die-and-exile effect should
  not. `_compile_dies_exile` is its own compiler, checking `event.origin is
  Zone.BATTLEFIELD` on top of the destination check every graveyard-exile
  reader already makes. **Corpseweaver Prodigy** (off-set, a real card
  printing the identical sentence) proves the shape is read off the
  sentence, not Garruk's name.
- **Draconic Visitor** (Reality Fracture), "If one or more artifact tokens
  would be created under your control, that many 5/5 red Dragon creature
  tokens with flying are created instead." - `_compile_extra_token`'s
  "those tokens **plus** ..." shape leaves the original batch alone and adds
  more; this one has no "those tokens" at all, so the whole batch becomes a
  different kind of token (`_compile_token_substitution`, `event.definition`
  replaced rather than `event.extra` appended to). **Divine Visitation**
  (off-set, a real and well-known card: a different filter - "creature
  tokens", not "artifact tokens" - and a different token) proves the same
  thing.

The rules these rest on:

- **CR 700.4** - "'Dies' means 'is put into a graveyard from the
  battlefield.'"
- **CR 614.6** - a replaced event never happens; the modified one happens in
  its place, which is why `event.origin`/`event.card` are read *before* the
  move (CR 400.7's "new object" has not been minted yet).
- **CR 614.16** - "if an effect would create one or more tokens" replacement
  effects, and **CR 701.7b** - a token-creation replacement effect applies
  "before considering any continuous effects that will modify the
  characteristics of that token", which is why `create_tokens`'s own
  replacement pass is what a scenario here calls, the same as `Doubling
  Season`'s reader (`test_token_creation_replacement.py`) already does.
- **CR 111.2** - "under your control" is the token entering under the
  *creating* player's control, which both `_extra_token_applies` (already
  proven) and the new substitution reuse unchanged.

Tomik, Izzet Sparkmage's "If a source you control would deal noncombat
damage to an opponent or a permanent an opponent controls, it deals that
much damage plus 1 instead." and Yoshimaru, Beloved Companion's "If one or
more +1/+1 counters would be put on a creature you control, that many plus
one +1/+1 counters are put on it instead." both already compiled through
`_compile_damage_plus_amount` and `_compile_counter_doubler` with no code
change at all - verified end to end below rather than only at the parser.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Color, Type, Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario

SERVO = TokenDefinition(
    types=(Type.ARTIFACT, Type.CREATURE), subtypes=("Servo",), colors=(), power=1, toughness=1
)
SOLDIER = TokenDefinition(
    types=(Type.CREATURE,), subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1
)


# --------------------------------------------------------------------------
# "If a creature an opponent controls would die, exile it instead."
# (Garruk, Veiled Butcher)
# --------------------------------------------------------------------------


def test_garruk_exiles_an_opponents_creature_instead_of_letting_it_die():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Garruk, Veiled Butcher"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE


def test_garruk_does_not_touch_his_own_controllers_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Garruk, Veiled Butcher", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD, "alice's own creature is not 'an opponent controls'"


def test_garruk_does_not_catch_a_creature_milled_from_the_library():
    """CR 700.4's "dies" is battlefield-only - a card leaving the library for
    the graveyard never "dies" and must not be exiled instead."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Garruk, Veiled Butcher"])
        .player("bob", library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_of_library = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")

    scenario.game.put_into_graveyard(top_of_library)

    assert top_of_library.zone is Zone.GRAVEYARD


def test_corpseweaver_prodigy_exiles_the_identical_shape_off_set():
    """Off-set proof: a real card printing the identical sentence."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Corpseweaver Prodigy"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE


# --------------------------------------------------------------------------
# "If one or more artifact tokens would be created under your control, that
# many 5/5 red Dragon creature tokens with flying are created instead."
# (Draconic Visitor)
# --------------------------------------------------------------------------


def test_draconic_visitor_replaces_an_artifact_token_with_a_dragon():
    scenario = Scenario().player("alice", battlefield=["Draconic Visitor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (token,) = create_tokens(scenario.game, SERVO, "alice")

    assert token.name == "Dragon Token"
    assert scenario.game.characteristics_of(token).power_toughness == (5, 5)
    assert scenario.game.characteristics_of(token).has_ability("Flying")
    assert "Servo" not in scenario.game.characteristics_of(token).subtypes


def test_draconic_visitor_keeps_the_same_count():
    scenario = Scenario().player("alice", battlefield=["Draconic Visitor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    dragons = create_tokens(scenario.game, SERVO, "alice", count=3)

    assert len(dragons) == 3
    assert all(state.name == "Dragon Token" for state in dragons)


def test_draconic_visitor_leaves_a_nonartifact_token_alone():
    scenario = Scenario().player("alice", battlefield=["Draconic Visitor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (token,) = create_tokens(scenario.game, SOLDIER, "alice")

    assert token.name == "Soldier Token"


def test_draconic_visitor_does_not_catch_an_opponents_artifact_token():
    scenario = Scenario().player("alice", battlefield=["Draconic Visitor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (token,) = create_tokens(scenario.game, SERVO, "bob")

    assert token.name == "Servo Token"


def test_divine_visitation_replaces_a_creature_token_with_an_angel_off_set():
    """Off-set proof: a real, well-known card - a different filter ("creature
    tokens", not "artifact tokens") and a different substituted token."""
    scenario = Scenario().player("alice", battlefield=["Divine Visitation"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (token,) = create_tokens(scenario.game, SOLDIER, "alice")

    assert token.name == "Angel Token"
    assert scenario.game.characteristics_of(token).power_toughness == (4, 4)
    assert has_keyword(token, Keyword.FLYING, scenario.game)
    assert has_keyword(token, Keyword.VIGILANCE, scenario.game)


# --------------------------------------------------------------------------
# Tomik, Izzet Sparkmage and Yoshimaru, Beloved Companion: already read by
# `_compile_damage_plus_amount` and `_compile_counter_doubler` with no code
# change needed - verified end to end here rather than only at the parser.
# --------------------------------------------------------------------------


def test_tomik_izzet_sparkmage_adds_one_to_noncombat_damage_dealt_to_an_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tomik, Izzet Sparkmage", "Grizzly Bears"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.player("bob")

    dealt = scenario.game.deal_damage(bob, 3, source=bears)

    assert dealt == 4, "noncombat damage from a source alice controls, plus 1"


def test_tomik_izzet_sparkmage_leaves_its_own_controllers_damage_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tomik, Izzet Sparkmage", "Grizzly Bears"], life=20)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    alice = scenario.player("alice")

    dealt = scenario.game.deal_damage(alice, 3, source=bears)

    assert dealt == 3, "not dealt to an opponent - no plus 1"


def test_yoshimaru_beloved_companion_adds_one_plus_one_counter():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Yoshimaru, Beloved Companion", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "+1/+1", 2)

    assert bears.counters["+1/+1"] == 3, "2 stated, plus one more"


def test_yoshimaru_beloved_companion_leaves_an_opponents_creature_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Yoshimaru, Beloved Companion"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, "+1/+1", 2)

    assert theirs.counters["+1/+1"] == 2, "not a creature alice controls - no plus one"

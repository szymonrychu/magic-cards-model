"""A non-legendary permanent's own two-word name does not shorten to its
first word inside its own printed text (CR 201.5c, CR 205.3m).

`machines/abilities.self_reference_names`'s bare-two-word and epithet
shortenings are a legendary-permanent convention (see that function's own
docstring; `tests/test_self_reference_names.py` proves the reader itself
against the three reported cards plus an off-set generality proof). This
file proves the *engine* reaches that reader with the right answer: every
real call site - `machines/layers.py`'s battlefield sweep among them - now
computes `legendary` off the real printed card
(`Supertype.LEGENDARY in card.supertypes`), the same live `Card` a real game
holds, rather than the function's own permissive `True` default a caller
with nothing to check falls back on.

`layer_readable_sentences` is exercised directly, with Eldrazi Temple's own
real `Card` and its own computed `legendary` flag, because Eldrazi Temple's
particular corrupted line - "Spend this mana only to cast colorless Eldrazi
spells" - sits on a mana ability CR 605.3b resolves immediately, outside the
continuous-effects/trigger-effect systems `tests/test_dies_trigger_self_
reference.py`/`tests/scenarios/test_planeswalker_bare_name_self_reference.py`
already exercise end-to-end for a *triggered* ability's own resolution; this
is the sibling proof for the activated-ability/static-sweep side of the same
call graph. The Thopter Assembly game confirms the ordinary gameplay case
this fix must not have broken is still exactly right.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 201.5c, CR 205.3m, CR 205.4a, CR 605.3b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import layer_readable_sentences
from magic_cards_model.models import Supertype, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_engine_reads_a_real_non_legendary_cards_supertype_through():
    """Eldrazi Temple, read the same way `machines/layers.py`'s battlefield
    sweep reads any permanent: `legendary` computed off the real printed
    `Card`, not defaulted. The reported corruption - "Eldrazi" rewritten to
    "this permanent" inside its own mana ability's spend restriction - is
    gone once that real, correctly-`False` value reaches the reader."""
    temple = card("Eldrazi Temple")
    legendary = Supertype.LEGENDARY in temple.supertypes
    assert legendary is False

    sentences = layer_readable_sentences(
        temple.oracle_text, card_name=temple.name, legendary=legendary
    )

    assert any("colorless Eldrazi spells" in sentence for sentence in sentences)
    assert any("abilities of colorless Eldrazi" in sentence for sentence in sentences)
    assert not any("this permanent" in sentence for sentence in sentences)


def test_thopter_assemblys_upkeep_trigger_still_creates_its_tokens():
    """The ordinary gameplay case this fix must not have broken: with no
    other Thopters in play, Thopter Assembly's own upkeep trigger still
    returns it to hand and creates five 1/1 flying Thopter tokens."""
    scenario = Scenario().player("alice", battlefield=["Thopter Assembly"]).player("bob").build()
    scenario.start_at(Step.UNTAP)
    assembly = scenario.find("Thopter Assembly", Zone.BATTLEFIELD, "alice")
    scenario.advance()  # upkeep: "At the beginning of your upkeep" triggers
    scenario.game.put_triggers_on_stack()

    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert assembly.zone is Zone.HAND
    thopters = [
        state for state in scenario.game.battlefield if "Thopter" in state.subtypes and state.token
    ]
    assert len(thopters) == 5
    assert all(state.power == 1 and state.toughness == 1 for state in thopters)

"""Scenario: a token copy "except it has changeling" - CR 707.9a's added
ability being CR 702.73a's characteristic-defining ability, read by every copy
exception reader (`replacement.parse.copy_exception_keywords`, shared by the
enter-as-copy, become-a-copy and token-copy exception tails).

Dominion Infiltration is the reported card: "Choose X target creatures your
opponents control. For each of them, create a token that's a copy of that
creature, except it has changeling. Those tokens gain haste. Exile those
tokens at the beginning of the next end step." The token-side readers
(`_read_token_copy_except`, `control_copy._read_copy_exception_list`) took only
the layer 6 combat-keyword whitelist, which deliberately leaves changeling out
(CR 604.3a: a CDA granted by a later effect is no CDA), so the whole chain
failed closed. A copy exception is a copiable value (CR 707.9a), so there it
is a real CDA; the enter-as-copy reader already knew that for Omni-Changeling.

No non-trk printing is a *token* copy with a changeling exception (Scryfall
finds none), so generality is shown inside the set by varying the board: a
plain Bear, a flier with an enters trigger, a creature with its own creature
type, a legendary creature, X of 0, 1 and 2, and a lord that reads the copy's
new creature types. Omni-Changeling (a clone, handled before this) is the
regression proof for the shared reader.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.73a** - "Changeling is a characteristic-defining ability.
  'Changeling' means 'This object is every creature type.'"
- **CR 707.9a** - a copy effect's added ability "becomes part of the copiable
  values for the copy".
- **CR 707.2** - the copy gets the copiable values; counters and status are
  not copied.
- **CR 603.7** - the end-step exile is a delayed triggered ability the spell
  creates as it resolves.
"""

import pytest

from magic_cards_model.data.creature_types import creature_types
from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

EVERY_CREATURE_TYPE = frozenset(creature_types())


def _board(*, bob=("Grizzly Bears",), alice_extra=(), mountains=6):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dominion Infiltration"],
            battlefield=["Mountain"] * mountains + list(alice_extra),
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _infiltrate(scenario, targets):
    casting = scenario.cast("Dominion Infiltration")
    casting.x_value = len(targets)
    casting.choose_targets(list(targets))
    payment = casting.determine_cost(x_value=len(targets))
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * (3 + len(targets))))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _copies(scenario, name):
    return [s for s in scenario.game.battlefield if s.token and s.name == name]


def _types(scenario, permanent):
    return set(scenario.game.characteristics_of(permanent).subtypes)


def test_dominion_infiltration_is_handled():
    outcomes = [c for c in classify_clauses(card("Dominion Infiltration")) if c.text]
    assert {c.category for c in outcomes} == {HANDLED}, outcomes


def test_the_copy_is_every_creature_type_and_the_original_is_not():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _infiltrate(scenario, [bears])

    (copy,) = _copies(scenario, "Grizzly Bears")
    assert copy.controller == "alice"
    assert _types(scenario, copy) >= EVERY_CREATURE_TYPE
    assert "Goblin" in _types(scenario, copy) and "Bear" in _types(scenario, copy)
    assert "Goblin" not in _types(scenario, bears), "the original is untouched (CR 707.2)"
    assert (copy.power, copy.toughness) == (2, 2)


def test_the_copy_gains_haste_and_is_not_summoning_sick():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _infiltrate(scenario, [bears])

    (copy,) = _copies(scenario, "Grizzly Bears")
    assert scenario.can_attack(copy), "the haste rider"


def test_two_targets_make_two_copies_one_for_each():
    scenario = _board(bob=["Grizzly Bears", "Mulldrifter"])
    bears = scenario.creature("Grizzly Bears", "bob")
    drifter = scenario.creature("Mulldrifter", "bob")
    _infiltrate(scenario, [bears, drifter])

    (bear_copy,) = _copies(scenario, "Grizzly Bears")
    (drifter_copy,) = _copies(scenario, "Mulldrifter")
    for copy in (bear_copy, drifter_copy):
        assert copy.controller == "alice"
        assert _types(scenario, copy) >= EVERY_CREATURE_TYPE
    assert drifter_copy.power == 2 and drifter_copy.toughness == 2


def test_x_of_zero_chooses_nothing_and_creates_nothing():
    scenario = _board()
    _infiltrate(scenario, [])

    assert not [s for s in scenario.game.battlefield if s.token]


def test_a_copied_enters_trigger_fires_for_the_token():
    """CR 707.2: the copy has the enters trigger; it enters under alice's
    control, so alice draws the two cards."""
    scenario = _board(bob=["Mulldrifter"])
    drifter = scenario.creature("Mulldrifter", "bob")
    hand_before = len(scenario.player("alice").hand)
    _infiltrate(scenario, [drifter])
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before - 1 + 2


def test_the_copy_is_a_merfolk_for_a_lord_that_reads_creature_types():
    """CR 702.73a made visible: Lord of Atlantis gives other Merfolk +1/+1, and
    a Grizzly Bears copy with changeling is one."""
    scenario = _board(alice_extra=["Lord of Atlantis"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _infiltrate(scenario, [bears])

    (copy,) = _copies(scenario, "Grizzly Bears")
    assert (copy.power, copy.toughness) == (3, 3)
    assert (bears.power, bears.toughness) == (2, 2)


def test_the_copy_of_a_legendary_creature_keeps_its_legend_status():
    """The exception adds changeling and nothing else: a legendary original
    is copied as a legendary token (the legend rule is per controller, CR
    704.5j, so it does not touch bob's original)."""
    scenario = _board(bob=["Isamaru, Hound of Konda"])
    isamaru = scenario.creature("Isamaru, Hound of Konda", "bob")
    _infiltrate(scenario, [isamaru])

    (copy,) = _copies(scenario, "Isamaru, Hound of Konda")
    assert "Legendary" in copy.card.type_line
    assert isamaru.zone is Zone.BATTLEFIELD and copy.zone is Zone.BATTLEFIELD


def test_counters_on_the_original_are_not_copied():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    _infiltrate(scenario, [bears])

    (copy,) = _copies(scenario, "Grizzly Bears")
    assert (copy.power, copy.toughness) == (2, 2)


def test_the_copies_are_exiled_at_the_beginning_of_the_next_end_step():
    scenario = _board(bob=["Grizzly Bears", "Mulldrifter"])
    bears = scenario.creature("Grizzly Bears", "bob")
    drifter = scenario.creature("Mulldrifter", "bob")
    _infiltrate(scenario, [bears, drifter])
    assert len([s for s in scenario.game.battlefield if s.token]) == 2

    while scenario.step is not Step.END_STEP:
        while scenario.game.stack:
            scenario.resolve_top()
        scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()

    assert not [s for s in scenario.game.battlefield if s.token]
    assert bears.zone is Zone.BATTLEFIELD and drifter.zone is Zone.BATTLEFIELD


def test_omni_changeling_still_copies_with_changeling():
    """Regression proof for the shared reader: the clone path that read
    "except it has changeling" before the token readers did."""
    outcomes = [c for c in classify_clauses(card("Omni-Changeling")) if c.text]
    assert all(c.category == HANDLED for c in outcomes if "changeling" in c.text.lower()), outcomes


@pytest.mark.parametrize(
    "tail",
    [
        "it has changeling",
        "it has menace and changeling",
        "it has changeling and haste",
    ],
)
def test_the_exception_reader_takes_changeling_alone_or_in_a_list(tail):
    from magic_cards_model.machines.effects import _read_token_copy_except

    added, power, toughness, subtype = _read_token_copy_except(tail)
    assert "Changeling" in added[0]
    assert (power, toughness, subtype) == (None, None, None)


def test_the_exception_reader_still_refuses_a_keyword_it_does_not_know():
    from magic_cards_model.machines.effects import _read_token_copy_except

    assert _read_token_copy_except("it has changeling and flavour") is None

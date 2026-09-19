"""Scenario: "This creature gets +N/+N for each other creature named X" -
Relentless Rats' and Seven Dwarves' own self-counting pump (CR 613.4c,
sublayer 7c), read by `_SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE`/
`_self_pump_per_other_creature_named_builder` off the card's own printed
text with no `LAYER_EFFECTS` row for either any more (G14-3 of the number
sweep).

Seven Dwarves is the off-pool proof: a real, Modern-legal printing that was
not in the pool before this wave, sharing the shape but not the wording -
"named Seven Dwarves **you control**" instead of Relentless Rats' "on the
battlefield" - so this exercises the parser's optional "you control" reading,
not just a re-confirmation of Relentless Rats' own sentence. Relentless
Rats' own regression coverage (three Rats, an opponent's Rats, Dress Down,
an anthem stacking, round-trip) stays in `tests/scenarios/test_static_
abilities.py` and `tests/scenarios/test_layer_effects_round_trip.py`.

Every CR number here was already verified by the parser's own docstring
(CR 613.4c, CR 201.4, CR 613.6).
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from tests.scenarios.harness import Scenario


def computed(scenario):
    permanents = scenario.game.battlefield
    return compute_board(permanents, static_effects(permanents))


def test_one_seven_dwarves_is_its_printed_two_two():
    """ "for each *other* creature ... named Seven Dwarves" - alone, that is none."""
    scenario = Scenario().player("alice", battlefield=["Seven Dwarves"]).build()
    (dwarf,) = scenario.creatures("Seven Dwarves", username="alice")

    board = computed(scenario)

    assert board.of(dwarf).power_toughness == (2, 2)


def test_two_dwarves_are_each_a_three_three():
    scenario = Scenario().player("alice", battlefield=["Seven Dwarves", "Seven Dwarves"]).build()
    dwarves = scenario.creatures("Seven Dwarves", "Seven Dwarves")

    board = computed(scenario)

    assert [board.of(dwarf).power_toughness for dwarf in dwarves] == [(3, 3)] * 2


def test_a_dwarf_does_not_count_an_opponents_dwarves():
    """ "You control" - unlike Relentless Rats' "on the battlefield", Seven
    Dwarves only counts its controller's own other copies.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Seven Dwarves"])
        .player("bob", battlefield=["Seven Dwarves"])
        .build()
    )
    (mine,) = scenario.creatures("Seven Dwarves", username="alice")
    (theirs,) = scenario.creatures("Seven Dwarves", username="bob")

    board = computed(scenario)

    assert board.of(mine).power_toughness == (2, 2)
    assert board.of(theirs).power_toughness == (2, 2)

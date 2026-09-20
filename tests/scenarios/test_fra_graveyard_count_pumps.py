"""Scenario: FRA S9's graveyard-counting CR 613.4c pumps (sublayer 7c, not a
characteristic-defining ability - these add to a printed power/toughness,
never replace it).

- **Dark Matter Manipulator**, "This creature gets +2/+0 for every seven
  cards in your graveyard." - a *batch* count
  (`_SELF_PUMP_PER_GRAVEYARD_CARD_BATCH_RE`/
  `_self_pump_per_graveyard_card_batch_builder`), integer division by seven
  rather than one bonus per card.
- **Winter, Tormented Loner**, "Winter gets +1/+0 for each creature and
  planeswalker card in your graveyard." - the per-card count
  (`_SELF_PUMP_PER_GRAVEYARD_CARD_RE`/`_self_pump_per_graveyard_card_builder`)
  with an *and*-joined qualifier list (two card types, either counts), the
  shape that widened the reader from a single hard-coded `Type` to
  `card_types: Sequence[Type]`.

Both builders already existed from this file's earlier work; this file is
their first scenario-level test (the earlier work proved the parser matches
the sentence in isolation, not that it reaches a real board). No off-set
proof is added here: `_self_pump_per_graveyard_card_builder`'s single-type
form is already proven off-set-independent by Fiend Artisan's "for each
creature card" in `test_parsed_layer_effects.py`
(`test_fiend_artisans_variable_pump_counts_the_graveyard_live`), and the
*batch* divisor and the *and*-joined qualifier list are exercised here on the
two cards that motivated them, each proving the other is not a hardcode of
its own name (a batch-of-seven, single-type count on one; a per-card,
two-type count on the other - the shared machinery reads the sentence's own
divisor and qualifier list, not either card's name).

The rules these rest on:

- **CR 613.4c** - sublayer 7c: "Effects from... abilities that modify power
  and/or toughness (but that don't set power and/or toughness to a specific
  number or value) are applied." Both cards' printed power/toughness stands
  and this only adds to it - the reason neither uses `define_power_toughness`
  (CR 613.4a, sublayer 7a) the way a `*` characteristic-defining ability does.
- **CR 205.2a / CR 300.1** - Winter's "creature and planeswalker card" reads
  a card's own printed types, the same list `count_card_types` and delirium
  already read off a graveyard.
- **CR 611.3** - neither ability has a stated duration: the bonus lasts
  exactly as long as its source is on the battlefield with the ability,
  recomputed fresh (CR 613.5) as the graveyard grows.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_dark_matter_manipulator_gets_no_bonus_under_seven_cards():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Matter Manipulator"], graveyard=["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manipulator = scenario.creature("Dark Matter Manipulator", "alice")

    board = scenario.game.computed_board()

    assert board.of(manipulator).power_toughness == (1, 2), "printed 1/2, six cards is not seven"


def test_dark_matter_manipulator_gets_one_batch_at_exactly_seven_cards():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Matter Manipulator"], graveyard=["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manipulator = scenario.creature("Dark Matter Manipulator", "alice")

    board = scenario.game.computed_board()

    assert board.of(manipulator).power_toughness == (3, 2), "printed 1/2 plus one +2/+0 batch"


def test_dark_matter_manipulator_batches_by_integer_division_not_ceiling():
    """Fourteen cards is two full batches; thirteen is still only one - the
    bonus is `len(graveyard) // 7`, not `ceil(len(graveyard) / 7)`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Matter Manipulator"], graveyard=["Mountain"] * 13)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manipulator = scenario.creature("Dark Matter Manipulator", "alice")

    board = scenario.game.computed_board()

    assert board.of(manipulator).power_toughness == (3, 2), "13 // 7 == 1 batch, not 2"


def test_dark_matter_manipulator_grows_live_as_the_graveyard_grows():
    """CR 613.5: recomputed continually, not locked in when the creature
    entered - a card milled after it is on the battlefield still counts."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dark Matter Manipulator"],
            graveyard=["Mountain"] * 6,
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manipulator = scenario.creature("Dark Matter Manipulator", "alice")

    assert scenario.game.computed_board().of(manipulator).power_toughness == (1, 2)

    scenario.game.put_into_graveyard(scenario.player("alice").library[0])

    assert scenario.game.computed_board().of(manipulator).power_toughness == (3, 2)


def test_winter_tormented_loner_counts_creature_cards_in_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Winter, Tormented Loner"],
            graveyard=["Grizzly Bears", "Runeclaw Bear"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    winter = scenario.creature("Winter, Tormented Loner", "alice")

    board = scenario.game.computed_board()

    assert board.of(winter).power_toughness == (2, 3), "printed 0/3 plus two creature cards"


def test_winter_tormented_loner_counts_planeswalker_cards_too():
    """The "and"-joined qualifier list: a planeswalker card counts exactly
    like a creature card, proving the reader is not narrowed to one type."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Winter, Tormented Loner"],
            graveyard=["Grizzly Bears", "Ashiok, Dream Render"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    winter = scenario.creature("Winter, Tormented Loner", "alice")

    board = scenario.game.computed_board()

    assert board.of(winter).power_toughness == (2, 3), "printed 0/3 plus one of each type"


def test_winter_tormented_loner_ignores_noncreature_nonplaneswalker_cards():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Winter, Tormented Loner"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    winter = scenario.creature("Winter, Tormented Loner", "alice")

    board = scenario.game.computed_board()

    assert board.of(winter).power_toughness == (1, 3), "the instant does not count"


def test_winter_tormented_loner_reads_its_own_controllers_graveyard_only():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Winter, Tormented Loner"])
        .player("bob", graveyard=["Grizzly Bears", "Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    winter = scenario.creature("Winter, Tormented Loner", "alice")

    board = scenario.game.computed_board()

    assert board.of(winter).power_toughness == (0, 3), "an opponent's graveyard does not count"

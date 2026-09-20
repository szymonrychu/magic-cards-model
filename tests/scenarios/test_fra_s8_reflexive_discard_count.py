"""FRA stream S8: "`<antecedent, ending in a discard>`. When you discard one
or more [`<quality>`] cards this way, `<consequence, carrying the qualifying
count via "that many"/"that much">`." - CR 603.12's reflexive trigger family,
parametrized on a minimum-one *count* of qualifying discards rather than a
bare "when you do", and CR 607.1's linked-ability "that many"/"twice that
much" anaphora reading that count back in the consequence.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 121.1** - drawing a card.
- **CR 701.9a/701.9b** - discarding: moved to the graveyard, the discarding
  player's own choice of which by default.
- **CR 603.12** - the reflexive triggered ability itself, "checked
  immediately after being created", never waiting for a future occurrence.
- **CR 607.1** - a linked ability's anaphora onto exactly what an earlier
  ability on the same object affected - the count "that many"/"twice that
  much" carries forward here is this, not a fresh search of the board.
- **CR 701.26a** - tapping a permanent.
- **CR 122.1d** - a stun counter's own replacement effect: the next time it
  would untap, a stun counter is removed instead.

Seasoned Cryomancer's own ETB is the reported card: "draw two cards, then
discard two cards. When you discard one or more nonland cards this way, tap
up to that many target creatures and put a stun counter on each of them."
Borborygmos and Fblthp (real, non-FRA, non-pool) is the off-set proof: the
identical reflexive-discard-count shape with no quality restriction at all
(any card discarded qualifies), a different antecedent ("draw a card, then
you may discard any number of land cards" - CR 701.9b's default choice,
narrowed to a land-only pool, a new capability `_discard_cards` needed to
read this card at all), and a different consequence reading ("twice that
much damage to target creature" rather than "that many" bare) - proving the
merge, the quality reader, and the count substitution all generalize rather
than reading Seasoned Cryomancer's own exact sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_seasoned_cryomancer_taps_and_stuns_one_per_nonland_discard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Seasoned Cryomancer"],
            battlefield=["Island", "Island", "Island"],
            library=["Lightning Bolt", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Hill Giant", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    alice = scenario.player("alice")
    hill_giant = scenario.creature("Hill Giant", "bob")
    elvish_mystic = scenario.creature("Elvish Mystic", "bob")

    bolt = alice.library[0]
    bears = alice.library[1]
    assert bolt.name == "Lightning Bolt" and bears.name == "Grizzly Bears"

    # Both decisions are queued up front: the reflexive ability CR 603.3d
    # creates is put on the stack - and asks its own targets - as part of
    # finishing the ETB's own resolution below, before this scenario gets a
    # further chance to queue an answer.
    scenario.will_choose_cards(bolt, bears, username="alice")
    scenario.will_choose_targets(hill_giant, elvish_mystic, username="alice")
    scenario.cast_and_resolve("Seasoned Cryomancer", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.GRAVEYARD, "both drawn cards were discarded (CR 701.9a)"
    assert bears.zone is Zone.GRAVEYARD

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert hill_giant.tapped and elvish_mystic.tapped
    assert hill_giant.counters[Counter.STUN] == 1
    assert elvish_mystic.counters[Counter.STUN] == 1


def test_seasoned_cryomancer_creates_no_reflexive_ability_with_no_nonland_discard():
    """Both discards are lands, so CR 603.12's own event ("discard one or
    more nonland cards this way") never occurred - no reflexive ability is
    created at all, not one that resolves and taps nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Seasoned Cryomancer"],
            battlefield=["Island", "Island", "Island"],
            library=["Forest", "Mountain", "Swamp", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    alice = scenario.player("alice")
    hill_giant = scenario.creature("Hill Giant", "bob")

    forest = alice.library[0]
    mountain = alice.library[1]
    assert forest.name == "Forest" and mountain.name == "Mountain"

    scenario.will_choose_cards(forest, mountain, username="alice")
    scenario.cast_and_resolve("Seasoned Cryomancer", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD and mountain.zone is Zone.GRAVEYARD
    assert not scenario.game.pending_triggers, "no qualifying discard, no reflexive ability"
    assert not hill_giant.tapped
    assert hill_giant.counters[Counter.STUN] == 0


def test_borborygmos_and_fblthp_deals_twice_the_land_discard_count_in_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Borborygmos and Fblthp"],
            battlefield=["Forest", "Island", "Mountain", "Forest", "Island"],
            library=["Plains", "Grizzly Bears", "Swamp", "Lightning Bolt"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Island", "Mountain", "Forest", "Island")
    alice = scenario.player("alice")
    hill_giant = scenario.creature("Hill Giant", "bob")
    hill_giant_toughness = hill_giant.toughness

    plains = alice.library[0]
    assert plains.name == "Plains"

    # "You may discard any number of land cards": Plains is the only land
    # among the two cards drawn (Plains, Grizzly Bears) - the pool this
    # deal's own `predicate` narrows the choice to.
    scenario.will_choose_cards(plains, username="alice")
    scenario.will_choose_targets(hill_giant, username="alice")
    scenario.cast_and_resolve("Borborygmos and Fblthp", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert plains.zone is Zone.GRAVEYARD, "the one land drawn was discarded this way"

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # One land discarded -> "twice that much" -> 2 damage.
    assert hill_giant.damage == 2
    assert hill_giant.toughness == hill_giant_toughness

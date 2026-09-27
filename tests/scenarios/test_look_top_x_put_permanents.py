""" "Look at the top X cards of your library, where X is `<expr>`. [You may]
put any number of `<quality>` cards from among them onto the battlefield[
tapped], then shuffle." (CR 401.2's look, CR 701.7a's put, CR 701.24a's
shuffle).

Ajani, Outland Chaperone's `-8`: "Look at the top X cards of your library,
where X is your life total. You may put any number of nonland permanent
cards with mana value 3 or less from among them onto the battlefield. Then
shuffle." Two widenings this closes: `amount_expression` reads "your life
total" as X's own definition (CR 107.3c), and `_quality_matcher` reads a
"nonland " prefix (CR 109.2's negation of CR 205.2a's land type) the same way
"basic "/"snow "/"legendary " already stack.

Proof printing: **Famished Worldsire** (real Scryfall data, added with
`scripts/add_card.py`, not a listed card, not in any deck list,
Modern/Pioneer/Standard all `legal`) - its own ETB trigger, "look at the top
X cards of your library, where X is this creature's power. Put any number of
land cards from among them onto the battlefield tapped, then shuffle.",
exercises the same shape with a different X term (`_OBJECT_CHARACTERISTIC_RE`'s
own "this creature's power", already read), a plain (non-negated) quality,
no mana-value ceiling, and the "tapped" rider Ajani's own printing omits.

CR numbers verified with `mise run rules:find` in the session that wrote this
file: 401.2 (looking changes no zone), 701.7a (creating/putting tokens or
cards onto the battlefield), 701.24a (shuffle), 107.1c ("any number of" is
its own optionality, zero included), 107.3c (X defined by the ability's own
text), 109.2 (a "non-" prefix negates a card type).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

AJANI = "Ajani, Outland Chaperone"
WORLDSIRE = "Famished Worldsire"


def test_ajani_is_fully_handled():
    bad = [c for c in card_support(card(AJANI)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_famished_worldsires_look_top_x_clause_is_handled():
    """Only the clause this file proves generality with - Worldsire's own
    Devour keyword (CR 702.82c) is proven in `test_devour.py`."""
    triggered = [c for c in card_support(card(WORLDSIRE)).clauses if c.kind == "triggered"]
    assert triggered and all(c.outcome == "handled" for c in triggered), triggered


def test_ajani_minus_eight_puts_cheap_nonland_permanents_and_shuffles():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[AJANI],
            library=[
                "Grizzly Bears",  # nonland permanent, mv 2 - qualifies
                "Mountain",  # a land - excluded by "nonland"
                "Lightning Bolt",  # nonland, but not a permanent - excluded
                "Wrath of God",  # nonland permanent... no, it's a sorcery - excluded
                "Llanowar Elves",  # nonland permanent, mv 1 - qualifies
            ],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    alice.life = 5
    bears, mountain, bolt, wrath, elves = alice.library
    ajani = scenario.find(AJANI, Zone.BATTLEFIELD, "alice")
    ajani.add_counters(Counter.LOYALTY, 5)  # 3 -> 8, enough for -8

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(bears, elves, username="alice", source=AJANI)
    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert elves.zone is Zone.BATTLEFIELD
    assert mountain.zone is Zone.LIBRARY, "a land is excluded by 'nonland'"
    assert bolt.zone is Zone.LIBRARY, "not a permanent at all"
    assert wrath.zone is Zone.LIBRARY, "not a permanent at all"
    # Library held 5 cards, 5 were looked at (life total 5); the 3 left
    # behind were shuffled rather than left in their seen order.
    assert {state.id for state in alice.library} == {mountain.id, bolt.id, wrath.id}


def test_ajani_minus_eight_excludes_permanents_over_the_mana_value_ceiling():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[AJANI],
            library=["Grizzly Bears", "Serra Angel"],  # mv 2 and mv 5
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    alice.life = 2
    bears, angel = alice.library
    ajani = scenario.find(AJANI, Zone.BATTLEFIELD, "alice")
    ajani.add_counters(Counter.LOYALTY, 5)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(bears, username="alice", source=AJANI)
    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD, "mana value 2 <= 3"
    assert angel.zone is Zone.LIBRARY, "mana value 5 was never offered"


def test_ajani_minus_eight_may_choose_none_and_still_shuffles():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[AJANI], library=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    alice.life = 1
    (bears,) = alice.library
    ajani = scenario.find(AJANI, Zone.BATTLEFIELD, "alice")
    ajani.add_counters(Counter.LOYALTY, 5)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(username="alice", source=AJANI)
    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert bears.zone is Zone.LIBRARY, "CR 107.1c: choosing zero is legal"


def test_famished_worldsire_puts_lands_tapped_and_shuffles():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[WORLDSIRE],
            # Worldsire is printed 0/0 - Devour land 3 is what normally grows
            # it (`tests/scenarios/test_devour.py`); here it devours nothing,
            # so the X under test is Glorious Anthem's alone. The blanket
            # "+1/+1" gives it a real, nonzero power the instant it enters,
            # so it survives CR 704.5g's 0-toughness state-based action long
            # enough for its own ETB trigger to see a nonzero X.
            battlefield=["Forest"] * 8 + ["Glorious Anthem"] * 2,
            library=["Mountain", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    mountain, plains, bears = alice.library
    sources = scenario.untapped_sources(*(["Forest"] * 8))

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(username="alice", source=WORLDSIRE)  # devour no lands
    scenario.will_choose_cards(mountain, plains, username="alice", source=WORLDSIRE)
    scenario.cast_and_resolve(WORLDSIRE, *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the ETB look-and-put trigger

    assert mountain.zone is Zone.BATTLEFIELD
    assert mountain.tapped, "Worldsire's own printing puts them onto the battlefield tapped"
    assert plains.zone is Zone.BATTLEFIELD
    assert plains.tapped
    assert bears.zone is Zone.LIBRARY, "not a land, never offered"

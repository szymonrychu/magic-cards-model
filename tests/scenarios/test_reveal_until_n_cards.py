""" "Reveal cards from the top of your library until you reveal X `<kind>`
cards" - the variable-count sibling of the fixed "a `<kind>` card"
`machines/effects._REVEAL_UNTIL_KIND_RE` already reads, shared by
`machines/effects._reveal_until_n_of_kind` across the two structurally
different tails it is printed with in this pool: Aurora Awakener's own "put
any number of those permanent cards onto the battlefield, then put the rest
... on the bottom ... in a random order" (CR 608.2d's own choice among what
was found), and Sanar's own "for each of those colors, you may exile a card
of that color ..., then shuffle. You may cast the exiled cards this turn" (a
per-color choice, an ordinary CR 701.24a shuffle rather than a "bottom in a
random order", and CR 601.3's cast permission on top). One reveal-and-count
core, two genuinely different consumers, is the generality this file proves
on the two listed cards; the core itself is proven again off-pool below on
Skyserpent Seeker's own literal-count "put those `<kind>` cards onto the
battlefield[ tapped]" shape (`_merge_reveal_until_n_kind_put_onto_battlefield_
clauses`) - substituted for Old Stickfingers, whose own "When you cast this
spell, ..." wrapper needs CR 601.2i's cast-trigger recognition, a separate
subsystem out of scope here; see `MEMORY.md` for the dated substitution.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 701.15a: revealing a card from a hidden zone shows it to all players
  without changing its zone.
- CR 107.1b / CR 107.2: a count that would be negative is zero; "until you
  reveal zero `<kind>` cards" has nothing to look for.
- CR 608.2d: "put any number of those `<kind>` cards onto the battlefield"
  is the controller's own choice among what was found.
- CR 701.24a: an ordinary shuffle (Sanar's own "then shuffle") randomizes the
  whole library; "put ... on the bottom ... in a random order" (Aurora
  Awakener's own tail) is a different instruction that only reorders what it
  names.
- CR 601.3: a resolving ability's own time-boxed permission to cast specific
  cards it has exiled.
- CR 105.1 / CR 105.2c: the colors among a set of cards, colorless excluded.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

_WHITE = "Savannah Lions"


# -- Aurora Awakener: reveal until X permanent cards, put any number down ------


def test_aurora_awakener_reveals_until_x_permanent_cards_and_puts_any_number_down():
    """Vivid - white among permanents plus green Aurora Awakener itself
    (CR 603.6a) is two colors, so X is 2: Lightning Bolt is revealed and set
    aside (not a permanent card), then Grizzly Bears and Memnite stop the
    reveal at two permanent cards found. Alice puts only Grizzly Bears onto
    the battlefield (CR 608.2d's "any number"); Lightning Bolt and the
    unchosen Memnite go to the bottom in a random order (CR 401.4).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aurora Awakener"],
            library=["Lightning Bolt", "Grizzly Bears", "Memnite", "Forest"],
            battlefield=[_WHITE] + ["Forest"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 7)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY)
    memnite = scenario.find("Memnite", Zone.LIBRARY)
    scenario.will_choose_cards(bears, username="alice", source="Aurora Awakener")

    scenario.cast_and_resolve("Aurora Awakener", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"
    assert bolt.zone is Zone.LIBRARY
    assert memnite.zone is Zone.LIBRARY
    library_names = {state.name for state in scenario.player("alice").library}
    assert library_names == {"Lightning Bolt", "Memnite", "Forest"}


def test_aurora_awakener_stops_early_if_the_library_runs_out():
    """CR 701.15a/608.2c: the reveal stops when the library is empty even
    short of X - here Alice controls three colors (green Aurora Awakener,
    white, blue) but only two cards remain to look through, and neither is
    a permanent card, so nothing is found and nothing is put down.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aurora Awakener"],
            library=["Lightning Bolt", "Lightning Bolt"],
            battlefield=[_WHITE, "Cursecatcher"] + ["Forest"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 7)

    scenario.cast_and_resolve("Aurora Awakener", *sources)
    scenario.pass_until_resolved()

    # Both Lightning Bolts are revealed and neither is a permanent card, so
    # the reveal runs out of library before finding any match at all (CR
    # 608.2c) - nothing is put onto the battlefield, and both cards are
    # simply shuffled back (CR 401.4), still in the library.
    assert len(scenario.player("alice").library) == 2
    assert len(scenario.player("alice").graveyard) == 0


# -- Sanar: reveal until X nonland cards, exile per color, then cast ------------


def test_sanar_reveals_until_x_nonland_cards_and_may_exile_one_per_color():
    """Vivid - Sanar's hybrid {U/R}{U/R} cost makes it both blue and red
    (CR 202.2b), so X is 2 even with no other permanents: a Mountain is
    revealed and skipped (a land never counts), then Lightning Bolt and
    Goblin Guide - both red - stop the reveal at two nonland cards. "For each
    of those colors" is one color (red), so Alice is offered one exile
    choice among the two red cards; the Mountain returns to the library by
    an ordinary shuffle (CR 701.24a), not to any particular position.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sanar, Innovative First-Year"] + ["Mountain"] * 4,
            library=["Mountain", "Lightning Bolt", "Goblin Guide"],
        )
        .build()
    )
    scenario.start_at(Step.DRAW)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY)
    guide = scenario.find("Goblin Guide", Zone.LIBRARY)
    mountain_in_library = scenario.find("Mountain", Zone.LIBRARY)
    scenario.will_choose_cards(bolt, username="alice", source="Sanar, Innovative First-Year")

    scenario.advance()  # into the first (precombat) main phase
    assert scenario.step is Step.PRECOMBAT_MAIN
    scenario.pass_until_resolved()  # Sanar's own beginning-of-main-phase trigger

    assert bolt.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.pays_mana_cost is True

    # Goblin Guide (not chosen) and the Mountain are both back in the
    # library - CR 701.24a's shuffle, not "the bottom in a random order",
    # so their relative order is not asserted, only that both returned.
    assert guide.zone is Zone.LIBRARY
    assert mountain_in_library.zone is Zone.LIBRARY
    assert len(scenario.player("alice").library) == 2


# -- Off-pool proof: Skyserpent Seeker's literal-count reveal-until-N -----------


def test_skyserpent_seeker_reveals_until_two_land_cards_and_puts_them_down_tapped():
    """Off-pool proof (not a listed card, not in any deck) that `_reveal_
    until_n_of_kind`'s count generalisation - built for Aurora Awakener's and
    Sanar's own resolution-time X - is not hardcoded to either card: Exhaust -
    {4}: Reveal cards from the top of your library until you reveal two land
    cards. Put those land cards onto the battlefield tapped and the rest on
    the bottom of your library in a random order. Put a +1/+1 counter on this
    creature. (CR 702.177a's exhaust cost is a separate, already-tested
    mechanic - `test_exhaust.py` - this test is about the reveal.)

    Lightning Bolt (not a land) is revealed and set aside, then Forest and
    Swamp stop the reveal at two land cards found - both go onto the
    battlefield tapped (CR 401.4's ordinary battlefield-entry-tapped rule,
    read the same as `_PUT_REVEALED_CARD_RE`'s own "onto the battlefield
    tapped" case), a mandatory placement (no `CHOOSE_CARDS` decision, unlike
    Aurora Awakener's own "any number" choice), while Lightning Bolt goes to
    the bottom in a random order (`_shuffle_remainder_to_bottom`, the same
    helper Aurora Awakener's own reader calls).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[],
            library=["Lightning Bolt", "Forest", "Swamp", "Island"],
            battlefield=["Skyserpent Seeker"] + ["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seeker = scenario.creature("Skyserpent Seeker", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY)
    forest = scenario.find("Forest", Zone.LIBRARY)
    swamp = scenario.find("Swamp", Zone.LIBRARY)
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.activate(seeker, *sources)
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert swamp.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(forest).username == "alice"
    assert scenario.game.controller_of(swamp).username == "alice"
    assert forest.tapped
    assert swamp.tapped
    assert bolt.zone is Zone.LIBRARY
    library_names = {state.name for state in scenario.player("alice").library}
    assert library_names == {"Lightning Bolt", "Island"}
    assert seeker.counters[Counter.PLUS_ONE] == 1

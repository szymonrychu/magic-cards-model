"""Rituals that add mana on resolution rather than through a mana ability
(CR 106.4, CR 605.1a): Pyretic Ritual and Desperate Ritual both print "Add
{R}{R}{R}." as their whole effect, and Manamorphose prints "Add two mana in
any combination of colors. Draw a card."

None of the three is a mana ability (CR 605.5: "spells aren't mana
abilities"), so the mana arrives when the spell *resolves*, off the stack,
not through the fast path `pay_with`/`mana_from` read for a permanent's own
"{T}: Add ..." line. `_parse_add_mana_clause` (opened to spells this wave)
and the new `_parse_add_any_combination_mana_clause` are the resolution-time
readers.

Desperate Ritual also prints "Splice onto Arcane {1}{R}" (CR 702.47a) - not
built anywhere in this engine (`docs/engine-coverage.md` records the gap;
`_SPLICE_LINE_RE` only keeps that line from poisoning the ritual's own
"Add {R}{R}{R}." clause the way an unstripped Kicker/Flashback/Cycling line
already used to poison other cards' effects). `test_desperate_ritual_...`
below is the ritual's own mana working in full despite that gap, not a claim
that splice itself does anything.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 106.4, CR 605.1a, CR 605.5, CR 702.47a,
CR 121.1 (draw).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def test_pyretic_ritual_adds_three_red_mana():
    scenario = (
        Scenario().player("alice", hand=["Pyretic Ritual"], battlefield=["Mountain"] * 2).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Pyretic Ritual", *sources)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 3}


def test_pyretic_ritual_mana_can_pay_for_another_spell():
    """The mana is real and spendable, not just a number on the pool."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pyretic Ritual", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain"] * 2,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Pyretic Ritual", *sources)

    pool = scenario.player("alice").mana_pool
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert pool.floating == {Color.RED: 2}
    assert scenario.player("bob").life == 17


def test_desperate_ritual_adds_three_red_mana_despite_its_unbuilt_splice_line():
    """Splice onto Arcane is not modelled - see this file's header - but that
    gap must not take the ritual's own "Add {R}{R}{R}." down with it."""
    scenario = (
        Scenario().player("alice", hand=["Desperate Ritual"], battlefield=["Mountain"] * 2).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Desperate Ritual", *sources)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 3}


def test_manamorphose_adds_two_mana_of_the_chosen_colors_and_draws_a_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Manamorphose"],
            library=["Mountain"],
            battlefield=["Mountain"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Manamorphose", *sources)

    pool = scenario.player("alice").mana_pool
    # Unscripted CHOOSE_A_QUALITY answers default to the first offered
    # colour (`default_answer`), so both units come back white.
    assert pool.total == 2
    assert pool.floating == {Color.WHITE: 2}
    assert scenario.find("Mountain", Zone.HAND, "alice").zone is Zone.HAND


def test_manamorphose_lets_each_unit_of_mana_choose_its_own_color():
    """ "Any combination of colors" divides the total into individually
    chosen parts (CR 107.4h) - scripting a different colour for the second
    unit proves the two choices are independent, not one colour doubled."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Manamorphose"],
            library=["Mountain"],
            battlefield=["Mountain"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.will_choose(Color.WHITE.value, source="Manamorphose", times=1)
    scenario.will_choose(Color.BLUE.value, source="Manamorphose", times=1)

    scenario.cast_and_resolve("Manamorphose", *sources)

    pool = scenario.player("alice").mana_pool
    assert pool.floating == {Color.WHITE: 1, Color.BLUE: 1}

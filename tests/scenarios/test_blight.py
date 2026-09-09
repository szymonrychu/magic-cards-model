"""Blight: CR 701.68a's optional additional cost, and its linked bonus clause.

"To blight N" means to put N -1/-1 counters on a creature you control
(CR 701.68a). Requiting Hex prints it as "As an additional cost to cast this
spell, you may blight 1." (CR 118.8b's optional additional cost, matching
kicker's and offspring's own shape) with a linked "If this spell's
additional cost was paid, you gain 2 life." - read generically off
`CastRecord.optional_additional_cost_paid`
(`machines/effects._parse_if_additional_cost_paid_clause`), not off any one
keyword by name, so a kicker or offspring card's own "if this spell's
additional cost was paid" clause would read the same way.

`Casting.pay_blight` (the cost itself) is proved a second time on Burning
Curiosity - a sorcery, not an instant, and a different card entirely -
outside the deck pool and outside this wave's brief. Burning Curiosity's own
bonus ("exile the top three cards instead") is a CR 608.2c "instead"
replacement shape this wave does not read; see docs/engine-coverage.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_paying_blight_puts_counters_and_grants_the_bonus():
    """Requiting Hex: "Destroy target creature with mana value 2 or less. If
    this spell's additional cost was paid, you gain 2 life."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Requiting Hex"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    life_before = scenario.player("alice").life

    casting = scenario.cast("Requiting Hex", username="alice")
    casting.pay_blight(bears)
    casting.choose_targets([memnite])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert memnite.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before + 2


def test_declining_blight_pays_nothing_and_grants_no_bonus():
    """CR 118.8b: declining an optional additional cost is a legal
    announcement, and the linked bonus does not fire."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Requiting Hex"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    life_before = scenario.player("alice").life

    scenario.cast_and_resolve("Requiting Hex", *sources, username="alice", targets=[memnite])

    assert bears.counters[Counter.MINUS_ONE] == 0
    assert memnite.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before


def test_burning_curiosity_pays_its_own_blight_cost():
    """Burning Curiosity: "As an additional cost to cast this spell, you may
    blight 1." - a sorcery, not an instant, and a card outside the deck pool
    and this wave's brief, proving `Casting.pay_blight` is not wired to
    Requiting Hex by name.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Burning Curiosity"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")

    casting = scenario.cast("Burning Curiosity", username="alice")
    casting.pay_blight(bears)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1

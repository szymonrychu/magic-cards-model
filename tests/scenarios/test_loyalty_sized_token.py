"""A token sized by its source planeswalker's loyalty.

One mechanic: Nissa, Ascended Animist's "+1: Create an X/X green Phyrexian
Horror creature token, where X is Nissa's loyalty." X is defined by the text
(CR 107.3c), read once as the ability resolves (CR 608.2h) - after the +1
loyalty cost has been paid (CR 606.4), and after anything that changed her
loyalty in response. Her loyalty on the battlefield is her loyalty counters
(CR 306.5c), so compleated's reduced entry (CR 702.150a) feeds straight into
X. If she has left the battlefield by then, CR 608.2h uses her last known
information.

Every CR number above was read with `mise run rules:find` in the session that
wrote this file.

No proof printing: a Scryfall search (2026-09-23) for "(X is|equal to)
(its|<name>'s|this planeswalker's) loyalty" across Modern, Pioneer and
Standard finds Nissa alone; the amount term ("<self>'s loyalty") is the
`amount_expression` sibling of "its power"/"its toughness", which the pool
already proves. See MEMORY.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenState
from tests.scenarios.harness import Scenario

NISSA = "Nissa, Ascended Animist"
HORROR = "Phyrexian Horror"


def _horrors(scenario: Scenario) -> list:
    return [
        permanent
        for permanent in scenario.game.battlefield
        if isinstance(permanent, TokenState) and permanent.name.startswith(HORROR)
    ]


def _staged_nissa() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[NISSA])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_plus_one_makes_a_token_the_size_of_her_loyalty_after_the_cost():
    """Printed loyalty 7; the +1 is paid first (CR 606.4), so X is 8."""
    scenario = _staged_nissa()
    nissa = scenario.find(NISSA, Zone.BATTLEFIELD, "alice")

    scenario.activate(nissa, index=0)
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert nissa.loyalty == 8
    assert scenario.game.characteristics_of(horror).power_toughness == (8, 8)
    assert "Phyrexian" in horror.subtypes and "Horror" in horror.subtypes


def test_loyalty_lost_in_response_shrinks_the_token():
    """CR 608.2h: Lightning Bolt takes three loyalty from Nissa (CR 120.3c)
    while the +1 waits on the stack - X is 8 - 3 = 5."""
    scenario = _staged_nissa()
    nissa = scenario.find(NISSA, Zone.BATTLEFIELD, "alice")

    scenario.activate(nissa, index=0)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[nissa])
    scenario.resolve_top()
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert nissa.loyalty == 5
    assert scenario.game.characteristics_of(horror).power_toughness == (5, 5)


def test_the_token_keeps_its_size_when_her_loyalty_changes_later():
    """The X is fixed once, as the token is created: a later loss of loyalty
    does not shrink a token that already exists."""
    scenario = _staged_nissa()
    nissa = scenario.find(NISSA, Zone.BATTLEFIELD, "alice")
    scenario.activate(nissa, index=0)
    scenario.resolve_top()

    nissa.remove_counters(Counter.LOYALTY, 3)

    (horror,) = _horrors(scenario)
    assert scenario.game.characteristics_of(horror).power_toughness == (8, 8)


def test_nissa_gone_before_resolution_uses_her_last_known_loyalty():
    """CR 608.2h: destroyed with the +1 on the stack, Nissa's last known
    loyalty (8) still sizes the token."""
    scenario = _staged_nissa()
    nissa = scenario.find(NISSA, Zone.BATTLEFIELD, "alice")
    scenario.activate(nissa, index=0)

    scenario.game.destroy(nissa)
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert scenario.game.characteristics_of(horror).power_toughness == (8, 8)


def _cast_nissa(forests_tapped: int) -> tuple[Scenario, object]:
    scenario = Scenario().player("alice", hand=[NISSA], battlefield=["Forest"] * 7).player("bob")
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*(["Forest"] * forests_tapped))
    nissa = scenario.cast_and_resolve(NISSA, *lands)
    return scenario, nissa


def test_compleated_with_both_symbols_paid_in_life_feeds_x():
    """Both {G/P} paid with life: she enters with 7 - 2*2 = 3 (CR 702.150a),
    the +1 makes 4, and the token is 4/4."""
    scenario, nissa = _cast_nissa(5)
    assert nissa.loyalty == 3

    scenario.activate(nissa, index=0)
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert scenario.game.characteristics_of(horror).power_toughness == (4, 4)


def test_compleated_with_one_symbol_paid_in_life_feeds_x():
    """One {G/P} paid with life: 7 - 2 = 5, +1 makes 6, a 6/6 token."""
    scenario, nissa = _cast_nissa(6)
    assert nissa.loyalty == 5

    scenario.activate(nissa, index=0)
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert scenario.game.characteristics_of(horror).power_toughness == (6, 6)


def test_cast_with_mana_alone_enters_at_full_loyalty_and_makes_an_eight():
    """Every symbol paid with mana: 7, +1 makes 8, an 8/8."""
    scenario, nissa = _cast_nissa(7)

    scenario.activate(nissa, index=0)
    scenario.resolve_top()

    (horror,) = _horrors(scenario)
    assert scenario.game.characteristics_of(horror).power_toughness == (8, 8)

"""Scenario: `Game.activation_cost_reduction_for` (CR 601.2f via CR 602.2b)
counts a "costs [N] less to activate for each [quality] you control" clause
against the computed board (CR 613.5), not the printed `state.card.types`/
`.supertypes` `test_off_battlefield_activation.py`'s own baseline exercises.

Otawara, Soaring City's Channel: "This ability costs {1} less to activate
for each legendary creature you control" already has a working regression
test with two *printed* legendary creatures (Ragavan, Questing Beast) in
`test_off_battlefield_activation.py::test_otawaras_cost_reduction_is_its_own_ability_not_a_third_clause`.
This file is the printed/computed divergence that baseline cannot exercise:
Shifting Woodland's own Delirium ability (CR 706, CR 707.2, CR 707.4) makes
it a copy of a legendary creature card sitting in the graveyard - a
Legendary Creature only on the computed board, while its own printed card
is an ordinary land.

Every CR number was looked up with `mise run rules:find` this session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Supertype, Type
from tests.scenarios.harness import Scenario


def test_otawaras_channel_counts_a_computed_only_legendary_creature():
    """Delirium is active (creature, artifact, instant, land in the
    graveyard - four card types, CR 205.2a), so Shifting Woodland may become
    a copy of Ragavan, Nimble Pilferer - Legendary Creature - sitting in the
    graveyard. `activation_cost_reduction_for` has to read the computed
    supertypes and types to see that alice now controls a legendary
    creature at all; the printed `Shifting Woodland` card is a plain land.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Otawara, Soaring City"],
            battlefield=[
                "Shifting Woodland",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Island",
                "Island",
                "Island",
            ],
            graveyard=["Ragavan, Nimble Pilferer", "Sol Ring", "Lightning Bolt", "Island"],
        )
        .player("bob", battlefield=["Mox Opal"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    woodland = scenario.find("Shifting Woodland", Zone.BATTLEFIELD, "alice")
    ragavan = scenario.find("Ragavan, Nimble Pilferer", Zone.GRAVEYARD, "alice")
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD, "bob")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    otawara = scenario.find("Otawara, Soaring City", Zone.HAND, "alice")

    reason = scenario.why_cannot_activate(woodland, 1)
    assert reason is None, "delirium: creature/artifact/instant/land in the graveyard"
    scenario.activate(woodland, *forests, index=1, targets=[ragavan])
    scenario.resolve_top()

    chars = scenario.game.characteristics_of(woodland)
    assert chars.name == "Ragavan, Nimble Pilferer"

    assert Type.CREATURE in chars.types
    assert Supertype.LEGENDARY in chars.supertypes
    assert woodland.name == "Shifting Woodland"  # the printed card never changed

    islands = scenario.untapped_sources("Island", "Island", "Island")
    activation = off_battlefield_activation(scenario.game, otawara, "alice", targets=[mox])

    assert str(activation.cost.mana) == "{2}{U}", (
        "one computed-only legendary creature: {3}{U} reduced by {1}"
    )

    payment = activation.begin_paying()
    for island in islands:
        payment.tap_for_mana(island, [Color.BLUE])
    payment.pay()
    activation.activate()
    activation.resolve()

    assert mox.zone is Zone.HAND
    assert scenario.game.controller_of(mox).username == "bob"


def test_otawaras_channel_does_not_count_the_land_before_it_copies_anything():
    """The inverse: with no Shifting Woodland activation, alice controls no
    legendary creature at all, so Otawara's Channel costs its full {3}{U}.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Otawara, Soaring City"],
            battlefield=["Shifting Woodland", "Island", "Island"],
        )
        .player("bob", battlefield=["Mox Opal"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD, "bob")
    otawara = scenario.find("Otawara, Soaring City", Zone.HAND, "alice")

    activation = off_battlefield_activation(scenario.game, otawara, "alice", targets=[mox])

    assert str(activation.cost.mana) == "{3}{U}"

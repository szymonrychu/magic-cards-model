""" "Whenever `<a player>` activates an ability that isn't a mana ability" -
a trigger on CR 602.2's activation itself.

CR 602.2: "To activate an ability is to put it onto the stack and pay its
costs, so that it will eventually resolve and have its effect."

CR 605.1a: "An activated ability is a mana ability if it meets all of the
following criteria: it doesn't require a target (see rule 115.6), it could
add mana to a player's mana pool when it resolves, it's not a loyalty ability
(see rule 606, "Loyalty Abilities"), and its cost and effect don't move any
card to or from a library." A loyalty ability, a cycling ability and an equip
ability are all non-mana activated abilities; tapping a land for mana is not.

CR 109.2: "If a spell or ability uses a description of an object that
includes a card type or subtype, but doesn't refer to a specific zone or
include the word "card," "spell," "source," or "scheme," it means a
permanent of that card type or subtype on the battlefield." - Immolation
Shaman's "an ability of an artifact, creature, or land" is an ability of such
a permanent, so a creature card cycled from a hand does not count.

Flamescroll Celebrant is the listed card ("an opponent"); Burning-Tree
Shaman ("a player") and Immolation Shaman (a type-qualified source) are the
proof printings, both Modern-legal and in no api deck.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cycling_activation, equip_activation
from magic_cards_model.models import CardState, Zone
from magic_cards_model.support import classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

CELEBRANT = "Flamescroll Celebrant"
CELEBRANT_CARD = "Flamescroll Celebrant // Revel in Silence"
BURNING_TREE = "Burning-Tree Shaman"
IMMOLATION = "Immolation Shaman"


def pay_and_activate(activation, *mana: CardState):
    payment = activation.begin_paying()
    for source in mana:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return activation.activate()


def drain(scenario) -> None:
    while scenario.game.stack:
        scenario.pass_until_resolved()


def test_an_opponents_loyalty_activation_costs_them_one_life() -> None:
    """A loyalty ability is not a mana ability (CR 605.1a) - Bob's +2 is
    punished, and the trigger resolves before the +2 does."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Garruk, Veiled Butcher"])
        .player("alice", battlefield=[CELEBRANT_CARD])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find("Garruk, Veiled Butcher", Zone.BATTLEFIELD, "bob")

    scenario.activate(garruk, index=0, targets=[])

    assert scenario.stack_names()[-1] == f"{CELEBRANT}'s triggered ability"
    scenario.resolve_top()
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20


def test_an_opponent_cycling_a_card_is_punished() -> None:
    """Cycling is an activated ability that functions in the hand (CR
    702.29a) - still an ability activated, still not a mana ability."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[CELEBRANT_CARD])
        .player("bob", hand=["Censor"], library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    censor = scenario.find("Censor", Zone.HAND, "bob")

    pay_and_activate(
        cycling_activation(scenario.game, censor, "bob"),
        *scenario.untapped_sources("Island", username="bob"),
    )
    drain(scenario)

    assert scenario.player("bob").life == 19


def test_an_opponent_equipping_is_punished() -> None:
    """Equip (CR 702.6a) is an activated ability too."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain"])
        .player("alice", battlefield=[CELEBRANT_CARD])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    pay_and_activate(
        equip_activation(scenario.game, cutter, bears, "bob"),
        *scenario.untapped_sources("Mountain", "Mountain", username="bob"),
    )
    assert scenario.stack_names()[-1] == f"{CELEBRANT}'s triggered ability"
    drain(scenario)

    assert scenario.player("bob").life == 19


def test_each_activation_triggers_it_separately() -> None:
    """Two activations are two events - two pings."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[CELEBRANT_CARD])
        .player(
            "bob",
            hand=["Censor", "Censor"],
            library=["Island", "Island"],
            battlefield=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.untapped_sources("Island", "Island", username="bob")

    for island in (first, second):
        censor = scenario.find("Censor", Zone.HAND, "bob")
        pay_and_activate(cycling_activation(scenario.game, censor, "bob"), island)
        drain(scenario)

    assert scenario.player("bob").life == 18


def test_tapping_a_land_for_mana_is_a_mana_ability_and_is_not_punished() -> None:
    """CR 605.1a: a mana ability never goes on the stack (CR 605.3b) and is
    exactly what "that isn't a mana ability" excludes."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Mountain"])
        .player("alice", battlefield=[CELEBRANT_CARD])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    assert scenario.activate(mountain, username="bob") is None

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_its_controllers_own_activations_are_not_punished() -> None:
    """ "an opponent" - Alice pumping her own Celebrant takes no damage."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[CELEBRANT_CARD, "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    celebrant = scenario.creature(CELEBRANT, "alice")

    scenario.activate(celebrant, *scenario.untapped_sources("Mountain", "Mountain"))

    assert scenario.stack_names() == [f"{CELEBRANT}'s activated ability"]
    drain(scenario)
    assert scenario.player("alice").life == 20
    assert scenario.game.characteristics_of(celebrant).power_toughness[0] == 4


def test_burning_tree_shaman_punishes_every_player_including_its_controller() -> None:
    """Proof printing: "a player" - its controller's own activation pings
    its controller, an opponent's pings the opponent."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[BURNING_TREE, CELEBRANT_CARD, "Mountain", "Mountain"])
        .player("bob", hand=["Censor"], library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    celebrant = scenario.creature(CELEBRANT, "alice")

    scenario.activate(celebrant, *scenario.untapped_sources("Mountain", "Mountain"))
    drain(scenario)
    assert scenario.player("alice").life == 19

    censor = scenario.find("Censor", Zone.HAND, "bob")
    pay_and_activate(
        cycling_activation(scenario.game, censor, "bob"),
        *scenario.untapped_sources("Island", username="bob"),
    )
    drain(scenario)
    # Burning-Tree Shaman and Flamescroll Celebrant both punish Bob.
    assert scenario.player("bob").life == 18


def test_immolation_shaman_punishes_an_ability_of_a_creature_on_the_battlefield() -> None:
    """Proof printing: "an ability of an artifact, creature, or land" - Bob's
    own creature's activated ability counts (and his own Immolation Shaman
    does not punish him for it: "an opponent")."""
    scenario = (
        Scenario()
        .player("bob", battlefield=[IMMOLATION] + ["Mountain"] * 5)
        .player("alice", battlefield=[IMMOLATION])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_shaman = scenario.creature(IMMOLATION, "bob")

    scenario.activate(
        bobs_shaman, *scenario.untapped_sources(*["Mountain"] * 5, username="bob"), username="bob"
    )
    drain(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20


def test_immolation_shaman_punishes_an_equip_ability_of_an_artifact() -> None:
    scenario = (
        Scenario()
        .player("bob", battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain"])
        .player("alice", battlefield=[IMMOLATION])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    pay_and_activate(
        equip_activation(scenario.game, cutter, bears, "bob"),
        *scenario.untapped_sources("Mountain", "Mountain", username="bob"),
    )
    drain(scenario)

    assert scenario.player("bob").life == 19


def test_immolation_shaman_ignores_a_creature_card_cycled_from_hand() -> None:
    """CR 109.2: "creature" with no "card" is a creature permanent - Vizier
    of Tumbling Sands cycled from Bob's hand is a creature *card*."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[IMMOLATION])
        .player(
            "bob",
            hand=["Vizier of Tumbling Sands"],
            library=["Island"],
            battlefield=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vizier = scenario.find("Vizier of Tumbling Sands", Zone.HAND, "bob")

    island, other = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.choose_trigger_targets("Vizier of Tumbling Sands", [island])
    pay_and_activate(cycling_activation(scenario.game, vizier, "bob"), island, other)
    drain(scenario)

    assert scenario.player("bob").life == 20


def test_immolation_shaman_ignores_a_planeswalkers_loyalty_ability() -> None:
    """A planeswalker is none of "an artifact, creature, or land"."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Garruk, Veiled Butcher"])
        .player("alice", battlefield=[IMMOLATION])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find("Garruk, Veiled Butcher", Zone.BATTLEFIELD, "bob")

    scenario.activate(garruk, index=0, targets=[])
    drain(scenario)

    assert scenario.player("bob").life == 20


def test_the_sweep_reads_every_activation_punisher() -> None:
    for name in (CELEBRANT_CARD, BURNING_TREE, IMMOLATION):
        outcomes = classify_clauses(card(name))
        triggered = [outcome for outcome in outcomes if outcome.source.startswith("triggered")]
        assert triggered, (name, outcomes)
        assert {outcome.category for outcome in triggered} == {"handled"}, (name, outcomes)

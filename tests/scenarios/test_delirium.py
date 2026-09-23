"""Scenario: *delirium* - a card whose effect changes with the card types in a graveyard.

Two of the most-played cards in Modern's red decks carry it, and both were in the
tournament lists this file's card pool came from: Unholy Heat and Violent Urge.

The interesting thing about *delirium* is that there is nothing to build. It is
an **ability word** (CR 207.2c: "Ability words are similar to keywords in that
they tie together cards that have similar functionality, but they have no special
rules meaning"), so the entire mechanic is the sentence printed after the word,
and the only real question is what counts.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 207.2c** - an ability word has no rules meaning of its own.
- **CR 205.2a / CR 300.1** - the card types. A card with two of them counts for
  both, which is why one Dryad Arbor (`Land Creature`) is worth two types.
- **CR 611.2c** - a resolving spell's effect is fixed as it resolves; the
  condition is not rechecked afterwards.
- **CR 613.6** - one spell's effect can apply in more than one layer, each part
  in its own.
- **CR 613.1f / CR 113.10** - "gains" is an ability-adding effect, layer 6.
- **CR 613.4c** - +1/+0 is sublayer 7c.
- **CR 702.7a / CR 702.4 / CR 510.4** - first strike and double strike, and the
  extra combat damage step they cause.
- **CR 120.5** - damage does not destroy a creature; a state-based action does.

The counting is `count_card_types` in `machines/layers.py`, and the effects are
`delirium_damage` and, for Violent Urge's rider, `machines/effects.py`'s
`_parse_conditional_referent_clause`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import ContinuousEffects
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

#: Four distinct card types (CR 300.1): creature, instant, sorcery, artifact.
FOUR_TYPES = ["Grizzly Bears", "Lightning Bolt", "Preordain", "Mishra's Bauble"]
#: Three of them - one short of delirium.
THREE_TYPES = ["Grizzly Bears", "Lightning Bolt", "Preordain"]


def hold_effects(scenario) -> ContinuousEffects:
    """Give the game the store of durational continuous effects it lacks.

    `models/game.py` has no `continuous_effects` field yet, so this attaches one
    exactly as that one-line field would; `machines/effects.py` finds it through
    `continuous_effects(game)`. Everything else here is the real engine.
    """
    store = ContinuousEffects()
    store.note(scenario.game.battlefield)
    object.__setattr__(scenario.game, "continuous_effects", store)
    return store


def _heat_board(graveyard: list[str], defender: str = "Serra Angel") -> Scenario:
    """Alice holding Unholy Heat with a stacked graveyard; Bob holding the target."""
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Unholy Heat"],
            battlefield=["Mountain"],
            graveyard=graveyard,
        )
        .player("bob", library=["Forest"], battlefield=[defender])
    )


# -- Unholy Heat: 2 damage, or 6 -------------------------------------------


def test_without_delirium_unholy_heat_deals_two():
    """ "Unholy Heat deals 2 damage to target creature or planeswalker."

    Three card types in the graveyard is one short, so the base number applies.
    A Serra Angel is 4/4, so 2 damage is marked and CR 120.5 leaves it standing:
    "Damage dealt to a creature ... doesn't destroy it."
    """
    scenario = _heat_board(THREE_TYPES).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Unholy Heat", mountain, targets=[angel])

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_with_delirium_unholy_heat_deals_six():
    """*Delirium* - "Unholy Heat deals 6 damage instead if there are four or more
    card types among cards in your graveyard."

    Four types, so 6 damage, which is lethal to a 4/4 - and it is the
    state-based action (CR 120.5) that puts the Angel in the graveyard, not the
    damage itself.
    """
    scenario = _heat_board(FOUR_TYPES).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Unholy Heat", mountain, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD


def test_a_land_creature_in_the_graveyard_counts_for_two_types():
    """CR 205.2a's card types are counted per type, not per card. Dryad Arbor is
    a `Land Creature`, so a graveyard of Dryad Arbor, Lightning Bolt and
    Preordain holds four types - land, creature, instant, sorcery - with only
    three cards in it.

    This is the case that separates counting types from counting cards, and it
    is exactly the case a naive implementation gets wrong.
    """
    scenario = _heat_board(["Dryad Arbor", "Lightning Bolt", "Preordain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Unholy Heat", mountain, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD


def test_duplicate_card_types_do_not_stack():
    """Four creatures are one card type, not four. A graveyard of nothing but
    creatures never has delirium however deep it gets.
    """
    creatures = ["Grizzly Bears", "Watchwolf", "Serra Angel", "Craw Wurm"]
    scenario = _heat_board(creatures).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Unholy Heat", mountain, targets=[angel])

    assert angel.damage == 2


def test_delirium_counts_your_graveyard_and_not_your_opponents():
    """ "...among cards in **your** graveyard." An opponent with a full graveyard
    does not turn a Heat on.

    Worth a test of its own because the layer engine's other card-type counter,
    Tarmogoyf, counts "cards in **all** graveyards" - the two are one word apart
    on the card and a whole different question in play.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Unholy Heat"],
            battlefield=["Mountain"],
            graveyard=["Grizzly Bears"],
        )
        .player(
            "bob",
            library=["Forest"],
            battlefield=["Serra Angel"],
            graveyard=FOUR_TYPES,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Unholy Heat", mountain, targets=[angel])

    assert angel.damage == 2


def test_the_count_is_taken_on_resolution_and_not_on_casting():
    """CR 608.2 does the effect when the spell resolves, so the graveyard that
    matters is the one at that moment. Here the fourth type arrives while the
    Heat is on the stack, and it counts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Unholy Heat"],
            battlefield=["Mountain", "Mishra's Bauble"],
            graveyard=THREE_TYPES,
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_onto_stack("Unholy Heat", mountain, targets=[angel])

    # An artifact reaches the graveyard while the Heat waits: a fourth type.
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "alice")
    scenario.game.put_into_graveyard(bauble)

    scenario.pass_until_resolved()

    assert angel.zone is Zone.GRAVEYARD


# -- Violent Urge: two layers from one resolution --------------------------


def _urge_board(graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Violent Urge"],
            battlefield=["Mountain", "Grizzly Bears"],
            graveyard=graveyard,
        )
        .player("bob", library=["Forest"])
    )


def test_violent_urge_pumps_and_grants_first_strike():
    """ "Target creature gets +1/+0 and gains first strike until end of turn."

    CR 613.6 splits one spell across layers: the +1/+0 is sublayer 7c
    (CR 613.4c) and first strike (CR 702.7a) is an ability grant in layer 6
    (CR 613.1f, CR 113.10). Both come out of one resolution with one timestamp.
    """
    scenario = _urge_board(THREE_TYPES).build()
    store = hold_effects(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Violent Urge", mountain, targets=[bears])

    computed = store.board(scenario.game.battlefield)[bears]
    assert computed.power_toughness == (3, 2)
    assert computed.has_ability("First strike")
    assert not computed.has_ability("Double strike")


def test_violent_urge_with_delirium_grants_double_strike_as_well():
    """*Delirium* - "that creature gains double strike until end of turn."

    Double strike is CR 702.4; CR 510.4 is what it buys - a first combat damage
    step for the creatures that have it, then a second for everything else. The
    +1/+0 and the first strike still happen: the delirium clause adds a third
    effect rather than replacing the first two.
    """
    scenario = _urge_board(FOUR_TYPES).build()
    store = hold_effects(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Violent Urge", mountain, targets=[bears])

    computed = store.board(scenario.game.battlefield)[bears]
    assert computed.power_toughness == (3, 2)
    assert computed.has_ability("First strike")
    assert computed.has_ability("Double strike")


def test_the_delirium_clause_is_not_rechecked_after_resolution():
    """CR 611.2c fixes what a resolving spell's effect does at the moment it is
    created. The delirium clause is not a "for as long as" duration (CR 611.2b),
    so emptying the graveyard afterwards does not take the double strike back.
    """
    scenario = _urge_board(FOUR_TYPES).build()
    store = hold_effects(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Violent Urge", mountain, targets=[bears])
    scenario.player("alice").zones[Zone.GRAVEYARD].clear()

    computed = store.board(scenario.game.battlefield)[bears]
    assert computed.has_ability("Double strike")


def test_first_strike_granted_by_violent_urge_reaches_combat():
    """CR 702.7b and CR 510.4: if any attacking or blocking creature has first
    strike as the combat damage step begins, there are two combat damage steps.

    A 2/2 given first strike kills a 2/2 blocker before it strikes back. Today
    both die, because combat never sees the grant.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Violent Urge"],
            battlefield=["Mountain", "Grizzly Bears"],
            graveyard=THREE_TYPES,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    hold_effects(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Violent Urge", mountain, targets=[mine])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mine)
    scenario.advance()
    scenario.block(mine, theirs)
    scenario.combat_damage()

    assert theirs.zone is Zone.GRAVEYARD
    assert mine.zone is Zone.BATTLEFIELD

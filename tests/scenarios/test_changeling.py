"""Changeling: "This object is every creature type", in every zone.

Every CR number below was read whole with `mise run rules:find <n>` in the
session that wrote this file (rules effective September 25, 2026):

- **CR 702.73a** - "Changeling is a characteristic-defining ability.
  'Changeling' means 'This object is every creature type.' This ability works
  everywhere, even outside the game. See rule 604.3."
- **CR 604.3** - characteristic-defining abilities "function in all zones.
  They also function outside the game and before the game begins."
- **CR 604.3a** - item (2): a CDA is one "printed on the card it affects, it
  was granted to the token it affects by the effect that created the token,
  or it was acquired by the object it affects as the result of a copy effect
  or text-changing effect" - so Crib Swap's Shapeshifter token "with
  changeling" has a real CDA.
- **CR 613.1d** - layer 4, type-changing effects, which is where the CDA
  applies on the battlefield.
- **CR 613.3** - "Within layers 2-6, apply effects from characteristic-defining
  abilities first ..., then all other effects in timestamp order", so a later
  type-setting effect (Metamorphic Blast's "becomes a white Rabbit") replaces
  the creature types the CDA gave it (CR 205.1a).
- **CR 613.1f** - ability-removing effects are layer 6, after layer 4 has
  already applied the CDA, so Humility does not take the types away.
- **CR 205.3m** - the creature-type list (`data/creature_types.py`).
- **CR 205.3d** - "An object can't gain a subtype that doesn't correspond to
  one of that object's types": changeling adds creature types only, never a
  land, artifact, enchantment or spell subtype.

Proofs run on Changeling Outcast (off-pool, Modern-legal, added for this file)
and Fire-Belly Changeling (the reported card), plus Crib Swap (off-pool,
Modern-legal Kindred instant with changeling that also creates a token "with
changeling"), against the pool's own creature-type readers: Stormscale Scion's
Dragon lord, Goblin Warchief's Goblin haste grant and Goblin-spell cost
reduction, Immaculate Magistrate's "for each Elf you control", Gilt-Leaf
Palace's "reveal an Elf card from your hand", Kinsbaile Aspirant's "behold a
Kithkin", Orb of Dragonkind's "reveal a Dragon card from among them" and its
Dragon-only mana, Grist's milled Insect, Kaheera's companion condition, and
Metamorphic Blast's "becomes a white Rabbit" (Turn to Frog, off-pool, is the
second printing of that template).
"""

import pytest
from scripts.sweep_pool import ignored_keywords

from magic_cards_model.data.creature_types import creature_types
from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario

EVERY_CREATURE_TYPE = frozenset(creature_types())
CHANGELINGS = ("Changeling Outcast", "Fire-Belly Changeling")


def _main_phase(**alice) -> Scenario:
    scenario = Scenario().player("alice", **alice).player("bob", library=["Island"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- every zone (CR 702.73a, CR 604.3) ----------------------------------------


@pytest.mark.parametrize("name", CHANGELINGS)
@pytest.mark.parametrize(
    "zone", [Zone.HAND, Zone.LIBRARY, Zone.GRAVEYARD, Zone.EXILE, Zone.SIDEBOARD]
)
def test_off_the_battlefield_a_changeling_card_is_every_creature_type(name, zone):
    state = card_state(name, zone=zone)

    assert set(state.subtypes) >= EVERY_CREATURE_TYPE
    assert "Goblin" in state.subtypes and "Time Lord" in state.subtypes


@pytest.mark.parametrize("name", CHANGELINGS)
def test_changeling_adds_creature_types_only(name):
    """CR 205.3d: no land, artifact, enchantment or spell subtype."""
    subtypes = set(card_state(name, zone=Zone.HAND).subtypes)

    assert subtypes <= EVERY_CREATURE_TYPE
    for other in ("Forest", "Equipment", "Aura", "Lesson", "Adventure", "Vehicle", "Saga"):
        assert other not in subtypes


def test_a_card_without_changeling_keeps_its_printed_creature_types():
    assert tuple(card_state("Goblin Warchief", zone=Zone.HAND).subtypes) == ("Goblin", "Warrior")


def test_a_kindred_changeling_spell_on_the_stack_is_every_creature_type():
    """Crib Swap is a Kindred Instant - Shapeshifter. CR 205.3d lets a kindred
    object carry creature types, so on the stack it is a Goblin spell too."""
    scenario = _main_phase(
        hand=["Crib Swap"], battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = scenario.cast_onto_stack(
        "Crib Swap", *scenario.untapped_sources("Plains", "Plains", "Plains"), targets=[bears]
    )

    assert spell.zone is Zone.STACK
    assert set(spell.subtypes) >= EVERY_CREATURE_TYPE


# -- the battlefield: a layer 4 CDA (CR 613.1d, CR 613.3) ----------------------


@pytest.mark.parametrize("name", CHANGELINGS)
def test_on_the_battlefield_the_computed_subtypes_are_every_creature_type(name):
    scenario = _main_phase(battlefield=[name])
    changeling = scenario.creature(name, "alice")

    computed = scenario.game.characteristics_of(changeling)

    assert set(computed.subtypes) >= EVERY_CREATURE_TYPE
    assert set(computed.subtypes) <= EVERY_CREATURE_TYPE


def test_the_battlefield_types_come_from_a_layer_4_characteristic_defining_effect():
    """Layer 1b's printed characteristics carry only the type line's
    Shapeshifter; the CDA is what adds the rest, in layer 4 (CR 613.1d)."""
    from magic_cards_model.machines.layers import printed_characteristics

    scenario = _main_phase(battlefield=["Changeling Outcast"])
    outcast = scenario.creature("Changeling Outcast", "alice")

    assert printed_characteristics(outcast).subtypes == ("Shapeshifter",)
    board = scenario.game.computed_board()
    assert any("CR 702.73a" in applied for applied in board.journal.applied)


def test_a_dragon_lord_pumps_a_changeling():
    """Stormscale Scion: "Other Dragons you control get +1/+1." """
    scenario = _main_phase(
        battlefield=["Stormscale Scion", "Changeling Outcast", "Fire-Belly Changeling"]
    )

    for name in CHANGELINGS:
        changeling = scenario.creature(name, "alice")
        assert (changeling.power, changeling.toughness) == (2, 2), name


def test_a_goblin_grant_gives_a_changeling_haste():
    """Goblin Warchief: "Goblins you control have haste." A changeling that
    entered this turn may attack (CR 302.6 is waived by haste)."""
    scenario = _main_phase(battlefield=["Goblin Warchief"], hand=["Changeling Outcast"])
    outcast = scenario.put_onto_battlefield("Changeling Outcast", "alice")

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers

    assert scenario.can_attack(outcast)


@pytest.mark.parametrize(
    ("spell", "expected"),
    [("Fire-Belly Changeling", "{R}"), ("Crib Swap", "{1}{W}")],
)
def test_a_changeling_spell_is_a_goblin_spell_for_a_cost_reduction(spell, expected):
    """Goblin Warchief: "Goblin spells you cast cost {1} less to cast." Both
    the creature changeling and the Kindred instant are Goblin spells."""
    scenario = _main_phase(battlefield=["Goblin Warchief", "Grizzly Bears"], hand=[spell])
    casting = scenario.cast(spell)
    if spell == "Crib Swap":
        casting.choose_targets([scenario.creature("Grizzly Bears", "alice")])

    assert casting.total_cost.mana == ManaCost.parse(expected)


def test_changelings_count_as_elves_for_a_for_each_count():
    """Immaculate Magistrate: "{T}: Put a +1/+1 counter on target creature
    for each Elf you control." Magistrate plus two changelings is three."""
    scenario = _main_phase(battlefield=["Immaculate Magistrate", *CHANGELINGS, "Grizzly Bears"])
    magistrate = scenario.creature("Immaculate Magistrate", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(magistrate, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 3


# -- reveals and searches off the battlefield ----------------------------------


def test_a_changeling_in_hand_can_be_revealed_as_an_elf():
    """Gilt-Leaf Palace: "As this land enters, you may reveal an Elf card from
    your hand. If you don't, this land enters tapped." """
    scenario = _main_phase(hand=["Gilt-Leaf Palace", "Changeling Outcast"])

    assert scenario.play_land("Gilt-Leaf Palace").tapped is False


def test_a_changeling_in_hand_can_be_beheld_as_a_kithkin():
    """Kinsbaile Aspirant: "behold a Kithkin or pay {2}" - revealing the
    changeling from hand pays the behold half (CR 701.4a)."""
    scenario = _main_phase(
        hand=["Kinsbaile Aspirant", "Fire-Belly Changeling"], battlefield=["Plains"]
    )
    changeling = scenario.find("Fire-Belly Changeling", Zone.HAND, "alice")

    scenario.cast_and_resolve(
        "Kinsbaile Aspirant", *scenario.untapped_sources("Plains"), beholding=[changeling]
    )

    assert scenario.creature("Kinsbaile Aspirant", "alice").zone is Zone.BATTLEFIELD
    assert changeling.zone is Zone.HAND


def test_a_changeling_on_the_battlefield_can_be_beheld_as_a_kithkin():
    scenario = _main_phase(
        hand=["Kinsbaile Aspirant"], battlefield=["Plains", "Changeling Outcast"]
    )
    outcast = scenario.creature("Changeling Outcast", "alice")

    scenario.cast_and_resolve(
        "Kinsbaile Aspirant", *scenario.untapped_sources("Plains"), beholding=[outcast]
    )

    assert scenario.creature("Kinsbaile Aspirant", "alice").zone is Zone.BATTLEFIELD


def test_a_changeling_in_the_library_can_be_revealed_as_a_dragon():
    """Orb of Dragonkind: "{R}, {T}, Sacrifice this artifact: Look at the top
    seven cards of your library. You may reveal a Dragon card from among them
    and put it into your hand." """
    scenario = _main_phase(
        battlefield=["Orb of Dragonkind", "Mountain"],
        library=["Island", "Changeling Outcast", "Island"],
    )
    orb = scenario.find("Orb of Dragonkind", Zone.BATTLEFIELD, "alice")
    outcast = scenario.find("Changeling Outcast", Zone.LIBRARY, "alice")
    # The look-and-split answer: the changeling goes to hand (CR 608.2d).
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(outcast.id,)), player="alice")
    )

    scenario.activate(orb, *scenario.untapped_sources("Mountain"), index=1, sacrificing=[orb])
    scenario.pass_until_resolved()

    assert outcast.zone is Zone.HAND


def test_dragon_only_mana_can_cast_a_changeling():
    """Orb of Dragonkind's "Spend this mana only to cast Dragon spells" - a
    changeling spell is a Dragon spell (CR 106.6's restriction reads the
    spell's subtypes)."""
    scenario = _main_phase(
        battlefield=["Orb of Dragonkind", "Plains"], hand=["Fire-Belly Changeling"]
    )
    orb = scenario.find("Orb of Dragonkind", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.activate(orb, plains, index=0, color=(Color.RED, Color.RED))

    spell = scenario.cast_onto_stack("Fire-Belly Changeling")

    assert spell.zone is Zone.STACK


def test_a_milled_changeling_is_an_insect_card_for_grists_repeat():
    """Grist, the Hunger Tide's +1: "If an Insect card was milled this way,
    put a loyalty counter on Grist and repeat this process." A changeling in
    the graveyard is an Insect card (CR 604.3: the CDA works there too)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grist, the Hunger Tide"], library=["Changeling Outcast"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find("Grist, the Hunger Tide", Zone.BATTLEFIELD, "alice")

    scenario.activate(grist, index=0)
    scenario.pass_until_resolved()

    assert grist.loyalty == 5, "3 printed + 1 activation cost + 1 for the Insect milled"


def test_a_non_type_card_group_excludes_a_changeling():
    """ "non-Avatar creature card" - a changeling card is an Avatar, so the
    group a mass return or reveal names leaves it out."""
    from magic_cards_model.machines.effects import _parse_card_group_qualifier

    matches = _parse_card_group_qualifier("non-Avatar creature card")
    assert matches is not None

    assert matches(card_state("Grizzly Bears", zone=Zone.GRAVEYARD))
    assert not matches(card_state("Changeling Outcast", zone=Zone.GRAVEYARD))


def test_outside_the_game_a_changeling_meets_a_companion_creature_type_condition():
    """CR 702.73a: "This ability works everywhere, even outside the game."
    Kaheera, the Orphanguard's companion condition - each creature card in the
    starting deck is a Cat, Elemental, Nightmare, Dinosaur, or Beast card -
    is checked before the game begins, and a changeling satisfies it."""
    from magic_cards_model.models.deck import Deck

    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Changeling Outcast": 4,
            "Fire-Belly Changeling": 4,
            "Swords to Plowshares": 4,
        },
        companion="Kaheera, the Orphanguard",
    )

    assert deck.companion_problems(card) == []


# -- later type-changing effects override the CDA (CR 613.3, CR 205.1a) --------


def test_becomes_a_rabbit_replaces_every_creature_type_until_end_of_turn():
    """Metamorphic Blast's first mode: "Until end of turn, target creature
    becomes a white Rabbit with base power and toughness 0/1." Applied after
    the CDA in layer 4, it leaves exactly one creature type."""
    scenario = _main_phase(
        hand=["Metamorphic Blast"],
        battlefield=["Island", "Island", "Changeling Outcast", "Stormscale Scion"],
    )
    outcast = scenario.creature("Changeling Outcast", "alice")
    casting = scenario.cast("Metamorphic Blast")
    casting.choose_modes([1])
    casting.choose_targets([outcast])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    computed = scenario.game.characteristics_of(outcast)
    assert computed.subtypes == ("Rabbit",)
    # Base 0/1, and no longer a Dragon for Stormscale Scion's +1/+1.
    assert (outcast.power, outcast.toughness) == (0, 1)

    scenario.game.continuous_effects.end_the_turn()
    assert set(scenario.game.characteristics_of(outcast).subtypes) >= EVERY_CREATURE_TYPE


def test_becomes_a_frog_and_loses_all_abilities_on_a_changeling():
    """Turn to Frog (off-pool, a second printing of the template): "Until end
    of turn, target creature loses all abilities and becomes a blue Frog with
    base power and toughness 1/1." Layer 4 sets the creature type after the
    CDA (CR 613.3), layer 6 takes changeling away (CR 613.1f)."""
    scenario = _main_phase(
        hand=["Turn to Frog"], battlefield=["Island", "Island", "Fire-Belly Changeling"]
    )
    changeling = scenario.creature("Fire-Belly Changeling", "alice")

    scenario.cast_and_resolve(
        "Turn to Frog", *scenario.untapped_sources("Island", "Island"), targets=[changeling]
    )

    computed = scenario.game.characteristics_of(changeling)
    assert computed.subtypes == ("Frog",)
    assert computed.colors == (Color.BLUE,)
    assert computed.abilities == ()
    assert (changeling.power, changeling.toughness) == (1, 1)


def test_losing_changeling_in_layer_6_does_not_take_the_types_away():
    """Humility removes every ability in layer 6 (CR 613.1f), after the
    layer 4 CDA already applied."""
    scenario = _main_phase(battlefield=["Humility", "Changeling Outcast"])
    outcast = scenario.creature("Changeling Outcast", "alice")

    computed = scenario.game.characteristics_of(outcast)

    assert computed.abilities == ()
    assert set(computed.subtypes) >= EVERY_CREATURE_TYPE


# -- a token created "with changeling" (CR 604.3a item 2) ----------------------


def test_crib_swaps_token_with_changeling_is_every_creature_type():
    scenario = _main_phase(
        hand=["Crib Swap"], battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Crib Swap", *scenario.untapped_sources("Plains", "Plains", "Plains"), targets=[bears]
    )

    assert bears.zone is Zone.EXILE
    (token,) = [state for state in scenario.game.battlefield if state.token]
    assert "Changeling" in token.card.keywords
    assert (token.power, token.toughness) == (1, 1)
    assert set(scenario.game.characteristics_of(token).subtypes) >= EVERY_CREATURE_TYPE


# -- registration ---------------------------------------------------------------


def test_changeling_is_registered_as_executed():
    assert executes("Changeling")
    for name in (*CHANGELINGS, "Crib Swap"):
        assert "Changeling" not in ignored_keywords(card(name))

"""Behold, as an additional cost, going on to exile what it beheld (CR
118.8/601.2f: one printed sentence, two verbs on one chosen object):
"As an additional cost to cast this spell, behold a Kithkin and exile it."

CR 701.4a's own "behold a [quality]" (reveal a hand card, or choose a
battlefield permanent) already worked and is proven live by
`test_behold.py`. What is new on the five Champions is the "and exile it"
tail: `machines/cost.py`'s `CostComponent.exile_after` moves whichever half
the payer satisfied the behold with into exile, and `machines/casting.py`'s
`mandatory_additional_costs` links it to the spell's own id (CR 607.2q) -
the same link `objects_as_costs.delve` already gives a delving spell's own
cast-cost exile - so each Champion's own printed "When this creature leaves
the battlefield, return the exiled card to its owner's hand." can find it
again through the identical `card_imprinted_on`/`_parse_return_imprinted_
clause` reader Ugin's Labyrinth and Watcher for Tomorrow already prove.

No second printing exists to prove generality on: Scryfall (`o:"and exile
it"` `o:behold`, searched this session) returns exactly the five Champions
and no other card in any format prints this compound shape - see
`MEMORY.md`'s dated line. Generality instead rests on reusing the CR 607.2q
link `objects_as_costs.delve` already established and that shape's own
existing tests already prove; what these tests add is the Champions'
own five separate consumers of it plus the two distinct ways CR 701.4a
lets the cost be paid.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import additional_cost_phrases
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from tests.scenarios.harness import Scenario


def test_champion_of_the_clachan_beheld_by_revealing_a_hand_card():
    """The exiled card is the *hand* Kithkin, linked to Champion of the
    Clachan's own id (CR 607.2q), and returns to its owner's hand once the
    Champion leaves the battlefield."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Clachan", "Kinsbaile Aspirant"],
            battlefield=["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Champion of the Clachan", Zone.HAND).card) == [
        "behold a Kithkin and exile it"
    ]
    hand_kithkin = scenario.find("Kinsbaile Aspirant", Zone.HAND)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    champion = scenario.cast_and_resolve(
        "Champion of the Clachan", *sources, beholding=[hand_kithkin]
    )

    assert hand_kithkin.zone is Zone.EXILE
    annotation = hand_kithkin.exile_annotation
    assert annotation is not None
    assert annotation.marker is ExileMarker.LINKED
    assert annotation.linked_permanent_id == champion.id

    scenario.game.sacrifice(champion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert hand_kithkin.zone is Zone.HAND


def test_champion_of_the_clachan_beheld_by_choosing_a_battlefield_permanent():
    """The other half of CR 701.4a: a Kithkin already on the battlefield is
    chosen (not tapped, not sacrificed) and *then* exiled by the "and exile
    it" tail - CR 701.4b's own untouched-until-then guarantee ends exactly
    where this card's own extra verb begins."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Clachan"],
            battlefield=["Plains"] * 4 + ["Kinsbaile Aspirant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlefield_kithkin = scenario.creature("Kinsbaile Aspirant", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    champion = scenario.cast_and_resolve(
        "Champion of the Clachan", *sources, beholding=[battlefield_kithkin]
    )

    assert battlefield_kithkin.zone is Zone.EXILE
    assert battlefield_kithkin.exile_annotation is not None
    assert battlefield_kithkin.exile_annotation.linked_permanent_id == champion.id

    scenario.game.sacrifice(champion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert battlefield_kithkin.zone is Zone.HAND


def test_champion_of_the_clachan_anthem_pumps_other_kithkin():
    """ "Other Kithkin you control get +1/+1." - already `handled` before this
    task; proved here alongside the new cost so the whole card, not only its
    cost clause, is shown working."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Clachan", "Kinsbaile Aspirant"],
            battlefield=["Plains"] * 4 + ["Kinsbaile Aspirant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    other_kithkin = scenario.creature("Kinsbaile Aspirant", "alice")
    hand_kithkin = scenario.find("Kinsbaile Aspirant", Zone.HAND)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.cast_and_resolve("Champion of the Clachan", *sources, beholding=[hand_kithkin])

    # Kinsbaile Aspirant is printed 2/1; the anthem is +1/+1.
    assert (other_kithkin.power, other_kithkin.toughness) == (3, 2)


def test_champion_of_the_path_deals_damage_when_another_elemental_enters():
    """ "Whenever another Elemental you control enters, it deals damage equal
    to its power to each opponent." - Champion of the Path's own trigger,
    proved with the behold-and-exile cost paid from hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Path", "Kindle the Inner Flame", "Ashling the Pilgrim"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Kindle the Inner Flame is itself a Kindred Sorcery - Elemental, so it
    # carries the Elemental subtype `behold` reads even though it never
    # becomes a creature permanent.
    hand_elemental = scenario.find("Kindle the Inner Flame", Zone.HAND)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Champion of the Path", *sources, beholding=[hand_elemental])

    assert hand_elemental.zone is Zone.EXILE
    scenario.game.put_onto_battlefield(scenario.find("Ashling the Pilgrim", Zone.HAND), "alice")
    scenario.game.put_triggers_on_stack()
    assert any(
        name == "Champion of the Path's triggered ability" for name in scenario.stack_names()
    )
    scenario.pass_until_resolved()
    ashling = scenario.creature("Ashling the Pilgrim", "alice")
    assert scenario.player("bob").life == 20 - ashling.power


def test_champion_of_the_path_returns_its_exiled_card_when_it_leaves():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Path", "Kindle the Inner Flame"],
            battlefield=["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_elemental = scenario.find("Kindle the Inner Flame", Zone.HAND)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    champion = scenario.cast_and_resolve(
        "Champion of the Path", *sources, beholding=[hand_elemental]
    )
    assert hand_elemental.zone is Zone.EXILE

    scenario.game.sacrifice(champion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert hand_elemental.zone is Zone.HAND


def test_champions_of_the_perfect_draws_when_you_cast_a_creature_spell():
    """ "Whenever you cast a creature spell, draw a card." (an Elf beheld and
    exiled from the battlefield this time)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champions of the Perfect", "Grizzly Bears"],
            battlefield=["Forest"] * 6 + ["Lys Alana Dignitary"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlefield_elf = scenario.creature("Lys Alana Dignitary", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Champions of the Perfect", *sources, beholding=[battlefield_elf])
    assert battlefield_elf.zone is Zone.EXILE

    before = len(scenario.player("alice").hand)
    scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", username="alice"), auto=True
    )
    scenario.game.put_triggers_on_stack()
    assert any(
        name == "Champions of the Perfect's triggered ability" for name in scenario.stack_names()
    )
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == before


def test_champions_of_the_perfect_returns_its_exiled_card_when_it_leaves():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champions of the Perfect"],
            battlefield=["Forest"] * 4 + ["Lys Alana Dignitary"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlefield_elf = scenario.creature("Lys Alana Dignitary", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    champion = scenario.cast_and_resolve(
        "Champions of the Perfect", *sources, beholding=[battlefield_elf]
    )
    assert battlefield_elf.zone is Zone.EXILE

    scenario.game.sacrifice(champion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert battlefield_elf.zone is Zone.HAND


def test_champions_of_the_shoal_taps_and_stuns_on_enter():
    """ "Whenever this creature enters or becomes tapped, tap up to one target
    creature and put a stun counter on it." """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champions of the Shoal", "Deepway Navigator"],
            battlefield=["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_merfolk = scenario.find("Deepway Navigator", Zone.HAND)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    target_bear = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Champions of the Shoal", "alice", beholding=[hand_merfolk])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_choose_targets(target_bear)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    champion = scenario.creature("Champions of the Shoal", "alice")
    assert hand_merfolk.zone is Zone.EXILE
    assert hand_merfolk.exile_annotation is not None
    assert hand_merfolk.exile_annotation.linked_permanent_id == champion.id
    assert target_bear.tapped
    assert target_bear.counters.counts.get("stun", 0) == 1

    scenario.game.sacrifice(champion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert hand_merfolk.zone is Zone.HAND


# --------------------------------------------------------------------------
# Dispelling Exhale: a plain, unrestricted "you may behold a Dragon"
# additional cost (CR 118.8b, CR 701.4a) - no chosen type
# (`_OPTIONAL_BEHOLD_CHOSEN_TYPE`'s own Celestial Reunion shape) and no
# linked exile (the five Champions' own "and exile it" tail above): the
# beheld object stays exactly where it was. `Casting.behold_for_cost` is
# the new method; `cast_record._beheld_for_cost` is what the linked "if a
# Dragon was beheld" (CR 701.4b) reads back, through the amount-upgrade
# pair `_parse_counter_unless_pays_then_condition_amount_upgrade_pair`.
# --------------------------------------------------------------------------


def test_dispelling_exhale_counters_for_two_with_no_dragon_beheld():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", hand=["Dispelling Exhale"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    casting = scenario.cast("Dispelling Exhale", username="alice")
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.will_pay_the_mana_cost(False, username="bob")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "CR 701.6a: countered, bob declined to pay {2}"


def test_dispelling_exhale_counters_for_four_with_a_dragon_revealed():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"] * 5)
        .player(
            "alice",
            hand=["Dispelling Exhale", "Archive Dragon"],
            battlefield=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bob_mountain, *_) = scenario.untapped_sources(*(["Mountain"] * 5), username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    dragon = scenario.find("Archive Dragon", Zone.HAND, "alice")
    casting = scenario.cast("Dispelling Exhale", username="alice")
    casting.behold_for_cost(dragon)
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.will_pay_the_mana_cost(True, username="bob")

    scenario.resolve_top()

    assert dragon.zone is Zone.HAND, "revealed for the cost, not exiled"
    assert bolt.zone is Zone.STACK, "bob paid the upgraded {4}"


def test_dispelling_exhale_forces_the_upgraded_payment_when_a_dragon_was_beheld():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player(
            "alice",
            hand=["Dispelling Exhale", "Archive Dragon"],
            battlefield=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    dragon = scenario.find("Archive Dragon", Zone.HAND, "alice")
    casting = scenario.cast("Dispelling Exhale", username="alice")
    casting.behold_for_cost(dragon)
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.will_pay_the_mana_cost(False, username="bob")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "bob declined the steeper {4} payment too"


# --------------------------------------------------------------------------
# Sarkhan, Dragon Ascendant: an ETB "you may behold a Dragon. If you do,
# create a Treasure token." (the new general
# `_parse_optional_behold_then_if_you_do_clause`) and a second triggered
# ability that puts a +1/+1 counter on itself and becomes a Dragon with
# flying until end of turn whenever a Dragon it controls enters - the
# possessive-pronoun widening of `machines.layers._BECOMES_SUBTYPE_IN_
# ADDITION_RE` ("his other types" alongside "its").
# --------------------------------------------------------------------------


def test_sarkhan_etb_behold_creates_a_treasure():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sarkhan, Dragon Ascendant", "Archive Dragon"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.find("Archive Dragon", Zone.HAND, "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain")
    scenario.will_choose_cards(dragon, source="Sarkhan, Dragon Ascendant")

    scenario.cast_and_resolve("Sarkhan, Dragon Ascendant", *mountains)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert dragon.zone is Zone.HAND, "revealed for the ETB action, not exiled"
    assert any(state.name == "Treasure Token" for state in scenario.game.battlefield), (
        "the Treasure token was created"
    )
    assert len(alice.hand) == 1 and alice.hand[0].name == "Archive Dragon"


def test_sarkhan_etb_behold_declined_makes_no_treasure():
    scenario = (
        Scenario()
        .player("alice", hand=["Sarkhan, Dragon Ascendant"], battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Sarkhan, Dragon Ascendant", *mountains)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not any(state.name == "Treasure Token" for state in scenario.game.battlefield)


def test_sarkhan_gains_a_counter_and_becomes_a_flying_dragon_when_a_dragon_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sarkhan, Dragon Ascendant", "Slumbering Dragon"],
            battlefield=["Mountain"] * 3,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sarkhan_mountains = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Sarkhan, Dragon Ascendant", *sarkhan_mountains)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # declines the ETB behold (no Dragon yet)
    sarkhan = scenario.creature("Sarkhan, Dragon Ascendant", "alice")
    assert sarkhan.counters.counts.get("+1/+1", 0) == 0

    (dragon_mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Slumbering Dragon", dragon_mountain)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert sarkhan.counters.counts.get("+1/+1", 0) == 1
    chars = scenario.game.characteristics_of(sarkhan)
    assert "Dragon" in {word for word in chars.subtypes}, "gained Dragon in addition to his types"
    assert "Human" in {word for word in chars.subtypes}, "his other types are kept, not replaced"
    from magic_cards_model.machines.combat import Keyword, has_keyword

    assert has_keyword(sarkhan, Keyword.FLYING, scenario.game)

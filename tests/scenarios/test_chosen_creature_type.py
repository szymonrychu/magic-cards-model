"""CR 205.3m creature types chosen at runtime (CR 614.12a's "as [this]
enters, choose a creature type" and its own consumers), plus a fresh choice
made mid-game rather than on entry.

`machines/chosen_type.py` is the new module this task adds. What already
existed before this task, reused rather than duplicated:

- CR 614.12a's own choice storage (`CardState.choice`, `ChoiceKind.
  CREATURE_TYPE`) and its bare "choose a creature type" reader
  (`machines/replacement.py`'s `_CHOOSE_A_CREATURE_TYPE_RE`).
- The chosen-type anthem (`machines/layers.py`'s `_chosen_type_anthem_
  builder`), widened here only to add a trailing "and have `<keywords>`"
  tail (Chronicle of Victory's "... and have first strike and trample.",
  Oko's own emblem text).

What this task adds:

- The **restricted** enumerated choice - "choose Elemental, Elf, Faerie,
  Giant, Goblin, Kithkin, Merfolk, or Treefolk" (Dawn-Blessed Pennant,
  Eclipsed Realms) - `chosen_type.RESTRICTED_TRIBAL_TYPES` narrows the
  offered `Decision.options` and refuses any other answer. No second real
  printing exists for this exact eight-item list (Scryfall's own oracle
  search, this session, returns only these two) - see `MEMORY.md`.
- `CostModifierKind.CHOSEN_TYPE_DECREASE` (Gathering Stone's "Spells you
  cast of the chosen type cost `{1}` less to cast"), proven again on Urza's
  Incubator's differently-worded "Creature spells of the chosen type cost
  `{2}` less to cast" (no "you cast", "Creature" qualifier) - a genuine
  second Modern-legal printing, found by `card_search` this session.
- Gathering Stone's own combined "enters and at the beginning of your
  upkeep" trigger condition (`machines/triggers._expand_enters_and_upkeep`)
  and its look-reveal-or-graveyard effect (`chosen_type.parse_gathering_
  stone_look_clause`).
- Selfless Safewright's fresh, non-CR-614.12a choice made as a *triggered*
  ability resolves, granting other permanents of that type a temporary
  keyword (`chosen_type.parse_choose_type_hexproof_indestructible_clause`,
  `machines/layers.PermanentsControlledByWithSubtype` - a brand new
  selector, since every existing chosen-type/subtype selector in the pool
  was creature-only).
- Oko, Lorwyn Liege's own "-6: Choose a creature type. You get an emblem
  with '...'" (`chosen_type.parse_choose_creature_type_then_emblem_clause`)
  - a fresh choice recorded on the emblem itself, read back by the same
  widened anthem builder above.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario

# -- the restricted enumerated choice (Dawn-Blessed Pennant, Eclipsed Realms) --


def test_dawn_blessed_pennant_chooses_from_the_restricted_list():
    """ "As this artifact enters, choose Elemental, Elf, Faerie, Giant,
    Goblin, Kithkin, Merfolk, or Treefolk." Then: "Whenever a permanent you
    control of the chosen type enters, you gain 1 life." """
    scenario = (
        Scenario()
        .player("alice", hand=["Dawn-Blessed Pennant", "Eclipsed Boggart"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Dawn-Blessed Pennant")
    (plains,) = scenario.untapped_sources("Plains")
    pennant = scenario.cast_and_resolve("Dawn-Blessed Pennant", plains)
    assert pennant.choice is not None and pennant.choice.value == "Goblin"

    before = scenario.player("alice").life
    scenario.game.put_onto_battlefield(scenario.find("Eclipsed Boggart", Zone.HAND), "alice")
    scenario.game.put_triggers_on_stack()
    assert any(
        name == "Dawn-Blessed Pennant's triggered ability" for name in scenario.stack_names()
    )
    while scenario.stack_names():
        scenario.pass_until_resolved()
    assert scenario.player("alice").life == before + 1


def test_dawn_blessed_pennant_refuses_a_type_outside_the_restricted_list():
    """ "Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or
    Treefolk" is a closed list (CR 614.12a's own choice, narrowed by the
    printed sentence) - "Human" is a real creature type (CR 205.3m) and is
    still not a legal answer to *this* card's own question."""
    scenario = (
        Scenario().player("alice", hand=["Dawn-Blessed Pennant"], battlefield=["Plains"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Human", source="Dawn-Blessed Pennant")
    (plains,) = scenario.untapped_sources("Plains")
    raised = False
    try:
        scenario.cast_and_resolve("Dawn-Blessed Pennant", plains)
    except ValueError:
        raised = True
    assert raised


def test_dawn_blessed_pennant_returns_a_card_of_the_chosen_type():
    """{2}, {T}, Sacrifice this artifact: Return target card of the chosen
    type from your graveyard to your hand." (already `handled` before this
    task; proved here alongside the new choice)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dawn-Blessed Pennant"],
            battlefield=["Mountain"] * 3,
            graveyard=["Eclipsed Boggart"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Dawn-Blessed Pennant")
    (first_mountain,) = scenario.untapped_sources("Mountain")
    pennant = scenario.cast_and_resolve("Dawn-Blessed Pennant", first_mountain)

    scenario.activate(
        pennant,
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[scenario.find("Eclipsed Boggart", Zone.GRAVEYARD)],
    )
    scenario.pass_until_resolved()
    assert scenario.find("Eclipsed Boggart", Zone.HAND) is not None


def test_eclipsed_realms_taps_for_a_restricted_mana_spent_only_on_the_chosen_type():
    """ "As this land enters, choose Elemental, Elf, Faerie, Giant, Goblin,
    Kithkin, Merfolk, or Treefolk." + "{T}: Add one mana of any color. Spend
    this mana only to cast a spell of the chosen type or activate an ability
    of a source of the chosen type." (CR 106.6's own spend restriction).
    `Boggart Brute` is a Goblin (the chosen type): the restricted mana is
    legal to spend on it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eclipsed Realms", "Boggart Brute"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Eclipsed Realms")
    scenario.play_land("Eclipsed Realms")
    realms = scenario.find("Eclipsed Realms", Zone.BATTLEFIELD)
    assert realms.choice is not None and realms.choice.value == "Goblin"

    scenario.cast_and_resolve("Boggart Brute", auto=True)
    assert scenario.find("Boggart Brute", Zone.BATTLEFIELD) is not None


def test_eclipsed_realms_restricted_mana_cannot_pay_for_an_unrelated_spell():
    """The chosen type is Elf; `Grizzly Bears` is neither an Elf spell nor an
    ability of an Elf source, so the land's own restricted mana cannot pay
    for it (CR 106.6) - only its unrestricted `{T}: Add {C}.` can, and that
    alone is not enough colour to cast a `{1}{G}` spell."""
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Eclipsed Realms", "Eclipsed Realms"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for realms in scenario.game.permanents_controlled_by("alice"):
        realms.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")

    sources = scenario.untapped_sources("Eclipsed Realms", "Eclipsed Realms")
    casting = scenario.cast("Grizzly Bears", "alice")
    payment = casting.begin_paying()
    refused = False
    try:
        scenario.pay_with(payment, *sources)
    except ValueError:
        refused = True
    assert refused, "the chosen-type restriction should refuse a Bears cast"


# -- an open "choose a creature type" and its consumers (Chronicle of Victory) --


def test_chronicle_of_victory_pumps_and_draws_for_the_chosen_type():
    """ "Creatures you control of the chosen type get +2/+2 and have first
    strike and trample." (the anthem builder, widened this task for a
    keyword tail) and "Whenever you cast a spell of the chosen type, draw a
    card." (already `handled`)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chronicle of Victory", "Eclipsed Boggart"],
            battlefield=["Mountain"] * 9,
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Chronicle of Victory")
    sources = scenario.untapped_sources(*["Mountain"] * 6)
    scenario.cast_and_resolve("Chronicle of Victory", *sources)

    scenario.cast_onto_stack(
        "Eclipsed Boggart", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
    boggart = scenario.creature("Eclipsed Boggart", "alice")
    # Eclipsed Boggart is a 2/3 Goblin; Chronicle's anthem is +2/+2.
    computed = scenario.game.characteristics_of(boggart)
    assert (computed.power, computed.toughness) == (4, 5)
    assert has_keyword(boggart, "First Strike", scenario.game)
    assert has_keyword(boggart, "Trample", scenario.game)


def test_urza_s_incubator_discounts_creature_spells_of_the_chosen_type_for_any_player():
    """Proof printing for `CostModifierKind.CHOSEN_TYPE_DECREASE`'s own
    generality: Urza's Incubator's "Creature spells of the chosen type cost
    `{2}` less to cast" has neither Gathering Stone's "you cast" (so it
    discounts *any* player's matching spell) nor its unqualified "spells"
    (so a noncreature spell of the chosen type is not discounted)."""
    scenario = (
        Scenario()
        .player("bob", hand=["Boggart Brute"], battlefield=["Mountain"] * 4)
        .player("alice", battlefield=["Urza's Incubator"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    incubator = scenario.find("Urza's Incubator", Zone.BATTLEFIELD)
    incubator.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Goblin")
    casting = scenario.cast("Boggart Brute", "bob")
    # Boggart Brute's own mana value is 3 ({2}{R}); Urza's Incubator
    # discounts its {2} generic component for bob too, since its own
    # sentence names no caster at all.
    assert casting.total_cost.mana.converted == 1


def test_gathering_stone_discounts_only_its_own_controllers_spells():
    """The mirror check: Gathering Stone's own "you cast" does *not* apply
    to another player's spell, unlike Urza's Incubator above."""
    scenario = (
        Scenario()
        .player("bob", hand=["Boggart Brute"], battlefield=["Mountain"] * 4)
        .player("alice", battlefield=["Gathering Stone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Gathering Stone", Zone.BATTLEFIELD)
    stone.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Goblin")
    casting = scenario.cast("Boggart Brute", "bob")
    # Alice's Gathering Stone says "you cast": no discount for bob's own
    # cast, unlike Urza's Incubator above.
    assert casting.total_cost.mana.converted == 3


def test_gathering_stone_look_reveal_hand_or_graveyard_on_enter_and_upkeep():
    """ "When this artifact enters and at the beginning of your upkeep, look
    at the top card of your library. If it's a card of the chosen type, you
    may reveal it and put it into your hand. If you don't put the card into
    your hand, you may put it into your graveyard." - the enters half,
    matching."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gathering Stone"],
            battlefield=["Mountain"] * 4,
            library=["Eclipsed Boggart"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Gathering Stone")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    stone = scenario.cast_and_resolve("Gathering Stone", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True)
    scenario.pass_until_resolved()
    assert scenario.find("Eclipsed Boggart", Zone.HAND) is not None
    assert stone.choice is not None


def test_gathering_stone_may_bin_a_non_matching_top_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gathering Stone"],
            battlefield=["Mountain"] * 4,
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Goblin", source="Gathering Stone")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Gathering Stone", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True)
    scenario.pass_until_resolved()
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD) is not None


# -- a fresh choice at resolution, not CR 614.12a (Selfless Safewright) --------


def test_selfless_safewright_grants_other_permanents_of_the_chosen_type():
    """ "When this creature enters, choose a creature type. Other permanents
    you control of that type gain hexproof and indestructible until end of
    turn." - not itself, and not a permanent of a different type."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Selfless Safewright"],
            battlefield=["Forest"] * 5 + ["Lys Alana Dignitary", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    other_elf = scenario.creature("Lys Alana Dignitary", "alice")
    other_bear = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")

    safewright = scenario.cast_and_resolve("Selfless Safewright", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose("Elf")
    scenario.pass_until_resolved()

    assert has_keyword(other_elf, "Hexproof", scenario.game)
    assert has_keyword(other_elf, "Indestructible", scenario.game)
    assert not has_keyword(other_bear, "Hexproof", scenario.game)
    assert not has_keyword(safewright, "Hexproof", scenario.game), "not itself - 'other'"

    scenario.game.cleanup_step()
    assert not has_keyword(other_elf, "Hexproof", scenario.game), "until end of turn"


# -- a fresh choice on a loyalty ability, minted onto an emblem (Oko) ---------


def test_oko_minus_six_makes_an_emblem_for_a_freshly_chosen_type():
    """ "-6: Choose a creature type. You get an emblem with 'Creatures you
    control of the chosen type get +3/+3 and have vigilance and
    hexproof.'" - the same widened anthem builder Chronicle of Victory
    proves, read off a command-zone emblem (CR 114.4) instead of a
    permanent's own static line."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Oko, Lorwyn Liege", "Lys Alana Dignitary"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    oko = scenario.find("Oko, Lorwyn Liege", Zone.BATTLEFIELD)
    oko.counters.set("loyalty", 12)
    oko.transform()

    scenario.will_choose("Elf")
    scenario.activate(oko, index=2)
    scenario.pass_until_resolved()

    emblems = scenario.game.emblems_of("alice")
    assert len(emblems) == 1
    assert emblems[0].choice is not None and emblems[0].choice.value == "Elf"

    # Lys Alana Dignitary is printed 2/3; the emblem's own anthem is +3/+3.
    dignitary = scenario.creature("Lys Alana Dignitary", "alice")
    computed = scenario.game.characteristics_of(dignitary)
    assert (computed.power, computed.toughness) == (5, 6)
    assert has_keyword(dignitary, "Vigilance", scenario.game)
    assert has_keyword(dignitary, "Hexproof", scenario.game)

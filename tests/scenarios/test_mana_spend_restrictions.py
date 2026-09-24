"""CR 106.6: mana produced with a restriction on how it may be spent.

"Some spells or abilities that produce mana restrict how that mana can be
spent, have an additional effect that affects the spell or ability that mana is
spent on, or create a delayed triggered ability..." - CR 106.6, looked up this
session. Only the first of the three is modelled; the "additional effect" half
(Cavern of Souls's and Delighted Halfling's "and that spell can't be countered")
is still not.

Fifteen printings in the pool carry one, and between them they cover both
purposes a restriction can name and every shape of clause the grammar reads:

  Shang-Chi, Master of Kung Fu  "... only to activate abilities of creature
                                 sources."
  Sunken Citadel                "... only to activate abilities of land
                                 sources."
  Eldrazi Temple                "... only to cast colorless Eldrazi spells or
                                 activate abilities of colorless Eldrazi."
  Cavern of Souls               "... only to cast a creature spell of the
                                 chosen type, ..."
  Delighted Halfling            "... only to cast a legendary spell, ..."
  Tablet of Discovery           "... only to cast instant and sorcery spells."
  Fíli and Kíli, Joyous         "... only to cast Dwarf, Equipment, and Saga
                                 spells."
  Interdimensional Web Watch    "... only to cast spells from exile."
  Smokebraider                  "... only to cast Elemental spells or
                                 activate abilities of Elementals."
  Orb of Dragonkind             "... only to cast Dragon spells or activate
                                 abilities of Dragons."
  Woodland Weavemaster          "... only to cast Elf spells and activate
                                 abilities of Elf sources."
  Codsworth, Handy Helper       "... only to cast Aura and/or Equipment
                                 spells."
  Séance Board                  "... only to cast instant, sorcery, Demon,
                                 and Spirit spells."
  Rivaz of the Claw             "... only to cast Dragon creature spells."
  Chandra, Chill of Compliance  "... only to cast a noncreature spell." -
                                 CR 109.2's negation of a printed card type
                                 (`SpendClause.excluded_types`), a loyalty
                                 ability's own resolution-time "Add", never a
                                 `{T}: Add` mana ability at all (CR 605.1a
                                 excludes loyalty abilities by name).

Tablet of Discovery, Fíli and Kíli and the Web Watch are the first clause
shapes beyond a single quality word; Smokebraider prints Eldrazi Temple's
shape on a different creature type, and Orb of Dragonkind prints
Smokebraider's on a different one again.

A **joined list of qualities** is one clause offering each of them as an
alternative, not several clauses and not a conjunction - CR 205.2b, looked up
this session, makes an object "satisfy the criteria for any effect that
applies to any of their card types", and no spell is ever both an instant and
a sorcery. **Juxtaposition** is the other reading of the same grammar: "Dragon
creature spells" describes one object that is both, so both are required. The
joining word is the only thing that tells them apart, which is why "and", "or"
and "and/or" all count as one, and why all three also split two whole clauses
where a phrase cannot be read as one.

A **printed plural** ("abilities of Elementals", "of Dragons") names the
subtype a type line prints in the singular, and is read back to it against the
whole of CR 205.3's list (`magic_cards_model/data/subtypes.py`) rather than by
guessing at English morphology.

A **zone tail** narrows the clause to one of CR 400.1's seven zones, checked
against the zone the cast started in (CR 601.2a moves the card to the stack
before any cost is paid, so that zone is carried, never read back off the
spell).

Fíli and Kíli, Joyous was added to the pool for this file: it is the second
and-joined list in print and shares none of Tablet of Discovery's wording - a
three-item list of subtypes with an Oxford comma, on a creature rather than an
artifact - so it is what proves the parser reads the mechanic and not the one
sentence it was built against.

Smokebraider was added for the same reason on the other side of the printing:
it is the second card in print with "Add two mana in any combination of colors",
the mana ability the Web Watch needed read before its restriction could be
tested at all, and it carries a restriction sentence that shares nothing with
the Web Watch's zone tail. Two printings, no shared wording - the parser reads
the template, not the card.

The restriction lives on the mana in the pool, not on its source: the mana
ability has already resolved (CR 605.3b) by the time the mana is spent, so the
source can leave the battlefield without taking the restriction with it. It
dies when the mana does, at the step and phase boundary CR 703.4q and CR 500.5
name.

The point of the file is the **refusals**. Mana that is produced and then pays
for anything is indistinguishable from no restriction at all, which is what
this engine did before.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.cost import spend_restriction
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.mana import ManaSpend, SpendPurpose
from tests.cards import card, card_state, pool
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _ready(scenario, name: str):
    """A permanent of `name`, past summoning sickness so its `{T}` works.

    CR 302.6 is tested in `test_summoning_sickness.py`; every board here starts
    the creature already settled so the file is about CR 106.6 and nothing else.
    """
    permanent = scenario.find(name, Zone.BATTLEFIELD)
    permanent.summoning_sick = False
    return permanent


def _float_shang_chi(scenario, color: Color = Color.GREEN):
    """Tap Shang-Chi for two restricted mana of one colour, straight into the
    player's pool (CR 605.3b: a mana ability never uses the stack)."""
    shang_chi = _ready(scenario, "Shang-Chi, Master of Kung Fu")
    scenario.game.activate_ability(shang_chi, 0, "alice", color=color)
    return shang_chi


def _restrictions(scenario, username: str = "alice") -> list[str]:
    return [entry.restriction.text for entry in scenario.player(username).mana_pool.restricted]


# --------------------------------------------------------------------------
# The happy path, and the four ways it is not the happy path
# --------------------------------------------------------------------------


def test_shang_chis_mana_pays_an_activated_ability_of_a_creature():
    """The legal direction: "abilities of creature sources" is a question about
    the **source** of the ability, and Basking Rootwalla is a creature already
    on the battlefield, so its `{1}{G}` activation is exactly what this mana is
    for."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)
    assert scenario.player().mana_pool.floating == {Color.GREEN: 2}

    rootwalla = _ready(scenario, "Basking Rootwalla")
    scenario.activate(rootwalla, index=0)
    assert scenario.player().mana_pool.is_empty
    scenario.resolve_top()

    assert scenario.game.characteristics_of(rootwalla).power == 3


def test_shang_chis_mana_cannot_pay_for_a_creature_spell():
    """The other direction of the same source-not-spell distinction, and the
    one a reviewer reaches for first: a *creature spell* is not an ability of a
    creature source, so two green mana that would obviously pay `{G}` refuse
    to."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Shang-Chi, Master of Kung Fu"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)

    casting = scenario.cast("Llanowar Elves", "alice")
    payment = casting.begin_paying()

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to activate abilities"):
        payment.pay()

    # CR 733.1: nothing was spent, so the mana is still there, still restricted.
    assert scenario.player().mana_pool.floating == {Color.GREEN: 2}
    # CR 601.2a moved the Elves to the stack as the cast was proposed; CR 601.6
    # is what puts it back once the cast turns out to be illegal.
    casting.cancel()
    assert scenario.find("Llanowar Elves", Zone.HAND).zone is Zone.HAND


def test_shang_chis_mana_cannot_pay_a_noncreature_sources_ability():
    """Right purpose, wrong source: Icy Manipulator's `{1}, {T}:` is an
    activated ability, and `{1}` is generic mana that green pays - but the
    source is an Artifact, not a creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shang-Chi, Master of Kung Fu", "Icy Manipulator", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)

    manipulator = _ready(scenario, "Icy Manipulator")
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    payment = scenario.game.begin_activating(manipulator, 0, "alice")

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to activate abilities"):
        payment.pay()
    assert forest.untapped is True


def test_the_restriction_is_carried_by_the_mana_not_by_its_source():
    """CR 605.3b resolves a mana ability immediately, so by the time the mana is
    spent the source has nothing more to do with it. Shang-Chi is sacrificed
    with the mana still floating and the restriction is unmoved - both halves:
    it still refuses the spell, and it still pays the creature's ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves"],
            battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shang_chi = _float_shang_chi(scenario)
    scenario.game.sacrifice(shang_chi)
    assert shang_chi.zone is Zone.GRAVEYARD

    assert _restrictions(scenario) == [
        "Spend this mana only to activate abilities of creature sources."
    ]
    with pytest.raises(ValueError, match="Spend this mana only"):
        scenario.cast("Llanowar Elves", "alice").begin_paying().pay()

    rootwalla = _ready(scenario, "Basking Rootwalla")
    scenario.activate(rootwalla, index=0)
    assert scenario.player().mana_pool.is_empty


def test_the_restriction_is_lost_with_the_mana_at_a_step_boundary():
    """CR 703.4q and CR 500.5: "as each step or phase ends, any unspent mana
    left in a player's mana pool empties". There is no separate lifetime for
    the tag - it was on the mana, and the mana is gone."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shang-Chi, Master of Kung Fu", "Basking Rootwalla"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)
    assert _restrictions(scenario) != []

    scenario.advance()

    pool = scenario.player().mana_pool
    assert pool.is_empty
    assert pool.restricted == []


# --------------------------------------------------------------------------
# Which mana pays when more than one could
# --------------------------------------------------------------------------


def test_a_mixed_pool_spends_the_restricted_mana_before_the_free_mana():
    """The trap on the other side of the refusal. Both the Forest's green and
    Shang-Chi's green legally pay Basking Rootwalla's `{1}{G}`; spending the
    Forest's first would strand a restricted mana that could have paid, and
    the next play would be refused for no reason the rules give.

    CR 118.3a leaves *which* mana pays to the payer, so preferring the mana
    that can do less is a legal choice - and the only one that does not throw
    a legal play away.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Shang-Chi, Master of Kung Fu",
                "Basking Rootwalla",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)
    for forest in scenario.untapped_sources("Forest", "Forest"):
        scenario.game.activate_ability(forest, 0, "alice")
    assert scenario.player().mana_pool.floating == {Color.GREEN: 4}

    rootwalla = _ready(scenario, "Basking Rootwalla")
    scenario.activate(rootwalla, index=0)

    pool = scenario.player().mana_pool
    assert pool.floating == {Color.GREEN: 2}
    # The two that survived are the unrestricted ones.
    assert pool.restricted_total == 0


def test_two_restrictions_in_one_pool_are_kept_apart():
    """Shang-Chi's mana and Delighted Halfling's sit in the same pool and are
    not interchangeable: only the Halfling's pays for Ragavan, a legendary
    spell, and it does so while the Shang-Chi mana is refused for it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ragavan, Nimble Pilferer"],
            battlefield=["Shang-Chi, Master of Kung Fu", "Delighted Halfling"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)
    halfling = _ready(scenario, "Delighted Halfling")
    scenario.game.activate_ability(halfling, 1, "alice", color=Color.RED)

    pool = scenario.player().mana_pool
    assert pool.floating == {Color.GREEN: 2, Color.RED: 1}
    assert sorted(_restrictions(scenario)) == [
        "Spend this mana only to activate abilities of creature sources.",
        "Spend this mana only to cast a legendary spell, and that spell can't be countered.",
    ]

    ragavan = scenario.cast_and_resolve("Ragavan, Nimble Pilferer")

    assert ragavan.zone is Zone.BATTLEFIELD
    # The Halfling's red paid; Shang-Chi's green was never eligible and is
    # still floating, still restricted.
    assert pool.floating == {Color.GREEN: 2}
    assert _restrictions(scenario) == [
        "Spend this mana only to activate abilities of creature sources."
    ]


def test_restricted_mana_does_not_pay_a_cost_that_cannot_say_what_it_is_for():
    """A payment opened with no `spend` cannot show the restriction was
    honoured, so it gets none of the restricted mana. Refusing is the
    fail-closed direction; permitting would make every unwired cost a hole in
    the restriction."""
    scenario = Scenario().player("alice", battlefield=["Shang-Chi, Master of Kung Fu"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_shang_chi(scenario)

    pool = scenario.player().mana_pool
    assert pool.can_pay(_cost("{G}"), spend=None) is False
    assert (
        pool.can_pay(
            _cost("{G}"),
            spend=ManaSpend.activating(card("Basking Rootwalla")),
        )
        is True
    )


def _cost(text: str):
    from magic_cards_model.models.mana import ManaCost

    return ManaCost.parse(text)


# --------------------------------------------------------------------------
# The other three printings
# --------------------------------------------------------------------------


def test_eldrazi_temples_restricted_mana_casts_a_colorless_eldrazi():
    """Eldrazi Temple's `{T}: Add {C}{C}.` is worth having only if it can be
    spent; four of them cast Sire of Seven Deaths, a `{7}` colorless Eldrazi.
    `auto_tap` reaches for the restricted ability here because the restriction
    permits this cast - before this wave it was excluded outright and the cast
    was impossible."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sire of Seven Deaths"],
            battlefield=["Eldrazi Temple"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sire = scenario.cast_onto_stack("Sire of Seven Deaths", username="alice", auto=True)

    assert sire.zone is Zone.STACK
    assert len(scenario.untapped_sources()) == 0


def test_eldrazi_temples_restricted_mana_cannot_cast_a_colorless_non_eldrazi():
    """Colorless is not enough: Mind Stone is a colorless artifact and not an
    Eldrazi, so the `{C}{C}` ability is off the table and only the plain
    `{T}: Add {C}.` remains - one mana against a `{2}` cost."""
    scenario = (
        Scenario().player("alice", hand=["Mind Stone"], battlefield=["Eldrazi Temple"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (temple,) = scenario.untapped_sources("Eldrazi Temple")
    payment = scenario.cast("Mind Stone", "alice").begin_paying()

    with pytest.raises(ValueError, match="no combination of the available mana sources"):
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))

    assert temple.tapped is False


def test_cavern_of_souls_restricted_mana_needs_the_chosen_type():
    """Cavern of Souls's restriction reads "of the chosen type", so it is not
    checkable at all until CR 614.12a's answer is on the permanent. With Elf
    chosen it casts Llanowar Elves; that is the whole point of the land."""
    scenario = (
        Scenario().player("alice", hand=["Cavern of Souls", "Llanowar Elves"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Elf", source="Cavern of Souls")
    cavern = scenario.play_land("Cavern of Souls")

    scenario.game.activate_ability(cavern, 1, "alice", color=Color.GREEN)
    assert _restrictions(scenario) == [
        "Spend this mana only to cast a creature spell of the chosen type, and that "
        "spell can't be countered."
    ]

    elves = scenario.cast_and_resolve("Llanowar Elves")
    assert elves.zone is Zone.BATTLEFIELD


def test_cavern_of_souls_refuses_a_creature_of_a_different_type():
    """The same land with Zombie chosen refuses the same Elf. The restriction
    is read against the recorded choice, not against "some creature"."""
    scenario = (
        Scenario().player("alice", hand=["Cavern of Souls", "Llanowar Elves"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Zombie", source="Cavern of Souls")
    cavern = scenario.play_land("Cavern of Souls")
    scenario.game.activate_ability(cavern, 1, "alice", color=Color.GREEN)

    casting = scenario.cast("Llanowar Elves", "alice")
    with pytest.raises(ValueError, match="Spend this mana only to cast a creature spell"):
        casting.begin_paying().pay()

    casting.cancel()  # CR 601.6, undoing CR 601.2a's move
    assert scenario.find("Llanowar Elves", Zone.HAND).zone is Zone.HAND


def test_delighted_halflings_mana_refuses_a_nonlegendary_spell():
    """ "a legendary spell" is a supertype test (CR 205.4a). Llanowar Elves is a
    creature spell and not legendary, so the Halfling's mana will not pay for
    it even though it is the right colour."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Delighted Halfling"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    halfling = _ready(scenario, "Delighted Halfling")
    scenario.game.activate_ability(halfling, 1, "alice", color=Color.GREEN)

    with pytest.raises(ValueError, match="Spend this mana only to cast a legendary spell"):
        scenario.cast("Llanowar Elves", "alice").begin_paying().pay()


def test_chandras_mana_refuses_a_creature_spell():
    """Chandra, Chill of Compliance's second `+1`: "Add {U}. Spend this mana
    only to cast a noncreature spell." (CR 109.2's negation of CR 205.2a's
    card type.) A loyalty ability (CR 606), not a mana ability at all
    (CR 605.1a excludes loyalty abilities by name) - the mana is added as
    the ability *resolves*, off the stack, not straight into the pool the
    way `{T}: Add` skips the stack for.

    Aerial Doombot is a creature spell and blue, so the colour is right and
    the restriction is still the reason it is refused.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Aerial Doombot"], battlefield=["Chandra, Chill of Compliance"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.find("Chandra, Chill of Compliance", Zone.BATTLEFIELD)
    scenario.activate(chandra, index=1)
    scenario.pass_until_resolved()

    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    with pytest.raises(ValueError, match="Spend this mana only to cast a noncreature spell"):
        scenario.cast("Aerial Doombot", "alice").begin_paying().pay()


def test_chandras_mana_pays_for_a_noncreature_spell():
    """The legal direction: Opt is an instant, not a creature, so "noncreature
    spell" is satisfied and Chandra's own restricted {U} pays for it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Opt"], battlefield=["Chandra, Chill of Compliance"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.find("Chandra, Chill of Compliance", Zone.BATTLEFIELD)
    scenario.activate(chandra, index=1)
    scenario.pass_until_resolved()

    scenario.cast("Opt", "alice").begin_paying().pay()
    assert scenario.player().mana_pool.floating == {}


# --------------------------------------------------------------------------
# Reading the sentence
# --------------------------------------------------------------------------


#: The spend restrictions in the pool this grammar knowingly does not read,
#: each with the reason. A row here is a **deliberate** fail-closed case that
#: something else in the suite depends on being unread - not a to-do list and
#: not somewhere to park a card whose sentence is merely inconvenient. The
#: sweep below asserts the unread set is exactly this, in both directions, so
#: a printing added later that opens a new grammar shape still fails, and a
#: row that the grammar has since learned to read fails too rather than
#: quietly outliving its reason.
KNOWN_UNREAD_RESTRICTIONS = {
    # CR 106.6's clause is neither a "cast <quality> spells" nor an "activate
    # abilities of <quality> sources" purpose - it qualifies the *cost*, by a
    # symbol appearing in it. `scenarios/test_legal_actions.py` uses this
    # printing as the standing proof that `Action.restriction_understood` is
    # published as `False` rather than filtered away, so making the grammar
    # read it means finding that test another card, not deleting the row.
    "Rosheen Meanderer": "Spend this mana only on costs that contain {X}.",
}


def test_every_printed_restriction_in_the_pool_is_read():
    """Every "Spend this mana only" printing in the pool parses into clauses,
    bar the documented fail-closed rows above.

    A restriction the parser cannot read permits nothing at all, which is safe
    but is not coverage, so this sweeps the whole pool rather than naming the
    printings it happened to be written against: a card added later that opens
    a new grammar shape fails here instead of quietly failing closed in a game.

    Cavern of Souls is the one printing whose sentence cannot be read off the
    card alone - "of the chosen type" is CR 614.12a's answer, recorded on the
    permanent - so it is asked with a source carrying that answer, which is the
    only state that makes the sentence checkable.
    """
    unread: list[str] = []
    seen = 0
    for name, printing in sorted(pool().items()):
        text = printing.oracle_text or ""
        if "Spend this mana only" not in text:
            continue
        seen += 1
        source = None
        if "of the chosen type" in text:
            source = card_state(name, Zone.BATTLEFIELD)
            source.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")
        restriction = spend_restriction(text, source)
        if restriction is None or not restriction.understood:
            unread.append(name)

    assert seen >= 7, f"the pool sweep found only {seen} spend restrictions"
    assert unread == sorted(KNOWN_UNREAD_RESTRICTIONS)


def test_the_clauses_each_printed_restriction_is_read_into():
    """The shapes behind the sweep above, one assertion each - a sweep that
    only counts would pass on a parser that read every sentence into the same
    wrong clause."""
    shang_chi = spend_restriction(card("Shang-Chi, Master of Kung Fu").oracle_text)
    assert shang_chi is not None
    assert [clause.purpose for clause in shang_chi.clauses] == [SpendPurpose.ACTIVATE_ABILITY]

    # CR 106.6 on a triggered mana ability: "Spend this mana only to pay
    # cumulative upkeep costs" (CR 702.24a) is neither a cast nor an
    # activation, so it reads into its own purpose and pays for neither.
    snowfall = spend_restriction("Spend this mana only to pay cumulative upkeep costs.")
    assert snowfall is not None
    assert [clause.purpose for clause in snowfall.clauses] == [SpendPurpose.PAY_CUMULATIVE_UPKEEP]

    citadel = spend_restriction(card("Sunken Citadel").oracle_text)
    assert citadel is not None
    assert [clause.purpose for clause in citadel.clauses] == [SpendPurpose.ACTIVATE_ABILITY]
    assert citadel.clauses[0].types == frozenset({Type.LAND})

    temple = spend_restriction(card("Eldrazi Temple").oracle_text)
    assert temple is not None
    assert [clause.purpose for clause in temple.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]

    halfling = spend_restriction(card("Delighted Halfling").oracle_text)
    assert halfling is not None
    assert halfling.clauses[0].supertypes == frozenset({"legendary"})

    # PART A: an and-joined type list is ONE clause offering both types, not a
    # second alternative clause - no spell is ever both an instant and a
    # sorcery, so two clauses would be two ways of saying the same thing.
    tablet = spend_restriction(card("Tablet of Discovery").oracle_text)
    assert tablet is not None
    assert [clause.purpose for clause in tablet.clauses] == [SpendPurpose.CAST_SPELL]
    assert tablet.clauses[0].types == frozenset({Type.INSTANT, Type.SORCERY})
    # ... and the list is alternatives, which is what the joining word says.
    assert tablet.clauses[0].joined is True
    # Juxtaposition is the other reading: Eldrazi Temple's mana wants a spell
    # that is colorless *and* an Eldrazi, not either of the two.
    assert temple.clauses[0].joined is False

    dwarves = spend_restriction(card("Fíli and Kíli, Joyous").oracle_text)
    assert dwarves is not None
    assert len(dwarves.clauses) == 1
    assert dwarves.clauses[0].subtypes == frozenset({"dwarf", "equipment", "saga"})

    # PART B: the zone dimension, and nothing else narrowed with it.
    watch = spend_restriction(card("Interdimensional Web Watch").oracle_text)
    assert watch is not None
    assert len(watch.clauses) == 1
    assert watch.clauses[0].zone is Zone.EXILE
    assert watch.clauses[0].types == frozenset()


def test_and_splits_two_clauses_the_way_or_does():
    """Woodland Weavemaster, added to the pool for this: "{T}: Add X mana of
    any one color, where X is this creature's power. Spend this mana only to
    cast Elf spells and activate abilities of Elf sources." - read off Scryfall
    this session.

    It is Eldrazi Temple's two-clause sentence with "and" where the Temple
    prints "or", and it is the commoner of the two templates: "cast Room spells
    and unlock doors" (Smoky Lounge) prints it too. Alternatives were split on
    " or " alone, so this sentence read as nothing at all and the mana paid for
    neither of the two things it names.

    The whole phrase is still offered to the grammar before any split, which is
    what keeps "cast instant and sorcery spells" one clause: a joining word
    between two *clauses* only gets to split when the sentence cannot be read
    as one clause in the first place.
    """
    restriction = spend_restriction(card("Woodland Weavemaster").oracle_text)

    assert restriction is not None
    assert restriction.understood is True
    assert [clause.purpose for clause in restriction.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]
    assert [clause.subtypes for clause in restriction.clauses] == [
        frozenset({"elf"}),
        frozenset({"elf"}),
    ]
    assert restriction.allows(ManaSpend.casting(card("Elvish Mystic"), zone=Zone.HAND)) is True
    assert restriction.allows(ManaSpend.activating(card("Elvish Mystic"))) is True
    assert restriction.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.HAND)) is False


def test_and_or_joins_a_type_list_inside_one_clause():
    """The same two words in the other role, on a printing that really says
    them: Codsworth, Handy Helper's "{T}: Add {W}{W}. Spend this mana only to
    cast Aura and/or Equipment spells." - read off Scryfall this session, and
    added to the pool because the joiner list named it as an example without
    anything in the repo proving the printing exists. It does; Cormela, Glamour
    Thief ("instant and/or sorcery spells") and Master of Dark Rites
    ("Vampire, Cleric, and/or Demon spells") print it too.

    "and/or" between two qualities is one clause offering both, exactly as
    "and" and "or" are - no spell is an Aura and an Equipment at once - and
    that is why the whole phrase is read before anything is split on it.
    """
    restriction = spend_restriction(card("Codsworth, Handy Helper").oracle_text)

    assert restriction is not None
    assert restriction.understood is True
    assert len(restriction.clauses) == 1
    assert restriction.clauses[0].subtypes == frozenset({"aura", "equipment"})
    assert restriction.allows(ManaSpend.casting(card("Hyena Umbra"), zone=Zone.HAND)) is True
    assert restriction.allows(ManaSpend.casting(card("Shadowspear"), zone=Zone.HAND)) is True
    assert restriction.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.HAND)) is False


def test_a_joined_list_is_alternatives_even_where_it_crosses_card_types_and_subtypes():
    """Séance Board, added to the pool for this: "{T}: Add X mana of any one
    color, where X is the number of soul counters on this artifact. Spend this
    mana only to cast instant, sorcery, Demon, and Spirit spells." - read off
    Scryfall this session.

    One list, joined by commas and "and", holding two card types and two
    creature types. It is four alternatives: CR 205.2b (looked up this session)
    makes an object "satisfy the criteria for any effect that applies to any of
    their card types", and no spell is ever an instant *and* a Demon. Asking
    for a card type from the list **and** a subtype from it meant this mana
    paid for nothing at all - a printing whose whole purpose is to pay for four
    kinds of spell.
    """
    restriction = spend_restriction(card("Séance Board").oracle_text)

    assert restriction is not None
    assert restriction.understood is True
    (clause,) = restriction.clauses
    assert clause.types == frozenset({Type.INSTANT, Type.SORCERY})
    assert clause.subtypes == frozenset({"demon", "spirit"})

    # A Demon that is not an instant, and an instant that is not a Demon.
    assert restriction.allows(ManaSpend.casting(card("Griselbrand"), zone=Zone.HAND)) is True
    assert restriction.allows(ManaSpend.casting(card("Lightning Bolt"), zone=Zone.HAND)) is True
    # And a creature spell that is none of the four.
    assert restriction.allows(ManaSpend.casting(card("Grizzly Bears"), zone=Zone.HAND)) is False


def test_juxtaposed_qualities_are_all_required_where_a_joined_list_is_alternatives():
    """The other half of the same rule, and the joining word is the whole
    discriminator: Rivaz of the Claw's "{T}: Add two mana in any combination of
    colors. Spend this mana only to cast Dragon creature spells." - read off
    Scryfall this session, added to the pool for this.

    Nothing joins "Dragon" to "creature" there, because they are not
    alternatives: they describe one object that is both, and a spell that is
    only one of them is not what the card names. The same reading is what makes
    "artifact creature spells" refuse a plain creature - a shape no printing
    uses today, which is exactly why the rule has to come from the templating
    rather than from a list of the sentences seen so far.
    """
    restriction = spend_restriction(card("Rivaz of the Claw").oracle_text)

    assert restriction is not None
    assert restriction.understood is True
    (clause,) = restriction.clauses
    assert clause.types == frozenset({Type.CREATURE})
    assert clause.subtypes == frozenset({"dragon"})

    assert restriction.allows(ManaSpend.casting(card("Clarion Conqueror"), zone=Zone.HAND)) is True
    # A creature that is not a Dragon, and a Dragon card that is not a creature
    # spell - neither is a Dragon creature spell.
    assert restriction.allows(ManaSpend.casting(card("Grizzly Bears"), zone=Zone.HAND)) is False
    assert restriction.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.HAND)) is False


def test_a_chosen_type_nobody_chose_leaves_the_restriction_unread_and_unspendable():
    """Cavern of Souls with no recorded choice: the sentence is present and
    cannot be checked, so it is kept, quoted, and permits nothing. Mana that
    looked spendable and was not is the defect this whole subsystem exists to
    prevent, so the unread case fails towards refusing."""
    unread = spend_restriction(card("Cavern of Souls").oracle_text)

    assert unread is not None
    assert unread.understood is False
    assert unread.allows(ManaSpend.casting(card("Llanowar Elves"), zone=Zone.HAND)) is False
    assert unread.allows(None) is False


# --------------------------------------------------------------------------
# An and-joined type list: one clause, not two alternatives
# --------------------------------------------------------------------------


def _float_tablet(scenario):
    """Tap Tablet of Discovery for its restricted `{R}{R}`.

    The Tablet prints two mana abilities and only the second carries the
    CR 106.6 sentence, so the index is the whole point of the helper: index 0
    is the unrestricted `{T}: Add {R}`.
    """
    tablet = _ready(scenario, "Tablet of Discovery")
    scenario.game.activate_ability(tablet, 1, "alice")
    return tablet


def test_tablet_of_discoverys_mana_pays_for_an_instant():
    """ "instant and sorcery spells" is one type list, not one type.

    CR 205.2b, looked up this session: "Some objects have more than one card
    type... Such objects satisfy the criteria for any effect that applies to
    any of their card types." No single spell is both an instant and a
    sorcery, so the printed "and" joins a *list of qualifying types* inside
    one clause - the mana pays for either.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_tablet(scenario)
    assert scenario.player().mana_pool.floating == {Color.RED: 2}

    casting = scenario.cast("Lightning Bolt", "alice", targets=["bob"])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD).zone is Zone.GRAVEYARD
    assert scenario.game.player("bob").life == 17


def test_tablet_of_discoverys_mana_pays_for_a_sorcery():
    """The other half of the same list, on the same restriction. Lava Spike is
    a sorcery, and the mana that just paid for an instant pays for it too."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lava Spike"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_tablet(scenario)

    casting = scenario.cast("Lava Spike", "alice", targets=["bob"])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.player("bob").life == 17


def test_tablet_of_discoverys_mana_refuses_a_creature_spell():
    """The refusal that makes the list a list and not "any spell": Goblin Guide
    is a creature spell costing exactly the `{R}` the Tablet made, and the
    restriction still turns it down."""
    scenario = (
        Scenario()
        .player("alice", hand=["Goblin Guide"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float_tablet(scenario)

    # The restriction has to be *read* for this refusal to prove anything: an
    # unparsed sentence refuses everything, this one included, while saying
    # nothing about the type list.
    (restricted,) = scenario.player().mana_pool.restricted
    assert restricted.restriction.understood is True

    casting = scenario.cast("Goblin Guide", "alice")
    payment = casting.begin_paying()

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to cast instant and sorcery"):
        payment.pay()

    # CR 733.1: a refused payment spends nothing.
    assert scenario.player().mana_pool.floating == {Color.RED: 2}
    casting.cancel()
    assert scenario.find("Goblin Guide", Zone.HAND).zone is Zone.HAND


def test_an_and_joined_list_of_subtypes_is_read_on_a_different_printing():
    """Generality, proved on a card that is not the reported one.

    Fíli and Kíli, Joyous prints "Spend this mana only to cast Dwarf,
    Equipment, and Saga spells." - a three-item list of *subtypes* (CR 205.3),
    comma-separated with an Oxford "and", on a creature rather than an
    artifact. Nothing about Tablet of Discovery's sentence is reused: if the
    parser were fitted to "instant and sorcery", this would fail closed.

    Cori-Steel Cutter is an Artifact - Equipment costing `{1}{R}`, which the
    `{R}{R}` covers exactly.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cori-Steel Cutter", "Lightning Bolt"],
            battlefield=["Fíli and Kíli, Joyous"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dwarves = _ready(scenario, "Fíli and Kíli, Joyous")
    scenario.game.activate_ability(dwarves, 0, "alice")
    assert _restrictions(scenario) == [
        "Spend this mana only to cast Dwarf, Equipment, and Saga spells."
    ]

    # An instant is not on the list, even though it is the right colour.
    bolt = scenario.cast("Lightning Bolt", "alice", targets=["bob"])
    with pytest.raises(ValueError, match="Spend this mana only to cast Dwarf, Equipment, and Saga"):
        bolt.begin_paying().pay()
    bolt.cancel()

    casting = scenario.cast("Cori-Steel Cutter", "alice")
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# A zone clause: where the spell is being cast from
# --------------------------------------------------------------------------


def test_interdimensional_web_watchs_mana_pays_for_a_spell_cast_from_exile():
    """CR 400.1 names the seven zones; "from exile" narrows the clause to one
    of them, and the mana pays for a spell whose CR 601.2a move started there.

    The whole card drives it: its own enters trigger exiles the top two cards
    and hands out CR 601.3's permission to play them, and the mana its second
    ability makes is what pays for one of them. Nothing here reaches for
    `Game.grant_play_permission` behind the printing's back.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Interdimensional Web Watch"],
            library=["Mind Stone", "Forest"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Interdimensional Web Watch", *forests)
    scenario.pass_until_resolved()  # the enters trigger, and the exile it does
    mind_stone = scenario.find("Mind Stone", Zone.EXILE, "alice")

    watch = _ready(scenario, "Interdimensional Web Watch")
    scenario.game.activate_ability(watch, 0, "alice", color=Color.RED)
    assert scenario.player().mana_pool.floating == {Color.RED: 2}

    casting = scenario.cast("Mind Stone", "alice", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert mind_stone.zone is Zone.BATTLEFIELD


def test_interdimensional_web_watchs_mana_refuses_the_same_spell_from_hand():
    """The refusal is the point: the identical printing, the identical cost,
    cast from the hand instead. Only the origin zone differs, and it is the
    whole of what the clause asks about."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Stone"], battlefield=["Interdimensional Web Watch"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watch = _ready(scenario, "Interdimensional Web Watch")
    scenario.game.activate_ability(watch, 0, "alice", color=Color.RED)

    casting = scenario.cast("Mind Stone", "alice")
    payment = casting.begin_paying()

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to cast spells from exile"):
        payment.pay()

    assert scenario.player().mana_pool.floating == {Color.RED: 2}
    casting.cancel()
    assert scenario.find("Mind Stone", Zone.HAND).zone is Zone.HAND


def test_a_zone_the_grammar_does_not_know_leaves_the_restriction_unread():
    """The fail-closed direction for the new dimension, matching what an
    unrecorded chosen type already does.

    The sentence is Mm'menon, the Right Hand's - "Spend this mana only to cast
    a spell from anywhere other than your hand." - read off Scryfall this
    session. "anywhere" is not one of CR 400.1's seven zones, so the clause
    cannot be checked; the restriction is kept, quoted, and permits nothing at
    all rather than being quietly widened to every zone. The sentence is handed
    to the parser as text rather than added to the pool because the sweep below
    asserts every printing *in* the pool is read.
    """
    unread = spend_restriction(
        "{T}: Add {U}. Spend this mana only to cast a spell from anywhere other than your hand."
    )

    assert unread is not None
    assert unread.understood is False
    assert unread.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.EXILE)) is False
    assert unread.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.HAND)) is False


def test_the_web_watch_makes_two_mana_of_different_colors():
    """ "In any combination of colors" is not "of any one color".

    CR 106.1a's five colors are the universe for both, but Shang-Chi's "two
    mana of any **one** color" locks both mana to one of them and this does
    not - so the pair may be `{W}{U}`, and asking Shang-Chi for the same pair
    is asking for mana that card never offered. Both halves are asserted here,
    because a model that only knew how to make two of one colour would pass a
    test that only ever asked for two of one colour.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Interdimensional Web Watch", "Shang-Chi, Master of Kung Fu"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    watch = _ready(scenario, "Interdimensional Web Watch")
    scenario.game.activate_ability(watch, 0, "alice", color=[Color.WHITE, Color.BLUE])
    assert scenario.player().mana_pool.floating == {Color.WHITE: 1, Color.BLUE: 1}

    shang_chi = _ready(scenario, "Shang-Chi, Master of Kung Fu")
    with pytest.raises(ValueError, match="any one color"):
        scenario.game.activate_ability(shang_chi, 0, "alice", color=[Color.WHITE, Color.BLUE])


# --------------------------------------------------------------------------
# The same two shapes on a second printing that shares neither sentence
# --------------------------------------------------------------------------


def test_smokebraider_reads_the_same_combination_ability_and_a_type_restriction():
    """Smokebraider is the second printing of "Add two mana in any combination
    of colors" - "{T}: Add two mana in any combination of colors. Spend this
    mana only to cast Elemental spells or activate abilities of Elementals.",
    read off Scryfall this session and added to the pool for this file.

    It is what makes the mixed-colour ability a mechanic rather than one card:
    a creature instead of an artifact, and a restriction sentence that shares
    nothing with Interdimensional Web Watch's zone tail. Both halves of the
    printing are asserted here - the ability's shape, and the two clauses the
    CR 106.6 sentence reads into (CR 205.3m, looked up this session: Elemental
    is one of the creature types creatures and kindreds share).

    Both halves of the *sentence* are asserted too, and that is not pedantry:
    the cast half prints the subtype as the singular adjective "Elemental" and
    the activate half prints the plural noun "Elementals", and only the first
    of the two matches a printed type line as it stands. A test that asserted
    the first clause alone passed while the second permitted nothing at all.
    """
    smokebraider = card("Smokebraider")
    (ability,) = parse_mana_abilities(smokebraider)

    assert ability.any_color_mixed is True
    assert ability.any_color_count == 2

    restriction = spend_restriction(smokebraider.oracle_text)
    assert restriction is not None
    assert restriction.understood is True
    assert [clause.purpose for clause in restriction.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]
    assert restriction.clauses[0].subtypes == frozenset({"elemental"})
    assert restriction.clauses[1].subtypes == frozenset({"elemental"})
    assert restriction.allows(ManaSpend.activating(card("Smokebraider"))) is True


def test_smokebraiders_mana_pays_for_an_elemental_spell_of_two_colors():
    """The mixture is what pays: Voice of Resurgence costs `{G}{W}`, and one
    activation of Smokebraider covers it only because each of its two mana
    chooses its own colour. A model that read the ability as "two mana of any
    one color" would make `{G}{G}` and come up a white short."""
    scenario = (
        Scenario()
        .player("alice", hand=["Voice of Resurgence"], battlefield=["Smokebraider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    smokebraider = _ready(scenario, "Smokebraider")
    scenario.game.activate_ability(smokebraider, 0, "alice", color=[Color.GREEN, Color.WHITE])
    assert scenario.player().mana_pool.floating == {Color.GREEN: 1, Color.WHITE: 1}

    voice = scenario.cast_and_resolve("Voice of Resurgence")

    assert voice.zone is Zone.BATTLEFIELD


def test_smokebraiders_mana_activates_an_elementals_ability():
    """The activate half of the same sentence, played rather than parsed.

    "Activate abilities of Elementals" prints the subtype as a plural noun,
    which no type line ever says: Thornling's type line reads "Creature -
    Elemental Shapeshifter", singular, like every printed type line (CR 205.3b,
    looked up this session: subtypes "are listed after a long dash", one word
    each). So the clause is only checkable if the plural is read back to the
    subtype it names, and until it was, this activation - one of
    Smokebraider's two mana, spent on the `{G}` ability of an Elemental
    standing next to it - was refused by the card that exists to pay for it.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Smokebraider", "Thornling"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    smokebraider = _ready(scenario, "Smokebraider")
    scenario.game.activate_ability(smokebraider, 0, "alice", color=[Color.GREEN, Color.RED])
    assert scenario.player().mana_pool.floating == {Color.GREEN: 1, Color.RED: 1}

    thornling = _ready(scenario, "Thornling")
    scenario.activate(thornling, index=0)

    # The `{G}` half of the pool paid for it; the `{R}` is still floating and
    # still restricted (CR 118.3a, looked up this session: paying mana removes
    # "the indicated mana", and the rest is still there to be announced).
    assert scenario.player().mana_pool.floating == {Color.RED: 1}
    scenario.resolve_top()
    assert has_keyword(thornling, Keyword.HASTE, scenario.game)


def test_smokebraiders_mana_refuses_an_ability_of_a_source_that_is_not_an_elemental():
    """The other direction of the plural clause, so reading "Elementals" back
    to a subtype cannot have widened it to every source: Icy Manipulator's
    `{1}, {T}:` is an activated ability whose generic mana Smokebraider's would
    otherwise pay, and an Artifact is not an Elemental."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Smokebraider", "Icy Manipulator", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    smokebraider = _ready(scenario, "Smokebraider")
    scenario.game.activate_ability(smokebraider, 0, "alice", color=[Color.RED, Color.GREEN])

    manipulator = _ready(scenario, "Icy Manipulator")
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    with pytest.raises(ValueError, match="Spend this mana only"):
        scenario.activate(manipulator, index=0, targets=[forest])


def test_a_plural_subtype_is_read_on_a_printing_that_shares_nothing_with_smokebraider():
    """Orb of Dragonkind, added to the pool for this: "{1}, {T}: Add two mana
    in any combination of colors. Spend this mana only to cast Dragon spells or
    activate abilities of Dragons." - read off Scryfall this session.

    A different subtype, a different card type, a different cost, and the same
    two clause shapes. It is what says the plural is read as a mechanic rather
    than as one word learned from the card that exposed it: nothing here is
    Smokebraider's, and Clarion Conqueror is a Dragon that was never in either
    printing's own sentence.
    """
    orb = card("Orb of Dragonkind")
    restriction = spend_restriction(orb.oracle_text)

    assert restriction is not None
    assert restriction.understood is True
    assert [clause.purpose for clause in restriction.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]
    assert [clause.subtypes for clause in restriction.clauses] == [
        frozenset({"dragon"}),
        frozenset({"dragon"}),
    ]
    assert restriction.allows(ManaSpend.activating(card("Clarion Conqueror"))) is True
    assert restriction.allows(ManaSpend.activating(card("Icy Manipulator"))) is False


def test_a_capitalised_word_that_names_no_subtype_leaves_the_restriction_unread():
    """The fail-closed direction of the subtype vocabulary.

    The sentence is Gallifrey Council Chamber's - "Spend this mana only to cast
    a Time Lord or Alien spell or activate an ability of a Time Lord or Alien."
    - read off Scryfall this session. "Time Lord" is one subtype printed as two
    words, and this grammar reads one word at a time, so "Time" names no
    subtype at all. A word it cannot resolve fails the whole clause rather than
    being dropped: the restriction is kept, quoted, and permits nothing, which
    is the same direction an unknown zone already fails in.
    """
    unread = spend_restriction(
        "{T}: Add one mana of any color. Spend this mana only to cast a Time Lord or "
        "Alien spell or activate an ability of a Time Lord or Alien."
    )

    assert unread is not None
    assert unread.understood is False
    assert unread.allows(ManaSpend.casting(card("Mind Stone"), zone=Zone.HAND)) is False


def test_a_hand_picked_mixture_pays_the_spell_it_was_made_for():
    """The mixture has to survive being *named* by the caller, not only being
    chosen inside `Game.activate_ability`.

    A seat that picks its own mana sources - the api's `pay_with`, the
    harness's own hand-picked path - reaches `CostPayment.tap_for_mana(source,
    colors)` with the colours it wants, and that call re-checks the production
    against what the ability offers. "Add two mana in any combination of
    colors" was checked against one colour repeated per colour, so `{G}{W}` -
    the whole point of the printing - was refused by the very card that makes
    it, and Voice of Resurgence's `{G}{W}` could not be paid at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Voice of Resurgence"], battlefield=["Smokebraider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    smokebraider = _ready(scenario, "Smokebraider")

    casting = scenario.cast("Voice of Resurgence", "alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(smokebraider, [Color.GREEN, Color.WHITE])
    payment.pay()
    scenario.put_on_stack(casting)
    voice = scenario.resolve_top()

    assert voice.zone is Zone.BATTLEFIELD
    assert scenario.player().mana_pool.is_empty


def test_a_hand_picked_mixture_is_read_on_a_printing_that_is_not_smokebraiders():
    """The same on Rivaz of the Claw, whose restriction and cost share nothing
    with Smokebraider's: `{T}: Add two mana in any combination of colors. Spend
    this mana only to cast Dragon creature spells.`

    North Wind Avatar is `{2}{U}{U}{R}`, so the mixture is not a convenience
    here - one blue and one red out of the same activation is the only way this
    card's mana helps pay for it at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["North Wind Avatar"],
            battlefield=["Rivaz of the Claw", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rivaz = _ready(scenario, "Rivaz of the Claw")
    islands = scenario.untapped_sources("Island", "Island", "Island")

    casting = scenario.cast("North Wind Avatar", "alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(rivaz, [Color.BLUE, Color.RED])
    for island in islands:
        payment.tap_for_mana(island, [Color.BLUE])
    payment.pay()
    scenario.put_on_stack(casting)
    avatar = scenario.resolve_top()

    assert avatar.zone is Zone.BATTLEFIELD


def test_any_one_color_still_refuses_a_mixture_in_the_engines_own_words():
    """The mixture is licensed by the printed words and by nothing else.
    Shang-Chi's "Add two mana of any **one** color" is the same count locked to
    a single colour, so naming two colours there is asking for mana the card
    never offered - and it is refused with the reason, not with a bare "cannot
    be tapped"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Shang-Chi, Master of Kung Fu"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shang_chi = _ready(scenario, "Shang-Chi, Master of Kung Fu")

    casting = scenario.cast("Llanowar Elves", "alice")
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="cannot be tapped to add"):
        payment.tap_for_mana(shang_chi, [Color.GREEN, Color.WHITE])

    casting.cancel()


def test_smokebraiders_mana_refuses_a_spell_that_is_not_an_elemental():
    """The refusal half, on the same board: Llanowar Elves is a green creature
    spell the floating `{G}` would otherwise pay for, and an Elf is not an
    Elemental."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Smokebraider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    smokebraider = _ready(scenario, "Smokebraider")
    scenario.game.activate_ability(smokebraider, 0, "alice", color=[Color.GREEN, Color.WHITE])

    casting = scenario.cast("Llanowar Elves", "alice")
    with pytest.raises(ValueError, match="Spend this mana only to cast Elemental spells"):
        casting.begin_paying().pay()

    casting.cancel()  # CR 601.6, undoing CR 601.2a's move
    assert scenario.find("Llanowar Elves", Zone.HAND).zone is Zone.HAND


def test_a_second_spell_phrase_shares_the_first_ones_cast():
    """Maelstrom of the Spirit Dragon's "Spend this mana only to cast a Dragon
    spell or an Omen spell" - the second phrase's "cast" is elided, not
    missing (CR 205.3k's Omen spell type)."""
    maelstrom = spend_restriction(card("Maelstrom of the Spirit Dragon").oracle_text)
    assert maelstrom is not None and maelstrom.understood
    assert [clause.purpose for clause in maelstrom.clauses] == [SpendPurpose.CAST_SPELL] * 2
    assert [set(clause.subtypes) for clause in maelstrom.clauses] == [{"dragon"}, {"omen"}]
    # The borrowed verb still has to make a readable phrase.
    unread = spend_restriction("Spend this mana only to cast a Dragon spell or an Omen.")
    assert unread is not None and not unread.understood


# --------------------------------------------------------------------------
# "to activate an ability of a <quality> source" - the singular wording, and
# a second infinitive "to" after the "or" (C02-T1: Villainous Hideout; proof
# printing Cargo Ship, Modern/Pioneer/Standard, in no deck under
# `magic-cards-model-api/decks/`).
# --------------------------------------------------------------------------


def test_villainous_hideouts_mana_casts_a_villain():
    """Villainous Hideout: "{T}: Add one mana of any color. Spend this mana
    only to cast a Villain spell or to activate an ability of a Villain
    source." - its {B} and a Swamp cast Red Room Recruit ({1}{B})."""
    scenario = (
        Scenario()
        .player("alice", hand=["Red Room Recruit"], battlefield=["Villainous Hideout", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hideout = scenario.find("Villainous Hideout", Zone.BATTLEFIELD)
    scenario.game.activate_ability(hideout, 1, "alice", color=Color.BLACK)
    (swamp,) = scenario.untapped_sources("Swamp")

    recruit = scenario.cast_onto_stack("Red Room Recruit", swamp, username="alice")

    assert recruit.zone is Zone.STACK
    assert scenario.player("alice").mana_pool.floating == {}


def test_villainous_hideouts_mana_refuses_a_creature_that_is_not_a_villain():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Villainous Hideout", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hideout = scenario.find("Villainous Hideout", Zone.BATTLEFIELD)
    scenario.game.activate_ability(hideout, 1, "alice", color=Color.GREEN)
    (forest,) = scenario.untapped_sources("Forest")

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Grizzly Bears", forest, username="alice")


def test_proof_cargo_ships_mana_activates_an_artifacts_ability():
    """Cargo Ship: "Spend this mana only to cast an artifact spell or activate
    an ability of an artifact source." - its {C} pays Icy Manipulator's {1}."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cargo Ship", "Icy Manipulator"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ship = scenario.find("Cargo Ship", Zone.BATTLEFIELD)
    scenario.game.activate_ability(ship, 0, "alice")
    manipulator = _ready(scenario, "Icy Manipulator")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.activate(manipulator, index=0, targets=[forest])

    assert scenario.player("alice").mana_pool.floating == {}


def test_proof_cargo_ships_mana_refuses_a_creature_spell():
    scenario = (
        Scenario()
        .player("alice", hand=["Memnite", "Grizzly Bears"], battlefield=["Cargo Ship", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ship = scenario.find("Cargo Ship", Zone.BATTLEFIELD)
    scenario.game.activate_ability(ship, 0, "alice")
    (forest,) = scenario.untapped_sources("Forest")

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Grizzly Bears", forest, username="alice")

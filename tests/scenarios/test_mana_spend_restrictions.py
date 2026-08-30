"""CR 106.6: mana produced with a restriction on how it may be spent.

"Some spells or abilities that produce mana restrict how that mana can be
spent, have an additional effect that affects the spell or ability that mana is
spent on, or create a delayed triggered ability..." - CR 106.6, looked up this
session. Only the first of the three is modelled; the "additional effect" half
(Cavern of Souls's and Delighted Halfling's "and that spell can't be countered")
is still not.

Four printings in the pool carry one, and between them they cover both
purposes a restriction can name:

  Shang-Chi, Master of Kung Fu  "... only to activate abilities of creature
                                 sources."
  Eldrazi Temple                "... only to cast colorless Eldrazi spells or
                                 activate abilities of colorless Eldrazi."
  Cavern of Souls               "... only to cast a creature spell of the
                                 chosen type, ..."
  Delighted Halfling            "... only to cast a legendary spell, ..."

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
from magic_cards_model.machines.cost import spend_restriction
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.mana import ManaSpend, SpendPurpose
from tests.cards import card
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

    with pytest.raises(ValueError, match="Spend this mana only to cast a creature spell"):
        scenario.cast("Llanowar Elves", "alice").begin_paying().pay()

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


# --------------------------------------------------------------------------
# Reading the sentence
# --------------------------------------------------------------------------


def test_every_printed_restriction_in_the_pool_is_read():
    """A restriction the parser cannot read permits nothing at all, which is
    safe but is not coverage. These four are the whole of the pool and all four
    are genuinely parsed - Cavern of Souls only once its chosen type is on the
    permanent, which is why it is asked for here with a source."""
    shang_chi = spend_restriction(card("Shang-Chi, Master of Kung Fu").oracle_text)
    assert shang_chi is not None and shang_chi.understood
    assert [clause.purpose for clause in shang_chi.clauses] == [SpendPurpose.ACTIVATE_ABILITY]

    temple = spend_restriction(card("Eldrazi Temple").oracle_text)
    assert temple is not None and temple.understood
    assert [clause.purpose for clause in temple.clauses] == [
        SpendPurpose.CAST_SPELL,
        SpendPurpose.ACTIVATE_ABILITY,
    ]

    halfling = spend_restriction(card("Delighted Halfling").oracle_text)
    assert halfling is not None and halfling.understood
    assert halfling.clauses[0].supertypes == frozenset({"legendary"})


def test_a_chosen_type_nobody_chose_leaves_the_restriction_unread_and_unspendable():
    """Cavern of Souls with no recorded choice: the sentence is present and
    cannot be checked, so it is kept, quoted, and permits nothing. Mana that
    looked spendable and was not is the defect this whole subsystem exists to
    prevent, so the unread case fails towards refusing."""
    unread = spend_restriction(card("Cavern of Souls").oracle_text)

    assert unread is not None
    assert unread.understood is False
    assert unread.allows(ManaSpend.casting(card("Llanowar Elves"))) is False
    assert unread.allows(None) is False

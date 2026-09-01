"""Judge scenarios: costs the engine cannot yet read off a card.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#991** - How does Waterbend work? (a cost that lets untapped artifacts
  and creatures each pay for {1}, instead of producing mana)
- **DDR#997** - Back from the Brink + Delraich (an activated ability that names
  a different card's mana cost as its own cost, ignoring that card's
  alternative cost)
- **DDR#978** - Ancestral Vision + Sphere of Resistance (a generic "spells cost
  more" static ability, and Suspend on top of it)
- **DDR#998** - Llanowar Elves + Umbral Mantle (CR 601.2f's total cost is
  settled *before* CR 601.2g's mana abilities and CR 601.2h's payment, so no
  untap-for-mana trick can reach back and change it)
- **DDR#996** - Gran-Gran + Iroh, Grand Lotus (a cost reduction conditioned on
  what is in your graveyard, read after CR 601.2a has already moved the spell
  out of that graveyard)

DDR#997 is no longer `xfail`, and its old reason was wrong twice over.
`cost_component_for_phrase` **does** read "Exile a creature card from your
graveyard and pay its mana cost" - `_PHRASE_EXILE_AND_PAY_MANA_COST` is the
reader and `pay_mana_cost_of_chosen` is how the chosen card's own mana cost
reaches `Game.activation_cost`. What failed was the test: it passed the chosen
card as `sacrificing=` for an *exile* component, and asserted on
`Player.battlefield`, an attribute that does not exist.

DDR#991 is still `xfail`, on a narrower and now-true reason. `machines/cost.py`
reads `Waterbend {3}` as the `{3}` it names (CR 701.67a's "Pay [cost]"), and
`machines/objects_as_costs.waterbend` already spends the taps - but a waterbend
cost is *mana*, and `Game.activation_cost` routes an unclassified cost piece
through `cost_component_for_phrase` alone, which can only return a
`CostComponent` and so never sees it. That one branch in `models/game.py` is
the whole of what is left.

DDR#978's cost-increase half is no longer `xfail` - a concurrent engine wave
landed static "spells cost more" abilities (Sphere of Resistance and its kin)
reaching the casting path, so `test_sphere_of_resistance_taxes_every_spell_by_one_generic_mana`
now passes as an ordinary test. Its docstring says what changed.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import TotalCost, total_cost_for_phrase, waterbend_mana_cost
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import ManaCost, Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#991 - Waterbend: tap instead of paying mana
# --------------------------------------------------------------------------


def test_the_waterbend_cost_reads_as_the_mana_it_names():
    """DDR#991's first half, and the part `machines/cost.py` owns.

    CR 701.67a: "'Waterbend [cost]' means '**Pay [cost].** For each generic
    mana in that cost, you may tap an untapped artifact or creature you control
    rather than pay that mana.'" The first sentence is a plain mana cost, and
    `total_cost_for_phrase` reads it as one - which is what a `Waterbend {3}`
    activation owes before anybody taps anything.

    The second sentence is not part of the cost. CR 701.67b calls it "the
    alternate method to pay for mana described in rule 701.67a", and it works
    on an already-open payment exactly the way convoke does (CR 702.51b: the
    ability "isn't an additional or alternative cost and applies only after the
    total cost ... is determined") - `machines/objects_as_costs.waterbend` is
    that half, and it was already here.
    """
    assert total_cost_for_phrase("Waterbend {3}") == TotalCost(mana=ManaCost.parse("{3}"))
    assert waterbend_mana_cost("Waterbend {3}") == ManaCost.parse("{3}")
    assert waterbend_mana_cost("Exert this creature") is None


def test_waterbend_lets_an_untapped_creature_pay_part_of_the_cost():
    """DDR#991: each untapped artifact or creature tapped this way pays for {1}.

    CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each generic mana in
    that cost, you may tap an untapped artifact or creature you control rather
    than pay that mana.'" Flexible Waterbender's own ability is `Waterbend {3}:
    This creature has base power and toughness 5/2 until end of turn.` - three
    generic mana, payable entirely by tapping three permanents and spending no
    mana at all. CR 701.67a says "an untapped artifact or creature you control"
    with no "other", so the Waterbender may tap itself; it has vigilance, which
    is beside the point - vigilance is about attacking (nothing here attacks).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Flexible Waterbender", "Grizzly Bears", "Llanowar Elves", "Sol Ring"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    waterbender = scenario.creature("Flexible Waterbender", "alice")
    fodder = [
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Llanowar Elves", "alice"),
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"),
    ]

    # No mana sources tapped for mana at all - CR 701.67a's three taps are the
    # whole payment.
    scenario.activate(waterbender, tapping=fodder)
    scenario.resolve_top()

    assert all(permanent.tapped for permanent in fodder)
    assert waterbender.power == 5 and waterbender.toughness == 2


# --------------------------------------------------------------------------
# DDR#997 - "pay its mana cost" ignores that card's own alternative cost
# --------------------------------------------------------------------------


def test_back_from_the_brink_charges_delraichs_real_mana_cost_not_its_alternative():
    """DDR#997: an ability that names a card's mana cost sees the real one.

    Delraich reads "You may sacrifice three black creatures rather than pay
    this spell's mana cost" - but CR 113.6d says that ability "functions on the
    stack", i.e. only when Delraich itself is being cast, and CR 118.9c is
    explicit that an alternative cost "doesn't change a spell's mana cost, only
    what its controller has to pay to cast it. Spells and abilities that ask
    for that spell's mana cost still see the original value." Back from the
    Brink's activation cost asks for Delraich's mana cost directly rather than
    casting it, so the correct behaviour is charging {6}{B} in mana and giving
    the alternative cost nothing to apply to.

    This was `xfail` on a false diagnosis. `cost_component_for_phrase` does
    read "Exile a creature card from your graveyard and pay its mana cost" -
    `_PHRASE_EXILE_AND_PAY_MANA_COST` is that reader, and it sets
    `pay_mana_cost_of_chosen` so `Game.activation_cost` folds the chosen
    card's own printed `{6}{B}` in. Two bugs in the *test* hid it: the chosen
    card was passed as `sacrificing=` where the component is an exile, and the
    assertion read `Player.battlefield`, which does not exist - the
    battlefield is shared, on `Game`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Delraich"],
            battlefield=[
                "Back from the Brink",
                "Swamp",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    back_from_the_brink = scenario.find("Back from the Brink", Zone.BATTLEFIELD, "alice")
    delraich = scenario.find("Delraich", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(
        "Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    scenario.activate(back_from_the_brink, *sources, exiling=[delraich])
    scenario.resolve_top()

    assert delraich.zone is Zone.EXILE
    tokens = [state for state in scenario.game.battlefield if state.name == "Delraich"]
    assert len(tokens) == 1, "a token copy of Delraich should have entered the battlefield"


# --------------------------------------------------------------------------
# DDR#978 - a generic "spells cost more" static ability
# --------------------------------------------------------------------------


def test_sphere_of_resistance_taxes_every_spell_by_one_generic_mana():
    """DDR#978, now landed: a concurrent engine wave taught the casting path to
    read a static "spells cost more" ability off a *different* permanent and
    apply it as a cost increase, not just a reduction.

    CR 601.2f: "Some effects may increase or reduce the cost to pay." Sphere of
    Resistance's static ability is unconditional - it taxes every spell, not
    only ones with mana symbols already in their cost - so Lightning Bolt goes
    from {R} to {1}{R} while Sphere of Resistance is out. One Mountain is only
    ever enough to pay the untaxed {R}, so the cast fails; verified separately
    (not in this test) that two Mountains let it through for exactly {1}{R} and
    the Bolt resolves normally.

    Ancestral Vision's own half of this episode still needs Suspend on top of
    this, which `docs/engine-coverage.md` lists as parsed by
    `machines/abilities.py` but not executed by `Game` at all - a second,
    still-missing piece, which is why this test isolates the cost-increase half
    with an ordinary instant instead.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Sphere of Resistance"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])


# --------------------------------------------------------------------------
# DDR#998 - the total cost is settled before mana abilities and before payment
# --------------------------------------------------------------------------


def test_a_cost_increaser_that_leaves_mid_payment_does_not_lower_the_locked_in_cost():
    """DDR#998's second half: once CR 601.2f has determined the total cost, it
    does not go back down.

    The episode's Thalia/Village Rites example in engine-reachable form. CR
    601.2f: "The player determines the total cost of the spell ... Once the
    total cost is determined, any effects that directly affect the total cost
    are applied." CR 601.2g then gives the chance to activate mana abilities,
    and CR 601.2h is where the cost is actually paid - so *everything* a player
    does from 601.2g onwards, sacrificing the tax permanent included, happens
    after the number was fixed.

    Sphere of Resistance ("Spells cost {1} more to cast", confirmed with
    `resolve_cards`) stands in for Thalia here because it is the cost
    increase this engine actually reads - see
    `test_sphere_of_resistance_taxes_every_spell_by_one_generic_mana` above.
    Killing it after `begin_paying` (CR 601.2f is already behind us) must leave
    the Bolt costing {1}{R}, and it does.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Sphere of Resistance", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sphere = scenario.find("Sphere of Resistance", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{1}{R}"

    # CR 601.2h has not happened yet, but CR 601.2f already has.
    scenario.game.destroy(sphere)
    assert sphere.zone is Zone.GRAVEYARD
    assert str(payment.cost) == "{1}{R}"

    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


@pytest.mark.xfail(
    strict=True,
    reason="ONE line is left, and it is in models/game.py. Everything else "
    "measured working: `keywords.equip_activation` pays CR 702.6a's `Equip {0}` "
    "and attaches the Mantle, the layer-6 quoted-ability grant puts "
    "`{3}, {Q}: This creature gets +2/+2 until end of turn.` on the Elves as "
    "`Game.activated_abilities(elves)[1]`, `machines/abilities._classify_cost` "
    "already classifies `{Q}` as `CostKind.UNTAP`, `Game.begin_activating` "
    "already gates CR 602.5a on `{CostKind.TAP, CostKind.UNTAP}`, and "
    "`machines/cost.cost_component_for_phrase('{Q}')` now reads CR 107.6's "
    "untap symbol into a `ComponentKind.UNTAP` component (with `untap_cost`, "
    "`_why_not_untap`'s already-untapped refusal, and its pay/unpay halves). "
    "What is missing is that `Game.activation_cost` has no `CostKind.UNTAP` "
    "branch, so `{Q}` falls through to the generic `OTHER` reader, which builds "
    "the component with no card in it - CR 107.6's 'this permanent' is a "
    "self-reference `_cost_refers_to_self` cannot see in a bare symbol - and "
    "the activation dies on 'untap needs 1 card(s) chosen, 0 given'. It needs "
    "the exact mirror of the `CostKind.TAP` branch beside it:\n"
    "            elif piece.kind is CostKind.UNTAP:\n"
    "                components.append(\n"
    "                    untap_cost(permanent, payer=controller, description=piece.text)\n"
    "                )\n"
    "with `untap_cost` added to the `machines.cost` import list.",
)
def test_umbral_mantle_cannot_untap_llanowar_elves_for_a_third_mana():
    """DDR#998: the untap cannot pay for itself.

    Umbral Mantle (confirmed with `resolve_cards`): "Equipped creature has
    '{3}, {Q}: This creature gets +2/+2 until end of turn.' ({Q} is the untap
    symbol.) Equip {0}". CR 107.6: "The untap symbol in an activation cost
    means 'Untap this permanent.'"

    The sequencing is the whole question. CR 602.1a makes `{3}, {Q}` the
    activation cost, CR 601.2h pays it - "the player pays the total cost" -
    and CR 601.2g is the last moment mana abilities may be activated for it:
    "mana abilities must be activated before costs are paid", which CR 605.3a
    says the same way from the mana ability's side. The Elves is untapped by
    CR 601.2h, strictly after that window has closed, so the green mana it can
    make once untapped is a *later* mana and never the third one paying for
    this very activation.

    Both halves are here, because the refusal is only worth anything against a
    working activation. First three Forests pay the {3} and the tapped Elves is
    untapped by CR 601.2h. Then the Elves taps for its one green mana again,
    that mana empties as the step ends (CR 500.5, CR 703.4q), and only two
    Forests are left - one short. The second activation must be refused, and
    nothing about the Elves may change: still tapped, still its printed power
    plus the +2/+2 the first activation already gave it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Llanowar Elves", "Umbral Mantle", *["Forest"] * 5],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    mantle = scenario.find("Umbral Mantle", Zone.BATTLEFIELD, "alice")

    equip = equip_activation(scenario.game, mantle, elves, "alice")
    equip.begin_paying().pay()  # CR 118.5: {0} is paid by saying so
    equip.activate()
    scenario.resolve_top()
    assert mantle.is_attached

    # The Elves taps for its one green mana, which empties as the step ends.
    scenario.activate(elves, index=0)
    assert elves.tapped
    scenario.advance()

    # Three Forests pay the {3}; CR 601.2h then untaps the Elves.
    scenario.activate(elves, *scenario.untapped_sources(*["Forest"] * 3), index=1)
    scenario.resolve_top()
    assert not elves.tapped
    assert elves.power == int(elves.card.power) + 2

    # It taps for green again, and that mana empties too. Two Forests are left.
    scenario.activate(elves, index=0)
    assert elves.tapped
    scenario.advance()

    with pytest.raises(ValueError):
        scenario.activate(elves, *scenario.untapped_sources(*["Forest"] * 2), index=1)

    assert elves.tapped
    assert elves.power == int(elves.card.power) + 2


# --------------------------------------------------------------------------
# DDR#996 - a graveyard-counting discount, read after CR 601.2a emptied it
# --------------------------------------------------------------------------

#: A real Lesson card, so the graveyard the two static abilities below count is
#: made of the card type they actually name (Instant - Lesson, confirmed with
#: `resolve_cards`).
_LESSON = "Combustion Technique"


def _iroh_and_gran_gran(lessons: int) -> "Scenario":
    """Iroh, Grand Lotus and Gran-Gran on the battlefield, `lessons` Lesson
    cards in the graveyard, and a creature of bob's for the Lesson to target.
    """
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Iroh, Grand Lotus", "Gran-Gran", "Mountain", "Mountain"],
            graveyard=[_LESSON] * lessons,
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_iroh_grants_a_lesson_in_the_graveyard_flashback_one():
    """DDR#996's setup: the flashback cost replaces the mana cost.

    Iroh, Grand Lotus (confirmed with `resolve_cards`): "During your turn, each
    Lesson card in your graveyard has flashback {1}." CR 400.7g is what keeps
    that grant alive once CR 601.2a moves the card to the stack: "If an effect
    grants a nonland card an ability that allows it to be cast, that ability
    will continue to apply to the new object that card became after it moved to
    the stack as a result of being cast that way" - the point the episode
    spends its middle section on.

    So the total cost determined at CR 601.2f starts from {1}, not from
    Combustion Technique's printed {1}{R} - and Gran-Gran, on the same
    battlefield with four Lessons in the graveyard, then takes that {1} away
    entirely (her own discount, the next test's subject).
    """
    scenario = _iroh_and_gran_gran(lessons=4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast(_LESSON, from_zone=Zone.GRAVEYARD)
    # CR 601.2b: the alternative cost is announced before CR 601.2c's targets.
    # `Casting.granted_cast_options` is what finds the granted flashback.
    casting.use_keyword("flashback")
    casting.choose_targets([bears])

    assert str(casting.alternative_cost.mana) == "{1}", "the granted flashback cost"
    assert str(casting.begin_paying().cost) == "", "and Gran-Gran's {1} off it"


def test_gran_grans_discount_counts_the_graveyard_after_the_spell_left_it():
    """DDR#996: casting the Lesson itself takes it out of the count.

    Gran-Gran (confirmed with `resolve_cards`): "Noncreature spells you cast
    cost {1} less to cast as long as there are three or more Lesson cards in
    your graveyard." CR 601.2a is the first step of casting - "a player first
    moves that card ... from where it is to the stack" - and CR 601.2f, where
    the discount would apply, is five steps later. So a player flashing back
    one of exactly three Lessons has two left when the cost is determined and
    gets no discount; four is the number that makes the trick work.

    Both halves are asserted here: four Lessons discounts Iroh's flashback {1}
    down to nothing, three does not.
    """
    with_four = _iroh_and_gran_gran(lessons=4).build()
    with_four.start_at(Step.PRECOMBAT_MAIN)
    four_target = with_four.creature("Grizzly Bears", "bob")
    four_casting = with_four.cast(_LESSON, from_zone=Zone.GRAVEYARD)
    four_casting.use_keyword("flashback")
    four_casting.choose_targets([four_target])
    four_cost = four_casting.begin_paying()

    with_three = _iroh_and_gran_gran(lessons=3).build()
    with_three.start_at(Step.PRECOMBAT_MAIN)
    three_target = with_three.creature("Grizzly Bears", "bob")
    three_casting = with_three.cast(_LESSON, from_zone=Zone.GRAVEYARD)
    three_casting.use_keyword("flashback")
    three_casting.choose_targets([three_target])
    three_cost = three_casting.begin_paying()

    assert str(four_cost.cost) == "", "the granted {1}, discounted away entirely"
    assert str(three_cost.cost) == "{1}", "no discount: only two Lessons are left to count"

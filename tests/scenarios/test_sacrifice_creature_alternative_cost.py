"""Scenario: "You may sacrifice a nontoken <color> creature rather than pay
this spell's mana cost."

The Flare cycle's CR 118.9 alternative cost. The cost phrase is read by the
same reader every printed sacrifice cost goes through, so the colour word
(CR 105.2), "nontoken" (CR 111.1) and "creature" are each a demand checked
when the cost is paid:

- **Flare of Malice** - the reported card: a nontoken *black* creature.
- **Flare of Denial** - off-pool second printing: a nontoken *blue* creature,
  a different colour demand and a targeted spell ("Counter target spell.").

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- CR 118.9: an alternative cost is paid rather than the mana cost; CR 118.9a
  only one alternative cost can be applied to a spell; CR 118.9c it does not
  change the spell's mana cost; CR 118.9d cost increases still apply on top.
- CR 601.2b: the intention to pay it is announced while casting; CR 601.2h
  the total cost is paid then; CR 118.3 an unpayable cost cannot be paid.
- CR 701.21a: a player can sacrifice only a permanent they control.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.models import Zone

from .harness import Scenario

FLARE = "Flare of Malice"
DENIAL = "Flare of Denial"


def _scenario(*alice_battlefield: str, bob_battlefield: tuple[str, ...] = ("Serra Angel",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[FLARE, "Song of Totentanz"], battlefield=list(alice_battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _pitch_flare(scenario, *sacrificed) -> None:
    """Alice casts Flare of Malice for its alternative cost and it resolves."""
    casting = scenario.cast(FLARE, username="alice")
    casting.use_alternative_cost(choosing=list(sacrificed))
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def _refused(scenario, *chosen) -> str:
    """The engine's own reason for refusing `chosen` as the sacrifice."""
    casting = scenario.cast(FLARE, username="alice")
    casting.use_alternative_cost(choosing=list(chosen))
    payment = casting.begin_paying()
    with pytest.raises(ValueError) as refusal:
        payment.pay()
    return str(refusal.value)


def _make_black_rat(scenario):
    """A 1/1 black Rat token for alice, made with Song of Totentanz (X=1)."""
    casting = scenario.cast("Song of Totentanz", username="alice")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    (rat,) = [state for state in scenario.game.battlefield if state.token]
    return rat


def test_the_offer_is_listed_as_a_printed_one_sacrifice():
    """The printed line is read off the card itself (CR 118.9) and the listing
    reports the one object it needs chosen (CR 601.2b)."""
    scenario = _scenario("Dark Confidant")
    casting = scenario.cast(FLARE, username="alice")

    (option,) = casting.alternative_costs
    assert option.source is AlternativeCostSource.PRINTED
    assert option.available
    assert option.requires == 1
    assert option.description == "sacrifice a nontoken black creature"


def test_sacrificing_a_nontoken_black_creature_casts_it_with_no_mana():
    """No land at all: Dark Confidant is sacrificed as the cost (CR 601.2h),
    nothing else is paid, and the edict still resolves against bob."""
    scenario = _scenario("Dark Confidant")
    confidant = scenario.creature("Dark Confidant", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    _pitch_flare(scenario, confidant)

    assert confidant.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.find(FLARE, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_the_only_black_creature_may_be_the_one_sacrificed():
    """Nothing requires another black creature to remain: alice's sole
    creature, Vampire Nighthawk, pays the whole cost."""
    scenario = _scenario("Vampire Nighthawk")
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")

    _pitch_flare(scenario, nighthawk)

    assert nighthawk.zone is Zone.GRAVEYARD
    assert [state for state in scenario.game.battlefield if state.controller == "alice"] == []


def test_a_multicolored_black_creature_is_black_enough():
    """CR 105.2: Kroxa is black and red - black is one of its colours, so it
    pays a "black creature" cost."""
    scenario = _scenario("Kroxa, Titan of Death's Hunger")
    kroxa = scenario.creature("Kroxa, Titan of Death's Hunger", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    _pitch_flare(scenario, kroxa)

    assert kroxa.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD


def test_a_black_creature_token_is_refused():
    """CR 111.1: "nontoken" - a black Rat token cannot pay, and the engine
    says why in its own words."""
    scenario = _scenario("Mountain", "Mountain")
    rat = _make_black_rat(scenario)

    assert _refused(scenario, rat) == "Rat Token is a token"
    assert rat.zone is Zone.BATTLEFIELD


def test_a_nonblack_creature_is_refused():
    """CR 105.2: Grizzly Bears is green, not black."""
    scenario = _scenario("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _refused(scenario, bears) == "Grizzly Bears is not B"
    assert bears.zone is Zone.BATTLEFIELD


def test_an_opponents_black_creature_cannot_be_sacrificed():
    """CR 701.21a: a player cannot sacrifice a permanent they do not control,
    however black it is."""
    scenario = _scenario(bob_battlefield=("Dark Confidant",))
    bobs = scenario.creature("Dark Confidant", "bob")

    assert _refused(scenario, bobs) == "alice does not control Dark Confidant"
    assert bobs.zone is Zone.BATTLEFIELD


def test_with_nothing_to_sacrifice_the_cost_cannot_be_paid():
    """CR 118.3: announcing is not paying - with no creature chosen the
    payment refuses."""
    scenario = _scenario("Swamp")

    assert _refused(scenario) == "sacrifice needs 1 card(s) chosen, 0 given"


def test_only_one_alternative_cost_may_be_applied():
    """CR 118.9a: the alternative cost cannot be announced twice."""
    scenario = _scenario("Dark Confidant", "Vampire Nighthawk")
    casting = scenario.cast(FLARE, username="alice")
    casting.use_alternative_cost(choosing=[scenario.creature("Dark Confidant", "alice")])

    with pytest.raises(ValueError, match="only one alternative cost"):
        casting.use_alternative_cost(choosing=[scenario.creature("Vampire Nighthawk", "alice")])


def test_the_alternative_cost_does_not_change_the_mana_cost():
    """CR 118.9c: Flare of Malice still has mana value 4 while cast for a
    creature, and no mana is owed."""
    scenario = _scenario("Dark Confidant")
    casting = scenario.cast(FLARE, username="alice")
    casting.use_alternative_cost(choosing=[scenario.creature("Dark Confidant", "alice")])
    casting.determine_cost()

    assert casting.spell.card.cmc == 4
    assert casting.total_cost.mana.generic == 0
    assert casting.total_cost.mana.symbols == ()


def test_a_cost_increase_applies_on_top_of_the_sacrifice():
    """CR 118.9d: Sphere of Resistance's {1} is still owed on top of the
    sacrificed creature."""
    scenario = _scenario("Dark Confidant", "Swamp", "Sphere of Resistance")
    confidant = scenario.creature("Dark Confidant", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast(FLARE, username="alice")
    casting.use_alternative_cost(choosing=[confidant])
    payment = casting.determine_cost()

    assert casting.total_cost.mana.generic == 1

    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert confidant.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD


def test_it_may_still_be_cast_for_its_printed_mana_cost():
    """CR 118.9b: the alternative cost is optional - four Swamps pay
    {2}{B}{B} and alice's black creature stays."""
    scenario = _scenario("Dark Confidant", "Swamp", "Swamp", "Swamp", "Swamp")
    confidant = scenario.creature("Dark Confidant", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        FLARE,
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice"),
        username="alice",
    )

    assert confidant.zone is Zone.BATTLEFIELD
    assert angel.zone is Zone.GRAVEYARD


# -- Flare of Denial: the off-pool second printing ----------------------------


def _bob_bolts_alice_with_denial_ready(alice_battlefield: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", hand=[DENIAL], battlefield=alice_battlefield, life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast("Lightning Bolt", username="bob", targets=["alice"])
    payment = bolt.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", username="bob"))
    scenario.put_on_stack(bolt)
    scenario.pass_priority("bob")
    return scenario


def test_flare_of_denial_sacrifices_a_nontoken_blue_creature_to_counter():
    """The same cost with a different colour word: Delver of Secrets (blue)
    pays it and the countered Bolt never reaches alice."""
    scenario = _bob_bolts_alice_with_denial_ready(["Delver of Secrets"])
    delver = scenario.creature("Delver of Secrets", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.STACK, "bob")

    casting = scenario.cast(DENIAL, username="alice")
    casting.use_alternative_cost(choosing=[delver])
    casting.choose_targets([bolt])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert delver.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_flare_of_denial_refuses_a_black_creature():
    """Flare of Denial's demand is blue: a black creature cannot pay it."""
    scenario = _bob_bolts_alice_with_denial_ready(["Dark Confidant"])
    confidant = scenario.creature("Dark Confidant", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.STACK, "bob")

    casting = scenario.cast(DENIAL, username="alice")
    casting.use_alternative_cost(choosing=[confidant])
    casting.choose_targets([bolt])
    with pytest.raises(ValueError) as refusal:
        casting.begin_paying().pay()

    assert str(refusal.value) == "Dark Confidant is not U"
    assert confidant.zone is Zone.BATTLEFIELD

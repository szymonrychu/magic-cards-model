""" "When `<this>` dies, if it was a creature, return it to the battlefield
under its owner's control. It's an enchantment. (It's not a creature.)" - the
Enduring cycle's own death trigger.

CR 700.4: "The term dies means "is put into a graveyard from the
battlefield."" - any permanent, not only a creature, which is why the
intervening *if* matters: the returned enchantment dying again sets off the
trigger event, and CR 603.4's "if it was a creature" stops it there.

CR 603.10a: a leaves-the-battlefield ability looks back in time, so "it was a
creature" is asked of the permanent as it last existed on the battlefield.

CR 205.1a: "Some effects set an object's card type. In most such cases, the
new card type(s) replaces any existing card types." and "If an object's card
type is removed, the subtypes correlated with that card type will remain if
they are also the subtypes of a card type the object currently has;
otherwise, they are also removed" - so the returned card is an enchantment
with no Sheep or Glimmer subtype (the ruling on Enduring Innocence says the
same: "Sheep and Glimmer are both creature types. Enduring Innocence won't
have those creature types when its last ability returns it to the
battlefield because it won't be a creature.").

CR 400.7: the returned permanent is a new object - and it enters already an
enchantment, so a "whenever another creature enters" ability does not see a
creature arrive.

Enduring Innocence is the listed card; Enduring Curiosity is the proof
printing (Modern, Pioneer and Standard legal, in no api deck).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

INNOCENCE = "Enduring Innocence"
CURIOSITY = "Enduring Curiosity"


def _dies_and_returns(scenario, name: str, owner: str = "alice"):
    permanent = scenario.creature(name)
    scenario.game.destroy(permanent)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names()[-1] == f"{name}'s triggered ability"
    scenario.resolve_top()
    return scenario.find(name, Zone.BATTLEFIELD, owner)


def test_both_printings_are_fully_supported() -> None:
    for name in (INNOCENCE, CURIOSITY):
        statuses = {clause.status for clause in card_support(card(name)).clauses}
        assert statuses == {"handled"}, (name, card_support(card(name)).clauses)


def test_it_returns_as_an_enchantment_that_is_not_a_creature() -> None:
    scenario = Scenario().player("alice", battlefield=[INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    returned = _dies_and_returns(scenario, INNOCENCE)

    chars = scenario.game.characteristics_of(returned)
    assert tuple(chars.types) == (Type.ENCHANTMENT,)
    assert not chars.is_creature
    # CR 205.1a: Sheep and Glimmer correlate with the creature type only.
    assert tuple(chars.subtypes) == ()
    assert returned.controller == "alice"


def test_it_is_a_new_object_that_the_trigger_does_not_see_twice() -> None:
    """The returned enchantment dying again is a dies event (CR 700.4), but it
    was not a creature, so the intervening if refuses it (CR 603.4)."""
    scenario = Scenario().player("alice", battlefield=[INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    returned = _dies_and_returns(scenario, INNOCENCE)

    scenario.game.destroy(returned)
    scenario.game.put_triggers_on_stack()

    assert returned.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_it_returns_under_its_owners_control() -> None:
    """ "under its owner's control" - a creature bob controls but alice owns
    comes back to alice."""
    scenario = Scenario().player("alice", hand=[INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    innocence = scenario.find(INNOCENCE, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(innocence, "bob")
    assert scenario.game.controller_of(innocence).username == "bob"

    scenario.game.destroy(innocence)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert innocence.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(innocence).username == "alice"
    assert not scenario.game.characteristics_of(innocence).is_creature


def test_nothing_returns_if_the_card_left_the_graveyard() -> None:
    """CR 400.7: exiled from the graveyard in response, it is a new object
    the trigger cannot find - it stays in exile."""
    scenario = Scenario().player("alice", battlefield=[INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    innocence = scenario.creature(INNOCENCE)
    scenario.game.destroy(innocence)
    scenario.game.put_triggers_on_stack()

    scenario.game.exile_cards([innocence])
    scenario.resolve_top()

    assert innocence.zone is Zone.EXILE


def test_it_enters_as_an_enchantment_so_creature_entering_triggers_ignore_it() -> None:
    """A second Enduring Innocence's "one or more other creatures you control
    with power 2 or less enter" does not see the returned one: it is an
    enchantment as it enters, not a creature that later stops being one."""
    scenario = Scenario().player("alice", battlefield=[INNOCENCE, INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, _second = scenario.creatures(INNOCENCE, INNOCENCE)

    scenario.game.destroy(first)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert first.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


def test_its_own_entry_does_not_set_off_its_other_creatures_ability() -> None:
    """Enduring Innocence's other trigger says "one or more *other*
    creatures", so casting it (or putting it onto the battlefield) does not
    draw off its own arrival."""
    scenario = Scenario().player("alice", hand=[INNOCENCE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    innocence = scenario.find(INNOCENCE, Zone.HAND, "alice")

    scenario.game.put_onto_battlefield(innocence, "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_lethal_bolt_kills_it_and_it_comes_back() -> None:
    """The ordinary way it dies: CR 704.5g's lethal damage, then the trigger."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[INNOCENCE, "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    innocence = scenario.creature(INNOCENCE)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[innocence]
    )
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert innocence.zone is Zone.BATTLEFIELD
    assert not scenario.game.characteristics_of(innocence).is_creature


def test_curiosity_comes_back_as_an_enchantment_too() -> None:
    """The proof printing: same trigger, different card - a 4/3 Cat Glimmer
    with flash comes back a plain enchantment with no power or toughness."""
    scenario = Scenario().player("alice", battlefield=[CURIOSITY]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    returned = _dies_and_returns(scenario, CURIOSITY)

    chars = scenario.game.characteristics_of(returned)
    assert tuple(chars.types) == (Type.ENCHANTMENT,)
    assert tuple(chars.subtypes) == ()
    scenario.state_based_actions()
    assert returned.zone is Zone.BATTLEFIELD


def test_curiosity_as_an_enchantment_still_draws_off_combat_damage() -> None:
    """Its other ability keeps working once it is no longer a creature: a
    creature alice controls hitting bob draws her a card."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"], battlefield=[CURIOSITY, "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _dies_and_returns(scenario, CURIOSITY)
    bears = scenario.creature("Grizzly Bears")

    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CURIOSITY}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.find("Island", Zone.HAND, "alice").zone is Zone.HAND

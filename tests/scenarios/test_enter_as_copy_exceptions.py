"""CR 707.9's copy exceptions on "enter as a copy", and the candidate filter.

The "except ..." tail of an enter-as-a-copy replacement (CR 614.1c) is part of
the copying process, not a later effect:

- CR 707.9a: "Some copy effects cause the copy to gain an ability as part of
  the copying process. This ability becomes part of the copiable values for
  the copy, along with any other abilities that were copied."
- CR 707.9b: "Some copy effects modify a characteristic as part of the copying
  process. The final set of values for that characteristic becomes part of the
  copiable values of the copy."
- CR 205.1b: "in addition to its other types" keeps every prior type.

Printings (each verified against Scryfall this session):

- Mockingbird (listed card) - "except it's a Bird in addition to its other
  types and it has flying": a subtype and a keyword.
- Phantasmal Image (Modern; not in any deck list) - "except it's an Illusion
  in addition to its other types and it has "When this creature becomes the
  target of a spell or ability, sacrifice it."": a subtype and a quoted
  triggered ability - the second printing for the ability-granting exception.
- Clever Impersonator (Modern, Pioneer; not in any deck list) - "enter as a
  copy of any nonland permanent on the battlefield": the "non<type>" candidate
  filter.
- Sakashima of a Thousand Faces - "except it has Sakashima's other abilities"
  is still not a keyword or a quoted ability, so the fail-closed notice stays
  for it.

No mocks: every card is a real printing from the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.replacement import (
    ReplacementKind,
    UnreadableCopyExceptionNotice,
    parse_replacement_effects,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

PHANTASMAL_TRIGGER = "When this creature becomes the target of a spell or ability, sacrifice it."


def _copy_clause(name):
    (effect,) = [
        effect
        for effect in parse_replacement_effects(card(name))
        if effect.kind is ReplacementKind.ENTERS_AS_COPY
    ]
    return effect


def _copy_questions(scenario, source):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.source == source
    ]


# --------------------------------------------------------------------------
# Reading the tail
# --------------------------------------------------------------------------


def test_mockingbirds_tail_reads_as_a_subtype_and_a_keyword():
    effect = _copy_clause("Mockingbird")
    assert effect.copy_exception_unparsed is None
    assert effect.copy_exception is not None
    assert effect.copy_exception.added_subtypes == ("Bird",)
    assert effect.copy_exception.added_abilities == ("Flying",)


def test_phantasmal_images_tail_reads_as_a_subtype_and_a_quoted_ability():
    """The quoted ability is kept whole, quotes stripped - the " or " inside
    it is not a list separator."""
    effect = _copy_clause("Phantasmal Image")
    assert effect.copy_exception_unparsed is None
    assert effect.copy_exception.added_subtypes == ("Illusion",)
    assert effect.copy_exception.added_abilities == (PHANTASMAL_TRIGGER,)


def test_a_tail_granting_something_that_is_not_an_ability_still_fails_closed():
    effect = _copy_clause("Sakashima of a Thousand Faces")
    assert effect.copy_exception is None
    assert effect.copy_exception_unparsed == "it has Sakashima's other abilities"


# --------------------------------------------------------------------------
# Playing it out: Phantasmal Image
# --------------------------------------------------------------------------


def _phantasmal_board(*extra_hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Phantasmal Image", *extra_hand],
            battlefield=["Island", "Island", "Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Serra Angel", "Forest"], hand=["Giant Growth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_phantasmal_image_is_an_illusion_copy_with_the_granted_trigger():
    scenario = _phantasmal_board()
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(angel, username="alice", source="Phantasmal Image")

    image = scenario.cast_and_resolve(
        "Phantasmal Image", *scenario.untapped_sources("Island", "Island", username="alice")
    )

    characteristics = scenario.game.characteristics_of(image)
    assert characteristics.name == "Serra Angel"
    assert (characteristics.power, characteristics.toughness) == (4, 4)
    assert "Angel" in characteristics.subtypes and "Illusion" in characteristics.subtypes
    assert "Flying" in characteristics.abilities
    assert PHANTASMAL_TRIGGER in characteristics.abilities
    # The copied Serra Angel itself gained nothing.
    angel_characteristics = scenario.game.characteristics_of(angel)
    assert "Illusion" not in angel_characteristics.subtypes
    assert PHANTASMAL_TRIGGER not in angel_characteristics.abilities
    assert scenario.game.unreadable_copy_exception_notices == []


def test_targeting_the_image_triggers_its_granted_sacrifice():
    """The granted ability works: bob's Giant Growth aimed at the
    Image-as-Angel triggers it, the trigger goes on the stack above the pump,
    and the Image is sacrificed before the pump resolves - which then has no
    legal target left."""
    scenario = _phantasmal_board()
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(angel, username="alice", source="Phantasmal Image")
    image = scenario.cast_and_resolve(
        "Phantasmal Image", *scenario.untapped_sources("Island", "Island", username="alice")
    )
    scenario.pass_priority("alice")
    (forest,) = scenario.untapped_sources("Forest", username="bob")

    growth = scenario.cast_onto_stack("Giant Growth", forest, username="bob", targets=[image])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names()[-1] != "Giant Growth"
    scenario.resolve_top()
    assert image.zone is Zone.GRAVEYARD
    assert image.owner == "alice"
    scenario.resolve_top()
    assert growth.zone is Zone.GRAVEYARD
    # The copied Serra Angel was never the target and is untouched.
    assert angel.zone is Zone.BATTLEFIELD


def test_a_clone_of_the_image_keeps_the_illusion_type_and_the_trigger():
    """CR 707.9a: the granted ability is part of the Image's copiable values,
    so Clone copying Image-as-Angel is an Illusion Angel with the trigger."""
    scenario = _phantasmal_board("Clone")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(angel, username="alice", source="Phantasmal Image")
    image = scenario.cast_and_resolve(
        "Phantasmal Image", *scenario.untapped_sources("Island", "Island", username="alice")
    )
    scenario.will_choose_cards(image, username="alice", source="Clone")

    clone = scenario.cast_and_resolve(
        "Clone", *scenario.untapped_sources(*["Island"] * 4, username="alice")
    )

    characteristics = scenario.game.characteristics_of(clone)
    assert characteristics.name == "Serra Angel"
    assert "Illusion" in characteristics.subtypes
    assert PHANTASMAL_TRIGGER in characteristics.abilities


# --------------------------------------------------------------------------
# The candidate filter: Clever Impersonator's "any nonland permanent"
# --------------------------------------------------------------------------


def test_clever_impersonator_offers_every_nonland_permanent_and_no_land():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Clever Impersonator"],
            battlefield=["Island", "Island", "Island", "Island", "Glorious Anthem"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Chalice of the Void", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    chalice = scenario.find("Chalice of the Void", Zone.BATTLEFIELD, "bob")
    lands = [state for state in scenario.game.battlefield if "Land" in state.card.type_line]
    scenario.will_choose_cards(anthem, username="alice", source="Clever Impersonator")

    impersonator = scenario.cast_and_resolve(
        "Clever Impersonator", *scenario.untapped_sources(*["Island"] * 4, username="alice")
    )

    (question,) = _copy_questions(scenario, "Clever Impersonator")
    assert set(question.cards) == {anthem.id, bears.id, chalice.id}
    assert not {land.id for land in lands} & set(question.cards)
    characteristics = scenario.game.characteristics_of(impersonator)
    assert characteristics.name == "Glorious Anthem"
    # A copy of an anthem is an anthem: bob's Bears are not alice's, but
    # alice's own creatures would get +2/+2 from two anthems. The copy is an
    # enchantment and no longer a creature.
    assert "Creature" not in [str(t) for t in characteristics.types]


def test_clever_impersonator_with_only_lands_enters_as_itself():
    scenario = (
        Scenario()
        .player("alice", hand=["Clever Impersonator"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    impersonator = scenario.cast_and_resolve(
        "Clever Impersonator", *scenario.untapped_sources(*["Island"] * 4, username="alice")
    )

    assert _copy_questions(scenario, "Clever Impersonator") == []
    assert scenario.game.characteristics_of(impersonator).name == "Clever Impersonator"


# --------------------------------------------------------------------------
# Fail closed, still, for a tail that is not a readable exception
# --------------------------------------------------------------------------


def test_an_unreadable_tail_still_notices_and_enters_as_itself():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sakashima of a Thousand Faces"],
            battlefield=["Island", "Island", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sakashima = scenario.cast_and_resolve(
        "Sakashima of a Thousand Faces",
        *scenario.untapped_sources(*["Island"] * 4, username="alice"),
    )

    assert scenario.game.characteristics_of(sakashima).name == "Sakashima of a Thousand Faces"
    notices = scenario.game.unreadable_copy_exception_notices
    assert len(notices) == 1
    assert isinstance(notices[0], UnreadableCopyExceptionNotice)
    assert notices[0].text == "it has Sakashima's other abilities"

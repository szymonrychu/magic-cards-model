"""Multiversal Passage: a land that chooses its own basic land type as it
enters, then optionally pays life to enter untapped.

    "As this land enters, choose a basic land type. Then you may pay 2 life.
    If you don't, it enters tapped."
    "This land is the chosen type."

Two CR 614.12a choices share one entrance: which basic land type (a fifth
"as [this] enters, choose ..." shape alongside color/card name/creature
type/odd-or-even), and the shockland-shaped optional payment - here spread
over "Then you may pay 2 life." rather than fused into the leading "As this
land enters, ..." clause, because that clause is already spent on the type
choice. The second printed sentence, "This land is the chosen type.", reads
the first choice back as a CR 613.1d layer 4 type-setting effect (CR 305.7),
scoped to this one permanent - the identical modification Blood Moon's own
board-wide effect already gives every nonbasic land, over `_only(source.id)`
instead of a selector that reaches the whole battlefield.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 614.1c** - "As [this permanent] enters . . . ," and "[This permanent]
  enters with . . . ," are both replacement effects of this one shape.
- **CR 614.12** / **CR 614.12a** - such an effect comes from the permanent
  itself, applies before it is on the battlefield, and a choice it requires
  is made then, not later.
- **CR 305.6** - the five basic land types, and the intrinsic mana ability
  each one carries "even if the text box doesn't actually contain that
  text".
- **CR 305.7** - "If an effect sets a land's subtype to one or more of the
  basic land types, the land no longer has its old land type. It loses all
  abilities generated from its rules text ... and it gains the appropriate
  mana ability for each new basic land type."
- **CR 205.4c** - "basic" is the land supertype, not one of the five types.
- **CR 119.4** - paying life is refused below the life total.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.layers import BASIC_LAND_TYPES
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario

PASSAGE = "Multiversal Passage"


def _board(battlefield=()):
    scenario = Scenario().player("alice", hand=[PASSAGE], battlefield=list(battlefield)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _quality_questions(scenario, source: str):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_A_QUALITY and decision.source == source
    ]


# --------------------------------------------------------------------------
# The choice itself - only CR 305.6's five basic land types are legal
# --------------------------------------------------------------------------


def test_multiversal_passage_offers_only_the_five_basic_land_types():
    scenario = _board()
    scenario.will_choose("Island", source=PASSAGE)
    scenario.will_pay_the_life(True)

    scenario.play_land(PASSAGE)

    (question,) = _quality_questions(scenario, PASSAGE)
    assert question.options == tuple(BASIC_LAND_TYPES)


def test_choosing_a_basic_land_type_is_recorded_on_the_permanent():
    scenario = _board()
    scenario.will_choose("Swamp", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)

    assert passage.choice == Choice(kind=ChoiceKind.BASIC_LAND_TYPE, value="Swamp")


# --------------------------------------------------------------------------
# "This land is the chosen type." - CR 305.7's setting effect
# --------------------------------------------------------------------------


def test_the_land_becomes_the_chosen_type_and_gains_its_mana_ability():
    scenario = _board()
    scenario.will_choose("Forest", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)
    characteristics = scenario.game.computed_board().of(passage)

    assert characteristics.subtypes == ("Forest",)
    assert characteristics.abilities == ("{T}: Add {G}.",)


def test_a_different_chosen_type_gives_a_different_mana_ability():
    scenario = _board()
    scenario.will_choose("Mountain", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)
    characteristics = scenario.game.computed_board().of(passage)

    assert characteristics.subtypes == ("Mountain",)
    assert characteristics.abilities == ("{T}: Add {R}.",)


def test_the_land_does_not_gain_the_basic_supertype():
    """CR 205.4c: setting the subtype never adds the "basic" supertype -
    Multiversal Passage is still a nonbasic land that merely reads as a
    Plains/Island/etc."""
    scenario = _board()
    scenario.will_choose("Plains", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)
    characteristics = scenario.game.computed_board().of(passage)

    assert not characteristics.is_basic


# --------------------------------------------------------------------------
# "Then you may pay 2 life. If you don't, it enters tapped." - the second,
# separately-worded CR 614.12a choice, paired back up by
# `_self_enters_modifiers` even though it is not fused into the leading
# "As this land enters, ..." clause.
# --------------------------------------------------------------------------


def test_paying_the_life_lets_it_enter_untapped():
    scenario = _board()
    scenario.will_choose("Island", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)

    assert not passage.tapped
    assert scenario.player("alice").life == 18


def test_declining_the_life_taps_it():
    scenario = _board()
    scenario.will_choose("Island", source=PASSAGE)
    scenario.will_pay_the_life(False)

    passage = scenario.play_land(PASSAGE)

    assert passage.tapped
    assert scenario.player("alice").life == 20


def test_a_life_total_too_low_to_pay_still_enters_tapped():
    """CR 119.4: paying is refused below the life total, so the choice never
    actually reaches the player - it enters tapped without anyone having
    decided anything, the same as an unaffordable shockland payment."""
    scenario = _board()
    scenario.player("alice").life = 1
    scenario.will_choose("Island", source=PASSAGE)

    passage = scenario.play_land(PASSAGE)

    assert passage.tapped
    assert scenario.player("alice").life == 1


def test_the_land_is_the_chosen_type_whichever_way_the_payment_goes():
    """The two CR 614.12a choices are independent of each other."""
    scenario = _board()
    scenario.will_choose("Swamp", source=PASSAGE)
    scenario.will_pay_the_life(False)

    passage = scenario.play_land(PASSAGE)
    characteristics = scenario.game.computed_board().of(passage)

    assert passage.tapped
    assert characteristics.subtypes == ("Swamp",)


def test_multiversal_passage_still_produces_no_mana_of_the_old_land_type():
    """CR 305.7: the land "loses all abilities generated from its rules
    text [and] its old land types" - Multiversal Passage prints none of its
    own to begin with, so the chosen type's mana ability is the *only* one
    it ever has, not an addition to some unprinted default."""
    scenario = _board()
    scenario.will_choose("Island", source=PASSAGE)
    scenario.will_pay_the_life(True)

    passage = scenario.play_land(PASSAGE)
    characteristics = scenario.game.computed_board().of(passage)

    assert characteristics.abilities == ("{T}: Add {U}.",)

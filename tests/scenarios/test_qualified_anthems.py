"""Scenario: an anthem whose subject is narrowed by a qualifier.

`machines/layers.py` read "[other] creatures [you control|your opponents
control]" and nothing else, so six printings in the pool carried a real static
ability that the engine did not do and did not report:

- **Angel of Jubilation**, "Other nonblack creatures you control get +1/+1." -
  a colour negation.
- **Caretaker's Talent**, "Creature tokens you control get +2/+2." - CR 111.1's
  token/card split.
- **Fecund Greenshell**, "As long as you control ten or more lands, creatures
  you control get +2/+2." - a whole-board condition.
- **Aang, Destined Savior**, "Land creatures you control have vigilance." - two
  card types at once.
- **Leyline of the Guildpact**, "Each nonland permanent you control is all
  colors." - layer 5.
- **Ygra, Eater of All**, "Other creatures are Food artifacts in addition to
  their other types and have '...'" - a board-wide type grant with a quoted
  ability riding along.

The rules the qualifiers rest on:

- **CR 105.2** - "An object can be one or more of the five colors, or it can be
  no color at all", which is what makes "nonblack" a question about the colours
  an object has rather than a list of the other four.
- **CR 111.1** - "A token is a marker used to represent any permanent that isn't
  represented by a card." Not a characteristic, which is why it rides on
  `Characteristics.is_token`.
- **CR 205.2b** - "Some objects have more than one card type ... Such objects
  satisfy the criteria for any effect that applies to any of their card types" -
  a land creature is both.
- **CR 604.2** - a static ability's effects "are active as long as the permanent
  with the ability remains on the battlefield and has the ability", and
  **CR 611.3a** - such an effect "isn't 'locked in'; it applies at any given
  moment to whatever its text indicates". Together they are why the board
  condition is re-asked on every computation instead of stored with a duration.
- **CR 613.5** - the board is recomputed continually, which is what "re-asked"
  means in practice.
- **CR 613.4c** for the +N/+N, **CR 613.1f** for the keyword grants,
  **CR 613.1d** with **CR 205.1b** for Ygra's added types, **CR 613.1e** for
  Leyline of the Guildpact's colours, **CR 113.10a** for its quoted ability.
- **CR 613.3** - "Within layers 2-6, apply effects from characteristic-defining
  abilities first ... then all other effects in timestamp order", and
  **CR 613.7a** gives a static ability's effect the timestamp of the object it
  is on. Nothing here needs a tie broken, because no two of these six write the
  same characteristic of the same object.
- **CR 716.2a** gates a Class's later paragraphs behind its level, which is why
  Caretaker's Talent's anthem is not read off a level-1 Class.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.cards import card_state
from tests.scenarios.harness import Scenario

#: A 1/1 white Soldier, the shape a dozen real cards make. Its characteristics
#: are the ones the creating effect states (CR 111.3); it is a token because
#: nothing represents it as a card (CR 111.1).
SOLDIER = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller)


def board_of(*permanents):
    """The characteristics of a battlefield with only its static abilities
    applied - CR 613.7a's timestamp order is the argument order."""
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# --------------------------------------------------------------------------
# "Other nonblack creatures you control" (Angel of Jubilation)
# --------------------------------------------------------------------------


def test_angel_of_jubilation_pumps_a_nonblack_creature_you_control():
    """The half that has to work before the exclusions mean anything.

    Grizzly Bears is green, so it is nonblack (CR 105.2), and the +1/+1 is
    sublayer 7c (CR 613.4c).
    """
    angel = permanent("Angel of Jubilation")
    bears = permanent("Grizzly Bears")

    assert board_of(angel, bears).of(bears).power_toughness == (3, 3)


def test_angel_of_jubilation_leaves_a_black_creature_alone():
    """ "nonblack" excludes exactly the objects that are black.

    Faerie Macabre is a mono-black 2/2 (`resolve_cards`), so it is outside the
    subject and stays a 2/2 while the green Bear next to it grows.
    """
    angel = permanent("Angel of Jubilation")
    bears = permanent("Grizzly Bears")
    faerie = permanent("Faerie Macabre")

    board = board_of(angel, bears, faerie)
    assert board.of(bears).power_toughness == (3, 3)
    assert board.of(faerie).power_toughness == (2, 2), "black is not nonblack"


def test_angel_of_jubilation_does_not_pump_itself():
    """ "Other" is an identity test, not a colour one.

    The Angel is white - nonblack, and a creature its controller controls - so
    the only thing keeping it out of its own anthem is the word "other". A 3/3
    stays a 3/3.
    """
    angel = permanent("Angel of Jubilation")

    assert board_of(angel).of(angel).power_toughness == (3, 3)


def test_angel_of_jubilation_does_not_pump_an_opponents_creature():
    """ "you control" survives the qualifier being added in front of it."""
    angel = permanent("Angel of Jubilation")
    theirs = permanent("Grizzly Bears", controller="bob")

    assert board_of(angel, theirs).of(theirs).power_toughness == (2, 2)


# --------------------------------------------------------------------------
# "As long as you control ten or more lands" (Fecund Greenshell)
# --------------------------------------------------------------------------


def greenshell_board(lands: int) -> list:
    return [permanent("Fecund Greenshell"), permanent("Grizzly Bears")] + [
        permanent("Forest") for _ in range(lands)
    ]


def test_fecund_greenshell_pumps_the_team_once_the_tenth_land_is_there():
    """Fecund Greenshell: "As long as you control ten or more lands, creatures
    you control get +2/+2."

    The condition is counted off the board when the board is computed
    (CR 611.3a, CR 613.5), not stored with a duration. At ten lands the Bear is
    a 4/4 and the Turtle - itself a creature its controller controls, with no
    "other" in the sentence - is a 6/8.
    """
    permanents = greenshell_board(10)
    board = board_of(*permanents)
    greenshell, bears = permanents[0], permanents[1]

    assert board.of(bears).power_toughness == (4, 4)
    assert board.of(greenshell).power_toughness == (6, 8), "no 'other' in the sentence"


def test_fecund_greenshell_does_nothing_at_nine_lands():
    """One short is not "ten or more". The anthem is simply absent - not
    present-and-zero - which is what makes the next test possible.
    """
    permanents = greenshell_board(9)
    board = board_of(*permanents)
    greenshell, bears = permanents[0], permanents[1]

    assert board.of(bears).power_toughness == (2, 2)
    assert board.of(greenshell).power_toughness == (4, 6)


def test_the_gate_turns_off_again_when_a_land_leaves():
    """CR 604.2 and CR 611.3a: the condition is a live question, so an anthem
    that was on goes off the moment the board stops satisfying it - the case a
    condition frozen at the time the permanent entered would get wrong.
    """
    permanents = greenshell_board(10)
    bears = permanents[1]
    assert board_of(*permanents).of(bears).power_toughness == (4, 4)

    permanents.pop()  # one Forest leaves the battlefield

    assert board_of(*permanents).of(bears).power_toughness == (2, 2)


def test_the_gate_counts_only_the_lands_its_own_controller_has():
    """ "you control" - an opponent's ten lands do not turn it on."""
    permanents = [
        permanent("Fecund Greenshell"),
        permanent("Grizzly Bears"),
        *[permanent("Forest", controller="bob") for _ in range(10)],
    ]

    assert board_of(*permanents).of(permanents[1]).power_toughness == (2, 2)


# --------------------------------------------------------------------------
# "Creature tokens you control" (Caretaker's Talent, level 3)
# --------------------------------------------------------------------------


def talent_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Caretaker's Talent", "Grizzly Bears"])
        .player("bob")
    )


def test_caretakers_talent_at_level_three_pumps_tokens_only():
    """Caretaker's Talent's level-3 ability: "Creature tokens you control get
    +2/+2."

    CR 111.1 splits a token from a card, and nothing else about the two
    creatures differs: the Soldier token grows and the Grizzly Bears card does
    not.
    """
    scenario = talent_board().build()
    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")
    talent.class_level = 3
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    board = board_of(talent, soldier, bears)
    assert board.of(soldier).power_toughness == (3, 3)
    assert board.of(bears).power_toughness == (2, 2), "a card is not a token"


def test_caretakers_talent_grants_nothing_before_level_three():
    """CR 716.2a: a Class's paragraph belongs to the level it is printed under,
    so a level-2 Class does not have the level-3 ability at all.
    """
    scenario = talent_board().build()
    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")
    talent.class_level = 2
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")

    assert board_of(talent, soldier).of(soldier).power_toughness == (1, 1)


def test_caretakers_talent_does_not_pump_an_opponents_token():
    scenario = talent_board().build()
    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")
    talent.class_level = 3
    (theirs,) = create_tokens(scenario.game, SOLDIER, "bob")

    assert board_of(talent, theirs).of(theirs).power_toughness == (1, 1)


# --------------------------------------------------------------------------
# "Land creatures you control" (Aang, Destined Savior)
# --------------------------------------------------------------------------


def transformed_aang():
    aang = permanent("Aang, at the Crossroads")
    aang.transform()  # CR 712.8e: the back face is the one that has this ability
    return aang


def test_aang_grants_vigilance_to_a_land_creature():
    """Aang, Destined Savior: "Land creatures you control have vigilance."

    Dryad Arbor is a printed Land Creature (CR 205.2b: an object with more than
    one card type satisfies an effect that applies to any of them), so it is in
    the subject and the grant is layer 6 (CR 613.1f).
    """
    aang = transformed_aang()
    arbor = permanent("Dryad Arbor")

    assert board_of(aang, arbor).of(arbor).has_ability("Vigilance")


def test_aang_does_not_grant_vigilance_to_a_creature_that_is_not_a_land():
    aang = transformed_aang()
    bears = permanent("Grizzly Bears")

    assert not board_of(aang, bears).of(bears).has_ability("Vigilance")


def test_aang_does_not_grant_vigilance_to_a_land_that_is_not_a_creature():
    """Both halves of "land creature" are required; a plain Forest is neither
    in the subject nor changed by it.
    """
    aang = transformed_aang()
    forest = permanent("Forest")

    assert not board_of(aang, forest).of(forest).has_ability("Vigilance")


def test_aang_does_not_grant_vigilance_to_an_opponents_land_creature():
    aang = transformed_aang()
    theirs = permanent("Dryad Arbor", controller="bob")

    assert not board_of(aang, theirs).of(theirs).has_ability("Vigilance")


# --------------------------------------------------------------------------
# "Each nonland permanent you control is all colors" (Leyline of the Guildpact)
# --------------------------------------------------------------------------


FIVE_COLORS = {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}


def test_leyline_of_the_guildpact_makes_your_nonland_permanents_every_colour():
    """Layer 5 (CR 613.1e), setting rather than adding: a mono-green Bear ends
    up all five colours (CR 105.1's five).
    """
    leyline = permanent("Leyline of the Guildpact")
    bears = permanent("Grizzly Bears")

    assert set(board_of(leyline, bears).of(bears).colors) == FIVE_COLORS


def test_leyline_of_the_guildpact_leaves_your_lands_colourless():
    """ "nonland" excludes them - and the Leyline's *other* line is what
    changes a land, giving it every basic land type in layer 4 (CR 613.1d)
    rather than a colour in layer 5.
    """
    leyline = permanent("Leyline of the Guildpact")
    forest = permanent("Forest")

    board = board_of(leyline, forest)
    assert set(board.of(forest).colors) != FIVE_COLORS
    assert "Island" in board.of(forest).subtypes, "the other line still applies"


def test_leyline_of_the_guildpact_does_not_recolour_an_opponents_permanent():
    leyline = permanent("Leyline of the Guildpact")
    theirs = permanent("Grizzly Bears", controller="bob")

    assert set(board_of(leyline, theirs).of(theirs).colors) == {Color.GREEN}


def test_a_land_creature_is_still_a_land_for_the_leyline():
    """CR 205.2b again, this time keeping something *out*: Dryad Arbor is a
    creature, but it is also a land, so "nonland permanent" does not reach it.
    Read off the computed board, so layer 4 has already had its say.
    """
    leyline = permanent("Leyline of the Guildpact")
    arbor = permanent("Dryad Arbor")

    assert set(board_of(leyline, arbor).of(arbor).colors) == {Color.GREEN}


# --------------------------------------------------------------------------
# "Other creatures are Food artifacts ... and have '...'" (Ygra, Eater of All)
# --------------------------------------------------------------------------


YGRA_ABILITY = "{2}, {T}, Sacrifice this permanent: You gain 3 life."


def test_ygra_turns_every_other_creature_into_a_food_artifact():
    """Ygra, Eater of All: "Other creatures are Food artifacts in addition to
    their other types and have "{2}, {T}, Sacrifice this permanent: You gain 3
    life.""

    Layer 4 adds the artifact card type and the Food subtype and keeps
    everything printed (CR 613.1d, CR 205.1b); layer 6 adds the quoted ability
    (CR 613.1f, CR 113.10a). No controller is named, so an opponent's creature
    is caught too.
    """
    ygra = permanent("Ygra, Eater of All")
    bears = permanent("Grizzly Bears")
    theirs = permanent("Savannah Lions", controller="bob")

    board = board_of(ygra, bears, theirs)
    for creature in (bears, theirs):
        assert Type.ARTIFACT in board.of(creature).types
        assert Type.CREATURE in board.of(creature).types, "CR 205.1b keeps the old type"
        assert "Food" in board.of(creature).subtypes
        assert board.of(creature).has_ability(YGRA_ABILITY)


def test_ygra_is_not_food_itself():
    """ "Other" - and it matters, because Ygra's own ward cost is sacrificing a
    Food and its trigger counts Food hitting a graveyard.
    """
    ygra = permanent("Ygra, Eater of All")
    bears = permanent("Grizzly Bears")

    board = board_of(ygra, bears)
    assert "Food" not in board.of(ygra).subtypes
    assert Type.ARTIFACT not in board.of(ygra).types
    assert not board.of(ygra).has_ability(YGRA_ABILITY)


def test_ygra_makes_the_granted_ability_activatable():
    """The quoted line reaches `Game.activated_abilities` as a real ability, not
    only the computed characteristics (CR 113.10a).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ygra, Eater of All", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    static_effects(scenario.game.battlefield)

    (granted,) = scenario.game.activated_abilities(bears)
    assert granted.cost == "{2}, {T}, Sacrifice this permanent"
    assert granted.effect == "You gain 3 life."


def test_ygra_leaving_takes_the_granted_ability_back_off():
    """CR 604.2: the grant lasts only while Ygra is on the battlefield with the
    ability, so the stored text is reconciled away rather than left behind.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ygra, Eater of All", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    ygra = scenario.creature("Ygra, Eater of All", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    static_effects(scenario.game.battlefield)
    assert bears.granted_ability_texts == (YGRA_ABILITY,)

    scenario.game.destroy(ygra)
    static_effects(scenario.game.battlefield)

    assert bears.granted_ability_texts == ()
    assert scenario.game.activated_abilities(bears) == []

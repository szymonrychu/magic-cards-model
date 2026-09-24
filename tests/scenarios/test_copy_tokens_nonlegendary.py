"""Token copies (CR 707.2, CR 111.1) with a CR 707.9b exception, and a
token that "becomes a creature" if the copy is not one.

- Multiversal Incursion: "For each nontoken creature you control, create a
  token that's a copy of that creature, except it isn't legendary."
- Ultron, Artificial Malevolence: "Whenever another nontoken artifact you
  control enters, you may pay {2}. If you do, create a token that's a copy
  of it. If the token isn't a creature, it becomes a 2/2 Robot Villain
  creature in addition to its other types." - CR 118.12's "if you do", then
  a layer 4 type addition (CR 205.1b) and a sublayer 7b base P/T (CR 613.4b)
  on the token only when it is not already a creature.

Off-set proof (legal, in no deck list):

- Tawnos's Tinkering: "Put two +1/+1 counters on target artifact, creature,
  or land you control. Untap that permanent. If it isn't a creature, it
  becomes a 0/0 creature in addition to its other types." - the same "if it
  isn't a creature, it becomes an N/N creature" rider, after a targeted
  spell instead of a token.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

INCURSION = "Multiversal Incursion"
ULTRON = "Ultron, Artificial Malevolence"


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _tokens(scenario, name):
    return [card for card in scenario.game.battlefield if card.name == name and card.token]


# -- Multiversal Incursion -------------------------------------------------------------


def _incursion_board(alice, bob=()):
    return (
        Scenario()
        .player("alice", hand=[INCURSION], battlefield=list(alice) + ["Island"] * 7)
        .player("bob", battlefield=list(bob))
        .build()
    )


def test_multiversal_incursion_copies_each_nontoken_creature_nonlegendary():
    scenario = _incursion_board(["Absorbing Man", "Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(INCURSION, *scenario.untapped_sources(*["Island"] * 7))
    scenario.state_based_actions()

    (man_token,) = _tokens(scenario, "Absorbing Man")
    assert Supertype.LEGENDARY not in _chars(scenario, man_token).supertypes
    assert len(_tokens(scenario, "Grizzly Bears")) == 1
    assert not _tokens(scenario, "Hill Giant")  # not alice's
    # The legendary original is still there: the copy is not legendary.
    assert [c for c in scenario.game.battlefield if c.name == "Absorbing Man" and not c.token]


def test_multiversal_incursion_does_not_copy_tokens():
    """Cast twice: the second copies the nontoken Bears only, not the token
    the first made."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[INCURSION, INCURSION], battlefield=["Grizzly Bears"] + ["Island"] * 14
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(INCURSION, *scenario.untapped_sources(*["Island"] * 7))
    scenario.cast_and_resolve(INCURSION, *scenario.untapped_sources(*["Island"] * 7))

    assert len(_tokens(scenario, "Grizzly Bears")) == 2


# -- Ultron, Artificial Malevolence ------------------------------------------------------


def _ultron_board(hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[ULTRON, "Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _artifact_enters(scenario, name, *, pay):
    if pay:
        scenario.will_pay_the_mana_cost(sources=scenario.untapped_sources("Island", "Island"))
    else:
        scenario.will_pay_the_mana_cost(False)
    entered = scenario.put_onto_battlefield(name, "alice")
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()
    return entered


def test_ultron_copies_a_noncreature_artifact_into_a_robot_villain():
    scenario = _ultron_board(["Mind Stone"])

    _artifact_enters(scenario, "Mind Stone", pay=True)

    (token,) = _tokens(scenario, "Mind Stone")
    chars = _chars(scenario, token)
    assert Type.ARTIFACT in chars.types and Type.CREATURE in chars.types
    assert {"Robot", "Villain"} <= set(chars.subtypes)
    assert chars.power_toughness == (2, 2)
    assert any("Add {C}" in line for line in chars.abilities)


def test_ultron_copy_of_an_artifact_creature_stays_what_it_is():
    scenario = _ultron_board(["Ornithopter"])

    _artifact_enters(scenario, "Ornithopter", pay=True)

    (token,) = _tokens(scenario, "Ornithopter")
    chars = _chars(scenario, token)
    assert chars.power_toughness == (0, 2)
    assert "Robot" not in chars.subtypes


def test_ultron_without_payment_makes_nothing():
    scenario = _ultron_board(["Mind Stone"])

    _artifact_enters(scenario, "Mind Stone", pay=False)

    assert not _tokens(scenario, "Mind Stone")


def test_ultrons_token_entering_does_not_trigger_it_again():
    """ "nontoken artifact" - the token copy is a token."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Stone"],
            battlefield=[ULTRON] + ["Island"] * 4,
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_mana_cost(True, times=None)

    scenario.put_onto_battlefield("Mind Stone", "alice")
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()

    assert len(_tokens(scenario, "Mind Stone")) == 1


# -- Tawnos's Tinkering (off-set proof) ----------------------------------------------------


def test_tawnoss_tinkering_animates_a_noncreature_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tawnos's Tinkering"],
            battlefield=["Mind Stone", "Forest", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    stone.tap()

    scenario.cast_and_resolve(
        "Tawnos's Tinkering",
        *scenario.untapped_sources("Forest", "Island", "Island", "Island"),
        targets=[stone],
    )

    assert not stone.tapped
    assert stone.counters[Counter.PLUS_ONE] == 2
    chars = _chars(scenario, stone)
    assert Type.CREATURE in chars.types and Type.ARTIFACT in chars.types
    assert chars.power_toughness == (2, 2)


def test_tawnoss_tinkering_on_a_creature_only_adds_counters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tawnos's Tinkering"],
            battlefield=["Grizzly Bears", "Forest", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Tawnos's Tinkering",
        *scenario.untapped_sources("Forest", "Island", "Island", "Island"),
        targets=[bears],
    )

    assert _chars(scenario, bears).power_toughness == (4, 4)

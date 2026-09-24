""" "When this creature dies, reveal the top card of your library. You may put
that card onto the battlefield if it's a permanent card with mana value 3 or
less. Otherwise, put that card into your hand." - Matter Reshaper.

CR 701.20a: "To reveal a card, show that card to all players for a brief
time." Revealing is not a zone change; the card stays on top of the library
until the instruction moves it.

CR 202.3: "The mana value of an object is a number equal to the total amount
of mana in its mana cost" - read off the card in the library, so a land's is
0 and Thought-Knot Seer's is 4. "Otherwise" covers both the card failing the condition and
the player declining the "you may" (the ruling: "If you don't put the card
onto the battlefield for any reason, you put the card into your hand.").

CR 303.4f: "If an Aura is entering the battlefield under a player's control by
any means other than by resolving as an Aura spell, and the effect putting it
onto the battlefield doesn't specify the object or player the Aura will
enchant, that player chooses what it will enchant as the Aura enters the
battlefield. The player must choose a legal object or player according to the
Aura's enchant ability and any other applicable effects." An Aura with
nothing legal to enchant cannot be put onto the battlefield, so it goes to
the hand instead.

The reader is the same one Coiling Oracle's and Skyward Eye Prophets's
"reveal the top card ... If it's a land card, put it onto the battlefield.
Otherwise, put it into your hand." go through; the CR 303.4f Aura choice it
now makes is proved on Aid from the Cowl's differently worded "If it's a
permanent card, you may put it onto the battlefield." (Modern and Pioneer
legal, in no api deck). Skyward Eye Prophets (Modern legal, in no api deck)
proves the widened reader still reads the "If it's a <kind> card" shape.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

RESHAPER = "Matter Reshaper"
PROPHETS = "Skyward Eye Prophets"
COWL = "Aid from the Cowl"


def _reshaper_dies(library: list[str], battlefield: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", library=library, battlefield=[RESHAPER, *(battlefield or [])])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature(RESHAPER))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{RESHAPER}'s triggered ability"]
    return scenario


def test_matter_reshaper_is_fully_supported() -> None:
    statuses = {clause.status for clause in card_support(card(RESHAPER)).clauses}
    assert statuses == {"handled"}, card_support(card(RESHAPER)).clauses


def test_a_cheap_permanent_may_go_onto_the_battlefield() -> None:
    scenario = _reshaper_dies(["Grizzly Bears", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True)

    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"


def test_declining_puts_it_into_the_hand() -> None:
    """ "Otherwise" is also the declined "you may" - the ruling: "If you
    don't put the card onto the battlefield for any reason, you put the card
    into your hand.\""""
    scenario = _reshaper_dies(["Grizzly Bears", "Island"])
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(False)

    scenario.resolve_top()

    assert bears.zone is Zone.HAND


def test_a_permanent_with_mana_value_four_goes_to_hand_unasked() -> None:
    """CR 202.3: Thought-Knot Seer's mana value is 4, over the limit - no
    question, straight to hand."""
    scenario = _reshaper_dies(["Thought-Knot Seer", "Island"])
    seer = scenario.find("Thought-Knot Seer", Zone.LIBRARY, "alice")
    asked = len(scenario.questions_asked())

    scenario.resolve_top()

    assert seer.zone is Zone.HAND
    assert len(scenario.questions_asked()) == asked


def test_a_nonpermanent_card_goes_to_hand() -> None:
    scenario = _reshaper_dies(["Lightning Bolt", "Island"])
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")

    scenario.resolve_top()

    assert bolt.zone is Zone.HAND


def test_a_land_is_a_permanent_card_with_mana_value_zero() -> None:
    scenario = _reshaper_dies(["Island", "Mountain"])
    island = scenario.player("alice").library[0]
    scenario.will_take_the_may(True)

    scenario.resolve_top()

    assert island.zone is Zone.BATTLEFIELD


def test_an_empty_library_does_nothing() -> None:
    """CR 609.3's "does only as much as possible": no top card, nothing to
    reveal or move."""
    scenario = _reshaper_dies([])

    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []


def test_an_aura_enters_attached_to_the_creature_its_controller_chooses() -> None:
    """CR 303.4f: Rancor put onto the battlefield without being cast is
    attached to a creature its controller chooses as it enters."""
    scenario = _reshaper_dies(["Rancor", "Island"], battlefield=["Grizzly Bears"])
    rancor = scenario.find("Rancor", Zone.LIBRARY, "alice")
    bears = scenario.creature("Grizzly Bears")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(bears)

    scenario.resolve_top()
    scenario.state_based_actions()

    assert rancor.zone is Zone.BATTLEFIELD
    assert rancor.attached_to == bears.id
    assert bears.power == 4


def test_an_aura_with_nothing_to_enchant_goes_to_hand() -> None:
    """CR 303.4f: with no creature on the battlefield Rancor cannot enter at
    all, so the "otherwise" arm puts it into the hand."""
    scenario = _reshaper_dies(["Rancor", "Island"])
    rancor = scenario.find("Rancor", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, times=None)

    scenario.resolve_top()

    assert rancor.zone is Zone.HAND


def test_the_proof_printing_reads_the_if_its_a_land_shape() -> None:
    """Skyward Eye Prophets through the widened reader: a land goes onto the
    battlefield, anything else into the hand."""
    scenario = (
        Scenario()
        .player("alice", library=["Island", "Lightning Bolt"], battlefield=[PROPHETS])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prophets = scenario.creature(PROPHETS)
    prophets.summoning_sick = False
    island, bolt = scenario.player("alice").library[:2]

    scenario.activate(prophets)
    scenario.resolve_top()
    assert island.zone is Zone.BATTLEFIELD

    prophets.tapped = False
    scenario.activate(prophets)
    scenario.resolve_top()
    assert bolt.zone is Zone.HAND


def test_aid_from_the_cowl_attaches_an_aura_it_puts_onto_the_battlefield() -> None:
    """The proof printing for the CR 303.4f half: Aid from the Cowl's revolt
    trigger reveals Rancor, and the Aura enters attached to a chosen
    creature rather than falling off to CR 704.5m."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Rancor", "Island"],
            battlefield=[COWL, "Grizzly Bears", "Memnite"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    rancor = scenario.find("Rancor", Zone.LIBRARY, "alice")
    scenario.game.sacrifice(scenario.creature("Memnite"))  # CR 207.2c's revolt
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(bears)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{COWL}'s triggered ability"]
    scenario.resolve_top()
    scenario.state_based_actions()

    assert rancor.zone is Zone.BATTLEFIELD
    assert rancor.attached_to == bears.id

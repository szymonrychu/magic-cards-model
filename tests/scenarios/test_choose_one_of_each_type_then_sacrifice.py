"""Scenario: "Each opponent chooses [one of each of several types] from among
the nonland permanents they control, then sacrifices the rest" (CR 701.21a
sacrifice, CR 107.1a "an artifact" naming a permanent type, CR 601.7a/602.3a
"the opponent" as the one who chooses).

Ajani, Nacatl Avenger's own `−4` is the vehicle: "Each opponent chooses an
artifact, a creature, an enchantment, and a planeswalker from among the
nonland permanents they control, then sacrifices the rest." Verified against
`resolve_cards` this session.

`_parse_each_opponent_choose_one_of_each_type_then_sacrifice`
(`machines/effects.py`) reads the shape generally, on the type list rather
than any card name - a future card printing the identical sentence with a
different mix of types reads the same way, with no registry row for either.

Two traps this file exists to catch:

- **The choice, and the permanents, belong to the opponent** - not to Ajani's
  own controller. Getting this backwards is invisible in a test where the
  activating player controls everything on the board, so every scenario here
  gives Ajani's controller nothing else to confuse the two with.
- **An opponent with none of a type keeps nothing of that type** - the
  ability does not require one of each to exist, and must not raise or
  silently invent one.

Ajani, Nacatl Pariah enters transformed at 3 loyalty (CR 306.5b), one short of
paying `−4` on the turn he flips - `add_counters` staging him up to 4 is the
same kind of setup a rigged library is for a search effect, not a mock: every
card and every choice made afterward is real.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _flip_and_charge_ajani(scenario: Scenario) -> CardState:
    """Ajani, Nacatl Pariah, transformed and given the loyalty to pay `−4`
    the same turn - `Counter.LOYALTY` staging stands in for "a turn already
    passed with him at 7+ loyalty", which is not the mechanic this file is
    about.

    Charged to 7, not the bare minimum of 4: paying `−4` from exactly 4 would
    leave him at 0 loyalty, and CR 704.5i's state-based action puts a
    planeswalker at 0 loyalty into its owner's graveyard the moment the cost
    is paid - before the ability he just activated ever resolves. That is a
    real (and separately interesting) interaction, but it is not this shape's
    own mechanic, so this file charges him past it rather than through it.
    """
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")
    ajani = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(ajani), "alice", transformed=True
    )
    assert ajani.name == "Ajani, Nacatl Avenger"
    ajani.add_counters(Counter.LOYALTY, 4)  # 3 -> 7, survives paying -4
    return ajani


def test_each_opponent_keeps_one_of_each_type_and_sacrifices_the_rest():
    """The whole printed shape: one artifact, one creature, one enchantment,
    and one planeswalker survive; the extra of each, and nothing else, is
    sacrificed. The land is never even asked about.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player(
            "bob",
            battlefield=[
                "Mox Opal",
                "Mind Stone",
                "Grizzly Bears",
                "Watchwolf",
                "Doubling Season",
                "Runed Halo",
                "Karn, the Great Creator",
                "Forest",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = _flip_and_charge_ajani(scenario)

    mox_opal = scenario.find("Mox Opal", Zone.BATTLEFIELD, "bob")
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    wolf = scenario.find("Watchwolf", Zone.BATTLEFIELD, "bob")
    doubling_season = scenario.find("Doubling Season", Zone.BATTLEFIELD, "bob")
    runed_halo = scenario.find("Runed Halo", Zone.BATTLEFIELD, "bob")
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    # One `CHOOSE_CARDS` question per type, in the printed order (artifact,
    # creature, enchantment, planeswalker) - queued in that same order so
    # each is consumed by the question it belongs to.
    scenario.will_choose_cards(mox_opal, username="bob", source="Ajani, Nacatl Avenger")
    scenario.will_choose_cards(bears, username="bob", source="Ajani, Nacatl Avenger")
    scenario.will_choose_cards(doubling_season, username="bob", source="Ajani, Nacatl Avenger")
    scenario.will_choose_cards(karn, username="bob", source="Ajani, Nacatl Avenger")

    scenario.activate(ajani, index=2)  # the -4
    scenario.resolve_top()

    assert mox_opal.zone is Zone.BATTLEFIELD, "the chosen artifact survives"
    assert bears.zone is Zone.BATTLEFIELD, "the chosen creature survives"
    assert doubling_season.zone is Zone.BATTLEFIELD, "the chosen enchantment survives"
    assert karn.zone is Zone.BATTLEFIELD, "the chosen planeswalker survives"
    assert mind_stone.zone is Zone.GRAVEYARD, "the unchosen extra artifact is sacrificed"
    assert wolf.zone is Zone.GRAVEYARD, "the unchosen extra creature is sacrificed"
    assert runed_halo.zone is Zone.GRAVEYARD, "the unchosen extra enchantment is sacrificed"
    assert forest.zone is Zone.BATTLEFIELD, (
        "a land is never one of the nonland permanents asked about"
    )


def test_no_permanent_of_a_type_keeps_nothing_of_that_type():
    """Bob controls no artifact and no planeswalker at all - CR 107.1a: there
    is no zero-permanent "an artifact" to choose, so nothing of either type
    is kept, and the ability does not raise or invent a substitute. His one
    creature and one enchantment are still each kept normally.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player("bob", battlefield=["Grizzly Bears", "Doubling Season"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = _flip_and_charge_ajani(scenario)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    doubling_season = scenario.find("Doubling Season", Zone.BATTLEFIELD, "bob")

    scenario.will_choose_cards(bears, username="bob", source="Ajani, Nacatl Avenger")
    scenario.will_choose_cards(doubling_season, username="bob", source="Ajani, Nacatl Avenger")

    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert doubling_season.zone is Zone.BATTLEFIELD


def test_each_opponent_chooses_for_their_own_board_not_ajanis_controller():
    """Two opponents, each keeping a different creature off their own board -
    Ajani's controller (alice) never chooses on anyone's behalf, and one
    opponent's sacrifice never touches the other's permanents.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .player("carol", battlefield=["Wall of Omens", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = _flip_and_charge_ajani(scenario)

    bob_bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    bob_wolf = scenario.find("Watchwolf", Zone.BATTLEFIELD, "bob")
    carol_wall = scenario.find("Wall of Omens", Zone.BATTLEFIELD, "carol")
    carol_giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "carol")

    scenario.will_choose_cards(bob_bears, username="bob", source="Ajani, Nacatl Avenger")
    scenario.will_choose_cards(carol_giant, username="carol", source="Ajani, Nacatl Avenger")

    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    assert bob_bears.zone is Zone.BATTLEFIELD
    assert bob_wolf.zone is Zone.GRAVEYARD
    assert carol_giant.zone is Zone.BATTLEFIELD
    assert carol_wall.zone is Zone.GRAVEYARD


def test_an_artifact_that_is_a_land_is_never_among_the_nonland_permanents():
    """ "from among the **nonland** permanents they control" is a question
    about what the permanents are (CR 613.5), not what they print.

    Toph, the First Metalbender's "Nontoken artifacts you control are lands in
    addition to their other types" is a layer-4 type change (CR 613.1d,
    CR 205.1b). Under her, bob controls no nonland artifact at all: both
    Mox Opal and Mind Stone are lands, whatever their printed type lines say,
    so the ability never asks bob to choose one and never sacrifices the
    other. Before this was read off the computed board, the pair were two
    printed artifacts, one kept and one destroyed.

    Toph herself is the creature bob keeps, so the sweep is real - Grizzly
    Bears still dies in the same resolution.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player(
            "bob",
            battlefield=[
                "Toph, the First Metalbender",
                "Mox Opal",
                "Mind Stone",
                "Grizzly Bears",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = _flip_and_charge_ajani(scenario)

    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD, "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    toph = scenario.find("Toph, the First Metalbender", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    for artifact in (mox, stone):
        assert Type.LAND in scenario.game.characteristics_of(artifact).types, "Toph made it a land"
        assert Type.LAND not in artifact.types, "its printed type line did not change"

    scenario.will_choose_cards(toph, username="bob", source="Ajani, Nacatl Avenger")

    scenario.activate(ajani, index=2)
    scenario.resolve_top()

    prompts = [
        decision.prompt
        for decision in scenario.questions_asked()
        if decision.source == "Ajani, Nacatl Avenger"
    ]
    assert not any("artifact" in prompt for prompt in prompts), (
        "bob controls no nonland artifact, so CR 107.1a asks nothing about one"
    )
    assert mox.zone is Zone.BATTLEFIELD, "a land is not a nonland permanent"
    assert stone.zone is Zone.BATTLEFIELD
    assert toph.zone is Zone.BATTLEFIELD, "the creature bob kept"
    assert bears.zone is Zone.GRAVEYARD, "the sweep did happen"

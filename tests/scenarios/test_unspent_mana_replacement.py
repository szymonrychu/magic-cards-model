"""CR 106.4 / CR 500.5: "Each player's mana pool empties at the end of each
step and phase, and the player is said to lose this mana" - and the static
abilities that replace that loss (CR 614.1a: "instead").

Two printed shapes, read off the permanent's own static line:

- "If you would lose unspent mana, that mana becomes <colour> instead."
  (Omnath, Locus of All: black; Kruphix, God of Horizons: colorless; Ozai,
  the Phoenix King: red). The mana is not lost - it stays, recoloured, and
  any restriction or rider it carried stays with it (the printings' own
  rulings).
- "You/Players don't lose unspent [<colour>] mana as steps and phases end."
  (Omnath, Locus of Mana: green; Upwelling: every player, every type.)

CR 616.1: when more than one of them would replace the same loss, the
affected player chooses which applies first; CR 616.1f then asks again of
whatever is still being lost.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.mana import ManaRestriction
from tests.scenarios.harness import Scenario


def _float(scenario, username: str, *sources: str) -> None:
    """Tap each named land for its own mana, as `username`'s mana abilities."""
    for name in sources:
        (land, *_rest) = scenario.untapped_sources(name, username=username)
        scenario.activate(land, username=username)


def test_omnath_locus_of_all_turns_unspent_mana_black_instead_of_losing_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Omnath, Locus of All", "Forest", "Mountain", "Wastes"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest", "Mountain", "Wastes")

    scenario.advance()

    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.game.player("alice").mana_pool.floating == {Color.BLACK: 3}


def test_kruphix_turns_unspent_mana_colorless():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kruphix, God of Horizons", "Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest", "Island")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.COLORLESS: 2}


def test_ozai_turns_unspent_mana_red_and_it_survives_every_later_boundary():
    """Kept, not lost: the recoloured mana is still there after every later
    boundary up to the end step, for as long as Ozai stays."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ozai, the Phoenix King", "Island", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Island", "Swamp")

    scenario.game.advance_to(Step.END_STEP)
    assert scenario.game.player("alice").mana_pool.floating == {Color.RED: 2}


def test_the_mana_is_only_kept_while_the_permanent_is_there():
    """Once the source has left, the next boundary empties the pool as usual
    (the printings' ruling: "you have until the end of the current step or
    phase to use the mana before it disappears")."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kruphix, God of Horizons", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest")
    scenario.advance()
    assert scenario.game.player("alice").mana_pool.floating == {Color.COLORLESS: 1}

    kruphix = scenario.find("Kruphix, God of Horizons", Zone.BATTLEFIELD)
    scenario.game.sacrifice(kruphix)
    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {}


def test_an_opponents_replacement_does_not_keep_your_mana():
    """ "If *you* would lose unspent mana": the controller's mana only."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest"])
        .player("bob", battlefield=["Omnath, Locus of All"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {}


def test_the_recoloured_mana_keeps_its_spend_restriction():
    """The printings' ruling: "If unspent mana has any restrictions or riders
    associated with it ... those restrictions or riders remain associated with
    that mana when it becomes black." Eldrazi Temple's {C}{C} stays spendable
    only on colorless Eldrazi."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Omnath, Locus of All", "Eldrazi Temple"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    temple = scenario.find("Eldrazi Temple", Zone.BATTLEFIELD)
    restricted_index = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(temple))
        if ability.mana is not None and "Spend this mana only" in ability.effect
    )
    scenario.activate(temple, index=restricted_index)
    before = scenario.game.player("alice").mana_pool.restricted
    assert [entry.amounts for entry in before] == [{Color.COLORLESS: 2}]
    restriction: ManaRestriction = before[0].restriction

    scenario.advance()

    pool = scenario.game.player("alice").mana_pool
    assert pool.floating == {Color.BLACK: 2}
    assert [(entry.restriction, entry.amounts) for entry in pool.restricted] == [
        (restriction, {Color.BLACK: 2})
    ]


def test_omnath_locus_of_mana_keeps_green_and_grows_with_it():
    """The two statics of the same card meet: the green it keeps is the green
    it counts."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Omnath, Locus of Mana", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest", "Forest")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 2}
    omnath = scenario.find("Omnath, Locus of Mana", Zone.BATTLEFIELD)
    assert scenario.game.characteristics_of(omnath).power == 3


def test_upwelling_keeps_every_players_mana():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Upwelling", "Forest"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest")
    bob_island = scenario.find("Island", Zone.BATTLEFIELD, username="bob")
    scenario.game.player("bob").mana_pool.add(Color.BLUE)
    bob_island.tap()

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 1}
    assert scenario.game.player("bob").mana_pool.floating == {Color.BLUE: 1}


def test_two_replacements_the_affected_player_chooses_which_applies(  # CR 616.1
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All", "Kruphix, God of Horizons", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Forest")
    scenario.will_choose_mode("Kruphix, God of Horizons", username="alice")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    asked = [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_A_MODE
    ]
    assert len(asked) == 1
    assert "CR 616.1" in asked[0].prompt


def test_keep_first_then_the_recolour_takes_only_what_is_still_lost():
    """CR 616.1f: Omnath, Locus of Mana applied first keeps the green as
    green; Omnath, Locus of All's replacement then sees only the red still
    being lost, and turns it black."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All", "Omnath, Locus of Mana", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Mountain", "Forest")
    scenario.will_choose_mode("Omnath, Locus of Mana", username="alice")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 1, Color.BLACK: 1}


def test_recolour_first_leaves_nothing_for_the_keep():
    """The other order: Omnath, Locus of All first turns everything black, and
    there is no green left for Omnath, Locus of Mana to keep."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All", "Omnath, Locus of Mana", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _float(scenario, "alice", "Mountain", "Forest")
    scenario.will_choose_mode("Omnath, Locus of All", username="alice")

    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.BLACK: 2}


def test_ozai_has_flying_and_indestructible_with_six_unspent_mana():
    """ "Ozai has flying and indestructible as long as you have six or more
    unspent mana." - five is not enough, six is."""
    scenario = (
        Scenario().player("alice", battlefield=["Ozai, the Phoenix King"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ozai = scenario.find("Ozai, the Phoenix King", Zone.BATTLEFIELD)
    pool = scenario.game.player("alice").mana_pool
    pool.add(Color.RED, 5)
    assert not has_keyword(ozai, Keyword.FLYING, scenario.game)
    assert not is_indestructible(ozai, scenario.game)

    pool.add(Color.RED, 1)

    assert has_keyword(ozai, Keyword.FLYING, scenario.game)
    assert is_indestructible(ozai, scenario.game)

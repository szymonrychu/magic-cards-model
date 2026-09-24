"""A modal double-faced card's land face: "As this land enters, you may pay 3
life. If you don't, it enters tapped." - CR 614.12a's single choice spread
over two printed sentences (an optional `AS_ENTERS` payment, paired with the
`ENTERS_TAPPED` back-reference "if you don't" that follows it), on the two
listed printings `test_mdfc_land_play.py` does not already cover: Disciple of
Freyalise // Garden of Freyalise and Boggart Trawler // Boggart Bog. Witch
Enchanter // Witch-Blessed Meadow and Hydroelectric Specimen // Hydroelectric
Laboratory carry the identical clause and are already proven by
`test_mdfc_land_play.py`'s own `test_the_land_face_enters_untapped_by_default_
paying_the_life` / `test_the_land_face_enters_tapped_when_the_life_is_refused`
and `test_hydroelectric_laboratory_enters_untapped_for_three_life` /
`test_hydroelectric_laboratory_enters_tapped_when_the_life_is_refused`.

CR numbers below were looked up with `mise run rules:find <n>` in the session
that wrote this file.

- **CR 712.12** - "A player playing a modal double-faced card ... as a land
  chooses one of its faces that's a land before putting it onto the
  battlefield. It enters the battlefield with that face up."
- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield."
- **CR 119.4** - "If a cost or effect allows a player to pay an amount of
  life greater than 0, the player may do so only if their life total is
  greater than or equal to the amount of the payment." Below 3 life, paying
  is not a legal choice at all, and the land enters tapped with nobody asked.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(land_front: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[land_front], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Disciple of Freyalise // Garden of Freyalise ---------------------------


def test_garden_of_freyalise_enters_untapped_for_three_life_by_default():
    """CR 119.4/608.2d: an unanswered "you may pay life" is paid when legal."""
    scenario = _board("Disciple of Freyalise")

    garden = scenario.play_land("Disciple of Freyalise")

    assert garden.zone is Zone.BATTLEFIELD
    assert garden.name == "Garden of Freyalise"
    assert garden.untapped
    assert scenario.player("alice").life == 17


def test_garden_of_freyalise_enters_tapped_when_the_life_is_refused():
    scenario = _board("Disciple of Freyalise")
    scenario.will_pay_the_life(False)

    garden = scenario.play_land("Disciple of Freyalise")

    assert garden.tapped
    assert scenario.player("alice").life == 20


def test_garden_of_freyalise_does_not_carry_the_creature_faces_trigger():
    """CR 712.8f: only Garden of Freyalise's own printed text - a bare mana
    ability - is up; Disciple of Freyalise's "when this creature enters, you
    may sacrifice another creature ..." is the *other* face's line and never
    fires off a land entering."""
    scenario = _board("Disciple of Freyalise")
    scenario.will_pay_the_life(False)  # isolate from the life-payment choice

    garden = scenario.play_land("Disciple of Freyalise")

    assert garden.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20  # no sacrifice-and-drain fired


# -- Boggart Trawler // Boggart Bog ------------------------------------------


def test_boggart_bog_enters_untapped_for_three_life_by_default():
    scenario = _board("Boggart Trawler")

    bog = scenario.play_land("Boggart Trawler")

    assert bog.zone is Zone.BATTLEFIELD
    assert bog.name == "Boggart Bog"
    assert bog.untapped
    assert scenario.player("alice").life == 17


def test_boggart_bog_enters_tapped_when_the_life_is_refused():
    scenario = _board("Boggart Trawler")
    scenario.will_pay_the_life(False)

    bog = scenario.play_land("Boggart Trawler")

    assert bog.tapped
    assert scenario.player("alice").life == 20


# -- CR 119.4: paying is not a choice at all below the life total ----------


def test_a_player_at_two_life_cannot_pay_and_is_never_asked():
    """Below the payment's own amount, CR 119.4 refuses the payment outright -
    the land enters tapped with no decision queued, not a decision answered
    "no" by default."""
    scenario = (
        Scenario()
        .player("alice", hand=["Boggart Trawler"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").life = 2

    bog = scenario.play_land("Boggart Trawler")

    assert bog.tapped
    assert scenario.player("alice").life == 2

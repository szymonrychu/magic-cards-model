"""Judge scenario: which zone an activated ability functions in (DDR#970).

"Can you sacrifice Gollum to itself?" Amy has Gollum, Patient Plotter on the
battlefield and wants to activate its second ability - "{B}, Sacrifice a
creature: Return this card from your graveyard to your hand. Activate only as a
sorcery." - sacrificing Gollum itself, so that the ability then finds Gollum in
the graveyard it just arrived in. The answer is no, and the reason is a zone
rule rather than anything about timing:

- **CR 113.6m** - "An ability whose cost or effect specifies that it moves the
  object it's on out of a particular zone functions only in that zone, unless
  its trigger condition or a previous part of its cost or effect already
  established a different zone." Gollum's *effect* returns Gollum from a
  graveyard, so the ability functions only while Gollum is in a graveyard. On
  the battlefield it does not exist to be activated.
- The episode's contrast, **CR 113.6j** - "An object's activated ability that
  has a cost that can't be paid while the object is on the battlefield
  functions from any zone in which its cost can be paid" - is the *other* way a
  graveyard ability gets there, and does not apply here: paying {B} and
  sacrificing a creature is perfectly possible on the battlefield.
- The caveat the episode reads off the rule ("unless ... a previous part of its
  cost or effect already established a different zone", the Plague Reaver case)
  does not bite either, because Gollum's cost says "Sacrifice **a creature**",
  not "Sacrifice this creature" - any creature pays it, so nothing in the cost
  establishes that Gollum is the thing being put into a graveyard.

`machines/abilities._activated_ability_zone` reads exactly this off the printed
text, and `machines/keywords.off_battlefield_activation` refuses the wrong zone.
The one gap is that `Game.activate_ability` - the battlefield path the harness's
`activate()` uses - never consults it, which is the `xfail` at the bottom.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 113.6b, CR 113.6j, CR 113.6m,
CR 602.5b is not cited, CR 701.9a is not cited.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.machines.triggers import activated_abilities_of
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def test_the_printed_ability_is_read_as_functioning_in_the_graveyard():
    """CR 113.6m, off the card's own words.

    Nothing in `machines/abilities.py` names Gollum: the effect sentence names
    "this card ... from your graveyard", and that is the whole derivation.
    """
    (ability,) = [
        ability
        for ability in activated_abilities_of(card("Gollum, Patient Plotter"))
        if ability.zone is not None
    ]

    assert ability.zone is Zone.GRAVEYARD
    assert ability.zone_rule == "CR 113.6m"
    assert ability.cost == "{B}, Sacrifice a creature"


def test_the_ability_cannot_be_activated_while_gollum_is_on_the_battlefield():
    """DDR#970's answer: the play is not possible.

    Sacrificing Gollum to its own ability is refused before any cost is paid,
    because the ability does not function in the zone Gollum is in (CR 113.6m).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gollum, Patient Plotter", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter", "alice")

    activation = off_battlefield_activation(scenario.game, gollum, "alice", sacrificing=[gollum])

    with pytest.raises(ValueError, match="functions in the graveyard"):
        activation.begin_paying()

    assert gollum.zone is Zone.BATTLEFIELD
    assert not any(source.tapped for source in scenario.game.battlefield)
    assert scenario.game.stack_is_empty


def test_the_same_ability_works_once_gollum_is_already_in_the_graveyard():
    """ "You can only activate Gollum's bottom ability if Gollum is already in
    your graveyard."

    The control for the refusal above: identical cost, identical ability, one
    different zone. Another creature pays the sacrifice - CR 113.6m's caveat
    would need the cost to name *Gollum*, and it does not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Gollum, Patient Plotter"],
            battlefield=["Swamp", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.find("Gollum, Patient Plotter", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = off_battlefield_activation(scenario.game, gollum, "alice", sacrificing=[bears])
    payment = activation.begin_paying()
    (swamp,) = scenario.untapped_sources("Swamp")
    payment.tap_for_mana(swamp, mana_from(swamp))
    payment.pay()
    activation.activate()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Gollum, Patient Plotter's activated ability"]

    scenario.resolve_top()
    assert gollum.zone is Zone.HAND


@pytest.mark.xfail(
    reason=(
        "`Game.activate_ability` - the battlefield activation path the harness's "
        "`activate()` uses - never reads `ActivatedAbility.zone`, so the very play "
        "DDR#970 rules out goes through: Gollum on the battlefield sacrifices "
        "itself to its own graveyard-only ability. Only "
        "`machines/keywords.off_battlefield_activation` enforces CR 113.6m."
    ),
    strict=True,
)
def test_the_battlefield_activation_path_also_refuses_the_wrong_zone():
    """CR 113.6m does not care which code path asked.

    An ability that functions only in a graveyard is not activatable from the
    battlefield, whichever door the activation comes through.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gollum, Patient Plotter", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter", "alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    with pytest.raises(ValueError):
        scenario.activate(gollum, swamp, sacrificing=[gollum])

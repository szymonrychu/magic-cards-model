"""Combat legality reads the *computed* board (CR 613.5), not the printed one.

`CardState.types`/`.subtypes` are CR 613.1's *starting point* - "the values of
the characteristics printed on that card", off whichever face is up
(CR 712.8d). CR 613.5 says the layer system's answer is applied "continually
and automatically", so two spots in `machines/combat.py` that filtered on the
printed read instead of `game.characteristics_of(...)` were wrong the moment a
layer-4 effect (CR 613.1d) touched the thing being asked about:

- `_defender_refusal` - CR 508.1b: "the active player announces which player,
  **planeswalker, or battle** each of the chosen creatures is attacking."
  Filtered on `permanent.types`, which already reads whichever face of a
  double-faced permanent is up (CR 712.8d) and so already got a transformed
  planeswalker right - but that is still only the CR 613.1 starting point,
  and CR 506.4/506.4d/506.4e are explicit that a permanent which *stops*
  being a planeswalker or battle mid-combat is removed from it, which only
  makes sense if what a permanent currently is includes layer 4.

  No printed continuous effect in this engine's card pool grants planeswalker
  or battle through layer 4 (checked every builder in `machines/layers.py`),
  so there is no real card here that makes the old and new code disagree.
  The fix is still made - `characteristics_of` is what every other computed
  read in this file already uses - and the tests below are the regression
  that must keep holding: a transformed planeswalker face is still
  attackable, and a plain creature or land still is not.

- `landwalk_refusal` - CR 702.14c: landwalk cares whether the defending
  player "controls at least one land with the specified land type", read off
  `permanent.subtypes` before this fix. Urborg, Tomb of Yawgmoth's "Each land
  is a Swamp in addition to its other land types" is a real, live layer-4
  land-subtype grant (CR 613.1d, CR 305.7's "gains the new land type[] ...
  keeps its land types" for an *additional* type), and a land that is only a
  Swamp because of Urborg has to stop a swampwalker exactly as one that says
  Swamp on its own type line would.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import landwalk_refusal
from magic_cards_model.models import Zone

from .harness import Scenario


def test_a_transformed_planeswalker_face_is_a_legal_attack_target():
    """Ajani, Nacatl Pariah's back face, Ajani, Nacatl Avenger, is a
    Legendary Planeswalker (CR 508.1b) - a regression on the DFC case the old
    printed-read comment already called out, now exercised through the
    computed board instead.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Ajani, Nacatl Pariah"])
        .build()
    )
    ajani = scenario.creature("Ajani, Nacatl Pariah", "bob")
    ajani.transform()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.can_attack(bears, defending=ajani)
    scenario.attack_with(bears, defending=ajani)
    assert scenario.game.combat.attacks[0].defender.card_id == ajani.id


def test_a_plain_creature_permanent_is_not_a_legal_attack_target():
    """The inverse: an ordinary creature - not a player, planeswalker, or
    battle - is never a legal thing to declare an attack against (CR 508.1b
    lists only those three), whether the read is printed or computed.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    assert not scenario.can_attack(bears, defending=giant)
    assert scenario.game.why_cannot_attack(bears, giant) is not None


def test_landwalk_sees_a_land_type_urborg_grants():
    """Urborg makes bob's Forest a Swamp too (CR 613.1d), so Street Wraith's
    swampwalk (CR 702.14c) refuses every block - even though "Swamp" is
    nowhere on the Forest's own printed type line.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Street Wraith", "Urborg, Tomb of Yawgmoth"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wraith = scenario.creature("Street Wraith", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert "Swamp" not in forest.subtypes, "the printed type line is still just Forest"

    refusal = landwalk_refusal(scenario.game, wraith, "bob")
    assert refusal is not None and "Swamp" in refusal


def test_landwalk_does_not_apply_without_the_granting_effect():
    """The inverse, same shape minus Urborg: bob's Forest never becomes a
    Swamp, so Street Wraith's swampwalk does not stop it being blocked.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Street Wraith"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wraith = scenario.creature("Street Wraith", "alice")

    assert landwalk_refusal(scenario.game, wraith, "bob") is None

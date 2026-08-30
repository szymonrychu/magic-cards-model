"""A transformed permanent's characteristics (CR 712, CR 701.27).

`CardState.transformed` used to be a flag nothing read: a Delver of Secrets
that had flipped was still a 1/1 Human Wizard with no flying, an Ajani, Nacatl
Pariah that had been returned transformed was still a Cat Warrior creature with
no loyalty abilities to activate, and a Duskwatch Recruiter that had become
Krallenhorde Howler kept the `{2}{G}` ability printed on the face that was no
longer up. This file is that flag reaching characteristics.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up. Only permanents represented by double-faced tokens and
  double-faced cards can transform."
- **CR 701.27g** - "Some spells and abilities refer to a 'transformed
  permanent.' This phrase refers to a double-faced permanent on the
  battlefield with its back face up."
- **CR 712.8d** - "While a double-faced permanent has its front face up, it has
  only the characteristics of its front face."
- **CR 712.8e** - "While a nonmodal double-faced permanent has its back face
  up, it has only the characteristics of its back face. However, its mana value
  is calculated using the mana cost of its front face."
- **CR 202.3b** - the same exception said the other way round: "the mana value
  of the back face of a nonmodal double-faced permanent or spell's back face is
  calculated as though it had the mana cost of its front face."
- **CR 712.8a** - "While a double-faced card is outside the game or in a zone
  other than the battlefield or stack, it has only the characteristics of its
  front face" - which is why leaving the battlefield is the end of a transform.
- **CR 712.8f** / **CR 712.12** - a *modal* double-faced permanent's up face is
  the one it was played as, chosen once. `transformed` must not be confused
  with it; `test_mdfc_land_play.py` owns that case and the regression guard
  below only checks the two stay apart.
- **CR 712.14a** - "If a spell or ability puts a double-faced card onto the
  battlefield 'transformed' ..., it enters the battlefield with its back face
  up." Ajani's own trigger says exactly that, and it is the only way a creature
  face becomes a planeswalker with any loyalty at all (CR 306.5b).
- **CR 712.18** - "When a double-faced permanent transforms or converts, it
  doesn't become a new object. Any effects that applied to that permanent will
  continue to apply to it."
- **CR 109.3** - abilities are among an object's characteristics, so they move
  with the face like power and toughness do.
- **CR 306.5b** - a planeswalker enters with loyalty counters equal to its
  printed loyalty; **CR 606.4** - a loyalty ability's cost is putting on or
  removing that many.
- **CR 603.4** - the intervening *if* the werewolves' transform triggers carry.
- **CR 702.9b** - flying: "A creature with flying can't be blocked except by
  creatures with flying and/or reach."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# -- Delver of Secrets: the flip gains creature characteristics -------------


def _delver_board(top: str = "Lightning Bolt") -> Scenario:
    """Alice with Delver of Secrets out and `top` on top of her library."""
    return (
        Scenario()
        .player("alice", library=[top, "Forest"], battlefield=["Delver of Secrets"])
        .player("bob", library=["Forest"])
    )


def test_delver_of_secrets_is_its_front_face_until_it_transforms():
    """CR 712.8d: front face up, it has only the front face's characteristics -
    a 1/1 Human Wizard called Delver of Secrets, *without* flying, even though
    the printing's keyword list carries Flying for the back face's sake.
    """
    scenario = _delver_board().build()
    delver = scenario.creature("Delver of Secrets", "alice")

    assert delver.name == "Delver of Secrets"
    assert delver.power == 1 and delver.toughness == 1
    assert "Wizard" in delver.subtypes and "Insect" not in delver.subtypes
    assert "Flying" not in delver.keywords, "Flying is printed on Insectile Aberration"


def test_transforming_delver_of_secrets_makes_it_a_three_two_flier():
    """The upkeep trigger flips it for real (CR 701.27a), and CR 712.8e then
    gives it Insectile Aberration's name, types, power, toughness and flying.
    """
    scenario = _delver_board().build()
    delver = scenario.creature("Delver of Secrets", "alice")

    scenario.advance()  # untap -> upkeep, the trigger goes on the stack
    scenario.pass_until_resolved()

    assert delver.transformed
    assert delver.name == "Insectile Aberration"
    assert delver.power == 3 and delver.toughness == 2
    assert "Insect" in delver.subtypes and "Wizard" not in delver.subtypes
    assert "Flying" in delver.keywords
    assert scenario.game.characteristics_of(delver).power == 3, "the composed answer agrees"


def test_a_transformed_delver_keeps_its_front_faces_mana_value():
    """CR 202.3b / CR 712.8e's single exception: Insectile Aberration prints no
    mana cost, but the permanent's mana value is still Delver of Secrets' 1.
    """
    scenario = _delver_board().build()
    delver = scenario.creature("Delver of Secrets", "alice")
    scenario.advance()
    scenario.pass_until_resolved()

    assert delver.transformed
    assert delver.mana_cost is None, "CR 712.8e: the back face's own cost, and it prints none"
    assert delver.mana_value == 1
    assert scenario.game.characteristics_of(delver).mana_value == 1


def test_a_transformed_delver_cannot_be_blocked_by_a_ground_creature():
    """The flip has to reach combat, not just the data model: CR 702.9b stops
    Grizzly Bears blocking a flier it could have blocked a minute earlier.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Lightning Bolt", "Forest"], battlefield=["Delver of Secrets"])
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    delver = scenario.creature("Delver of Secrets", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(delver)
    assert scenario.game.can_block(bears, delver), "a 1/1 Human Wizard is blockable"

    # CR 712.18: transforming does not make it a new object, so it is still
    # the attacking creature - with flying now.
    delver.transform()  # CR 701.27a

    assert scenario.game.why_cannot_block(bears, delver) is not None


def test_a_transformed_delver_deals_its_back_faces_power_in_combat():
    """CR 510.1a assigns damage equal to power, and the power is the back
    face's 3 - the same read `machines/combat.py` makes."""
    scenario = _delver_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    delver = scenario.creature("Delver of Secrets", "alice")
    delver.transform()  # CR 701.27a
    scenario.attack_with(delver)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17, "3, not the front face's 1"


def test_leaving_the_battlefield_ends_the_transform():
    """CR 712.8a: in a graveyard it has only its front face's characteristics
    again, so the flag is cleared as it goes (CR 400.7 - a new object)."""
    scenario = _delver_board().build()
    delver = scenario.creature("Delver of Secrets", "alice")
    scenario.advance()
    scenario.pass_until_resolved()
    assert delver.transformed

    scenario.game.put_into_graveyard(delver)

    assert not delver.transformed
    assert delver.name == "Delver of Secrets"
    assert delver.power == 1


# -- Duskwatch Recruiter: two upkeep triggers, one on each face -------------


def _duskwatch_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice", library=["Forest", "Forest", "Forest"], battlefield=["Duskwatch Recruiter"]
        )
        .player(
            "bob",
            library=["Forest", "Forest"],
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
    )


def test_duskwatch_recruiter_transforms_when_no_spells_were_cast_last_turn():
    """ "At the beginning of each upkeep, if no spells were cast last turn,
    transform this creature." - a CR 603.4 intervening *if* answered from the
    previous turn's cast record, then CR 701.27a's turn over.
    """
    scenario = _duskwatch_board().build()
    duskwatch = scenario.creature("Duskwatch Recruiter", "alice")

    scenario.advance()  # alice's untap -> upkeep
    scenario.pass_until_resolved()

    assert duskwatch.transformed
    assert duskwatch.name == "Krallenhorde Howler"
    assert duskwatch.power == 3 and duskwatch.toughness == 3
    assert duskwatch.subtypes == ("Werewolf",)


def test_krallenhorde_howler_transforms_back_when_a_player_cast_two_spells():
    """The back face's own upkeep trigger - "if a player cast two or more spells
    last turn" - is an ability the permanent only has while that face is up
    (CR 712.8e, CR 109.3), and it turns it back over.
    """
    scenario = _duskwatch_board().build()
    duskwatch = scenario.creature("Duskwatch Recruiter", "alice")

    scenario.advance()  # alice's upkeep: nothing was cast, so it transforms
    scenario.pass_until_resolved()
    assert duskwatch.transformed

    # bob casts two spells on his own turn, at alice's face.
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain, second) = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["alice"], username="bob")
    scenario.cast_and_resolve("Lightning Bolt", second, targets=["alice"], username="bob")

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # alice's turn again
    scenario.advance()  # untap -> upkeep, where the back face's trigger fires
    scenario.pass_until_resolved()

    assert not duskwatch.transformed, "CR 701.27a turned it back over"
    assert duskwatch.name == "Duskwatch Recruiter"


def test_a_transformed_duskwatch_recruiter_loses_its_front_faces_ability():
    """CR 109.3 + CR 712.8e: abilities are characteristics, so Krallenhorde
    Howler does not have Duskwatch Recruiter's `{2}{G}` activated ability, and
    the untransformed permanent does not have the back face's static one.
    """
    scenario = _duskwatch_board().build()
    duskwatch = scenario.creature("Duskwatch Recruiter", "alice")

    front = scenario.game.activated_abilities(duskwatch)
    assert [ability.cost for ability in front] == ["{2}{G}"]

    scenario.advance()
    scenario.pass_until_resolved()
    assert duskwatch.transformed

    assert scenario.game.activated_abilities(duskwatch) == []
    assert "Creature spells you cast cost {1} less" in duskwatch.oracle_text
    assert "Look at the top three cards" not in duskwatch.oracle_text


# -- Ajani: a creature face and a planeswalker back face --------------------


def test_ajani_returned_transformed_is_a_planeswalker_with_his_printed_loyalty():
    """CR 712.14a: put onto the battlefield transformed, he arrives with his
    back face up, so CR 306.5b's intrinsic ability reads Ajani, Nacatl
    Avenger's printed 3 rather than the creature face's absent loyalty.
    """
    scenario = Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")
    assert Type.CREATURE in ajani.types

    ajani = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(ajani), "alice", transformed=True
    )

    assert ajani.name == "Ajani, Nacatl Avenger"
    assert ajani.types == (Type.PLANESWALKER,)
    assert ajani.subtypes == ("Ajani",), "no longer a Cat Warrior"
    assert ajani.loyalty == 3, "CR 306.5b, off the face that is up"
    assert ajani.zone is Zone.BATTLEFIELD, "not dead to CR 704.5i at 0 loyalty"


def test_a_transformed_ajani_has_his_back_faces_loyalty_abilities_and_not_his_fronts():
    """CR 109.3, CR 712.8e: the three loyalty abilities are Ajani, Nacatl
    Avenger's, and the front face - a creature with no activated ability at all
    - contributes none of them.
    """
    scenario = Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")
    assert scenario.game.activated_abilities(ajani) == [], "the Cat Warrior face has none"

    ajani = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(ajani), "alice", transformed=True
    )

    assert [ability.cost for ability in scenario.game.activated_abilities(ajani)] == [
        "+2",
        "0",
        "−4",
    ]


def test_ajanis_plus_two_is_payable_against_the_loyalty_he_entered_with():
    """CR 606.4: the `+2` puts two loyalty counters on as its cost, and the
    ability it pays for is one he only has transformed.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah", "Ocelot Pride"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")
    cat = scenario.creature("Ocelot Pride", "alice")
    ajani = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(ajani), "alice", transformed=True
    )

    scenario.activate(ajani, index=0)
    scenario.resolve_top()

    assert ajani.loyalty == 5
    assert cat.counter_count(Counter.PLUS_ONE) == 1


def test_an_untransformed_ajani_cannot_activate_the_back_faces_ability():
    """The mirror, and the one that would silently pass if `up_face` ignored
    `transformed` in the other direction: front face up, CR 712.8d gives him
    the creature face's characteristics, which include no loyalty ability.
    """
    scenario = Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")

    assert scenario.why_cannot_activate(ajani, index=0) is not None


# -- the boundaries this must not cross -------------------------------------


def test_a_single_faced_permanent_is_untouched_by_any_of_this():
    """`CardState.up_face` is `None` for a card with no faces, and every reader
    has to keep the top-level fallback - otherwise every ordinary permanent
    becomes typeless and nameless.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears", "Forest"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")

    assert bears.up_face is None and bears.up_face_name is None
    assert bears.name == "Grizzly Bears"
    assert bears.types == (Type.CREATURE,)
    assert bears.power == 2 and bears.toughness == 2
    assert bears.mana_value == 2
    assert forest.types == (Type.LAND,)
    assert forest.subtypes == ("Forest",)


def test_transform_does_nothing_to_a_single_faced_permanent():
    """CR 701.27a: "only permanents represented by double-faced tokens and
    double-faced cards can transform" (CR 712.9)."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    bears.transform()

    assert not bears.transformed
    assert bears.name == "Grizzly Bears"


def test_an_mdfc_land_face_is_not_reinterpreted_by_the_transform_flag():
    """CR 712.8f/712.12 against CR 712.8e: an MDFC played for its land face has
    a face chosen once, on the way in, and `transformed` is a different
    question. `test_mdfc_land_play.py` owns the land-play path; this only
    guards that the two do not share a switch.
    """
    scenario = Scenario().player("alice", hand=["Witch Enchanter"], library=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meadow = scenario.play_land("Witch Enchanter")

    assert not meadow.transformed, "playing a land face is not a transform"
    assert meadow.name == "Witch-Blessed Meadow"
    assert meadow.types == (Type.LAND,)

"""Lands that animate themselves until end of turn (the manland template).

"Until end of turn, this land becomes a P/T <colour(s)> <Subtype> creature
with <keyword(s)>. It's still a land." - Hall of Storm Giants ("a 7/7 blue
Giant creature with ward {3}"), and the proof printing Celestial Colonnade
("a 4/4 white and blue Elemental creature with flying and vigilance"), read by
one sentence shape rather than one card. Mishra's Factory's older trailing-
duration wording ("This land becomes a 2/2 Assembly-Worker artifact creature
until end of turn.") goes through the same reader and must keep working.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 613.1d / 613.1e / 613.1f / 613.4b** - the types go to layer 4, the
  colours to layer 5, the keywords to layer 6 and the P/T to layer 7b, one
  ability applying in each of its layers.
- **CR 613.4c** - a pump lands on top of the 7b P/T rather than being
  overwritten by it.
- **CR 205.1b** - "It's still a land" retains every prior card type and
  subtype.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
- **CR 702.21a** - ward is a triggered ability that counters an opponent's
  targeting spell or ability unless its controller pays; it only exists while
  the land has it.
- **CR 701.6a** - a countered spell does nothing and goes to the graveyard.
- **CR 302.6** - a land that came under its controller's control this turn
  can be animated but cannot attack.
- **CR 614.1d** - Hall's "If you control two or more other lands, this land
  enters tapped." is a replacement effect on how it enters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import ward_triggers
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario


def _hall_board(*, alice_hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=alice_hand or [],
            battlefield=["Hall of Storm Giants", *["Island"] * 6],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"] * 5)
    )


def _animate_hall(scenario) -> object:
    hall = scenario.find("Hall of Storm Giants", Zone.BATTLEFIELD, "alice")
    islands = scenario.untapped_sources(*["Island"] * 6, username="alice")
    scenario.activate(hall, *islands, index=1)
    scenario.pass_until_resolved()
    return hall


# -- Hall of Storm Giants ----------------------------------------------------


def test_hall_becomes_a_seven_seven_blue_giant_creature_that_is_still_a_land():
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hall = _animate_hall(scenario)

    computed = scenario.game.computed_board().of(hall)
    assert computed.is_creature
    assert computed.is_land, "CR 205.1b: 'It's still a land.'"
    assert (computed.power, computed.toughness) == (7, 7)
    assert computed.colors == (Color.BLUE,)
    assert "Giant" in computed.subtypes
    assert computed.has_ability("Ward {3}")


def test_hall_keeps_its_mana_ability_while_animated():
    """Nothing in the animation removes an ability (CR 613.1f adds only)."""
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)
    assert scenario.game.computed_board().of(hall).has_ability("{T}: Add {U}.")


def test_before_activation_hall_is_a_colourless_land_with_no_ward():
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = scenario.find("Hall of Storm Giants", Zone.BATTLEFIELD, "alice")

    computed = scenario.game.computed_board().of(hall)
    assert not computed.is_creature
    assert computed.power is None
    assert computed.colors == ()
    assert not computed.has_ability("Ward {3}")


def test_the_animation_ends_in_the_cleanup_step():
    """CR 514.2: every "until end of turn" effect ends in cleanup."""
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)

    while scenario.game.turn.active_player == "alice":
        scenario.advance()

    computed = scenario.game.computed_board().of(hall)
    assert not computed.is_creature
    assert computed.is_land
    assert computed.power is None
    assert computed.colors == ()
    assert not computed.has_ability("Ward {3}")


def test_an_opponents_bolt_at_the_animated_hall_triggers_ward():
    """CR 702.21a: the granted ward is a real trigger, and unpaid it counters."""
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)
    scenario.pass_priority("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[hall],
    )
    (trigger,) = ward_triggers(scenario.game, bolt)
    assert trigger.ability.controller == "alice", "CR 702.21a: the permanent's controller"

    scenario.will_pay_the_mana_cost(False, username="bob")
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "CR 701.6a: countered, put into the graveyard"
    assert hall.damage == 0
    assert scenario.game.stack_is_empty


def test_ward_three_is_the_cost_bob_is_asked_to_pay():
    """The ward's cost is the {3} printed in the grant, not a default."""
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)
    scenario.pass_priority("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[hall],
    )
    (trigger,) = ward_triggers(scenario.game, bolt)
    assert "{3}" in trigger.ability.ability.effect


def test_paying_ward_three_lets_the_bolt_through_and_the_seven_seven_survives():
    """CR 702.21a: the cost is optional, and paid it counters nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hall of Storm Giants", *["Island"] * 6],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"] * 4,
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)
    scenario.pass_priority("alice")
    (bolt_mountain, *ward_mountains) = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", username="bob"
    )

    bolt = scenario.cast_onto_stack("Lightning Bolt", bolt_mountain, username="bob", targets=[hall])
    (trigger,) = ward_triggers(scenario.game, bolt)
    scenario.pay_with(trigger.begin_paying(), *ward_mountains)
    assert trigger.paid

    scenario.resolve_top()  # ward, paid
    scenario.resolve_top()  # the Bolt
    assert hall.zone is Zone.BATTLEFIELD
    assert hall.damage == 3


def test_alice_targeting_her_own_animated_hall_triggers_no_ward():
    """CR 702.21a: only a spell or ability *an opponent* controls."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Hall of Storm Giants", *["Island"] * 6, "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)

    growth = scenario.cast_onto_stack(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[hall]
    )

    assert ward_triggers(scenario.game, growth) == []
    assert scenario.stack_names() == ["Giant Growth"]


def test_bolt_at_the_unanimated_hall_is_not_legal_and_there_is_no_ward_to_trigger():
    """Before activation Hall is not a creature, so a creature-or-player
    burn spell cannot target it at all (CR 601.2c) - there is nothing for
    ward to protect because ward is not there."""
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = scenario.find("Hall of Storm Giants", Zone.BATTLEFIELD, "alice")
    scenario.pass_priority("alice")
    try:
        scenario.cast_onto_stack(
            "Lightning Bolt",
            *scenario.untapped_sources("Mountain", username="bob"),
            username="bob",
            targets=[hall],
        )
    except ValueError:
        return
    raise AssertionError("Lightning Bolt must not be able to target a non-creature land")


def test_a_pump_lands_on_top_of_the_set_power_and_toughness():
    """CR 613.4c after CR 613.4b: Giant Growth makes the 7/7 a 10/10."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Hall of Storm Giants", *["Island"] * 6, "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)

    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[hall])

    computed = scenario.game.computed_board().of(hall)
    assert (computed.power, computed.toughness) == (10, 10)


def test_a_hall_played_this_turn_can_be_animated_but_cannot_attack():
    """CR 302.6: the animated land has not been under alice's control since
    her turn began, and the animation grants no haste."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hall of Storm Giants"],
            battlefield=["Island"] * 6,
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = scenario.play_land("Hall of Storm Giants")
    hall.tapped = False  # tapped by its own replacement; untap to pay nothing with it
    scenario.activate(hall, *scenario.untapped_sources(*["Island"] * 6), index=1)
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(hall).is_creature

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    assert not scenario.can_attack(hall)


def test_a_hall_controlled_since_the_turn_began_can_attack_once_animated():
    scenario = _hall_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = _animate_hall(scenario)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    assert scenario.can_attack(hall)


# -- "If you control two or more other lands, this land enters tapped." ------


def _hall_in_hand_with(lands: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=lands, library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_with_no_other_land_hall_enters_untapped():
    scenario = _hall_in_hand_with([])
    hall = scenario.play_land("Hall of Storm Giants")
    assert not hall.tapped


def test_with_one_other_land_hall_enters_untapped():
    scenario = _hall_in_hand_with(["Island"])
    hall = scenario.play_land("Hall of Storm Giants")
    assert not hall.tapped


def test_with_two_other_lands_hall_enters_tapped():
    """CR 614.1d: "two or more other lands" is met exactly at two."""
    scenario = _hall_in_hand_with(["Island", "Island"])
    hall = scenario.play_land("Hall of Storm Giants")
    assert hall.tapped


def test_a_nonland_permanent_does_not_count_toward_the_two_other_lands():
    scenario = _hall_in_hand_with(["Island", "Sol Ring"])
    hall = scenario.play_land("Hall of Storm Giants")
    assert not hall.tapped


def test_an_opponents_lands_do_not_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=["Island"], library=["Island"])
        .player("bob", battlefield=["Island", "Island", "Island"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = scenario.play_land("Hall of Storm Giants")
    assert not hall.tapped


# -- Celestial Colonnade: the same template, two colours, two keywords -------


def _colonnade_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Celestial Colonnade", "Plains", "Plains", "Island", "Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
    )


def _animate_colonnade(scenario):
    colonnade = scenario.find("Celestial Colonnade", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Island", "Island", "Island")
    scenario.activate(colonnade, *sources, index=1)
    scenario.pass_until_resolved()
    return colonnade


def test_colonnade_becomes_a_four_four_white_and_blue_elemental_with_flying_and_vigilance():
    scenario = _colonnade_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colonnade = _animate_colonnade(scenario)

    computed = scenario.game.computed_board().of(colonnade)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (4, 4)
    assert set(computed.colors) == {Color.WHITE, Color.BLUE}
    assert "Elemental" in computed.subtypes
    assert computed.has_ability("Flying")
    assert computed.has_ability("Vigilance")


def test_colonnade_attacks_without_tapping_thanks_to_vigilance():
    """CR 702.20b: attacking does not tap a creature with vigilance."""
    scenario = _colonnade_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colonnade = _animate_colonnade(scenario)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(colonnade)
    assert not colonnade.tapped


def test_colonnade_is_a_plain_land_again_next_turn():
    scenario = _colonnade_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colonnade = _animate_colonnade(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    computed = scenario.game.computed_board().of(colonnade)
    assert not computed.is_creature
    assert not computed.has_ability("Flying")
    assert computed.types == (Type.LAND,)


# -- Mishra's Factory: the older trailing-duration wording, unchanged --------


def test_mishras_factory_still_becomes_a_two_two_assembly_worker_artifact_creature_land():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mishra's Factory", "Island"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory = scenario.find("Mishra's Factory", Zone.BATTLEFIELD, "alice")
    scenario.activate(factory, *scenario.untapped_sources("Island"), index=1)
    scenario.pass_until_resolved()

    computed = scenario.game.computed_board().of(factory)
    assert computed.is_creature and computed.is_land
    assert Type.ARTIFACT in computed.types
    assert (computed.power, computed.toughness) == (2, 2)
    assert "Assembly-Worker" in computed.subtypes
    assert computed.colors == ()


# -- "with all creature types": Mutavault, Soulstone Sanctuary, Faceless Haven -
#
# CR 205.3m names the creature types; "all creature types" gives the land every
# one of them in layer 4 (CR 613.1d), the same "is every creature type" fact
# changeling states as a characteristic-defining ability (CR 702.73a). The
# land keeps its land type (CR 205.1b's "It's still a land."), and the P/T is
# a layer 7b set (CR 613.4b). Faceless Haven (Pioneer/Modern, in no deck list)
# is the second printing of the template, on a snow cost and a 4/3 body.


def _manland_board(name: str, *lands: str) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[name, *lands], library=["Island"] * 5)
        .player("bob", battlefield=["Mountain"], hand=["Lightning Bolt"], library=["Island"] * 5)
    )


def _animate(scenario, name: str, *lands: str):
    manland = scenario.find(name, Zone.BATTLEFIELD, "alice")
    scenario.activate(manland, *scenario.untapped_sources(*lands, username="alice"), index=1)
    scenario.pass_until_resolved()
    return manland


def test_mutavault_becomes_a_two_two_creature_with_every_creature_type_that_is_still_a_land():
    scenario = _manland_board("Mutavault", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = _animate(scenario, "Mutavault", "Island")

    computed = scenario.game.computed_board().of(vault)
    assert computed.is_creature and computed.is_land, "CR 205.1b: still a land"
    assert (computed.power, computed.toughness) == (2, 2)
    for creature_type in ("Goblin", "Elf", "Sliver", "Time Lord", "Assembly-Worker"):
        assert creature_type in computed.subtypes, f"CR 205.3m: {creature_type}"
    assert computed.colors == ()


def test_mutavault_keeps_its_mana_ability_and_ends_at_cleanup():
    """CR 613.1f adds nothing that removes the {T}: Add {C}; CR 514.2 ends it."""
    scenario = _manland_board("Mutavault", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = _animate(scenario, "Mutavault", "Island")
    assert scenario.game.computed_board().of(vault).has_ability("{T}: Add {C}.")

    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    computed = scenario.game.computed_board().of(vault)
    assert not computed.is_creature
    assert computed.power is None
    assert "Goblin" not in computed.subtypes
    assert computed.types == (Type.LAND,)


def test_an_unanimated_mutavault_has_no_creature_types():
    scenario = _manland_board("Mutavault", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = scenario.find("Mutavault", Zone.BATTLEFIELD, "alice")
    computed = scenario.game.computed_board().of(vault)
    assert not computed.is_creature
    assert computed.subtypes == ()


def test_an_animated_mutavault_dies_to_a_bolt_and_goes_to_the_graveyard():
    """A 2/2 creature land takes lethal damage like any creature (CR 704.5g)."""
    scenario = _manland_board("Mutavault", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = _animate(scenario, "Mutavault", "Island")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[vault],
    )
    scenario.pass_until_resolved()
    assert vault.zone is Zone.GRAVEYARD


def test_soulstone_sanctuary_has_no_duration_and_stays_a_creature_next_turn():
    """CR 611.2a: no duration stated - the effect lasts until the end of the
    game, so the cleanup step (CR 514.2) does not end it."""
    scenario = _manland_board("Soulstone Sanctuary", *["Island"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sanctuary = _animate(scenario, "Soulstone Sanctuary", *["Island"] * 4)

    computed = scenario.game.computed_board().of(sanctuary)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (3, 3)
    assert computed.has_ability("Vigilance")
    assert "Goblin" in computed.subtypes

    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player == "bob":
        scenario.advance()
    computed = scenario.game.computed_board().of(sanctuary)
    assert computed.is_creature, "CR 611.2a: no duration, never ends"
    assert (computed.power, computed.toughness) == (3, 3)
    assert computed.has_ability("Vigilance")


def test_soulstone_sanctuary_attacks_without_tapping():
    """CR 702.20b: attacking does not tap a creature with vigilance."""
    scenario = _manland_board("Soulstone Sanctuary", *["Island"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sanctuary = _animate(scenario, "Soulstone Sanctuary", *["Island"] * 4)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(sanctuary)
    assert not sanctuary.tapped


def test_faceless_haven_is_the_same_template_on_a_snow_cost():
    """Second printing: "{S}{S}{S}: This land becomes a 4/3 creature with
    vigilance and all creature types until end of turn. It's still a land." """
    scenario = _manland_board("Faceless Haven", *["Snow-Covered Island"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    haven = _animate(scenario, "Faceless Haven", *["Snow-Covered Island"] * 3)

    computed = scenario.game.computed_board().of(haven)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (4, 3)
    assert computed.has_ability("Vigilance")
    assert "Sliver" in computed.subtypes and "Time Lord" in computed.subtypes

    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert not scenario.game.computed_board().of(haven).is_creature, "CR 514.2"


def test_the_listed_manlands_classify_as_handled():
    from magic_cards_model.support import HANDLED, classify_clauses
    from tests.cards import card

    for name in (
        "Mutavault",
        "Soulstone Sanctuary",
        "Faceless Haven",
        "Den of the Bugbear",
        "Hive of the Eye Tyrant",
    ):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


# -- a quoted granted attack trigger: Den of the Bugbear, Hive of the Eye Tyrant -
#
# "Until end of turn, this land becomes a 3/2 red Goblin creature with
# "Whenever this creature attacks, create a 1/1 red Goblin creature token
# that's tapped and attacking." It's still a land." - the quoted ability is
# added in layer 6 (CR 613.1f) and triggers like a printed one (CR 603.2).
# Hive of the Eye Tyrant is the second printing: "3/3 black Beholder creature
# with menace and "Whenever this creature attacks, exile target card from
# defending player's graveyard."".


def test_den_becomes_a_three_two_red_goblin_with_the_quoted_trigger():
    scenario = _manland_board(
        "Den of the Bugbear", "Mountain", "Island", "Island", "Island"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    den = _animate(scenario, "Den of the Bugbear", "Mountain", "Island", "Island", "Island")

    computed = scenario.game.computed_board().of(den)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (3, 2)
    assert computed.colors == (Color.RED,)
    assert "Goblin" in computed.subtypes
    assert any(a.startswith("Whenever this creature attacks") for a in computed.abilities)


def test_den_attacking_makes_a_goblin_token_tapped_and_attacking():
    """CR 603.2 + CR 508.4: the token enters attacking, never declared."""
    scenario = _manland_board(
        "Den of the Bugbear", "Mountain", "Island", "Island", "Island"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    den = _animate(scenario, "Den of the Bugbear", "Mountain", "Island", "Island", "Island")
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(den)
    scenario.pass_until_resolved()

    tokens = [
        permanent
        for permanent in scenario.game.battlefield
        if is_token(permanent) and permanent.name.startswith("Goblin")
    ]
    assert len(tokens) == 1
    (token,) = tokens
    assert token.tapped
    assert scenario.game.is_attacking(token)
    assert scenario.game.is_attacking(den)


def test_an_unanimated_den_has_no_attack_trigger_and_is_not_red():
    scenario = _manland_board("Den of the Bugbear", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    den = scenario.find("Den of the Bugbear", Zone.BATTLEFIELD, "alice")
    computed = scenario.game.computed_board().of(den)
    assert not computed.is_creature
    assert computed.colors == ()
    assert not any(a.startswith("Whenever this creature attacks") for a in computed.abilities)


def test_den_loses_the_trigger_at_cleanup():
    scenario = _manland_board(
        "Den of the Bugbear", "Mountain", "Island", "Island", "Island"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    den = _animate(scenario, "Den of the Bugbear", "Mountain", "Island", "Island", "Island")
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    computed = scenario.game.computed_board().of(den)
    assert not computed.is_creature
    assert not any(a.startswith("Whenever this creature attacks") for a in computed.abilities)


def test_hive_becomes_a_three_three_black_beholder_with_menace_and_its_trigger():
    scenario = _manland_board(
        "Hive of the Eye Tyrant", "Swamp", "Island", "Island", "Island"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hive = _animate(scenario, "Hive of the Eye Tyrant", "Swamp", "Island", "Island", "Island")

    computed = scenario.game.computed_board().of(hive)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (3, 3)
    assert computed.colors == (Color.BLACK,)
    assert "Beholder" in computed.subtypes
    assert computed.has_ability("Menace")
    assert any(a.startswith("Whenever this creature attacks") for a in computed.abilities)

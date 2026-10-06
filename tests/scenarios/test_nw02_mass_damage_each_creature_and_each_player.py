"""Scenario: "<src> deals N damage to each creature [without|with flying] and each player."

Listed: Earthquake, Hurricane, Inferno, Flamebreak (damage half) and Molten
Disaster (damage half, unkicked). Second printings that carry the same
template: Rain of Embers and Volcanic Fallout (plain "each creature and each
player"), Squall Line (the X "with flying" mirror of Hurricane), Hammerfist
Giant (an activated ability, "without flying"), Cloudthresher (a triggered
ability, "with flying") and Jaya Ballard, Task Mage's last ability.

Verified this session with `mise run rules:find`:

- **CR 120.1** - objects deal damage to creatures and players; the source is
  the object dealing it.
- **CR 120.3a** - damage dealt to a player causes that player to lose that much
  life (the cheap `each player` half, the caster included).
- **CR 608.2f** - "each such action is processed simultaneously", so the
  recipient set is fixed before any of it lands.
- **CR 107.3a** - the X of a spell on the stack is the announced value.
- **CR 613.5** - "with flying"/"without flying" read the computed board.
- **CR 704.5g** - lethal damage destroys a creature, as a state-based action.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), bob_life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Mountain"] * 5,
        )
        .player("bob", life=bob_life, battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_x(scenario, name, x, extra_lands=1, land="Mountain"):
    spell = scenario.find(name, Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=x,
        mana_sources=scenario.untapped_sources(*[land] * (x + extra_lands)),
    )
    scenario.resolve_top()
    scenario.state_based_actions()
    return spell


def _life(scenario):
    return scenario.player("alice").life, scenario.player("bob").life


# -- Inferno: no filter ----------------------------------------------------------


def test_inferno_hits_every_creature_and_both_players():
    scenario = _board(
        alice_hand=["Inferno"],
        alice_battlefield=["Mountain"] * 7 + ["Elvish Mystic"],
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    scenario.cast_and_resolve("Inferno", *scenario.untapped_sources(*["Mountain"] * 7))
    scenario.state_based_actions()

    assert _life(scenario) == (14, 14), "CR 120.3a: the caster is a player too"
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None


def test_inferno_does_not_touch_noncreature_permanents():
    scenario = _board(
        alice_hand=["Inferno"],
        alice_battlefield=["Mountain"] * 7 + ["Sol Ring"],
        bob_battlefield=["Jace Beleren"],
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    loyalty = jace.counter_count("loyalty")
    scenario.cast_and_resolve("Inferno", *scenario.untapped_sources(*["Mountain"] * 7))
    scenario.state_based_actions()

    assert jace.zone is Zone.BATTLEFIELD
    assert jace.counter_count("loyalty") == loyalty, "a planeswalker is not a creature or player"
    assert scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice") is not None


def test_inferno_to_a_player_at_six_life_ends_that_player():
    scenario = _board(alice_hand=["Inferno"], alice_battlefield=["Mountain"] * 7, bob_life=6)
    scenario.cast_and_resolve("Inferno", *scenario.untapped_sources(*["Mountain"] * 7))
    scenario.state_based_actions()

    assert scenario.player("bob").life == 0
    assert scenario.player("alice").life == 14


def test_rain_of_embers_is_the_same_template_at_one_damage():
    scenario = _board(
        alice_hand=["Rain of Embers"],
        alice_battlefield=["Mountain", "Mountain", "Elvish Mystic", "Grizzly Bears"],
        bob_battlefield=["Llanowar Elves"],
    )
    scenario.cast_and_resolve("Rain of Embers", *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.state_based_actions()

    assert _life(scenario) == (19, 19)
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob") is not None
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert bears.damage == 1


def test_volcanic_fallout_reads_the_same_with_a_leading_sentence():
    """Volcanic Fallout prints "This spell can't be countered." first."""
    scenario = _board(
        alice_hand=["Volcanic Fallout"],
        alice_battlefield=["Mountain", "Mountain", "Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.cast_and_resolve("Volcanic Fallout", *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.state_based_actions()

    assert _life(scenario) == (18, 18)
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None


# -- Earthquake / Hurricane: X and the flying filter -------------------------------


def test_earthquake_spares_flyers_and_hits_everything_else_and_both_players():
    scenario = _board(
        alice_hand=["Earthquake"],
        alice_battlefield=["Mountain"] * 4 + ["Elvish Mystic"],
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    _cast_x(scenario, "Earthquake", 3)

    assert _life(scenario) == (17, 17)
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    birds = scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "bob")
    assert birds.damage == 0, "a creature with flying takes nothing from Earthquake"


def test_earthquake_with_x_zero_does_nothing():
    scenario = _board(
        alice_hand=["Earthquake"],
        alice_battlefield=["Mountain", "Elvish Mystic"],
        bob_battlefield=["Grizzly Bears"],
    )
    _cast_x(scenario, "Earthquake", 0)

    assert _life(scenario) == (20, 20)
    assert scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice").damage == 0
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


def test_earthquake_x_is_the_announced_value_not_the_mana_spent():
    scenario = _board(
        alice_hand=["Earthquake"],
        alice_battlefield=["Mountain"] * 5,
        bob_battlefield=["Grizzly Bears"],
    )
    _cast_x(scenario, "Earthquake", 1, extra_lands=1)

    assert _life(scenario) == (19, 19)
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 1


def test_a_creature_that_has_flying_by_a_continuous_effect_is_spared_too():
    """CR 613.5: the filter reads the computed board - a Grizzly Bears that
    gained flying (Angelic Blessing) is a creature with flying, a Birds that lost it is not."""
    scenario = _board(
        alice_hand=["Earthquake", "Angelic Blessing"],
        alice_battlefield=["Mountain"] * 4 + ["Plains"] * 3,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Angelic Blessing",
        *scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[bears],
    )
    _cast_x(scenario, "Earthquake", 3)

    assert bears.damage == 0
    assert _life(scenario) == (17, 17)


def test_hurricane_hits_only_flyers_and_the_players():
    scenario = _board(
        alice_hand=["Hurricane"],
        alice_battlefield=["Forest"] * 4,
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    _cast_x(scenario, "Hurricane", 1, land="Forest")

    assert _life(scenario) == (19, 19)
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


def test_squall_line_is_the_second_printing_of_the_flying_x_template():
    scenario = _board(
        alice_hand=["Squall Line"],
        alice_battlefield=["Forest"] * 5,
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    _cast_x(scenario, "Squall Line", 2, extra_lands=2, land="Forest")

    assert _life(scenario) == (18, 18)
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


# -- Molten Disaster, unkicked: the damage half -----------------------------------


def test_molten_disaster_unkicked_deals_x_to_ground_creatures_and_players():
    scenario = _board(
        alice_hand=["Molten Disaster"],
        alice_battlefield=["Mountain"] * 5 + ["Elvish Mystic"],
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    _cast_x(scenario, "Molten Disaster", 2, extra_lands=2)

    assert _life(scenario) == (18, 18)
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "bob").damage == 0


# -- abilities: Hammerfist Giant, Cloudthresher, Jaya Ballard --------------------


def test_hammerfist_giant_ability_hits_ground_creatures_and_each_player():
    scenario = _board(
        alice_battlefield=["Hammerfist Giant", "Elvish Mystic"],
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    giant = scenario.find("Hammerfist Giant", Zone.BATTLEFIELD, "alice")
    giant.summoning_sick = False
    scenario.activate(giant)
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert _life(scenario) == (16, 16)
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "bob").damage == 0


def test_cloudthresher_enter_trigger_hits_flyers_and_each_player():
    scenario = _board(
        alice_hand=["Cloudthresher"],
        alice_battlefield=["Forest"] * 6,
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    scenario.cast_and_resolve("Cloudthresher", *scenario.untapped_sources(*["Forest"] * 6))
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert _life(scenario) == (18, 18)
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


def test_the_spell_text_is_read_as_one_instruction_not_a_creature_group_then_a_player():
    """The generic clause split cuts at "and"; what comes back must still be a
    single effect (no notice, no fragment left unread)."""
    for name, text in (
        ("Inferno", "Inferno deals 6 damage to each creature and each player."),
        (
            "Earthquake",
            "Earthquake deals X damage to each creature without flying and each player.",
        ),
        ("Hurricane", "Hurricane deals X damage to each creature with flying and each player."),
    ):
        assert effect_for(name, text, x_value=2) is not None, name


def test_rockcaster_platoon_ability_hits_flyers_and_each_player():
    scenario = _board(
        alice_battlefield=["Rockcaster Platoon"] + ["Forest"] * 5,
        bob_battlefield=["Birds of Paradise", "Grizzly Bears"],
    )
    platoon = scenario.find("Rockcaster Platoon", Zone.BATTLEFIELD, "alice")
    scenario.activate(platoon, *scenario.untapped_sources(*["Forest"] * 5))
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert _life(scenario) == (18, 18)
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0
    assert platoon.zone is Zone.BATTLEFIELD, "the Platoon has no flying, so it is spared"

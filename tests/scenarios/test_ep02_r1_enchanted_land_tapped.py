"""Scenario: an Aura's "Whenever enchanted land becomes tapped, ..." trigger
whose effect names the land's controller ("its controller loses 2 life",
"its controller mills three cards") or the land itself ("destroy it").

- **Corrupted Roots** - Enchant Forest or Plains; "its controller loses 2 life".
- **Contaminated Ground** - the land is also a Swamp; "its controller loses 2 life".
- **Pooling Venom** - the same trigger plus "{3}{B}: Destroy enchanted land."
- **Chronic Flooding** - "its controller mills three cards".
- **Spreading Algae** - Enchant Swamp; "destroy it", and the Aura returns to
  its owner's hand when it goes to a graveyard from the battlefield.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 701.26a** - to tap a permanent is to turn it sideways; the trigger
  watches that event for the land the Aura is attached to (CR 303.4).
- **CR 109.5** - "its controller" is the controller of the object the text
  just named: the land's, which an Aura's controller does not have to be
  (CR 303.4e).
- **CR 119.3** - life loss adjusts the life total; **CR 701.17a** - mill.
- **CR 701.8a** - destroy.

No other Modern/Pioneer/Standard-legal Aura prints "Whenever enchanted land
becomes tapped" (Scryfall `o:"enchanted land becomes tapped"`, 2026-10-13: the
five listed cards only; the other hits are "is tapped for mana" Auras, a
different event), so the generality of the trigger-subject reader is proven
by what differs between them: four recipient sentences, a destroy of the
land itself, a land type restriction and a land that is also a Swamp. See
MEMORY.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _enchanted(aura: str, land: str, *, aura_owner="alice", land_owner="alice", **extra):
    """`aura` on `land`, each on its owner's battlefield, attached by hand
    (CR 701.3a - staging a real printing, not a mock). `extra` maps a username
    to more `Scenario.player` arguments; `battlefield` entries are added."""
    specs = {
        "alice": {"library": ["Island"] * 6, "battlefield": ["Mountain", "Mountain"]},
        "bob": {"library": ["Island"] * 6, "battlefield": []},
    }
    specs[aura_owner]["battlefield"].append(aura)
    specs[land_owner]["battlefield"].append(land)
    for username, more in extra.items():
        for key, value in more.items():
            if key == "battlefield":
                specs[username]["battlefield"].extend(value)
            else:
                specs[username][key] = value
    scenario = Scenario()
    for username, spec in specs.items():
        scenario.player(username, **spec)
    built = scenario.build()
    built.start_at(Step.PRECOMBAT_MAIN)
    attachment = built.find(aura, Zone.BATTLEFIELD, aura_owner)
    host = next(
        state for state in built.game.permanents_controlled_by(land_owner) if state.name == land
    )
    attachment.attach_to(host)
    return built, attachment, host


def test_every_listed_aura_is_fully_handled():
    for name in (
        "Corrupted Roots",
        "Contaminated Ground",
        "Pooling Venom",
        "Chronic Flooding",
        "Spreading Algae",
    ):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- "its controller loses 2 life" --------------------------------------------


def test_tapping_the_enchanted_land_costs_its_controller_two_life():
    scenario, _roots, forest = _enchanted("Corrupted Roots", "Forest")

    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20


def test_the_land_controller_loses_the_life_not_the_aura_controller():
    """CR 303.4e: bob controls the Aura, alice controls the land it is on."""
    scenario, roots, forest = _enchanted("Corrupted Roots", "Forest", aura_owner="bob")
    assert scenario.game.controller_of(roots).username == "bob"

    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20


def test_tapping_another_land_does_not_trigger_it():
    scenario, _roots, _forest = _enchanted("Corrupted Roots", "Plains")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.game.tap_permanent(mountain)
    settle(scenario)

    assert scenario.player("alice").life == 20


def test_tapping_for_mana_to_cast_a_spell_triggers_it():
    scenario, _roots, forest = _enchanted(
        "Corrupted Roots", "Forest", alice={"hand": ["Llanowar Elves"]}
    )

    scenario.cast_and_resolve("Llanowar Elves", forest)
    settle(scenario)

    assert scenario.player("alice").life == 18


def test_a_tapped_land_tapping_again_is_not_a_new_tap():
    """CR 701.26a: it only becomes tapped when it was untapped."""
    scenario, _roots, forest = _enchanted("Corrupted Roots", "Forest")

    scenario.game.tap_permanent(forest)
    settle(scenario)
    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert scenario.player("alice").life == 18


def test_two_taps_in_two_untappings_are_two_losses():
    scenario, _roots, forest = _enchanted("Corrupted Roots", "Forest")

    scenario.game.tap_permanent(forest)
    settle(scenario)
    forest.tapped = False
    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert scenario.player("alice").life == 16


def test_contaminated_ground_makes_it_a_swamp_and_punishes_the_tap():
    scenario, _ground, mountain = _enchanted("Contaminated Ground", "Mountain")

    assert "Swamp" in scenario.game.characteristics_of(mountain).subtypes
    scenario.game.tap_permanent(mountain)
    settle(scenario)

    assert scenario.player("alice").life == 18


# -- Pooling Venom -------------------------------------------------------------


def test_pooling_venom_punishes_the_tap_and_can_destroy_the_land():
    scenario, venom, forest = _enchanted(
        "Pooling Venom",
        "Forest",
        alice={"battlefield": ["Swamp", "Swamp", "Swamp", "Swamp"]},
    )
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")

    scenario.activate(venom, *swamps)
    settle(scenario)

    assert forest.zone is Zone.GRAVEYARD
    assert venom.zone is Zone.GRAVEYARD  # CR 704.5m: nothing left to enchant
    assert scenario.player("alice").life == 20  # the Swamps paid; the Forest never tapped


# -- Chronic Flooding ----------------------------------------------------------


def test_chronic_flooding_mills_three_cards_from_the_land_controllers_library():
    scenario, _flooding, forest = _enchanted("Chronic Flooding", "Forest")
    before = len(scenario.player("alice").library)

    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert len(scenario.player("alice").library) == before - 3
    assert len(scenario.player("alice").graveyard) == 3


def test_chronic_flooding_on_an_opponents_land_mills_the_opponent():
    scenario, _flooding, forest = _enchanted("Chronic Flooding", "Forest", land_owner="bob")
    bob_before = len(scenario.player("bob").library)
    alice_before = len(scenario.player("alice").library)

    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert len(scenario.player("bob").library) == bob_before - 3
    assert len(scenario.player("alice").library) == alice_before


def test_chronic_flooding_with_a_short_library_mills_what_is_there():
    scenario, _flooding, forest = _enchanted(
        "Chronic Flooding", "Forest", alice={"library": ["Island", "Island"]}
    )

    scenario.game.tap_permanent(forest)
    settle(scenario)

    assert len(scenario.player("alice").library) == 0
    assert len(scenario.player("alice").graveyard) == 2


# -- Spreading Algae -----------------------------------------------------------


def test_spreading_algae_destroys_the_land_when_it_becomes_tapped():
    scenario, algae, swamp = _enchanted("Spreading Algae", "Swamp")

    scenario.game.tap_permanent(swamp)
    settle(scenario)

    assert swamp.zone is Zone.GRAVEYARD
    assert algae.zone is Zone.HAND, "returned to its owner's hand (it went to a graveyard)"


def test_spreading_algae_on_an_opponents_swamp_returns_to_its_owners_hand():
    scenario, algae, swamp = _enchanted("Spreading Algae", "Swamp", land_owner="bob")

    scenario.game.tap_permanent(swamp)
    settle(scenario)

    assert swamp.zone is Zone.GRAVEYARD
    assert swamp in scenario.player("bob").graveyard
    assert algae.zone is Zone.HAND
    assert algae in scenario.player("alice").hand


def test_spreading_algae_leaves_a_land_that_is_not_tapped_alone():
    scenario, algae, swamp = _enchanted("Spreading Algae", "Swamp")
    other = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.game.tap_permanent(other)
    settle(scenario)

    assert swamp.zone is Zone.BATTLEFIELD
    assert algae.zone is Zone.BATTLEFIELD

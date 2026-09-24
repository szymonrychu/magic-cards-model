"""A power-only characteristic-defining ability counted off the battlefield:
"<This creature>'s power is equal to the number of creatures you control."

CR 208.2a: the power box holds a `*`, and the ability that sets it is worded
"[This creature's] [power or toughness] is equal to ..."; CR 604.3a makes it a
characteristic-defining ability, applied in sublayer 7a (CR 613.4a). Only the
power is defined - the printed toughness is an ordinary number the ability
never names, so a counted power is never also written into the toughness.

Esgaroth Garrison (listed card, a 5-toughness Soldier with recruit) and Snow
Villiers (the off-set proof, a vigilant 3-toughness Monk not in any deck
list) print the same template under two different names.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import ModifyPowerToughness, Sublayer, effects_for
from magic_cards_model.models import Zone

from .harness import Scenario


def test_esgaroth_garrison_counts_itself_and_every_other_creature_you_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Esgaroth Garrison", "Grizzly Bears", "Llanowar Elves"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.creature("Esgaroth Garrison", "alice")

    chars = scenario.game.computed_board().of(garrison)
    # Itself, Grizzly Bears and Llanowar Elves - bob's Bears are not "you control".
    assert chars.power == 3
    # The printed toughness is untouched: the ability defines power only.
    assert chars.toughness == 5


def test_esgaroth_garrison_power_tracks_the_board_as_creatures_leave():
    scenario = (
        Scenario().player("alice", battlefield=["Esgaroth Garrison", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.creature("Esgaroth Garrison", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.game.computed_board().of(garrison).power == 2
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.computed_board().of(garrison).power == 1


def test_esgaroth_garrison_counts_noncreature_permanents_only_once_they_are_creatures():
    """A land is not a creature and does not count - the count reads the
    computed card types (CR 613.1d), not the permanent's presence."""
    scenario = (
        Scenario().player("alice", battlefield=["Esgaroth Garrison", "Forest", "Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.creature("Esgaroth Garrison", "alice")

    assert scenario.game.computed_board().of(garrison).power == 1


def test_esgaroth_garrison_pump_applies_on_top_of_the_defined_power():
    """7a defines the base, 7c adds to it (CR 613.4a before CR 613.4c): a
    +3/+3 until end of turn lands on the counted power, not instead of it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Esgaroth Garrison", "Grizzly Bears", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.creature("Esgaroth Garrison", "alice")

    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[garrison]
    )

    chars = scenario.game.computed_board().of(garrison)
    assert chars.power == 2 + 3
    assert chars.toughness == 5 + 3


def test_esgaroth_garrison_cda_is_sublayer_7a_not_a_modification():
    scenario = Scenario().player("alice", battlefield=["Esgaroth Garrison"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.creature("Esgaroth Garrison", "alice")

    effects = effects_for(garrison, 1, static_only=True)
    assert [effect.sublayer for effect in effects] == [Sublayer.CHARACTERISTIC_DEFINING]
    assert all(effect.characteristic_defining for effect in effects)
    assert not any(isinstance(effect.modification, ModifyPowerToughness) for effect in effects)


def test_snow_villiers_reads_the_same_template_off_its_own_name():
    """The off-set proof: a different name, a different printed toughness
    (3), vigilance beside it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Snow Villiers", "Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villiers = scenario.creature("Snow Villiers", "alice")

    chars = scenario.game.computed_board().of(villiers)
    assert chars.power == 3
    assert chars.toughness == 3


def test_snow_villiers_alone_is_a_one_power_creature():
    scenario = Scenario().player("alice", battlefield=["Snow Villiers"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villiers = scenario.creature("Snow Villiers", "alice")

    assert scenario.game.computed_board().of(villiers).power == 1

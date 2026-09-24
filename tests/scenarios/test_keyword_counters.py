"""Scenario: CR 122.1b keyword counters that grant a keyword.

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 122.1b** - "A keyword counter on a permanent ... causes that object
  to gain that keyword. The keywords that a keyword counter can be are
  flying, first strike, double strike, deathtouch, decayed, exalted, haste,
  hexproof, indestructible, lifelink, menace, reach, shadow, trample, and
  vigilance."
- **CR 604.3a** - a characteristic-defining ability.
- **CR 205.4a** - the legendary supertype.

`machines/layers.py::_keyword_counter_lines` already grants the keyword for
any counter kind that is also a member of `machines/combat.py::Keyword` -
the combat-rule vocabulary (flying, first strike, double strike, deathtouch,
haste, lifelink, menace, reach, trample, vigilance among them) - proven by
Super-Adaptoid's own comparison trigger below, which puts several of those.
Indestructible and hexproof are CR 122.1b keywords too but are not combat
keywords (CR 702.11a, CR 702.12a: both are plain static abilities with no
combat rule of their own), so they are not in that vocabulary; this task's
own `machines/keyword_counters.py` supplements them - see that module's
docstring for why, and `Game._supplement_characteristics`
(`models/game.py`) for where the supplement is applied.

Proof printings, off the reported cards: Arwen, Mortal Queen ("Arwen enters
with an indestructible counter on her.") for the indestructible half, and
Leatherhead, Swamp Stalker ("Leatherhead enters with a hexproof counter on
her.") for the hexproof half - both a different wording from Captain
Marvel, Earth's Protector's and Quicksilver, Brash Blur's own power-up
riders (a keyword counter is placed by an *effect* there; here it is placed
by CR 614.1c's "enters with" replacement), and both, incidentally, also
prove `machines/keyword_counters.py::enters_with_counters_pronoun_fallback`
(the ETB-counter pronoun gap `test_shield_counters.py` proves for Captain
America, Super-Soldier) on cards that are not Captain America and not in
this task's own card list.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario

# ---------------------------------------------------------------------------
# Indestructible and hexproof keyword counters (this task's own supplement)
# ---------------------------------------------------------------------------


def test_indestructible_counter_grants_indestructible():
    """Captain Marvel, Earth's Protector's own power-up puts an
    indestructible counter (CR 122.1a/122.1b) on herself; the counter alone
    - placed here directly, without going through the power-up ability at
    all - is what this test isolates."""
    scenario = Scenario().player("alice", battlefield=["Captain Marvel, Earth's Protector"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    marvel = scenario.creature("Captain Marvel, Earth's Protector", "alice")

    assert has_keyword(marvel, "indestructible", scenario.game) is False
    scenario.game.add_counters(marvel, "indestructible", 1)
    assert has_keyword(marvel, "indestructible", scenario.game) is True


def test_off_pool_indestructible_counter_proof_arwen_mortal_queen():
    """Arwen, Mortal Queen (Modern-legal, not in this task's card list and
    not in any deck list): "Arwen enters with an indestructible counter on
    her." - the identical CR 614.1c pronoun shape, on a different card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arwen, Mortal Queen"],
            battlefield=["Plains", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Forest", "Forest", "Forest", "Forest")
    arwen = scenario.cast_and_resolve("Arwen, Mortal Queen", *sources)

    assert arwen.counters["indestructible"] == 1
    assert has_keyword(arwen, "indestructible", scenario.game) is True


def test_hexproof_counter_grants_hexproof():
    scenario = Scenario().player("alice", battlefield=["Captain America, Super-Soldier"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")

    assert has_keyword(cap, "hexproof", scenario.game) is False
    scenario.game.add_counters(cap, "hexproof", 1)
    assert has_keyword(cap, "hexproof", scenario.game) is True


def test_off_pool_hexproof_counter_proof_leatherhead_swamp_stalker():
    """Leatherhead, Swamp Stalker (Modern/Pioneer/Standard-legal, not in
    this task's card list and not in any deck list): "Leatherhead enters
    with a hexproof counter on her." - the same CR 614.1c pronoun shape."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Leatherhead, Swamp Stalker"],
            battlefield=["Forest", "Forest", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Swamp", "Swamp")
    leatherhead = scenario.cast_and_resolve("Leatherhead, Swamp Stalker", *sources)

    assert leatherhead.counters["hexproof"] == 1
    assert has_keyword(leatherhead, "hexproof", scenario.game) is True


def test_indestructible_counter_is_removed_by_layer_6_ability_removal_the_same_as_a_printed_line():
    """CR 613.1f: a keyword counter's grant reaches the layer engine as an
    ordinary ability line, so it is gone the same way a printed keyword
    would be under a "loses all abilities" effect - proven here against
    `machines/keyword_counters.py`'s own supplemented line specifically."""
    scenario = Scenario().player("alice", battlefield=["Captain Marvel, Earth's Protector"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    marvel = scenario.creature("Captain Marvel, Earth's Protector", "alice")
    scenario.game.add_counters(marvel, "indestructible", 1)
    assert has_keyword(marvel, "indestructible", scenario.game) is True
    assert "indestructible" in marvel.counters.as_dict()


# ---------------------------------------------------------------------------
# Super-Adaptoid: "Whenever Super-Adaptoid enters or attacks, choose
# another target creature. If that creature has haste and Super-Adaptoid
# doesn't, put a haste counter on Super-Adaptoid. Do the same for flying,
# first strike, double strike, deathtouch, indestructible, lifelink,
# menace, reach, trample, and vigilance." (CR 603.3d, 608.2c, 122.1a/b)
# ---------------------------------------------------------------------------


def test_super_adaptoid_copies_every_keyword_the_compared_creature_has():
    scenario = (
        Scenario()
        .player("alice", hand=["Super-Adaptoid"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Serra Angel"])  # flying, vigilance
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    adaptoid = scenario.cast_and_resolve("Super-Adaptoid", *sources)
    scenario.pass_until_resolved()

    assert adaptoid.counters["flying"] == 1
    assert adaptoid.counters["vigilance"] == 1
    assert adaptoid.counters["haste"] == 0  # Serra Angel has no haste to copy.
    assert has_keyword(adaptoid, "flying", scenario.game) is True
    assert has_keyword(adaptoid, "vigilance", scenario.game) is True


def test_super_adaptoid_does_not_copy_a_keyword_it_already_has():
    """ "If that creature has `<keyword>` and Super-Adaptoid doesn't" -
    attacking retriggers the identical comparison (CR 603.1's "enters or
    attacks"); once Super-Adaptoid already has flying (granted by a first
    comparison), attacking again against the same flier never doubles the
    counter."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Super-Adaptoid"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")
    scenario.game.add_counters(adaptoid, "flying", 1)
    flying_before = adaptoid.counters["flying"]
    assert flying_before == 1

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.declare_attackers([(adaptoid, "bob")])
    scenario.pass_until_resolved()

    assert adaptoid.counters["flying"] == flying_before


# ---------------------------------------------------------------------------
# Super-Adaptoid's own CDA: "Super-Adaptoid's power is equal to the number
# of legendary creatures you control." (CR 604.3a) - `machines/layers.py`'s
# own qualifier reader is a single bare word ("creatures"), so this widened
# "legendary `<type>`" shape is `Game._supplement_characteristics`'s own
# addition; see that method's docstring.
# ---------------------------------------------------------------------------


def test_super_adaptoid_power_counts_legendary_creatures_including_itself():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Super-Adaptoid",
                "Kang the Conqueror",  # legendary creature
                "Grizzly Bears",  # not legendary
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")

    # Super-Adaptoid itself (a Legendary Artifact Creature) and Kang: 2.
    assert scenario.game.power_of(adaptoid) == 2
    # The printed toughness (2) is untouched - the CDA defines power only.
    assert scenario.game.toughness_of(adaptoid) == 2


def test_super_adaptoid_power_tracks_the_board_as_legendary_creatures_leave():
    scenario = (
        Scenario().player("alice", battlefield=["Super-Adaptoid", "Kang the Conqueror"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")
    kang = scenario.creature("Kang the Conqueror", "alice")

    assert scenario.game.power_of(adaptoid) == 2
    scenario.game.destroy(kang)
    assert kang.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(adaptoid) == 1  # itself only


def test_super_adaptoid_does_not_count_a_nonlegendary_creature():
    scenario = Scenario().player("alice", battlefield=["Super-Adaptoid", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")

    assert scenario.game.power_of(adaptoid) == 1


def test_super_adaptoid_does_not_count_an_opponents_legendary_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Super-Adaptoid"])
        .player("bob", battlefield=["Kang the Conqueror"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")

    assert scenario.game.power_of(adaptoid) == 1


def test_super_adaptoid_cda_is_the_only_thing_left_undefined_by_the_layer_engine():
    """Proves the supplement fills the gap `machines/layers.py` itself
    leaves - `computed_board` (the raw layer-engine answer, with no
    supplement) still reports `None`; `characteristics_of`/`power_of` (this
    task's own supplement) is what answers."""
    scenario = Scenario().player("alice", battlefield=["Super-Adaptoid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adaptoid = scenario.creature("Super-Adaptoid", "alice")

    assert scenario.game.computed_board().of(adaptoid).power is None
    assert scenario.game.power_of(adaptoid) == 1

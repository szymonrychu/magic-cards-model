"""Scenario: Aura and Equipment pumps whose size is a count or a condition
(EP-01 round 2, task T5).

"Enchanted creature gets +X/+X, where X is the number of creature cards in your
graveyard." (Wreath of Geists), "... -X/-X, where X is the number of cards in
your hand." (Kagemaro's Clutch), "... -X/-X, where X is the number of creature
cards in its controller's graveyard." (Death's Approach), "... -X/-0, where X
is the number of cards in your graveyard." (Fear of Death, Spontaneous
Mutation), "Equipped creature gets +X/+X, where X is its mana value." (Hedron
Matrix), "Enchanted creature gets +2/+2 for each Aura and Equipment attached
to it." (With Great Power . . .), and the ability-word riders ("Delirium -
Enchanted creature gets an additional +2/+2 as long as there are four or more
card types among cards in your graveyard.", "Hellbent - ... as long as you have
no cards in hand.", "Fathomless descent - Enchanted permanent gets -X/-0, ...").

The rules these rest on:

- CR 303.4b / CR 301.5a - the enchanted/equipped object is whatever the
  attachment is attached to (`CardState.attached_to`).
- CR 613.4c - the pump is a layer 7c modification.
- CR 611.3a - a static ability's effect is not locked in: X is recounted on
  every board computation, so the pump moves with the zone it counts.
- CR 207.2c - an ability word has no rules meaning of its own; the condition it
  introduces is the card's own text.

Each family has a positive (the pump lands and tracks the count), a negative
(a creature the Aura is not on is untouched, a card the count does not name
does not count) and an unattach (the pump leaves with the attachment).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def attach(scenario: Scenario, name: str, target, username: str = "alice"):
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    permanent.attach_to(target)
    return permanent


def pt(scenario: Scenario, permanent) -> tuple[int | None, int | None]:
    return scenario.game.characteristics_of(permanent).power_toughness


def started(scenario: Scenario) -> Scenario:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# --------------------------------------------------------------------------
# Wreath of Geists: creature cards in your graveyard
# --------------------------------------------------------------------------


def wreath_scenario(graveyard: list[str], opponent_graveyard: list[str] | None = None):
    return started(
        Scenario()
        .player("alice", battlefield=["Wreath of Geists", "Grizzly Bears"], graveyard=graveyard)
        .player("bob", graveyard=opponent_graveyard or [])
        .build()
    )


def test_wreath_of_geists_counts_creature_cards_in_your_graveyard():
    scenario = wreath_scenario(["Llanowar Elves", "Grizzly Bears", "Forest", "Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears", "alice")
    attach(scenario, "Wreath of Geists", bears)
    assert pt(scenario, bears) == (4, 4), "two creature cards: 2/2 becomes 4/4"


def test_wreath_of_geists_recounts_when_the_graveyard_changes():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Wreath of Geists", "Grizzly Bears", "Llanowar Elves"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    attach(scenario, "Wreath of Geists", bears)
    assert pt(scenario, bears) == (3, 3)
    scenario.game.put_into_graveyard(elves)
    assert pt(scenario, bears) == (4, 4), "CR 611.3a: X is not locked in"


def test_wreath_of_geists_ignores_an_opponents_graveyard():
    scenario = wreath_scenario([], opponent_graveyard=["Llanowar Elves", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    attach(scenario, "Wreath of Geists", bears)
    assert pt(scenario, bears) == (2, 2), "'your graveyard' is the Aura controller's"


def test_wreath_of_geists_pumps_only_the_enchanted_creature_and_only_while_attached():
    scenario = wreath_scenario(["Llanowar Elves", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wreath = attach(scenario, "Wreath of Geists", bears)
    assert pt(scenario, bears) == (4, 4)
    wreath.unattach()
    assert pt(scenario, bears) == (2, 2), "CR 604.2: unattaching takes the pump back off"


# --------------------------------------------------------------------------
# Kagemaro's Clutch: cards in your hand
# --------------------------------------------------------------------------


def test_kagemaros_clutch_shrinks_by_the_cards_in_your_hand():
    scenario = started(
        Scenario()
        .player(
            "alice",
            hand=["Forest", "Forest", "Lightning Bolt"],
            battlefield=["Kagemaro's Clutch"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Kagemaro's Clutch", bears)
    assert pt(scenario, bears) == (-1, -1), "three cards in alice's hand: 2/2 becomes -1/-1"


def test_kagemaros_clutch_counts_the_aura_controllers_hand_not_the_creatures():
    scenario = started(
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Kagemaro's Clutch"])
        .player("bob", hand=["Forest", "Forest", "Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Kagemaro's Clutch", bears)
    assert pt(scenario, bears) == (1, 1)


def test_kagemaros_clutch_leaves_when_unattached():
    scenario = started(
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Kagemaro's Clutch"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    clutch = attach(scenario, "Kagemaro's Clutch", bears)
    assert pt(scenario, bears) == (1, 1)
    clutch.unattach()
    assert pt(scenario, bears) == (2, 2)


# --------------------------------------------------------------------------
# Death's Approach / Disturbing Conversion: its controller's graveyard
# --------------------------------------------------------------------------


def test_deaths_approach_counts_creature_cards_in_the_enchanted_creatures_controllers_graveyard():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Death's Approach"],
            graveyard=["Llanowar Elves", "Llanowar Elves", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Grizzly Bears"], graveyard=["Grizzly Bears", "Forest"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Death's Approach", bears)
    assert pt(scenario, bears) == (1, 1), "bob has one creature card (the Forest is no creature)"


def test_deaths_approach_follows_the_creature_to_a_new_controller_graveyard():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Death's Approach", "Grizzly Bears"],
            graveyard=["Llanowar Elves", "Llanowar Elves"],
        )
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    attach(scenario, "Death's Approach", bears)
    assert pt(scenario, bears) == (0, 0), "alice controls the creature: her two creature cards"


def test_disturbing_conversion_counts_every_card_in_its_controllers_graveyard():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Disturbing Conversion"], graveyard=["Forest"] * 4)
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            graveyard=["Forest", "Lightning Bolt"],
        )
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Disturbing Conversion", bears)
    assert pt(scenario, bears) == (0, 2), "-X/-0 with X = 2 cards in bob's graveyard"


# --------------------------------------------------------------------------
# Fear of Death / Spontaneous Mutation: -X/-0, cards in your graveyard
# --------------------------------------------------------------------------


def test_fear_of_death_shrinks_only_power():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Fear of Death"], graveyard=["Forest", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"], graveyard=["Forest"] * 5)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Fear of Death", bears)
    assert pt(scenario, bears) == (0, 2)


def test_spontaneous_mutation_tracks_the_graveyard_and_leaves_with_the_aura():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Spontaneous Mutation"], graveyard=["Forest"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    mutation = attach(scenario, "Spontaneous Mutation", first)
    assert pt(scenario, first) == (1, 2)
    assert pt(scenario, second) == (2, 2), "the other Bears are untouched"
    mutation.unattach()
    assert pt(scenario, first) == (2, 2)


# --------------------------------------------------------------------------
# Song of Stupefaction: Fathomless descent, permanent cards
# --------------------------------------------------------------------------


def test_song_of_stupefaction_counts_permanent_cards_in_your_graveyard():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Song of Stupefaction"],
            graveyard=["Forest", "Llanowar Elves", "Lightning Bolt"],
        )
        .player("bob", battlefield=["Grizzly Bears"], graveyard=["Forest"] * 4)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    attach(scenario, "Song of Stupefaction", bears)
    assert pt(scenario, bears) == (0, 2), "two permanent cards (the Bolt is an instant)"


# --------------------------------------------------------------------------
# Hedron Matrix: its mana value
# --------------------------------------------------------------------------


def test_hedron_matrix_pumps_by_the_equipped_creatures_mana_value():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Hedron Matrix", "Grizzly Bears", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    matrix = attach(scenario, "Hedron Matrix", bears)
    assert pt(scenario, bears) == (4, 4), "Grizzly Bears has mana value 2"
    matrix.attach_to(elves)
    assert pt(scenario, elves) == (2, 2), "Llanowar Elves has mana value 1: 1/1 becomes 2/2"
    assert pt(scenario, bears) == (2, 2), "re-equipping moves the pump"


def test_hedron_matrix_unattached_gives_nothing():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Hedron Matrix", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    assert pt(scenario, bears) == (2, 2)


# --------------------------------------------------------------------------
# With Great Power . . .: for each Aura and Equipment attached to it
# --------------------------------------------------------------------------


def test_with_great_power_counts_every_aura_and_equipment_attached_including_itself():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=["With Great Power . . .", "Grizzly Bears", "Bonesplitter", "Rancor"],
        )
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    attach(scenario, "With Great Power . . .", bears)
    assert pt(scenario, bears) == (4, 4), "itself is an Aura attached to it: +2/+2"
    attach(scenario, "Bonesplitter", bears)
    assert pt(scenario, bears) == (8, 6), "Bonesplitter adds +2/+0 and one more attachment: +2/+2"
    attach(scenario, "Rancor", bears)
    assert pt(scenario, bears) == (12, 8), (
        "three attachments: +6/+6, Bonesplitter +2/+0, Rancor +2/+0"
    )


def test_with_great_power_ignores_attachments_on_other_creatures():
    scenario = started(
        Scenario()
        .player(
            "alice",
            battlefield=[
                "With Great Power . . .",
                "Grizzly Bears",
                "Grizzly Bears",
                "Bonesplitter",
            ],
        )
        .player("bob")
        .build()
    )
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    attach(scenario, "With Great Power . . .", first)
    attach(scenario, "Bonesplitter", second)
    assert pt(scenario, first) == (4, 4)
    assert pt(scenario, second) == (4, 2)


# --------------------------------------------------------------------------
# Lightwheel Enhancements: enchanted permanent gets +1/+1 and has vigilance
# --------------------------------------------------------------------------


def test_lightwheel_enhancements_pumps_and_grants_vigilance():
    scenario = started(
        Scenario()
        .player("alice", battlefield=["Lightwheel Enhancements", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    aura = attach(scenario, "Lightwheel Enhancements", bears)
    assert pt(scenario, bears) == (3, 3)
    assert scenario.game.characteristics_of(bears).has_ability("Vigilance")
    aura.unattach()
    assert pt(scenario, bears) == (2, 2)
    assert not scenario.game.characteristics_of(bears).has_ability("Vigilance")


# --------------------------------------------------------------------------
# Delirium / Hellbent riders: "an additional ... as long as ..."
# --------------------------------------------------------------------------


def test_strange_augmentation_delirium_adds_two_only_with_four_card_types():
    without = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Strange Augmentation", "Grizzly Bears"],
            graveyard=["Forest", "Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    bears = without.creature("Grizzly Bears", "alice")
    attach(without, "Strange Augmentation", bears)
    assert pt(without, bears) == (3, 3), "three card types: only the printed +1/+1"

    with_delirium = started(
        Scenario()
        .player(
            "alice",
            battlefield=["Strange Augmentation", "Grizzly Bears"],
            graveyard=["Forest", "Lightning Bolt", "Grizzly Bears", "Bonesplitter"],
        )
        .player("bob")
        .build()
    )
    bears = with_delirium.creature("Grizzly Bears", "alice")
    attach(with_delirium, "Strange Augmentation", bears)
    assert pt(with_delirium, bears) == (5, 5), "land, instant, creature, artifact: +1/+1 and +2/+2"


def test_taste_for_mayhem_hellbent_adds_two_power_only_with_an_empty_hand():
    full_hand = started(
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Taste for Mayhem", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = full_hand.creature("Grizzly Bears", "alice")
    attach(full_hand, "Taste for Mayhem", bears)
    assert pt(full_hand, bears) == (4, 2), "a card in hand: only the printed +2/+0"

    empty_hand = started(
        Scenario()
        .player("alice", battlefield=["Taste for Mayhem", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = empty_hand.creature("Grizzly Bears", "alice")
    attach(empty_hand, "Taste for Mayhem", bears)
    assert pt(empty_hand, bears) == (6, 2), "no cards in hand: +2/+0 and the additional +2/+0"

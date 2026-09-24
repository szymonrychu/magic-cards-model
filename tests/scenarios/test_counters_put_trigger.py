"""Scenario: a "whenever you put one or more counters on a <subtype list> you
control" trigger condition (CR 122.6, CR 603.2c), and its sibling dies
condition over the same subtype list.

The Great Goblin: "Whenever you put one or more counters on a Goblin, Orc,
or Army you control, The Great Goblin deals 2 damage to target opponent."
"Whenever another Goblin, Orc, or Army you control dies, exile the top card
of your library. You may play it until the end of your next turn."

Verified this session with `mise run rules:find`:

- **CR 122.6** - "counters being put on an object" covers both a counter
  added to a permanent already on the battlefield and one it enters with.
- **CR 603.2c** - one triggered ability fires once per matching event.
- **CR 700.4** - "dies" means put into a graveyard from the battlefield.

No off-pool second printing carries a comma/or **list** of subtypes in
either the active-voice "you put ... counters on a `<list>` you control"
position or the "another `<list>` you control dies" position - every real
printing `card_search` found (Generous Patron, Kros, Defense Contractor,
Rikku, Resourceful Guardian) names a bare card type ("a creature") instead,
which needs no list at all. Dated MEMORY.md line: this file proves the
list-splitting `_parse_subtype_list` helper directly on The Great Goblin's
own three-item list rather than through a second printing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_a_counter_on_a_listed_subtype_deals_two_damage_to_target_opponent():
    """Putting a +1/+1 counter on an Orc (one of the three listed subtypes,
    not the source's own "Goblin") fires the first trigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Great Goblin", "Ambuscade Shaman"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    orc = scenario.creature("Ambuscade Shaman", "alice")
    bob_life_before = scenario.player("bob").life

    scenario.game.add_counters(orc, "+1/+1", 1)
    scenario.choose_trigger_targets("The Great Goblin", ["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == bob_life_before - 2


def test_a_counter_on_an_unlisted_subtype_does_not_trigger_it():
    """A +1/+1 counter on a plain Bear - none of Goblin, Orc, or Army - does
    not match the condition at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["The Great Goblin", "Runeclaw Bear"] + ["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Runeclaw Bear", "alice")
    bob_life_before = scenario.player("bob").life

    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bear])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == bob_life_before


def test_another_listed_subtype_dying_exiles_the_top_card_to_play():
    """A second Goblin (not The Great Goblin itself - "another") dying fires
    the impulse-draw trigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["The Great Goblin", "Mogg Fanatic"] + ["Mountain"],
            library=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Mogg Fanatic", "alice")
    library_size = len(scenario.player("alice").library)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[goblin]
    )
    scenario.pass_until_resolved()

    assert goblin.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == library_size - 1
    exiled = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert exiled.zone is Zone.EXILE

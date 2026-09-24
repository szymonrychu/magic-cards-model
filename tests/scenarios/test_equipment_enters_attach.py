""" "When this Equipment enters, attach it to target `<type>` you control" (CR
701.3a's attach, CR 603.3d's target announced with the trigger) and the
kindred "then attach"/"then attach ... to the amassed Army" shapes that
follow a token- or army-creating clause with a mandatory attach.

Dwarven Mattock: "When this Equipment enters, attach it to target Dwarf you
control." Dwarven Shortsword: "When this Equipment enters, create a 2/2 red
Dwarf creature token, then attach this Equipment to it." Goblin Plate Mail:
"When this Equipment enters, amass Goblins 1, then attach this Equipment to
the amassed Army."

Glamdring, Foe-hammer // Gleam of Death's Adventure half, "Mill six cards,
then put all instant and sorcery cards from among them into your hand.",
lives here too: an Equipment-enters trigger creates the deck this file is
named for, and Gleam of Death is the other half of the same printing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_dwarven_mattock_attaches_itself_to_a_target_dwarf_on_entering():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dwarven Mattock"],
            battlefield=["Iron Hills Blacksmith", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dwarf = scenario.creature("Iron Hills Blacksmith", "alice")
    scenario.choose_trigger_targets("Dwarven Mattock", [dwarf])

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Dwarven Mattock", *sources)
    scenario.pass_until_resolved()

    mattock = scenario.find("Dwarven Mattock", Zone.BATTLEFIELD, "alice")
    assert mattock.attached_to == dwarf.id


def test_dwarven_mattock_does_nothing_with_no_legal_dwarf():
    """CR 608.2b: no legal target, no attach - the Equipment just sits there."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dwarven Mattock"], battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Dwarven Mattock", *sources)
    scenario.pass_until_resolved()

    mattock = scenario.find("Dwarven Mattock", Zone.BATTLEFIELD, "alice")
    assert mattock.attached_to is None


def test_dwarven_shortsword_creates_a_token_then_attaches_itself_to_it():
    scenario = (
        Scenario().player("alice", hand=["Dwarven Shortsword"], battlefield=["Plains"] * 4).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}

    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Dwarven Shortsword", *sources)
    scenario.pass_until_resolved()

    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    created = [state for state in scenario.game.battlefield if state.id not in before]
    token = next(state for state in created if state.name != "Dwarven Shortsword")
    assert token.subtypes == ("Dwarf",) or "Dwarf" in token.subtypes
    assert sword.attached_to == token.id


def test_kyoshi_battle_fan_creates_a_token_then_attaches_itself_to_it():
    """Avatar: The Last Airbender's own printing of the same template, proof
    the reader is not fitted to Dwarven Shortsword's exact wording."""
    scenario = (
        Scenario()
        .player("alice", hand=["Kyoshi Battle Fan"], battlefield=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Kyoshi Battle Fan", *sources)
    scenario.pass_until_resolved()

    fan = scenario.find("Kyoshi Battle Fan", Zone.BATTLEFIELD, "alice")
    created = [state for state in scenario.game.battlefield if state.id not in before]
    token = next(state for state in created if state.name != "Kyoshi Battle Fan")
    assert fan.attached_to == token.id


def test_goblin_plate_mail_amasses_then_attaches_to_the_amassed_army():
    scenario = (
        Scenario()
        .player("alice", hand=["Goblin Plate Mail"], battlefield=["Swamp", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}

    sources = scenario.untapped_sources("Swamp", "Mountain")
    scenario.cast_and_resolve("Goblin Plate Mail", *sources)
    scenario.pass_until_resolved()

    mail = scenario.find("Goblin Plate Mail", Zone.BATTLEFIELD, "alice")
    created = [state for state in scenario.game.battlefield if state.id not in before]
    army = next(state for state in created if state.name != "Goblin Plate Mail")
    assert "Army" in army.subtypes and "Goblin" in army.subtypes
    assert army.counter_count("+1/+1") == 1
    assert mail.attached_to == army.id


def test_goblin_plate_mail_reuses_an_army_already_controlled():
    """CR 701.47a's first step is skipped when the controller already has an
    Army - a second Goblin Plate Mail attaches to the Army the first one's
    own amass already created, instead of amassing a fresh token."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goblin Plate Mail", "Goblin Plate Mail"],
            battlefield=["Swamp", "Swamp", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    first_sources = scenario.untapped_sources("Swamp", "Mountain")
    scenario.cast_and_resolve("Goblin Plate Mail", *first_sources)
    scenario.pass_until_resolved()

    before = {state.id for state in scenario.game.battlefield}
    army = next(
        state
        for state in scenario.game.battlefield
        if "Army" in scenario.game.characteristics_of(state).subtypes
    )

    second_sources = scenario.untapped_sources("Swamp", "Mountain")
    scenario.cast_and_resolve("Goblin Plate Mail", *second_sources)
    scenario.pass_until_resolved()

    created = [state for state in scenario.game.battlefield if state.id not in before]
    assert not any("Army" in scenario.game.characteristics_of(state).subtypes for state in created)
    second_mail = next(
        state
        for state in scenario.game.battlefield
        if state.name == "Goblin Plate Mail" and state.attached_to == army.id
    )
    assert second_mail.attached_to == army.id
    assert army.counter_count("+1/+1") == 2


def test_gleam_of_death_mills_then_takes_every_instant_and_sorcery_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glamdring, Foe-hammer // Gleam of Death"],
            battlefield=["Island"] * 4,
            library=["Lightning Bolt", "Opt", "Grizzly Bears", "Forest", "Mountain", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")

    casting = scenario.cast("Glamdring, Foe-hammer", *[])
    casting.cast_as_adventure()
    assert casting.face == "Gleam of Death"
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    hand_names = {state.name for state in alice.hand}
    assert {"Lightning Bolt", "Opt"} <= hand_names
    graveyard_names = {state.name for state in alice.cards_in(Zone.GRAVEYARD)}
    assert graveyard_names == {"Grizzly Bears", "Forest", "Mountain", "Plains"}


def test_sting_puts_a_hone_counter_per_opponent_creature_then_attaches():
    """ "Put a hone counter on this permanent for each creature target
    opponent controls. Attach this permanent to up to one target creature
    you control." (CR 122.1j's hone counter, verified with `mise run
    rules:find 122`)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sting, Bilbo's Sword"],
            battlefield=["Grizzly Bears", "Island", "Island"],
        )
        .player("bob", battlefield=["Watchwolf", "Raging Goblin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.player("bob")

    scenario.choose_trigger_targets("Sting, Bilbo's Sword", [bob.username, bears])
    sources = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Sting, Bilbo's Sword", *sources)
    scenario.pass_until_resolved()

    sting = scenario.find("Sting, Bilbo's Sword", Zone.BATTLEFIELD, "alice")
    assert sting.counter_count("hone") == 2
    assert sting.attached_to == bears.id
    assert scenario.game.power_of(bears) == 4  # 2/2 base +2/+0 from hone counters


def test_cantankerous_keepers_mills_then_takes_every_elf_card():
    """A real, non-Adventure printing of the same "mill N, then put all
    `<quality>` cards from among them into your hand" template - proof the
    reader is not fitted to Gleam of Death's own wording."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cantankerous Keepers"],
            battlefield=["Forest"] * 6,
            library=["Llanowar Elves", "Elvish Mystic", "Mountain", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Cantankerous Keepers", *sources)
    scenario.pass_until_resolved()

    hand_names = {state.name for state in alice.hand}
    assert {"Llanowar Elves", "Elvish Mystic"} <= hand_names

"""Activated-ability prohibitions: "Activated abilities of <subject> can't be
activated [unless they're mana abilities]." (CR 602.5, CR 611.1).

The printings, read off their Scryfall oracle text in `data/printings`:

- Clarion Conqueror - "Activated abilities of artifacts, creatures, and
  planeswalkers can't be activated."
- Collector Ouphe - "Activated abilities of artifacts can't be activated."
- Cursed Totem - "Activated abilities of creatures can't be activated."
- Damping Matrix - "Activated abilities of artifacts and creatures can't be
  activated unless they're mana abilities."
- Karn, the Great Creator - "Activated abilities of artifacts your opponents
  control can't be activated."
- Pithing Needle - "As this artifact enters, choose a card name. / Activated
  abilities of sources with the chosen name can't be activated unless they're
  mana abilities."
- Disruptor Flute - the same chosen-name line, beside its cost increase.
- Stony Silence (proof printing, not a listed card, not in any deck) - an
  *enchantment* carrying Collector Ouphe's sentence.
- Phyrexian Revoker (proof printing) - "As this creature enters, choose a
  nonland card name. / Activated abilities of sources with the chosen name
  can't be activated." - the chosen-name line *without* the mana exemption,
  after a choice qualified by a characteristic.

The rules, looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated."
- **CR 611.1** - "A continuous effect modifies characteristics of objects,
  modifies control of objects, or affects players or the rules of the game".
- **CR 605.1a** - what a mana ability is, which the "unless they're mana
  abilities" tail spares.
- **CR 109.2** - a description with a card type and without the word "card",
  "spell" or "source" "means a permanent of that card type ... on the
  battlefield"; **CR 109.2c** - "source" means a source "in any zone". So
  Clarion Conqueror reaches only permanents, and Pithing Needle reaches a named
  card's cycling in its owner's hand.
- **CR 201.4 / 201.4a** - choosing a card name, and choosing one "with certain
  characteristics" (Phyrexian Revoker's "nonland").
"""

import pytest

from magic_cards_model.machines import Step, keywords
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Color
from tests.scenarios.harness import PlayedScenario, Scenario

CLARION = "Clarion Conqueror"
OUPHE = "Collector Ouphe"
TOTEM = "Cursed Totem"
MATRIX = "Damping Matrix"
NEEDLE = "Pithing Needle"
FLUTE = "Disruptor Flute"
STONY = "Stony Silence"
REVOKER = "Phyrexian Revoker"


def board(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    alice_hand: list[str] | None = None,
    bob_hand: list[str] | None = None,
) -> PlayedScenario:
    """A main phase of alice's turn, everything on the battlefield since before
    it began (so CR 302.6 never gets in the way of what is being measured)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, hand=alice_hand or [], library=["Forest"] * 5)
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def enter_naming(scenario: PlayedScenario, source: str, name: str, username: str = "alice"):
    """Put `source` onto the battlefield from hand, naming `name` as it enters
    (CR 614.12a's choice, asked of its controller)."""
    scenario.will_choose(name, source=source, username=username)
    return scenario.put_onto_battlefield(source, username)


def offered(scenario: PlayedScenario, card, username: str = "alice") -> list:
    """Every legal action `username` has that activates something of `card`'s."""
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.card_id == card.id
        and action.kind
        in {ActionKind.ACTIVATE, ActionKind.ACTIVATE_MANA, ActionKind.ACTIVATE_OFF_ZONE}
    ]


# -- a list of card types, symmetric (Clarion Conqueror) --------------------


def test_clarion_conqueror_stops_an_artifact_mana_ability():
    """No "unless they're mana abilities" tail: Sol Ring's `{T}: Add {C}{C}`
    is refused like anything else."""
    scenario = board([CLARION, "Sol Ring"])
    sol_ring = scenario.creature("Sol Ring")

    assert scenario.why_cannot_activate(sol_ring) == (
        "Sol Ring's activated abilities can't be activated: "
        "Clarion Conqueror says so (CR 602.5, CR 611.1)"
    )
    with pytest.raises(ValueError, match="Clarion Conqueror says so"):
        scenario.activate(sol_ring)
    assert offered(scenario, sol_ring) == []


def test_clarion_conqueror_stops_a_creatures_ability_including_its_controllers():
    """Symmetric: alice's own Llanowar Elves is caught along with bob's."""
    scenario = board([CLARION, "Llanowar Elves"], ["Llanowar Elves"])
    mine = scenario.creature("Llanowar Elves", "alice")
    theirs = scenario.creature("Llanowar Elves", "bob")

    assert scenario.why_cannot_activate(mine, username="alice") is not None
    assert scenario.why_cannot_activate(theirs, username="bob") is not None
    assert offered(scenario, mine) == []


def test_clarion_conqueror_stops_a_planeswalkers_loyalty_ability():
    """ "planeswalkers" is in the list: Liliana of the Veil cannot `+1`."""
    scenario = board([CLARION, "Liliana of the Veil"])
    liliana = scenario.creature("Liliana of the Veil")

    refusal = scenario.why_cannot_activate(liliana, index=0)
    assert refusal is not None and "Clarion Conqueror says so" in refusal
    assert offered(scenario, liliana) == []


def test_clarion_conqueror_leaves_lands_alone():
    """Lands are not in its list: a Forest still taps for {G}."""
    scenario = board([CLARION, "Forest"])
    forest = scenario.creature("Forest")

    assert scenario.why_cannot_activate(forest) is None
    scenario.activate(forest, color=Color.GREEN)
    assert forest.tapped


def test_clarion_conqueror_stops_equip():
    """Equip is a keyword *activated* ability of an artifact (CR 702.6a), so it
    is prohibited too - and it is not offered."""
    scenario = board([CLARION, "Bonesplitter", "Grizzly Bears", "Forest"])
    bonesplitter = scenario.creature("Bonesplitter")
    bears = scenario.creature("Grizzly Bears")

    activation = keywords.unannounced_equip_activation(scenario.game, bonesplitter, "alice")
    assert activation.why_not() == (
        "Bonesplitter's activated abilities can't be activated: "
        "Clarion Conqueror says so (CR 602.5, CR 611.1)"
    )
    with pytest.raises(ValueError, match="Clarion Conqueror says so"):
        keywords.equip_activation(scenario.game, bonesplitter, bears, "alice").begin_paying()
    assert offered(scenario, bonesplitter) == []


def test_clarion_conqueror_stops_crew():
    """Crew is the Vehicle's ability (CR 702.122a), and a Vehicle is an artifact."""
    scenario = board([CLARION, "Smuggler's Copter", "Grizzly Bears"])
    copter = scenario.creature("Smuggler's Copter")
    bears = scenario.creature("Grizzly Bears")

    with pytest.raises(ValueError, match="Clarion Conqueror says so"):
        keywords.crew_activation(scenario.game, copter, [bears], "alice").begin_paying()


def test_the_prohibition_ends_when_its_source_leaves():
    """CR 604.2 / CR 611.3a: rescanned every time, never locked in."""
    scenario = board([CLARION, "Sol Ring"])
    sol_ring = scenario.creature("Sol Ring")
    assert scenario.why_cannot_activate(sol_ring) is not None

    scenario.game.destroy(scenario.creature(CLARION))

    assert scenario.why_cannot_activate(sol_ring) is None
    assert offered(scenario, sol_ring) != []


# -- single card types (Collector Ouphe, Cursed Totem, Stony Silence) --------


def test_collector_ouphe_is_not_offered_in_legal_actions():
    scenario = board([OUPHE, "Mind Stone"])
    mind_stone = scenario.creature("Mind Stone")

    assert offered(scenario, mind_stone) == []
    assert scenario.why_cannot_activate(mind_stone, index=1) == (
        "Mind Stone's activated abilities can't be activated: "
        "Collector Ouphe says so (CR 602.5, CR 611.1)"
    )


def test_cursed_totem_stops_creatures_and_not_artifacts():
    scenario = board([TOTEM, "Devoted Druid", "Sol Ring"])
    druid = scenario.creature("Devoted Druid")
    sol_ring = scenario.creature("Sol Ring")

    assert scenario.why_cannot_activate(druid, index=0) == (
        "Devoted Druid's activated abilities can't be activated: "
        "Cursed Totem says so (CR 602.5, CR 611.1)"
    )
    assert scenario.why_cannot_activate(druid, index=1) is not None
    assert scenario.why_cannot_activate(sol_ring) is None


def test_cursed_totem_reads_the_computed_board_for_an_animated_artifact():
    """CR 613.5: an artifact turned into a creature is a creature - Karn's `+1`
    animates alice's own Mind Stone, and Cursed Totem now catches it."""
    scenario = board([TOTEM, "Karn, the Great Creator", "Mind Stone"])
    karn = scenario.creature("Karn, the Great Creator")
    mind_stone = scenario.creature("Mind Stone")
    assert scenario.why_cannot_activate(mind_stone) is None

    scenario.activate(karn, targets=[mind_stone])
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(mind_stone).is_creature
    assert scenario.why_cannot_activate(mind_stone) is not None


def test_stony_silence_an_enchantment_carries_the_same_sentence():
    """Proof on a second printing: the source's own card type is irrelevant,
    only the sentence is read."""
    scenario = board([STONY, "Sol Ring", "Llanowar Elves"], ["Mishra's Bauble"])

    assert scenario.why_cannot_activate(scenario.creature("Sol Ring")) == (
        "Sol Ring's activated abilities can't be activated: "
        "Stony Silence says so (CR 602.5, CR 611.1)"
    )
    bauble = scenario.creature("Mishra's Bauble", "bob")
    assert scenario.why_cannot_activate(bauble, username="bob") is not None
    assert scenario.why_cannot_activate(scenario.creature("Llanowar Elves")) is None


# -- the mana-ability exemption (Damping Matrix) -----------------------------


def test_damping_matrix_spares_mana_abilities_only():
    """CR 605.1a: Mind Stone's `{T}: Add {C}` is a mana ability and is spared;
    its draw ability is not. Devoted Druid the same, on a creature."""
    scenario = board([MATRIX, "Mind Stone", "Devoted Druid"])
    mind_stone = scenario.creature("Mind Stone")
    druid = scenario.creature("Devoted Druid")

    assert scenario.why_cannot_activate(mind_stone, index=0) is None
    assert scenario.why_cannot_activate(mind_stone, index=1) == (
        "Mind Stone's activated abilities can't be activated: "
        "Damping Matrix says so (CR 602.5, CR 611.1)"
    )
    assert scenario.why_cannot_activate(druid, index=0) is None
    assert scenario.why_cannot_activate(druid, index=1) is not None

    indexes = {action.ability_index for action in offered(scenario, mind_stone)}
    assert indexes == {0}


def test_damping_matrix_leaves_a_planeswalker_alone():
    """Artifacts and creatures only: Liliana still activates."""
    scenario = board([MATRIX, "Liliana of the Veil"])
    assert scenario.why_cannot_activate(scenario.creature("Liliana of the Veil")) is None


# -- sources with the chosen name (Pithing Needle, Disruptor Flute) ---------


def test_pithing_needle_stops_the_named_permanents_non_mana_abilities():
    scenario = board(["Forest"], ["Mind Stone"], alice_hand=[NEEDLE])
    enter_naming(scenario, NEEDLE, "Mind Stone")
    mind_stone = scenario.creature("Mind Stone", "bob")

    assert scenario.why_cannot_activate(mind_stone, index=0, username="bob") is None
    assert scenario.why_cannot_activate(mind_stone, index=1, username="bob") == (
        "Mind Stone's activated abilities can't be activated: "
        "Pithing Needle names it (CR 602.5, CR 611.1)"
    )
    indexes = {action.ability_index for action in offered(scenario, mind_stone, "bob")}
    assert indexes == {0}


def test_pithing_needle_is_symmetric_and_name_exact():
    """No controller in the sentence, so its own controller's copy is caught;
    a card with another name is not."""
    scenario = board(["Mind Stone", "Sol Ring"], alice_hand=[NEEDLE])
    enter_naming(scenario, NEEDLE, "Mind Stone")

    assert scenario.why_cannot_activate(scenario.creature("Mind Stone"), index=1) is not None
    assert scenario.why_cannot_activate(scenario.creature("Sol Ring")) is None


def test_pithing_needle_stops_a_planeswalkers_loyalty_abilities():
    """A loyalty ability is never a mana ability (CR 605.1a)."""
    scenario = board([], ["Liliana of the Veil"], alice_hand=[NEEDLE])
    enter_naming(scenario, NEEDLE, "Liliana of the Veil")
    liliana = scenario.creature("Liliana of the Veil", "bob")

    for index in range(3):
        assert scenario.why_cannot_activate(liliana, index=index, username="bob") is not None


def test_pithing_needle_reaches_a_card_in_hand():
    """CR 109.2c: a "source" is in any zone, so the named card's cycling is
    prohibited while it sits in its owner's hand."""
    scenario = board([], alice_hand=[NEEDLE], bob_hand=["Street Wraith"])
    enter_naming(scenario, NEEDLE, "Street Wraith")
    wraith = scenario.find("Street Wraith", Zone.HAND, "bob")

    activation = keywords.cycling_activation(scenario.game, wraith, "bob")
    assert activation.why_not() == (
        "Street Wraith's activated abilities can't be activated: "
        "Pithing Needle names it (CR 602.5, CR 611.1)"
    )
    with pytest.raises(ValueError, match="Pithing Needle names it"):
        activation.begin_paying()
    assert offered(scenario, wraith, "bob") == []


def test_a_card_type_prohibition_does_not_reach_a_card_in_hand():
    """CR 109.2: "artifacts" means artifact *permanents*. Collector Ouphe leaves
    a cycling artifact card in hand alone - here Street Wraith is a creature
    card and Cursed Totem, which names creatures, leaves its cycling alone."""
    scenario = board([TOTEM], bob_hand=["Street Wraith"])
    wraith = scenario.find("Street Wraith", Zone.HAND, "bob")

    assert keywords.cycling_activation(scenario.game, wraith, "bob").why_not() is None


def test_pithing_needle_stops_nothing_once_it_leaves():
    scenario = board([], ["Mind Stone"], alice_hand=[NEEDLE])
    needle = enter_naming(scenario, NEEDLE, "Mind Stone")
    mind_stone = scenario.creature("Mind Stone", "bob")
    assert scenario.why_cannot_activate(mind_stone, index=1, username="bob") is not None

    scenario.game.destroy(needle)

    assert scenario.why_cannot_activate(mind_stone, index=1, username="bob") is None


def test_disruptor_flute_carries_the_same_line():
    scenario = board([], ["Mind Stone"], alice_hand=[FLUTE])
    enter_naming(scenario, FLUTE, "Mind Stone")
    mind_stone = scenario.creature("Mind Stone", "bob")

    assert scenario.why_cannot_activate(mind_stone, index=0, username="bob") is None
    assert "Disruptor Flute names it" in (
        scenario.why_cannot_activate(mind_stone, index=1, username="bob") or ""
    )


def test_the_chosen_name_line_is_no_longer_an_unwired_choice():
    scenario = board([], alice_hand=[NEEDLE])
    enter_naming(scenario, NEEDLE, "Mind Stone")

    assert scenario.game.unwired_choice_notices == []


# -- proof printing: Phyrexian Revoker (qualified choice, no mana tail) -----


def test_phyrexian_revoker_asks_for_a_nonland_card_name():
    """CR 201.4a: "choose a nonland card name" is a choice with a
    characteristic - it is asked, and the answer recorded."""
    scenario = board([], ["Birds of Paradise"], alice_hand=[REVOKER])
    revoker = enter_naming(scenario, REVOKER, "Birds of Paradise")

    assert revoker.choice is not None and revoker.choice.value == "Birds of Paradise"


def test_phyrexian_revoker_stops_mana_abilities_too():
    """No "unless they're mana abilities": the named Birds cannot tap for mana."""
    scenario = board([], ["Birds of Paradise"], alice_hand=[REVOKER])
    enter_naming(scenario, REVOKER, "Birds of Paradise")
    birds = scenario.creature("Birds of Paradise", "bob")

    assert scenario.why_cannot_activate(birds, username="bob") == (
        "Birds of Paradise's activated abilities can't be activated: "
        "Phyrexian Revoker names it (CR 602.5, CR 611.1)"
    )
    with pytest.raises(ValueError, match="Phyrexian Revoker names it"):
        scenario.activate(birds, username="bob", color=Color.GREEN)
    assert offered(scenario, birds, "bob") == []


def test_phyrexian_revoker_refuses_a_land_name():
    """CR 201.4a: the name has to be of a card with the characteristic - a
    land's name is not a nonland card name."""
    scenario = board([], alice_hand=[REVOKER])
    scenario.will_choose("Forest", source=REVOKER, username="alice")

    with pytest.raises(ValueError, match="nonland"):
        scenario.put_onto_battlefield(REVOKER, "alice")

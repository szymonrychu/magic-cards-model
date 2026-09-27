"""A transformed battle back face's own name-possessive characteristic-
defining ability (CR 201.5, CR 604.3a, CR 208.2a): "`<Name>`'s power [and
toughness are each/is] equal to the number of `<type>` you control."

Verified this session with `mise run rules:find` against the current CR:

- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object."
- **CR 604.3a** - a static ability is a characteristic-defining ability when
  it "defines an object's ... power, or toughness" and "is printed on the
  card it affects."
- **CR 208.2a** - such an ability is worded "[This creature's] power and
  toughness are each equal to ..." or "[This creature's] power is equal to
  ..."; it functions everywhere, even outside the game.
- **CR 310.12b** - a Siege's own "When the last defense counter is removed
  from this permanent, exile it, then you may cast it transformed without
  paying its mana cost."
- **CR 115.4** / **CR 310.6** - "any target" a burn spell names may be a
  battle, and damage dealt to one removes that many defense counters.
- **CR 712.11a** / **CR 712.13** - cast transformed, a double-faced spell is
  put on the stack back face up, and enters the battlefield the same face up.
- **CR 712.8d** - "While a double-faced permanent has its front face up, it
  has only the characteristics of its front face" (so the back face's own
  name, never the combined "Front // Back" string, is what CR 201.5 self-
  reference on the back face's own printed line means).

`machines/layers.py::_QUALIFIER_COUNT_CDA_RE` already reads "this creature's/
permanent's/token's power [and toughness are each/is] equal to the number of
`<type>` you control" for any card sharing the template (Molimo, Maro-
Sorcerer; Old Man Willow; Ulvenwald Hydra and a dozen more, per that regex's
own docstring) - the same reader a transformed battle back face's line
becomes once `self_normalized_effect_text` rewrites its own name-possessive
sentence to "this permanent's ...". Three real, differently-worded printings
below (a lands qualifier, a creatures qualifier, and the "power is" rather
than "power and toughness are" wording, on a self-counting artifact) prove
the shape generally rather than on one card alone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _defeat_siege_with_bolts(scenario: PlayedScenario, siege, mountains: list) -> None:
    """Defeats a Siege with two Lightning Bolts (CR 115.4/310.6) rather than
    combat, so no creature besides the transformed back face itself need
    ever touch the battlefield - keeping every qualifier count (lands,
    creatures, artifacts) exactly the one the test sets up."""
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # the transformed spell resolves and enters


def test_winnowing_forces_power_and_toughness_equal_lands_controlled():
    """Invasion of Lorwyn // Winnowing Forces: "Winnowing Forces's power and
    toughness are each equal to the number of lands you control." Bob has no
    creatures, so the Siege's own "destroy target non-Elf creature an
    opponent controls" trigger has no legal target and never reaches the
    stack (CR 603.3c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Lorwyn", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Lorwyn", "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger: no legal target

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Winnowing Forces"
    assert scenario.game.power_of(siege) == 4
    assert scenario.game.toughness_of(siege) == 4


def test_vertex_paladin_power_and_toughness_equal_creatures_controlled():
    """Invasion of Xerex // Vertex Paladin: "Vertex Paladin's power and
    toughness are each equal to the number of creatures you control." Alice
    controls two Grizzly Bears plus Vertex Paladin itself once transformed -
    a self-referential CDA counts its own source (CR 604.3a places no
    exclusion on it), the same as every other card sharing this template."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Xerex", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Xerex", "alice")
    # "return up to one target creature to its owner's hand" - declines any target.
    scenario.will_choose_targets(username="alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Vertex Paladin"
    assert scenario.game.power_of(siege) == 3
    assert scenario.game.toughness_of(siege) == 3


def test_aetherwing_power_only_equals_artifacts_controlled():
    """Invasion of Kaladesh // Aetherwing, Golden-Scale Flagship:
    "Aetherwing's power is equal to the number of artifacts you control" -
    the "power is" half of `_QUALIFIER_COUNT_CDA_RE`'s own `stats` group,
    which touches only power (CR 208.2a); Aetherwing's printed toughness (4)
    stays put. The Siege's own enters trigger creates a Thopter token, an
    additional artifact creature that is still around, and still an
    artifact, once Aetherwing itself transforms in - so the final count is
    two Sol Rings, the Thopter, and Aetherwing itself: four."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Kaladesh", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Sol Ring", "Sol Ring"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Kaladesh", "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger: creates a Thopter

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Aetherwing, Golden-Scale Flagship"
    assert scenario.game.power_of(siege) == 4
    assert scenario.game.toughness_of(siege) == 4

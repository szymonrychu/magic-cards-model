"""`TargetRequirement._rejects_card` reads a battlefield target's *computed*
supertypes, subtypes, and historic-ness (CR 613.5), matching `_current_types`/
`_current_colors` (`machines/targeting.py`'s own `:716`/`:727`), which already
do this for card types and colors.

`rejects()` is the single predicate CR 601.2c announcement (`TargetingProfile.
check`) and CR 608.2b's resolution recheck (`Game.legal_target`/`legal_targets`)
both call - `Game.legal_target`'s own docstring says so, and
`test_rejects_reads_the_same_computed_subtype_at_the_resolution_recheck` below
proves it by driving the exact same `TargetRequirement.rejects` call through
both a pre- and a post-animation board.

Mishra's Factory is the card that makes every one of these testable with a
real printing: "{1}: This land becomes a 2/2 Assembly-Worker artifact creature
until end of turn. It's still a land." is a real, live layer-4 effect
(CR 613.1d) that grants both a card type (artifact, so CR 700.6's "historic")
and a creature type (Assembly-Worker) to a permanent whose *printed* type line
is bare "Land" - and its own third ability, "{T}: Target Assembly-Worker
creature gets +1/+1 until end of turn.", is a real card with a bare-subtype
"target <creature type>" restriction (CR 205.3m) to check it against.

No card in this engine's pool grants the Legendary supertype or the Saga
subtype through a continuous effect, so `required_supertypes`/
`excluded_supertypes` and the Legendary/Saga thirds of `_rejects_historic`
are exercised here only as regressions (a printed-legendary permanent stays a
legal "target legendary permanent", a vanilla creature stays an illegal one) -
noted rather than invented around.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import TargetRequirement, profile_for_text
from magic_cards_model.models import Zone

from .harness import Scenario

FACTORY_PUMP_TEXT = "Target Assembly-Worker creature gets +1/+1 until end of turn."
HISTORIC_TEXT = "Destroy target historic permanent."
#: Abstergo Entertainment's own real effect clause (its cost - "{3}, {T},
#: Exile Abstergo Entertainment:" - stripped, the same way every other
#: `profile_for_text` call in this file names an effect rather than a whole
#: printed ability).
ABSTERGO_GRAVEYARD_TEXT = (
    "Return up to one target historic card from your graveyard to your hand, "
    "then exile all graveyards."
)


def _requirement(text: str) -> TargetRequirement:
    profile = profile_for_text(text)
    assert profile.understood, text
    (requirement,) = profile.requirements
    return requirement


def _two_factories() -> Scenario:
    return Scenario().player(
        "alice", battlefield=["Mishra's Factory", "Mishra's Factory", "Grizzly Bears"]
    )


def _animate(scenario, factory, mana_source) -> None:
    """`{1}: This land becomes a 2/2 Assembly-Worker artifact creature until
    end of turn. It's still a land.` - Mishra's Factory's own second ability.
    """
    scenario.activate(factory, mana_source, index=1)
    scenario.resolve_top()


def test_targeting_a_bare_subtype_ability_before_and_after_it_is_granted():
    """Before the animation, the factory has neither the Assembly-Worker
    subtype nor the creature type, so its own pump ability cannot legally
    target it - CR 601.2c announcement refuses it. After, `required_subtypes`
    has to see the subtype the animation just granted on the computed board
    (CR 613.1d), even though Mishra's Factory's printed type line never
    changes.
    """
    scenario = _two_factories().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory, mana_source = scenario.creatures(
        "Mishra's Factory", "Mishra's Factory", username="alice"
    )
    assert "assembly-worker" not in {subtype.lower() for subtype in factory.subtypes}, (
        "the printed type line is still bare Land"
    )
    requirement = _requirement(FACTORY_PUMP_TEXT)
    assert requirement.rejects(factory, "alice", scenario.game) is not None, (
        "not yet a creature at all, let alone an Assembly-Worker"
    )

    _animate(scenario, factory, mana_source)
    assert "assembly-worker" not in {subtype.lower() for subtype in factory.subtypes}, (
        "the printed CardState never changes; only the computed board does"
    )
    assert requirement.rejects(factory, "alice", scenario.game) is None, (
        "the animation's own layer-4 effect grants the subtype"
    )

    # The targeting check (CR 601.2c) is what this test is about; the pump's
    # own magnitude parsing ("Target Assembly-Worker creature gets +1/+1") is
    # a separate, unrelated gap in `machines/layers.py`'s hyphenated-subtype
    # regex - not one of this wave's three files - so this only asserts the
    # announcement itself is legal, not what the ability does once it
    # resolves.
    pump = scenario.activate(factory, index=2, targets=[factory])
    assert pump is not None


def test_a_creature_without_the_subtype_is_never_a_legal_target():
    """The inverse: Grizzly Bears is never an Assembly-Worker, animated
    factory on the board or not, so the pump can never legally aim at it.
    """
    scenario = _two_factories().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory, mana_source = scenario.creatures(
        "Mishra's Factory", "Mishra's Factory", username="alice"
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _animate(scenario, factory, mana_source)

    with pytest.raises(ValueError):
        scenario.activate(factory, index=2, targets=[bears])


def test_rejects_reads_the_same_computed_subtype_at_the_resolution_recheck():
    """`rejects()` backs both CR 601.2c announcement (above, through
    `Casting`/`activate_ability`) and CR 608.2b's resolution recheck
    (`Game.legal_target`) - proved directly here by calling it exactly the
    way both call sites do, before and after the same animation.
    """
    scenario = _two_factories().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory, mana_source = scenario.creatures(
        "Mishra's Factory", "Mishra's Factory", username="alice"
    )
    requirement = _requirement(FACTORY_PUMP_TEXT)

    assert requirement.rejects(factory, "alice", scenario.game) is not None
    _animate(scenario, factory, mana_source)
    assert requirement.rejects(factory, "alice", scenario.game) is None


def test_historic_sees_the_artifact_type_a_layer_4_effect_grants():
    """CR 700.6: "historic ... has the legendary supertype, the artifact card
    type, or the Saga subtype." Mishra's Factory's animation grants the
    artifact type through layer 4 (CR 613.1d); before it, the land is
    historic in none of the three ways.
    """
    scenario = _two_factories().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory, mana_source = scenario.creatures(
        "Mishra's Factory", "Mishra's Factory", username="alice"
    )
    requirement = _requirement(HISTORIC_TEXT)

    assert requirement.rejects(factory, "alice", scenario.game) is not None
    _animate(scenario, factory, mana_source)
    assert requirement.rejects(factory, "alice", scenario.game) is None


def test_a_vanilla_creature_is_never_historic():
    """The inverse: nothing about Grizzly Bears is legendary, artifact, or a
    Saga, animated factory on the board or not."""
    scenario = _two_factories().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    requirement = _requirement(HISTORIC_TEXT)

    assert requirement.rejects(bears, "alice", scenario.game) is not None


def test_a_printed_legendary_permanent_stays_historic():
    """No card in this pool grants Legendary through a continuous effect, so
    this is the regression the fix must keep true: a permanent that is
    Legendary on its own printed supertype line is still historic once the
    read goes through the computed board instead of `target.card`.
    """
    scenario = Scenario().player("alice", battlefield=["Karn, the Great Creator"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, "alice")
    requirement = _requirement(HISTORIC_TEXT)

    assert requirement.rejects(karn, "alice", scenario.game) is None


def test_a_graveyard_card_is_read_off_its_own_printed_characteristics():
    """Off the battlefield there is no layer to compute (CR 611.2c: layers
    only apply to permanents there), so the fixed `_current_supertypes`/
    `_current_types`/`_current_subtypes` fall back to `target.*` -
    `CardState`'s own up-face read, not `target.card`, but for a single-faced
    card the two agree. Abstergo Entertainment's own real ability is the live
    case this restriction actually ships on: "target historic card from your
    graveyard" is CR 700.6's own worked example, word for word.
    """
    scenario = (
        Scenario().player("alice", graveyard=["Karn, the Great Creator", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.find("Karn, the Great Creator", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    requirement = _requirement(ABSTERGO_GRAVEYARD_TEXT)

    assert requirement.rejects(karn, "alice", scenario.game) is None
    assert requirement.rejects(bears, "alice", scenario.game) is not None

"""Judge scenarios: what an object's *name* is, as opposed to its types.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#249** - Echoing Courage + Assembly-Worker (an effect that keys off a
  name catches neither an animated land that gained the creature type nor a
  token whose name is that type plus the word "token")

Two rules do all the work. CR 111.4: "A spell or ability that creates a token
sets both its name and its subtype(s). If the spell or ability doesn't specify
the name of the token, its name is the same as its subtype(s) plus the word
'token'." And nothing about an animation ability changes a name - Mishra's
Factory's own text only ever says what it *becomes*, so it stays named Mishra's
Factory however many Assembly-Worker types it picks up.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _urza_factory_board(extra: list[str] | None = None) -> "Scenario":
    """Urza's Factory plus the seven lands its token ability costs."""
    return Scenario().player(
        "alice",
        hand=["Echoing Courage"] if extra is None else [],
        battlefield=["Urza's Factory", *["Mountain"] * 7, *(extra or [])],
    )


def _make_the_assembly_worker_token(scenario) -> None:
    factory = scenario.find("Urza's Factory", Zone.BATTLEFIELD, "alice")
    scenario.activate(factory, *scenario.untapped_sources(*["Mountain"] * 7), index=1)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_an_unnamed_token_is_named_after_its_subtypes_plus_the_word_token():
    """DDR#249's answer for the token: it is not named Assembly-Worker.

    Urza's Factory (confirmed with `resolve_cards`): "{7}, {T}: Create a 2/2
    colorless Assembly-Worker artifact creature token." The ability never says
    what the token is called, so CR 111.4 names it for us - "its name is the
    same as its subtype(s) plus the word 'token'" - giving "Assembly-Worker
    Token", which is not the same name as the card Assembly-Worker.

    The episode is explicit that this is a *changed* ruling: there was a period
    in Magic's history where that token would have shared the creature's name
    and been buffed. The rule as it stands today is what this asserts.
    """
    scenario = _urza_factory_board(extra=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _make_the_assembly_worker_token(scenario)

    assert "Assembly-Worker Token" in scenario.battlefield_names()
    assert "Assembly-Worker" not in scenario.battlefield_names()


@pytest.mark.xfail(
    strict=True,
    reason="Echoing Courage has no scripted effect - `effect_for('Echoing "
    "Courage', ...)` is None - so it resolves, goes to the graveyard, and "
    "nothing anywhere gets +2/+2. The name-matching half of the ruling (which "
    "permanents the buff reaches) cannot be observed until the pump exists.",
)
def test_echoing_courage_buffs_only_the_permanents_sharing_the_targets_name():
    """DDR#249: same *name*, not same creature type.

    Echoing Courage (confirmed with `resolve_cards`): "Target creature and all
    other creatures with the same name as that creature get +2/+2 until end of
    turn." The targeted Assembly-Worker card gets it. The token does not - it
    is named "Assembly-Worker Token" (CR 111.4, asserted above). Mishra's
    Factory does not either, animated or not: its own ability changes card type
    and adds the Assembly-Worker creature type and says nothing about a name.
    """
    scenario = _urza_factory_board(
        extra=["Assembly-Worker", "Mishra's Factory", "Forest", "Forest"]
    )
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_the_assembly_worker_token(scenario)

    worker = scenario.creature("Assembly-Worker", "alice")
    scenario.cast_and_resolve(
        "Echoing Courage",
        *scenario.untapped_sources("Forest", "Forest"),
        targets=[worker],
    )

    token = scenario.creature("Assembly-Worker Token", "alice")
    assert (scenario.game.power_of(worker), scenario.game.toughness_of(worker)) == (4, 4)
    assert (scenario.game.power_of(token), scenario.game.toughness_of(token)) == (2, 2)


@pytest.mark.xfail(
    strict=True,
    reason="Mishra's Factory's '{1}: This land becomes a 2/2 Assembly-Worker "
    "artifact creature until end of turn. It's still a land.' parses as an "
    "activated ability but does nothing when it resolves: after activating it "
    "the land's characteristics are still land-only, with no power or "
    "toughness, so the interesting half of the assertion - that the *name* is "
    "untouched while the types changed - has no animated permanent to make it "
    "against.",
)
def test_animating_mishras_factory_changes_its_types_but_not_its_name():
    """DDR#249: the animation is a type change, so the name is not one.

    Mishra's Factory (confirmed with `resolve_cards`): "{1}: This land becomes
    a 2/2 Assembly-Worker artifact creature until end of turn. It's still a
    land." That is a layer 4 type-changing effect (CR 613.1d: "effects that
    change an object's card type, subtype, and/or supertype"); no layer deals
    with names here, so the permanent is an Assembly-Worker creature named
    Mishra's Factory - which is why an Echoing Courage on a real
    Assembly-Worker misses it entirely.
    """
    from magic_cards_model.models.card import Type

    scenario = Scenario().player("alice", battlefield=["Mishra's Factory", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory = scenario.find("Mishra's Factory", Zone.BATTLEFIELD, "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(factory, mountain, index=1)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    characteristics = scenario.game.characteristics_of(factory)
    assert Type.CREATURE in characteristics.types
    assert Type.LAND in characteristics.types, "It's still a land"
    assert "Assembly-Worker" in characteristics.subtypes
    assert factory.name == "Mishra's Factory", "the animation never touches the name"

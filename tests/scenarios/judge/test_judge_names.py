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
    """Urza's Factory plus the seven lands its token ability costs.

    Echoing Courage is always in hand: it used to be dealt only when `extra`
    was `None`, which is the opposite of what the one test that casts it
    passes, so that test's `find` raised on an empty hand before it asserted
    anything at all.
    """
    return Scenario().player(
        "alice",
        hand=["Echoing Courage"],
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
    reason="`machines/layers.py` has no selector for CR 201.2a's 'the same name as that "
    "creature'. The `machines/effects.py` half is done: "
    "`_CONTINUOUS_PUMP_OR_KEYWORD_RE` now admits the 'Target creature and all other "
    "creatures with the same name as that creature' subject and `_parse_mixed_clauses` "
    "matches it against the whole unsplit text (the bare ' and ' inside the subject would "
    "otherwise be cut in two), so `effect_for('Echoing Courage', ...)` is no longer None and "
    "the spell reaches `create_continuous_effect`. That hands the card's own text to "
    "`machines/layers.parsed_layer_effects`, which returns None: `_PUMP_RE`'s `_SUBJECT` "
    "reads only 'target creature'/'this creature'/'this permanent'/'another target creature', "
    "and `_pump_and_keyword_builder` builds one `only_this_incarnation` effect per resolved "
    "target, so nothing anywhere can widen the effect to the other permanents sharing the "
    "target's name. Needed in `machines/layers.py`: a `same_name_as(name)` `Selector`, a "
    "`_TARGET_AND_SAME_NAME_PUMP_RE` sibling of `_PUMP_RE`, its dispatch beside "
    "`_PUMP_RE.fullmatch(sentence)` in `effects_for`, and a builder that selects on that name "
    "instead of on the target's identity. Everything the ruling turns on is already true "
    "board-side and asserted by the two tests around this one.",
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

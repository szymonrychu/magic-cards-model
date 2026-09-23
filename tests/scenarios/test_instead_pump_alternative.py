"""Scenario: an "instead" pump alternative applies the amount it resolved to.

A pump spell whose second sentence replaces the first with a bigger pump
when a kicker was paid or a condition holds:

- Colossal Growth: "Kicker {R} / Target creature gets +3/+3 until end of
  turn. If this spell was kicked, instead that creature gets +4/+4 and gains
  trample and haste until end of turn." (Modern, Pioneer)
- Might of Murasa: "Kicker {2}{G} / Target creature gets +3/+3 until end of
  turn. If this spell was kicked, that creature gets +5/+5 until end of turn
  instead." (Modern, Pioneer) - the trailing "instead" word order.
- You're Not Alone: "Target creature gets +2/+2 until end of turn. If you
  control three or more creatures, it gets +4/+4 until end of turn instead."
  (Modern, Pioneer, Standard) - a condition, not a kicker, and "it" as the
  anaphor.
- For the Family: "Target creature gets +2/+2 until end of turn. If you
  control four or more creatures, that creature gets +4/+4 until end of turn
  instead." (Modern, Pioneer)

None of the four is in the api deck pool. Legality was read off each
printing's own Scryfall `legalities` field.

The defect: `machines/effects.py` resolved the base-or-alternative choice
correctly, but either branch then reached the bare `create_continuous_effect`
sentinel, which re-read the *whole* printed text through
`parsed_layer_effects` - so the resolved alternative's own amount (and its
keywords) never applied; the continuous effect was always whatever the raw
card text parsed to, regardless of the branch chosen.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.33a** - "Kicker [cost]" means "You may pay an additional [cost] as
  you cast this spell."
- **CR 702.33d** - declaring the intention to pay a kicker cost makes the
  spell "kicked".
- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects."
- **CR 608.2c** - instructions are followed in the order written, and later
  text may modify the meaning of earlier text.
- **CR 611.2a** - a resolving spell's continuous effect lasts as long as
  stated ("until end of turn").
- **CR 611.2c** - the set of objects it affects is fixed when it begins.
- **CR 613.4c** - layer 7c, power/toughness modifications.
- **CR 613.1f** - layer 6, ability-adding effects (trample, haste).
- **CR 702.19a** / **CR 702.10a** - trample and haste are static abilities.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario, mana_from


def _board(spell: str, lands: list[str], creatures: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=lands + creatures)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_kicker_pump(scenario, spell: str, target, lands: list[str], *, kicked: bool) -> None:
    casting = scenario.cast(spell)
    if kicked:
        casting.pay_kicker()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*lands):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _pt(scenario, creature) -> tuple[int, int]:
    return scenario.game.characteristics_of(creature).power_toughness


# ---------------------------------------------------------------------------
# Colossal Growth - kicker, leading "instead", pump plus keywords.
# ---------------------------------------------------------------------------


def test_unkicked_colossal_growth_gives_only_the_base_pump():
    """Unkicked: +3/+3, and no trample or haste - the alternative's keywords
    belong to the alternative only (CR 614.1a)."""
    scenario = _board("Colossal Growth", ["Forest", "Forest", "Mountain"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_kicker_pump(scenario, "Colossal Growth", bears, ["Forest", "Forest"], kicked=False)

    assert _pt(scenario, bears) == (2 + 3, 2 + 3)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_kicked_colossal_growth_gives_the_alternative_pump_and_keywords():
    """Kicked (CR 702.33d): +4/+4 with trample and haste, *instead of* the
    base +3/+3 - not the base amount, and not both added together."""
    scenario = _board("Colossal Growth", ["Forest", "Forest", "Mountain"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_kicker_pump(
        scenario, "Colossal Growth", bears, ["Forest", "Forest", "Mountain"], kicked=True
    )

    assert _pt(scenario, bears) == (2 + 4, 2 + 4)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(bears, Keyword.HASTE, scenario.game)


def test_kicked_colossal_growth_ends_at_cleanup():
    """CR 611.2a: "until end of turn" - the alternative's own duration."""
    scenario = _board("Colossal Growth", ["Forest", "Forest", "Mountain"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_kicker_pump(
        scenario, "Colossal Growth", bears, ["Forest", "Forest", "Mountain"], kicked=True
    )
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _pt(scenario, bears) == (2, 2)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)


# ---------------------------------------------------------------------------
# Might of Murasa - kicker, trailing "instead".
# ---------------------------------------------------------------------------


_MURASA_LANDS = ["Forest", "Forest", "Forest", "Forest", "Forest", "Forest"]


def test_unkicked_might_of_murasa_gives_the_base_pump():
    scenario = _board("Might of Murasa", _MURASA_LANDS, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_kicker_pump(scenario, "Might of Murasa", bears, ["Forest", "Forest"], kicked=False)

    assert _pt(scenario, bears) == (2 + 3, 2 + 3)


def test_kicked_might_of_murasa_gives_the_alternative_pump():
    scenario = _board("Might of Murasa", _MURASA_LANDS, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_kicker_pump(scenario, "Might of Murasa", bears, _MURASA_LANDS[:5], kicked=True)

    assert _pt(scenario, bears) == (2 + 5, 2 + 5)


# ---------------------------------------------------------------------------
# You're Not Alone / For the Family - a condition, read at resolution.
# ---------------------------------------------------------------------------


def test_youre_not_alone_with_two_creatures_gives_the_base_pump():
    scenario = _board("You're Not Alone", ["Plains"], ["Grizzly Bears", "Savannah Lions"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "You're Not Alone", *scenario.untapped_sources("Plains"), targets=[bears]
    )

    assert _pt(scenario, bears) == (2 + 2, 2 + 2)


def test_youre_not_alone_with_three_creatures_gives_the_alternative_pump():
    scenario = _board(
        "You're Not Alone", ["Plains"], ["Grizzly Bears", "Savannah Lions", "Memnite"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "You're Not Alone", *scenario.untapped_sources("Plains"), targets=[bears]
    )

    assert _pt(scenario, bears) == (2 + 4, 2 + 4)


def test_for_the_family_with_three_creatures_gives_the_base_pump():
    scenario = _board("For the Family", ["Forest"], ["Grizzly Bears", "Savannah Lions", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "For the Family", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert _pt(scenario, bears) == (2 + 2, 2 + 2)


def test_for_the_family_with_four_creatures_gives_the_alternative_pump():
    scenario = _board(
        "For the Family",
        ["Forest", "Forest"],
        ["Grizzly Bears", "Savannah Lions", "Memnite", "Ornithopter"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "For the Family", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert _pt(scenario, bears) == (2 + 4, 2 + 4)

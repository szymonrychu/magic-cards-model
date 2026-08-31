"""Judge scenarios: "hexproof from [quality]", and the shorthand for more than one.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1007** - Does Nevinyrral, Urborg Tyrant Work?

Nevinyrral's real oracle text, confirmed with `resolve_cards`, begins
"Hexproof from artifacts, creatures, and enchantments". The episode's whole
point is a templating one: CR 702.11f defines the shorthand as "hexproof from
[quality A] **and from** [quality B]", and Nevinyrral's line is not written that
way, so the rule that would split it into three separate hexproof abilities does
not formally reach it. The intended reading - one hexproof ability per quality -
is not in doubt; the wording that authorizes it is.

The engine takes the intended reading. `machines/abilities.parse_abilities`
still leaves the printed line an `UnparsedAbility` - it is no keyword shape that
module knows - but `Casting._hexproof_refusal` now reads the permanent's own
ability *text* rather than Scryfall's `keywords` field, which carries a bare
"Hexproof" alongside "Hexproof from" and used to give Nevinyrral full CR 702.11b
hexproof, refusing far more than the card does.
Every CR number here was looked up with `knowledge_search(type="rules")` in the
sessions that wrote and fixed the file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import UnparsedAbility, parse_abilities
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_hexproof_from_line_is_not_parsed_into_a_keyword_at_all():
    """The gap, stated as an assertion rather than left implicit.

    CR 702.11d makes "hexproof from [quality]" a variant of hexproof: "This
    permanent can't be the target of [quality] spells your opponents control..."
    `machines/abilities` has no keyword shape for that variant, so the printed
    line stays an `UnparsedAbility` there - the targeting refusal reads the line
    itself instead (`Casting._hexproof_refusal`), which is what the two casting
    tests below assert.
    """
    (first, *_) = parse_abilities(card("Nevinyrral, Urborg Tyrant"))

    assert isinstance(first, UnparsedAbility)
    assert first.text == "Hexproof from artifacts, creatures, and enchantments"


def test_a_red_instant_may_still_target_nevinyrral():
    """Hexproof from artifacts, from creatures and from enchantments says
    nothing about an instant.

    CR 702.11d only refuses "[quality] spells your opponents control or
    abilities your opponents control from [quality] sources", and a Lightning
    Bolt is none of those qualities - so bob may aim one at Nevinyrral. This is
    the assertion that separates the three abilities the card is meant to have
    (CR 702.11f) from the one blanket ability Scryfall's `keywords` field would
    hand it.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", battlefield=["Nevinyrral, Urborg Tyrant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[nevinyrral])

    assert scenario.stack_names() == ["Lightning Bolt"]


def test_its_controllers_own_spell_may_target_it_either_way():
    """The control case, and correct under both readings.

    CR 702.11d, like CR 702.11b before it, is about *whose* spell it is: "spells
    your opponents control". alice's own Bolt is not an opponent's, so nothing
    refuses it whether the card has one hexproof ability or three.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Nevinyrral, Urborg Tyrant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[nevinyrral])

    assert scenario.stack_names() == ["Lightning Bolt"]

"""Regenerate: CR 701.19a's replacement shield, read off the printed clause.

"Regenerate target X." (`_REGENERATE_TARGET_RE`) already had a reader before
this wave; what was missing was `machines/keywords.executes()` crediting the
keyword at all, and a reader for the *self*-referential shape a targeted
clause cannot cover - "Regenerate this creature." (`_REGENERATE_SELF_RE`),
proved here on Ancient Silverback, a card neither in the deck pool nor named
in this wave's brief, alongside Welding Jar's own "target artifact" and
Asceticism's own "target creature" (already end-to-end tested elsewhere, in
`test_object_anaphoric_riders.py`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_welding_jar_regenerates_a_targeted_artifact():
    """Welding Jar: "Sacrifice this artifact: Regenerate target artifact."

    A different target quality (artifact, not creature) and a different cost
    shape (self-sacrifice, not mana) from Asceticism's own ability.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Abrupt Decay"], battlefield=["Swamp", "Forest"])
        .player("bob", battlefield=["Welding Jar", "Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jar = scenario.find("Welding Jar", Zone.BATTLEFIELD)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Swamp", "Forest", username="alice")

    scenario.cast_onto_stack("Abrupt Decay", *sources, username="alice", targets=[bauble])
    scenario.pass_priority()
    scenario.activate(jar, index=0, username="bob", targets=[bauble])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bauble.zone is Zone.BATTLEFIELD
    assert bauble.tapped
    assert jar.zone is Zone.GRAVEYARD, "the jar paid its own sacrifice cost"


def test_ancient_silverback_regenerates_itself():
    """Ancient Silverback: "{G}: Regenerate this creature." - no "target" word
    at all, so the targeted-clause reader cannot be the one that catches it;
    CR 201.5's self-reference is. Not in the deck pool, not named in this
    wave's brief.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Supreme Verdict"], battlefield=["Plains", "Plains", "Plains", "Island"])
        .player("bob", battlefield=["Ancient Silverback", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    silverback = scenario.creature("Ancient Silverback", "bob")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Island", username="alice")
    (forest,) = scenario.untapped_sources("Forest", username="bob")

    scenario.cast_onto_stack("Supreme Verdict", *sources, username="alice")
    scenario.pass_priority()
    scenario.activate(silverback, forest, index=0, username="bob")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert silverback.zone is Zone.BATTLEFIELD
    assert silverback.tapped
    assert silverback.damage == 0

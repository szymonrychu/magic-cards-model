"""Awaken the Maelstrom, Invasion of Alara's cast-transformed back face: five
sequential resolution instructions on one sorcery.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Awaken the Maelstrom (Sorcery, Modern/Pioneer legal):
    Awaken the Maelstrom is all colors.
    Target player draws two cards. You may put an artifact card from your
    hand onto the battlefield. Create a token that's a copy of a permanent
    you control. Distribute three +1/+1 counters among one, two, or three
    creatures you control. Destroy target permanent an opponent controls.

Before this session, `_spell_faces` (`support.py`) never asked `effect_for`
about this face's own text at all - a Battle Siege's back face fell through
to `parse_abilities`' bare `AbilityKind.STATIC` reading of the same text and
was scored an unaudited static ability of the *front* Siege permanent, the
same classifier artifact CR 712.11b's own `spell_only_face_names` already
existed to close for a modal DFC/Adventure's non-permanent face (see that
docstring). Two clauses had no reader at all once routed correctly: "create
a token that's a copy of a `<quality>` you control" (no "target" - CR 608.2d's
own choice, not CR 601.2d's targeting) and "distribute `<n>` counters among
`<count-phrase>` `<quality>` you control" (the identical untargeted shape).
Both are read generally (`_quality_matcher`, parameterised counts) rather
than hardcoded to "permanent"/"three" - see `machines/effects.py`'s own
`_CREATE_TOKEN_COPY_OF_QUALITY_YOU_CONTROL_RE` and `_DISTRIBUTE_COUNTERS_
AMONG_YOU_CONTROL_RE` docstrings for the real second printings (Moritte of
the Frost's identical "a permanent you control" noun phrase on a different
mechanic; no other real Modern/Pioneer-legal printing shares the "distribute
... among <enumerated count> creatures you control" shape with a literal
count rather than an X, so that one is proven on this card alone).

The leading "is all colors." line is CR 604.3's characteristic-defining
ability - never a resolution instruction (see `test_self_is_all_colors_
cda.py`) - stripped off before `effect_for` reads the rest
(`_strip_self_is_all_colors_sentence`).

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 310.12b** - a Siege's own intrinsic defeat trigger: exile it, then
  cast it transformed without paying its mana cost.
- **CR 712.11a/712.13** - cast transformed, a double-faced spell is put on
  the stack (and later the battlefield) back face up.
- **CR 601.2c** - all of a spell's targets are chosen as it is cast, before
  any of its instructions are followed.
- **CR 608.2c** - resolution follows the printed instructions in order.
- **CR 608.2d** - a "you may"/choice is made as the ability resolves.
- **CR 111.7/707.2** - a created token copies the copiable values of the
  chosen permanent.
- **CR 122.1a** - putting a +1/+1 counter on a creature.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

ALARA = "Invasion of Alara"


def test_the_five_clauses_all_resolve_in_order():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Ornithopter"],
            library=["Island", "Swamp", "Forest", "Plains"],
            battlefield=[ALARA, "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    siege = scenario.find(ALARA, Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.HAND, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    # Staged straight to 3 defense counters left - the removal that
    # actually zeroes it (below) is a real damage event, so CR 310.12b's
    # defeat trigger fires exactly the way combat damage would have.
    siege.counters.remove("defense", 4)
    assert siege.counter_count("defense") == 3

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    assert siege.zone is Zone.BATTLEFIELD  # CR 704.5v: its own trigger is pending

    scenario.will_take_the_may(True, username="alice")  # cast it transformed
    # CR 601.2c: both targets are chosen together as Awaken the Maelstrom is
    # cast - the player drawing (alice herself) and the permanent to destroy
    # (bob's Llanowar Elves, an opponent's permanent).
    scenario.will_choose_targets("alice", elves, username="alice", source="Awaken the Maelstrom")
    # "You may put an artifact card from your hand onto the battlefield."
    scenario.will_take_the_may(True, username="alice", source="Awaken the Maelstrom")
    scenario.will_choose_cards(ornithopter, username="alice", source="Awaken the Maelstrom")
    # "Create a token that's a copy of a permanent you control." - Mountain,
    # so the copy is never itself a creature eligible for the counters below.
    scenario.will_choose_cards(mountain, username="alice", source="Awaken the Maelstrom")
    # "Distribute three +1/+1 counters among one, two, or three creatures you
    # control." - Grizzly Bears and the newly-entered Ornithopter.
    scenario.will_choose_cards(bears, ornithopter, username="alice", source="Awaken the Maelstrom")

    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    assert scenario.stack_names() == ["Awaken the Maelstrom"]
    scenario.pass_until_resolved()  # Awaken the Maelstrom's own five clauses

    alice = scenario.player("alice")
    assert len(alice.hand) == 2, "drew two cards - target player was alice herself"

    assert ornithopter.zone is Zone.BATTLEFIELD, "put onto the battlefield, not cast"

    mountain_copies = [
        state
        for state in scenario.game.battlefield
        if state.name == "Mountain" and state.controller == "alice" and state is not mountain
    ]
    assert len(mountain_copies) == 1, "a token copy of the chosen permanent, Mountain"

    assert bears.counter_count("+1/+1") + ornithopter.counter_count("+1/+1") == 3
    assert bears.counter_count("+1/+1") >= 1
    assert ornithopter.counter_count("+1/+1") >= 1

    assert elves.zone is Zone.GRAVEYARD, "destroyed - the opponent's targeted permanent"

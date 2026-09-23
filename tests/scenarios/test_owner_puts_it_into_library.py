"""One reader for "the owner of `<target>` puts it into a library" - CR 108.3's
owner, never the resolving spell or ability's controller, and never the
target's own controller when the two differ.

Three subject forms, all anaphoric or possessive over the same target:

- "the owner of `<target>` puts it ..." (Deem Inferior, Sudden Setback).
- "`<target>`'s owner puts it ..." (Misleading Motes, Wan Shi Tong).
- "(Choose )?`<target>`. Its owner puts it ..." - a two-clause paragraph
  (Aether Gust; Subtlety's own "up to one" shape already read this way).

Two destinations, both CR 608.2d choices made by the target's owner via
`DecisionKind.PUT_ON_TOP_OR_BOTTOM`:

- "on their choice of the top or bottom of their library" - a bare choice.
- "into their library `<ordinal>` from the top or on the bottom" - the same
  choice, except the top side lands at a printed depth rather than the very
  top, CR 609.3 sliding it as deep as the library actually has room for.

And one dispatch the old per-shape readers never made: the target can be a
spell on the stack (CR 108.3, CR 401.2 - `_put_spell_in_library`, which
removes it from the stack and forgets its `CastRecord`, CR 400.7/608.2b) or a
permanent/other object anywhere else (`Game.put_cards_into_library`) - judged
by the *target's own zone* at resolution, not by which sentence named it, so
the same reader closes Aether Gust ("spell or permanent"), Sudden Setback
("spell or nonland permanent"), and every plain-permanent shape alike.

Every CR number below was looked up with `mise run rules:find <number>` in
the session that wrote this file: CR 108.3 (owner), CR 115.6 ("up to one" may
choose zero), CR 401.2 (a library stays face down, in whatever order),
CR 608.2d (the owner's own choice, made as the ability/spell resolves),
CR 609.3 ("as much as it can" when a printed depth outruns the library).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone
from tests.scenarios.harness import Scenario

# ---------------------------------------------------------------------------
# (a) Aether Gust on a red spell on the stack: the OWNER is asked, top or
# bottom, the spell never resolves, and its cast record is forgotten.
# ---------------------------------------------------------------------------


def _aether_gust_vs_spell_board() -> tuple[Scenario, CardState]:
    scenario = (
        Scenario()
        .player("alice", hand=["Aether Gust"], battlefield=["Island", "Island"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    mountain = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", *mountain, username="bob", targets=["alice"])
    assert scenario.game.cast_record_of(bolt) is not None, "sanity: the cast was recorded"
    scenario.pass_priority("bob")
    return scenario, bolt


def test_aether_gust_top_puts_the_targeted_red_spell_on_top_and_forgets_its_cast_record():
    scenario, bolt = _aether_gust_vs_spell_board()
    stamp_before = bolt.zone_change_stamp
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.will_choose_top(True, username="bob")
    scenario.cast_onto_stack("Aether Gust", *islands, username="alice", targets=[bolt])
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0] is bolt
    assert scenario.stack_names() == [], "the bolt never resolves - it left the stack instead"
    # `zone_change_stamp` is minted fresh by the move itself, so a plain
    # `cast_record_of(bolt)` would read `None` either way - the real question
    # is whether the record under the *old* stamp was explicitly dropped
    # (`Game.forget_cast_record`) rather than left as a stale, still-findable
    # `cast_record_as_last_known` entry (CR 400.7).
    assert scenario.game.cast_record_as_last_known(stamp_before) is None


def test_aether_gust_bottom_puts_the_targeted_red_spell_on_the_bottom():
    scenario, bolt = _aether_gust_vs_spell_board()
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.will_choose_top(False, username="bob")
    scenario.cast_onto_stack("Aether Gust", *islands, username="alice", targets=[bolt])
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bolt
    assert scenario.stack_names() == []


# ---------------------------------------------------------------------------
# (b) Aether Gust on a green permanent: the owner still chooses.
# ---------------------------------------------------------------------------


def test_aether_gust_on_a_green_permanent_the_owner_still_chooses():
    scenario = (
        Scenario()
        .player("alice", hand=["Aether Gust"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    islands = scenario.untapped_sources("Island", "Island", username="alice")

    scenario.will_choose_top(False, username="bob")
    scenario.cast_and_resolve("Aether Gust", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bears


# ---------------------------------------------------------------------------
# (c) A permanent controlled by a player who is not its owner: the owner is
# still the one asked, and the library it lands in is the owner's, not the
# controller's - stolen first with Act of Treason, a real pool printing.
# ---------------------------------------------------------------------------


def test_a_stolen_permanents_owner_is_asked_not_its_new_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Act of Treason", "Aether Gust"],
            battlefield=["Mountain", "Mountain", "Mountain", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Act of Treason", *mountains, targets=[bears])
    assert bears.controller == "alice", "sanity: alice now controls it"
    assert bears.owner == "bob", "sanity: bob still owns it (CR 108.3)"

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.will_choose_top(False, username="bob")
    scenario.cast_and_resolve("Aether Gust", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bears, "it went to the OWNER's library"
    assert scenario.player("alice").library == [], "never the controller's"


# ---------------------------------------------------------------------------
# (d) Misleading Motes - the possessive subject form, "target creature's
# owner puts it".
# ---------------------------------------------------------------------------


def test_misleading_motes_possessive_subject_form():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Misleading Motes"], battlefield=["Island", "Island", "Island", "Island"]
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(True, username="bob")
    scenario.cast_and_resolve("Misleading Motes", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0] is bears


# ---------------------------------------------------------------------------
# (e) Deem Inferior - "into their library second from the top or on the
# bottom": a library of 3 lands it at index 1, and a library of 0 leaves it
# the only card (CR 609.3).
# ---------------------------------------------------------------------------


def test_deem_inferior_second_from_the_top_of_a_three_card_library():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deem Inferior"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(True, username="bob")
    scenario.cast_and_resolve("Deem Inferior", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert bob.library[1] is bears, "second from the top is index 1"
    assert bob.library[0].name == "Forest", "the library's own order is otherwise untouched"
    assert bob.library[2].name == "Mountain"
    assert bob.library[3].name == "Plains"


def test_deem_inferior_from_an_empty_library_still_lands_second_from_the_top():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deem Inferior"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(True, username="bob")
    scenario.cast_and_resolve("Deem Inferior", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert bob.library == [bears], "CR 609.3: as deep as the library actually reaches"


def test_deem_inferior_the_bottom_choice_ignores_the_printed_depth():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deem Inferior"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(False, username="bob")
    scenario.cast_and_resolve("Deem Inferior", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert bob.library[-1] is bears


# ---------------------------------------------------------------------------
# (f) Wan Shi Tong, All-Knowing's own ETB trigger - the identical ordinal
# shape, off a triggered ability rather than a spell.
# ---------------------------------------------------------------------------


def test_wan_shi_tong_second_from_the_top():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wan Shi Tong, All-Knowing"],
            battlefield=["Island", "Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    islands = scenario.untapped_sources(
        "Island", "Island", "Island", "Island", "Island", username="alice"
    )

    scenario.choose_trigger_targets("Wan Shi Tong, All-Knowing", [bears])
    scenario.will_choose_top(True, username="bob")
    scenario.cast_and_resolve("Wan Shi Tong, All-Knowing", *islands)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.LIBRARY
    assert bob.library[1] is bears, "second from the top is index 1"
    assert bob.library[0].name == "Forest"
    assert bob.library[2].name == "Mountain"


# ---------------------------------------------------------------------------
# (g) Sudden Setback - already handled before this wave - keeps working for
# both a spell and a permanent, and now also forgets the cast record for a
# spell target (the latent gap the old "owner of" reader left open).
# ---------------------------------------------------------------------------


def test_sudden_setback_on_a_spell_still_works_and_now_forgets_its_cast_record():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Sudden Setback"], battlefield=["Island", "Island", "Island", "Island"]
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    mountain = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", *mountain, username="bob", targets=["alice"])
    assert scenario.game.cast_record_of(bolt) is not None
    stamp_before = bolt.zone_change_stamp
    scenario.pass_priority("bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(True, username="bob")
    scenario.cast_onto_stack("Sudden Setback", *islands, username="alice", targets=[bolt])
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0] is bolt
    assert scenario.stack_names() == []
    assert scenario.game.cast_record_as_last_known(stamp_before) is None


def test_sudden_setback_on_a_permanent_still_works():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Sudden Setback"], battlefield=["Island", "Island", "Island", "Island"]
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.will_choose_top(False, username="bob")
    scenario.cast_and_resolve("Sudden Setback", *islands, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bears

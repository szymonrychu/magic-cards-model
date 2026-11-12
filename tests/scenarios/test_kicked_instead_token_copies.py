"""Scenario: a kicker that swaps a spell's token copy for a different one -
"If this spell was kicked, instead for each creature target opponent controls,
create a token that's a copy of that creature" (the kicked half names its own
target and a "for each" frame) and "If this spell was kicked, create five of
those tokens instead" (the kicked half names the base's tokens by anaphor).

Mirror Universe Intrusion is the reported card:

    Create a token that's a copy of target creature an opponent controls,
    except it has menace. If this spell was kicked, instead for each creature
    target opponent controls, create a token that's a copy of that creature,
    except it has menace.

Three gaps kept it unread: `modal._instead_branch_effect` composes through
`parse_mixed_effect_for_spell` and never reached the spell-text-only
`control_copy._parse_for_each_creature_target_player_copy_clause`; that reader
hardcoded "target player"; and `targeting.kicked_instead_target_text` wanted
"<verb> target" in both halves, so the cast announced both targets at once.

Rite of Replication (a differently worded real printing, in the same set of
shapes) is the second card: "Create a token that's a copy of target creature.
If this spell was kicked, create five of those tokens instead." - one target,
a count change, "those tokens" read back as copies of that same target.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.33a** - kicker is an optional additional cost.
- **CR 601.2c** - a spell's targets are chosen as it is cast; a kicker paid
  decides which targets are chosen.
- **CR 614.1a** - "instead" replaces the base instruction whole.
- **CR 707.9a** - the copy exception ("except it has menace") is part of the
  copiable values.

The "for each" set is read once, as the instruction runs, so the new tokens are
not copied in turn (the engine's fixed-set-now convention, no rule cited).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

MIRROR = "Mirror Universe Intrusion"
RITE = "Rite of Replication"


def _lands(*, islands, swamps=0):
    return ["Island"] * islands + ["Swamp"] * swamps


def _board(spell, *, lands, bob=(), carol=None, alice_extra=()):
    scenario = Scenario().player(
        "alice", hand=[spell], battlefield=[*lands, *alice_extra], library=["Island"] * 5
    )
    scenario = scenario.player("bob", battlefield=list(bob), library=["Island"] * 5)
    if carol is not None:
        scenario = scenario.player("carol", battlefield=list(carol), library=["Island"] * 5)
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _mirror_board(**kwargs):
    return _board(MIRROR, lands=_lands(islands=5, swamps=4), **kwargs)


def _cast(scenario, spell, targets, *, kicked, mana):
    casting = scenario.cast(spell)
    if kicked:
        casting.pay_kicker()
    casting.choose_targets(list(targets))
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*mana))
    scenario.put_on_stack(casting)
    return casting


def _cast_mirror(scenario, target, *, kicked):
    mana = _lands(islands=5, swamps=4) if kicked else ["Island", "Island", "Swamp"]
    _cast(scenario, MIRROR, [target], kicked=kicked, mana=mana)
    scenario.resolve_top()


def _tokens(scenario, controller="alice"):
    return [s for s in scenario.game.battlefield if s.token and s.controller == controller]


def _menace(scenario, permanent):
    return has_keyword(permanent, Keyword.MENACE, scenario.game)


def test_both_cards_are_handled():
    for name in (MIRROR, RITE):
        outcomes = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in outcomes} == {HANDLED}, (name, outcomes)


# -- Mirror Universe Intrusion, unkicked ---------------------------------------


def test_unkicked_copies_the_target_creature_with_menace():
    scenario = _mirror_board(bob=["Grizzly Bears", "Mulldrifter"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_mirror(scenario, bears, kicked=False)

    (copy,) = _tokens(scenario)
    assert copy.name == "Grizzly Bears"
    assert _menace(scenario, copy), "CR 707.9a: the exception is a copiable value"
    assert not _menace(scenario, bears), "the original is untouched"
    assert not [s for s in _tokens(scenario, "bob")]


def test_unkicked_target_must_be_a_creature_an_opponent_controls():
    scenario = _mirror_board(alice_extra=["Grizzly Bears"], bob=["Grizzly Bears"])
    sources = scenario.untapped_sources("Island", "Island", "Swamp")
    mine = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.cast(MIRROR).choose_targets([mine])
    with pytest.raises(ValueError):
        scenario.cast(MIRROR).choose_targets([scenario.player("bob")])
    assert sources


# -- Mirror Universe Intrusion, kicked -----------------------------------------


def test_kicked_copies_every_creature_the_targeted_opponent_controls():
    scenario = _mirror_board(bob=["Grizzly Bears", "Mulldrifter", "Isamaru, Hound of Konda"])
    _cast_mirror(scenario, scenario.player("bob"), kicked=True)

    names = sorted(token.name for token in _tokens(scenario))
    assert names == ["Grizzly Bears", "Isamaru, Hound of Konda", "Mulldrifter"]
    assert all(_menace(scenario, token) for token in _tokens(scenario))
    assert all(token.controller == "alice" for token in _tokens(scenario))
    assert len([s for s in scenario.game.battlefield if s.controller == "bob"]) == 3


def test_kicked_announces_only_the_opponent_not_a_creature_as_well():
    """CR 601.2c: the kicked half has the one target, the player - choosing a
    creature in its place is refused, and one target is enough."""
    scenario = _mirror_board(bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    refused = scenario.cast(MIRROR)
    refused.pay_kicker()
    with pytest.raises(ValueError):
        refused.choose_targets([bears])
    casting = scenario.cast(MIRROR)
    casting.pay_kicker()
    casting.choose_targets([scenario.player("bob")])


def test_kicked_reads_only_the_targeted_opponents_creatures():
    scenario = _mirror_board(bob=["Grizzly Bears"], carol=["Mulldrifter", "Mulldrifter"])
    _cast_mirror(scenario, scenario.player("carol"), kicked=True)

    assert sorted(token.name for token in _tokens(scenario)) == ["Mulldrifter", "Mulldrifter"]


def test_kicked_ignores_the_casters_own_creatures_and_noncreatures():
    scenario = _mirror_board(alice_extra=["Llanowar Elves"], bob=["Grizzly Bears", "Sol Ring"])
    _cast_mirror(scenario, scenario.player("bob"), kicked=True)

    assert [token.name for token in _tokens(scenario)] == ["Grizzly Bears"]


def test_kicked_against_an_opponent_with_no_creatures_makes_nothing():
    scenario = _mirror_board(bob=["Sol Ring"])
    _cast_mirror(scenario, scenario.player("bob"), kicked=True)

    assert not _tokens(scenario)


def test_kicked_copies_of_tokens_and_the_new_tokens_are_not_copied_in_turn():
    """The set is read once as the spell resolves - three creatures give three
    tokens, not a chain of copies of copies."""
    scenario = _mirror_board(bob=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    _cast_mirror(scenario, scenario.player("bob"), kicked=True)

    assert len(_tokens(scenario)) == 3


def test_the_kicked_spell_is_paid_for_with_the_kicker():
    scenario = _mirror_board(bob=["Grizzly Bears"])
    _cast_mirror(scenario, scenario.player("bob"), kicked=True)

    lands = [s for s in scenario.game.permanents_controlled_by("alice") if not s.token]
    assert len(lands) == 9 and not [land for land in lands if land.untapped]


# -- Rite of Replication: "five of those tokens instead" -----------------------


def _rite_board(**kwargs):
    return _board(RITE, lands=_lands(islands=9), **kwargs)


def _cast_rite(scenario, target, *, kicked):
    _cast(scenario, RITE, [target], kicked=kicked, mana=["Island"] * (9 if kicked else 4))
    scenario.resolve_top()


def test_rite_unkicked_makes_one_copy():
    scenario = _rite_board(bob=["Grizzly Bears"])
    _cast_rite(scenario, scenario.creature("Grizzly Bears", "bob"), kicked=False)

    assert [token.name for token in _tokens(scenario)] == ["Grizzly Bears"]


def test_rite_kicked_makes_five_copies_of_the_same_target():
    scenario = _rite_board(bob=["Mulldrifter"])
    _cast_rite(scenario, scenario.creature("Mulldrifter", "bob"), kicked=True)

    assert [token.name for token in _tokens(scenario)] == ["Mulldrifter"] * 5


def test_rite_may_target_the_casters_own_creature():
    scenario = _rite_board(alice_extra=["Grizzly Bears"])
    _cast_rite(scenario, scenario.creature("Grizzly Bears", "alice"), kicked=True)

    assert len(_tokens(scenario)) == 5
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


# -- the shared reading: the widened "those tokens" rewrite --------------------


def test_the_those_tokens_alternative_is_rewritten_to_copies_of_the_same_target():
    from magic_cards_model.machines.effects import _ability_instead_alternative_text

    base = "Create a token that's a copy of target creature"
    assert _ability_instead_alternative_text(base, "create five of those tokens") == (
        "create five tokens that are copies of target creature"
    )
    with_exception = base + ", except it has menace"
    assert _ability_instead_alternative_text(with_exception, "create three of those tokens") == (
        "create three tokens that are copies of target creature, except it has menace"
    )


def test_a_plain_token_base_still_rewrites_as_before():
    from magic_cards_model.machines.effects import _ability_instead_alternative_text

    assert _ability_instead_alternative_text(
        "Create two 1/1 white Soldier creature tokens", "create four of those tokens"
    ) == ("create four 1/1 white Soldier creature tokens")


# -- the targeting texts -------------------------------------------------------


def test_kicked_instead_target_text_reads_a_spell_whose_halves_name_targets_in_any_shape():
    from magic_cards_model.machines.targeting import kicked_instead_target_text

    halves = kicked_instead_target_text(card(MIRROR).oracle_text)
    assert halves is not None
    unkicked, kicked = halves
    assert "target creature an opponent controls" in unkicked
    assert "target opponent" in kicked and "target creature" not in kicked
    assert kicked_instead_target_text(card(RITE).oracle_text) is None, "one target, no swap"

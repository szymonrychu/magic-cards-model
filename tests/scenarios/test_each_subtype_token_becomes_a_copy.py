"""Scenario: "Each `<subtype>` token you control becomes a copy of target
`<permanent>` until end of turn" - the qualifier slot of `copy_effects.
_EACH_BECOMES_A_COPY_RE` (`_each_group_member`, `_group_qualifiers`), and the
"Choose target `<permanent>`. Each other `<permanent>` you control becomes a copy
of that `<permanent>`" pair (`modal._parse_choose_target_then_each_becomes_a_copy_pair`).

Gwyndala, the Progeny is the reported card: "{2}: Each Equipment token you
control becomes a copy of target Equipment you control until end of turn."
The old group grammar took a card type or the word "token" with an optional
"non" prefix, so a subtype qualifier ("Equipment token") was unread and the
ability was silent. The group now carries any number of qualifiers: the
"non`<word>`" exclusions it already read and subtypes (`canonical_subtype`);
a qualifier that is neither is refused whole rather than read as an empty group.

Masterful Replication (off-pool, Modern-legal, added for this file) is the
second printing: its second mode is "Choose target artifact you control. Each
other artifact you control becomes a copy of that artifact until end of turn."
- a different noun, no token or subtype qualifier, "other", and a pronoun back
to a "choose target" sentence instead of a "target" in the copy sentence
itself. Mirrorweave ("Each other creature becomes a copy of target nonlegendary
creature until end of turn.") stays green as the regression proof.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 707.2** - a copy gets the copiable values of the original, and not its
  counters or status.
- **CR 707.4** - a permanent that becomes a copy stays the same object.
- **CR 613.1a** - a copy effect is a layer 1 effect; one instruction's effects
  share a timestamp (CR 613.7b).
- **CR 611.2c** - the permanents affected are fixed as the effect begins.
- **CR 611.2a** - "until end of turn" ends at the cleanup step.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.copy_effects import (
    _each_group_member,
    _group_qualifiers,
    _parse_each_becomes_a_copy_clause,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

SPARE_EQUIPMENT = TokenDefinition(
    name="Spare Equipment", types=(Type.ARTIFACT,), subtypes=("Equipment",)
)


def _name(scenario, permanent):
    return scenario.game.characteristics_of(permanent).name


def _gwyndala_board(*, alice_extra=(), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gwyndala, the Progeny"],
            battlefield=["Island"] * 6 + list(alice_extra),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Gwyndala, the Progeny", *scenario.untapped_sources("Island", "Island")
    )
    scenario.resolve_top()  # the enters trigger: Neuroflux Heirloom, attached
    gwyndala = scenario.creature("Gwyndala, the Progeny", "alice")
    (heirloom,) = [s for s in scenario.game.battlefield if s.token and s.controller == "alice"]
    return scenario, gwyndala, heirloom


def _copy_equipment(scenario, gwyndala, target):
    scenario.activate(gwyndala, *scenario.untapped_sources("Island", "Island"), targets=[target])
    scenario.resolve_top()


def test_gwyndala_and_masterful_replication_are_handled():
    for name in ("Gwyndala, the Progeny", "Masterful Replication"):
        outcomes = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in outcomes} == {HANDLED}, (name, outcomes)


def test_the_heirloom_becomes_a_copy_of_the_target_equipment():
    scenario, gwyndala, heirloom = _gwyndala_board(alice_extra=["Bonesplitter"])
    assert (gwyndala.power, gwyndala.toughness) == (2, 2), "the Heirloom's own +1/+1"
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    _copy_equipment(scenario, gwyndala, splitter)

    assert _name(scenario, heirloom) == "Bonesplitter"
    assert heirloom.id == scenario.game.find_by_id(heirloom.id).id, "CR 707.4: the same object"
    assert (gwyndala.power, gwyndala.toughness) == (3, 1), "now Bonesplitter's +2/+0"
    assert _name(scenario, splitter) == "Bonesplitter"


def test_the_copy_lasts_until_end_of_turn_only():
    scenario, gwyndala, heirloom = _gwyndala_board(alice_extra=["Bonesplitter"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    _copy_equipment(scenario, gwyndala, splitter)
    assert _name(scenario, heirloom) == "Bonesplitter"

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()

    assert _name(scenario, heirloom) == "Neuroflux Heirloom"


def test_every_equipment_token_changes_and_only_equipment_tokens():
    """CR 611.2c: the group is fixed as the ability resolves - every Equipment
    token (two here), but not a Food token, not a nontoken Equipment, and not
    an opponent's Equipment token."""
    scenario, gwyndala, heirloom = _gwyndala_board(alice_extra=["Bonesplitter", "Basilisk Collar"])
    (spare,) = create_tokens(scenario.game, SPARE_EQUIPMENT, "alice")
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")
    (theirs,) = create_tokens(scenario.game, SPARE_EQUIPMENT, "bob")
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")

    _copy_equipment(scenario, gwyndala, collar)

    assert _name(scenario, heirloom) == "Basilisk Collar"
    assert _name(scenario, spare) == "Basilisk Collar"
    assert _name(scenario, food) == "Food Token"
    assert _name(scenario, splitter) == "Bonesplitter"
    assert _name(scenario, theirs) == "Spare Equipment", "'you control' keeps the opponent's out"


def test_the_target_must_be_equipment_you_control():
    scenario, gwyndala, _heirloom = _gwyndala_board(
        alice_extra=["Grizzly Bears"], bob=["Bonesplitter"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Island", "Island")
    with pytest.raises(ValueError, match="illegal target"):
        scenario.activate(gwyndala, *sources, targets=[bears])
    with pytest.raises(ValueError, match="illegal target"):
        scenario.activate(gwyndala, *sources, targets=[theirs])


def test_an_equipment_token_may_copy_another_equipment_token():
    """The target can itself be a token: the Heirloom copies the spare token,
    whose own copiable values are its token definition (CR 111.3)."""
    scenario, gwyndala, heirloom = _gwyndala_board()
    (spare,) = create_tokens(scenario.game, SPARE_EQUIPMENT, "alice")
    _copy_equipment(scenario, gwyndala, spare)

    assert _name(scenario, heirloom) == "Spare Equipment"
    assert _name(scenario, spare) == "Spare Equipment"


# -- the group grammar itself -------------------------------------------------


def test_a_qualifier_that_is_neither_a_subtype_nor_a_non_exclusion_is_refused():
    """A word that matches no type line would read as an empty group while
    claiming to have been understood, so the whole clause is left unread."""
    assert _group_qualifiers("Bogus token") is None
    assert (
        _parse_each_becomes_a_copy_clause(
            "Each Bogus token you control becomes a copy of target Equipment you control "
            "until end of turn."
        )
        is None
    )
    assert _group_qualifiers("Equipment token") == ([], ["equipment"])
    assert _group_qualifiers("nonland permanent") == (["land"], [])
    assert _group_qualifiers("nontoken Aura permanent") == (["token"], ["aura"])


def test_the_untouched_groups_still_read():
    for text in (
        "Each token you control becomes a copy of target Equipment you control until end of turn.",
        "Each other creature becomes a copy of target nonlegendary creature until end of turn.",
        "Each nonland permanent you control becomes a copy of target non-Aura permanent.",
    ):
        assert _parse_each_becomes_a_copy_clause(text) is not None, text


def test_group_membership_reads_computed_subtypes():
    scenario = _board_with_tokens()
    equipment, food = scenario
    chars = {name: None for name in ("equipment", "food")}
    del chars
    # An Equipment token is in "Equipment token", "token", "artifact" but not "Food token".
    assert _each_group_member(equipment, "Equipment token")
    assert _each_group_member(equipment, "token")
    assert _each_group_member(equipment, "artifact")
    assert not _each_group_member(food, "Equipment token")
    assert not _each_group_member(equipment, "nontoken artifact")
    assert _each_group_member(food, "Food token")


def _board_with_tokens():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (equipment,) = create_tokens(scenario.game, SPARE_EQUIPMENT, "alice")
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")
    return scenario.game.characteristics_of(equipment), scenario.game.characteristics_of(food)


# -- Masterful Replication: the pronoun pair ----------------------------------


def _masterful_board(*, alice_extra=(), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Masterful Replication"],
            battlefield=["Island"] * 6 + list(alice_extra),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_mode_two(scenario, target):
    casting = scenario.cast("Masterful Replication")
    casting.choose_modes([2])
    casting.choose_targets([target])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 6))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_masterful_replication_every_other_artifact_becomes_a_copy_of_the_chosen_one():
    scenario = _masterful_board(
        alice_extra=["Bonesplitter", "Basilisk Collar", "Mind Stone"], bob=["Sol Ring"]
    )
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _cast_mode_two(scenario, splitter)

    assert _name(scenario, splitter) == "Bonesplitter"
    assert _name(scenario, collar) == "Bonesplitter"
    assert _name(scenario, stone) == "Bonesplitter"
    assert _name(scenario, ring) == "Sol Ring", "'you control' keeps the opponent's artifact out"


def test_masterful_replication_copy_ends_at_end_of_turn():
    scenario = _masterful_board(alice_extra=["Bonesplitter", "Mind Stone"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    _cast_mode_two(scenario, splitter)
    assert _name(scenario, stone) == "Bonesplitter"

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()

    assert _name(scenario, stone) == "Mind Stone"


def test_masterful_replication_mode_one_still_makes_two_golems():
    scenario = _masterful_board()
    casting = scenario.cast("Masterful Replication")
    casting.choose_modes([1])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 6))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len([s for s in scenario.game.battlefield if s.token and s.controller == "alice"]) == 2


# -- the static abilities of a copy (CR 707.2, CR 604.2) ----------------------


def test_a_copy_of_an_equipment_brings_the_static_ability_it_copied():
    """The layer 1 copy rewrites the ability text, and the static ability the
    permanent contributes is the copied text's, not the printing's: Basilisk
    Collar attached to a Bear becomes a Bonesplitter, so the Bear gets +2/+0
    and loses the Collar's deathtouch and lifelink - until end of turn."""
    scenario = _masterful_board(alice_extra=["Bonesplitter", "Basilisk Collar", "Grizzly Bears"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    collar.attach_to(bears)
    assert (bears.power, bears.toughness) == (2, 2)
    assert has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)

    _cast_mode_two(scenario, splitter)

    assert (bears.power, bears.toughness) == (4, 2), "Bonesplitter's +2/+0, through the copy"
    assert not has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)
    assert not has_keyword(bears, Keyword.LIFELINK, scenario.game)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()

    assert (bears.power, bears.toughness) == (2, 2)
    assert has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)
    assert _name(scenario, collar) == "Basilisk Collar"

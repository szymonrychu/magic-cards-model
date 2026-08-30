"""Scenario: an Oxford-comma noun list in a target restriction (CR 115.1).

The noun-reading loop in `_read_phrase` (`machines/targeting.py`) swallowed a
bare "or"/"and" between two nouns, but a comma was invisible to it: the word
tokenizer dropped punctuation entirely, so "target artifact, enchantment, or
nonbasic land" tokenized as `["artifact", "enchantment", "or", "nonbasic",
"land"]` and the loop stopped after "artifact" - the very next word,
"enchantment", is not "or"/"and", so the old tail check broke the loop right
there. Boseiju, Who Endures could destroy an artifact and nothing else its own
text plainly allows.

Fixed by keeping the comma as its own token and treating it exactly like "or"
and "and" between list items - see `_SOURCE_EXCLUDING`... no, see the noun
loop's leading `if word in {"or", "and", ","}: continue`.

**Order matters, and this file exists to prove it stayed in order**:
`test_negated_supertypes.py`'s fix has to land *before* this one. Each item in
the list may carry its own adjective - "nonbasic" belongs only to "land", the
third item - and the loop now tries a fresh adjective (`adjectives.take`)
before every item after the first, not only before the whole phrase. Fixing
the comma before supertypes existed would have made "nonbasic" attach nowhere,
turning "too narrow" (artifact only) into "too wide" (any land, including a
basic one) - strictly worse, per the assignment's own warning.
"""

from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Type
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.card_state import TargetRef
from tests.cards import card
from tests.scenarios.harness import Scenario

BOSEIJU_CHANNEL_TEXT = (
    "Destroy target artifact, enchantment, or nonbasic land an opponent "
    "controls. That player may search their library for a land card with a "
    "basic land type, put it onto the battlefield, then shuffle. This ability "
    "costs {1} less to activate for each legendary creature you control."
)


def test_all_three_nouns_are_read():
    profile = profile_for_text(BOSEIJU_CHANNEL_TEXT)
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.card_types == frozenset({Type.ARTIFACT, Type.ENCHANTMENT, Type.LAND})


def test_nonbasic_still_applies_only_to_the_land_item():
    """The regression the ordering note warns about: a fix that reads all three
    nouns but forgets which one "nonbasic" belongs to would accept a basic
    land here. It must not.
    """
    (requirement,) = profile_for_text(BOSEIJU_CHANNEL_TEXT).requirements
    assert requirement.excluded_supertypes == frozenset({Supertype.BASIC})

    forest = card("Forest")  # a real basic land printing
    assert Supertype.BASIC in forest.supertypes


def test_a_second_real_card_with_the_same_comma_shape():
    """Acidic Slime: "destroy target artifact, enchantment, or land" is the
    same three-item, comma-then-"or" list as Boseiju's, on a triggered ability
    rather than an activated one, and with no supertype adjective at all -
    checked so the comma fix is not read as Boseiju-specific.
    """
    profile = profile_for_text(
        "When this creature enters, destroy target artifact, enchantment, or land."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.card_types == frozenset({Type.ARTIFACT, Type.ENCHANTMENT, Type.LAND})


# -- candidate offering, on a real board -------------------------------------


def _boseiju_targeting_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Boseiju, Who Endures"])
        .player(
            "bob",
            battlefield=["Sol Ring", "Solitude", "Arid Mesa", "Mountain"],
        )
    )


def test_artifact_enchantment_and_nonbasic_land_are_all_legal_targets():
    """Boseiju's Channel ability cannot be fully activated from hand yet
    (`Game.why_cannot_activate`'s battlefield-only gate -
    `test_self_referential_costs.py` documents the same pre-existing gap), so
    this checks the same thing `activate_ability` would check -
    `TargetRequirement.rejects` - directly against real permanents, the way
    `test_targeting_adjectives.py` already does for other unreachable-by-full-
    activation cases.
    """
    scenario = _boseiju_targeting_board().build()
    sol_ring = scenario.creature("Sol Ring", "bob")
    mesa = scenario.creature("Arid Mesa", "bob")
    mountain = scenario.creature("Mountain", "bob")
    (requirement,) = profile_for_text(BOSEIJU_CHANNEL_TEXT).requirements

    assert requirement.rejects(sol_ring, "alice") is None, "an artifact is legal"
    assert requirement.rejects(mesa, "alice") is None, "a nonbasic land is legal"

    reason = requirement.rejects(mountain, "alice")
    assert reason is not None, "a basic land must not be a legal target"
    assert "nonbasic" in reason or "basic" in reason


def test_a_creature_is_not_offered():
    """Solitude is a creature, none of the three listed nouns - refused."""
    scenario = _boseiju_targeting_board().build()
    solitude = scenario.creature("Solitude", "bob")
    (requirement,) = profile_for_text(BOSEIJU_CHANNEL_TEXT).requirements
    assert requirement.rejects(solitude, "alice") is not None


def test_acidic_slime_offers_all_three_nouns_on_a_real_board():
    """A full, playable proof of the comma fix: Acidic Slime's ETB actually
    offers bob's enchantment as a candidate, not just artifacts.
    """
    from dataclasses import dataclass, field

    from magic_cards_model.machines.decisions import NOT_ANSWERED, Decision

    @dataclass
    class Provider:
        asked: list[Decision] = field(default_factory=list)

        def decide(self, decision):
            self.asked.append(decision)
            return NOT_ANSWERED

    scenario = (
        Scenario()
        .player("alice", hand=["Acidic Slime"])
        .player("bob", battlefield=["Sol Ring", "Solitude", "Mountain"])
        .build()
    )
    sol_ring = scenario.creature("Sol Ring", "bob")
    mountain = scenario.creature("Mountain", "bob")
    provider = Provider()
    scenario.game.decisions.provider = provider

    scenario.put_onto_battlefield("Acidic Slime")
    scenario.game.put_triggers_on_stack()

    offered = provider.asked[-1].targets
    assert TargetRef.to_card(sol_ring) in offered, "artifact"
    assert TargetRef.to_card(mountain) in offered, "land - the third, comma-separated item"


def test_alices_own_permanents_are_not_legal_targets():
    """ "an opponent controls" - the requirement's own controller restriction,
    unaffected by the comma fix and still enforced alongside it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boseiju, Who Endures", "Sol Ring"])
        .player("bob", battlefield=["Arid Mesa"])
        .build()
    )
    own_sol_ring = scenario.creature("Sol Ring", "alice")
    (requirement,) = profile_for_text(BOSEIJU_CHANNEL_TEXT).requirements
    reason = requirement.rejects(own_sol_ring, "alice")
    assert reason is not None

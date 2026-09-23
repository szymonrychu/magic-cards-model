"""Nahiri, the Unforgiving's 0 ability - "Exile target creature or Equipment
card with mana value less than Nahiri's loyalty from your graveyard." - on a
real board, through `TargetRequirement.rejects` the way
`test_oxford_comma_target_lists.py` already checks an unreachable-by-full-
activation restriction directly.

This was `sweep_pool.py --targeting`'s one unreadable phrase in the whole
pool. Two gaps, both in `machines/targeting.py`:

- **CR 107.1a's strict "less than"**: `_COMPARISON_CLAUSE` only ever read
  "... or equal to ..." comparisons (`ComparisonOperator.LESS_OR_EQUAL`/
  `GREATER_OR_EQUAL`); "less than Nahiri's loyalty" has no "or equal to" at
  all, so it hit `_COMPARISON_UNREADABLE` and failed the whole phrase closed.
  Fixed with `ComparisonOperator.LESS_THAN`/`GREATER_THAN` and a new
  `ComparisonCount.SOURCE_LOYALTY`, read generically off *any* capitalized
  name immediately before "'s loyalty" (CR 201.5's self-reference, the same
  reading `TargetRequirement.exiled_with_source` already gives "exiled with
  `<name>`" - see that flag's own docstring), never compared against the
  card's own printed name.
- **CR 205.3g's closed artifact-type list**: "creature or Equipment card" is
  a two-item noun list mixing an ordinary CR 300.1 card type with a bare
  subtype word eliding its own type - the same elision the parser already
  reads for a *lone* subtype (Greasefang, Okiba Boss's "target Vehicle
  card"), just as the second half of an "or". Equipment is an artifact
  subtype, never a creature one, so the two halves are read as a genuine
  disjunction (CR 115.1) via `TargetRequirement.alternatives`, not merged
  into one `card_types`/`required_subtypes` pair - a merge would have
  wrongly demanded every legal target, plain creatures included, also carry
  the "equipment" subtype.

CR 306.5c ("The loyalty of a planeswalker on the battlefield is equal to the
number of loyalty counters on it") and CR 301.5 (Equipment) were both looked
up with `mise run rules:find` in the session that wrote this file.
"""

from magic_cards_model.machines import parse_abilities
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _zero_ability_text() -> str:
    from tests.cards import card

    for ability in parse_abilities(card("Nahiri, the Unforgiving")):
        text = getattr(ability, "effect", None) or ability.text
        if "Exile target creature" in text:
            return text
    raise AssertionError("Nahiri, the Unforgiving's 0 ability text was not found")


def _board() -> Scenario:
    """Nahiri cast with every land tapped for mana (CR 118.13a's payment
    choice defaults to the mana that is there), so CR 702.150a's compleated
    replacement never applies and she enters at her plain printed loyalty, 5
    (CR 306.5b) - `test_compleated.py`'s own baseline case for this exact
    card. A mixed graveyard exercises both halves of the disjunction and the
    strict inequality's own boundary:

    - Grizzly Bears (creature, mana value 2): legal - a creature, and 2 < 5.
    - Acidic Slime (creature, mana value 5): illegal - a creature, but 5 is
      not *strictly* less than 5 (the "or equal to" families this parser
      already read would have wrongly accepted it).
    - Bonesplitter (artifact - Equipment, mana value 1): legal only through
      the alternative - not a creature at all.
    - Mind Stone (artifact, mana value 2, no Equipment subtype): illegal -
      neither a creature nor an Equipment, so neither half of the
      disjunction accepts it, even though 2 < 5 and it is an artifact.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Nahiri, the Unforgiving"],
            battlefield=["Mountain", "Mountain", "Plains", "Plains"],
            graveyard=["Grizzly Bears", "Acidic Slime", "Bonesplitter", "Mind Stone"],
        )
        .player("bob")
    )


def _requirement():
    profile = profile_for_text(_zero_ability_text())
    assert profile.understood
    (requirement,) = profile.requirements
    return requirement


def test_a_creature_below_the_loyalty_bound_is_legal():
    from magic_cards_model.machines import Step

    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")
    nahiri = scenario.cast_and_resolve("Nahiri, the Unforgiving", *lands)
    assert nahiri.loyalty == 5
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    assert _requirement().rejects(bears, "alice", scenario.game, nahiri.id) is None


def test_a_creature_equal_to_the_loyalty_bound_is_illegal():
    """The strict-inequality boundary: 5 is not less than 5. A parser that
    silently read "less than" as "or less" (subtracting nothing) or dropped
    the restriction entirely would wrongly accept Acidic Slime here."""
    from magic_cards_model.machines import Step

    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")
    nahiri = scenario.cast_and_resolve("Nahiri, the Unforgiving", *lands)
    assert nahiri.loyalty == 5
    slime = scenario.find("Acidic Slime", Zone.GRAVEYARD)

    reason = _requirement().rejects(slime, "alice", scenario.game, nahiri.id)
    assert reason is not None


def test_an_equipment_below_the_bound_is_legal_through_the_alternative():
    from magic_cards_model.machines import Step

    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")
    nahiri = scenario.cast_and_resolve("Nahiri, the Unforgiving", *lands)
    bonesplitter = scenario.find("Bonesplitter", Zone.GRAVEYARD)

    assert _requirement().rejects(bonesplitter, "alice", scenario.game, nahiri.id) is None


def test_a_plain_artifact_that_is_neither_creature_nor_equipment_is_illegal():
    """Mind Stone is below the loyalty bound and is an artifact card, but it
    is not a creature and does not carry the Equipment subtype - neither half
    of the disjunction accepts it. This is the failure mode a naive merge of
    `card_types`/`required_subtypes` (rather than `alternatives`) would get
    backwards: it would have *rejected* Grizzly Bears (no "equipment"
    subtype) rather than Mind Stone.
    """
    from magic_cards_model.machines import Step

    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")
    nahiri = scenario.cast_and_resolve("Nahiri, the Unforgiving", *lands)
    mind_stone = scenario.find("Mind Stone", Zone.GRAVEYARD)

    reason = _requirement().rejects(mind_stone, "alice", scenario.game, nahiri.id)
    assert reason is not None


def test_a_legal_creature_on_the_battlefield_is_not_a_legal_target():
    """CR 115.2: the ability's own "from your graveyard" narrows the zone -
    a creature of the same low mana value sitting on the battlefield instead
    must still be refused."""
    from magic_cards_model.machines import Step

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nahiri, the Unforgiving"],
            battlefield=["Mountain", "Mountain", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")
    nahiri = scenario.cast_and_resolve("Nahiri, the Unforgiving", *lands)
    bears = scenario.creature("Grizzly Bears", "alice")

    reason = _requirement().rejects(bears, "alice", scenario.game, nahiri.id)
    assert reason is not None

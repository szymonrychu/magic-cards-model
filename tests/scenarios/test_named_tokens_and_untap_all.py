"""Two token-creation templates: CR 111.9's named token, printed name-first
("create `<Name>`, a[n] `<descriptor>` token") rather than with a trailing
"named `<Name>`", and "untap all `<group>` you control" as a board-wide
selector alongside the pre-existing single-target untap clause.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 111.9** - "Some effects ... instruct a player to create a token that
  has the same name as ... a legendary character from the game's fiction ...
  Uncommonly, an effect will state a token's name directly."
- **CR 205.4a** - the legendary supertype, settable by the creating effect
  the same as any other characteristic (CR 111.3).
- **CR 701.29** - to untap a permanent.
- **CR 613.5** - continuous effects apply to computed characteristics, not
  the printed ones, so "tokens you control" is read off the live board.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_jiang_yanggu_creates_the_named_legendary_dog_token() -> None:
    """ "When Jiang Yanggu, Never Alone enters, create Mowu, a legendary 3/3
    green Dog creature token." - CR 111.9's name-first shape, with no "with
    <tail>" at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Jiang Yanggu, Never Alone"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Jiang Yanggu, Never Alone",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
    )
    scenario.resolve_top()  # the enters trigger

    mowu = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Mowu"
    ]
    assert len(mowu) == 1
    assert scenario.game.characteristics_of(mowu[0]).power_toughness == (3, 3)
    assert "Legendary" in [supertype.value.title() for supertype in mowu[0].card.supertypes]


def test_minsc_off_set_reads_the_same_name_first_shape_with_a_keyword_tail() -> None:
    """Minsc, Beloved Ranger (not in this pool, not the reported card): "When
    Minsc enters, create Boo, a legendary 1/1 red Hamster creature token with
    trample and haste." - the same name-first grammar, this time with a
    bare "and"-joined two-keyword tail (`_parse_whole_text_token_clause`'s
    own bare-"and" sidestep, extended this session to also try the
    name-first reader, not only the trailing-"named" one).
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Minsc, Beloved Ranger"], battlefield=["Mountain", "Forest", "Plains"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Minsc, Beloved Ranger", *scenario.untapped_sources("Mountain", "Forest", "Plains")
    )
    scenario.resolve_top()  # the enters trigger

    boo = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Boo"
    ]
    assert len(boo) == 1
    assert scenario.game.characteristics_of(boo[0]).power_toughness == (1, 1)
    assert "Trample" in boo[0].card.keywords
    assert "Haste" in boo[0].card.keywords


def test_jiang_yanggu_untaps_all_tokens_you_control_at_end_step() -> None:
    """ "At the beginning of your end step, untap all tokens you control." -
    a nontoken creature stays tapped; every token, whichever card made it,
    untaps.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Jiang Yanggu, Never Alone"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Jiang Yanggu, Never Alone",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
    )
    scenario.resolve_top()  # the enters trigger
    mowu = next(
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Mowu"
    )
    bears.tap()
    mowu.tap()

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.resolve_top()  # the end-step "untap all tokens" trigger

    assert bears.tapped, "Grizzly Bears is not a token - it stays tapped"
    assert not mowu.tapped, "Mowu is a token - it untaps"


def test_reset_off_set_untaps_all_lands_you_control() -> None:
    """Reset (not in this pool, not the reported card): "Cast this spell only
    during an opponent's turn after their upkeep step. Untap all lands you
    control." - the same "untap all `<group>` you control" grammar, with a
    land-type group instead of "tokens", and a leading CR 601.3b timing
    restriction that has to be stripped from the effect text before it (a
    restriction is not a CR 608.2c resolution instruction) rather than
    poisoning the real one after it, `_CAST_TIMING_RESTRICTION_RE`'s own
    fix this session.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Reset"], battlefield=["Island", "Island", "Forest", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, other_island, forest, mountain = scenario.untapped_sources(
        "Island", "Island", "Forest", "Mountain"
    )
    forest.tap()
    mountain.tap()

    scenario.cast_and_resolve("Reset", island, other_island)

    assert not forest.tapped
    assert not mountain.tapped

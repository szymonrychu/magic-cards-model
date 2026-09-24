"""Scenario: blocking restrictions C01-T4 adds or exercises - CR 509.1a's
"can't be blocked [by ...]" and CR 509.1b's "<subject> can't block".

Three shapes, each off a listed HOB card:

- **Duskwatch Hunter**: "This creature can't be blocked by tokens." - a new
  evasion-restriction shape (`combat._CANT_BE_BLOCKED_BY_TOKENS_RE`), read
  off the blocker's own token-ness (CR 111.1, `models.token.is_token`) the
  same layer-aware way `evasion_restriction_refusal` already reads every
  other "can't be blocked ..." sentence. No other legal printing, real or in
  this session's Scryfall snapshot, carries this exact phrase (checked both
  against `oracle-cards.jsonl` and against a live Scryfall search) - see the
  dated MEMORY.md line.
- **Old Fat Spider**: "This creature can't be blocked by creatures with power
  2 or less." - the pre-existing `_CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE` shape
  (already proven generic by Questing Beast in `test_evasion_restrictions.py`),
  exercised here on its own listed printing.
- **Gollum the Abandoned**: "Gollum can't block." - the pre-existing
  self-block-restriction machinery's name-based self-reference (CR 201.4's
  short-name convention, `combat._self_reference_alternatives`), proven
  generic on a second, differently-worded real printing: Rimrock Knight's
  "This creature can't block." (pronoun form rather than named-self form).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (509.1a, 509.1b, 111.1 already verified and cited by
`machines/combat.py`'s own docstrings, which this file follows).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario


def duel(attacker: str, *blockers: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker])
        .player("bob", battlefield=list(blockers))
    )


# -- Duskwatch Hunter: can't be blocked by tokens ----------------------------


def test_a_token_blocker_is_refused():
    scenario = duel("Duskwatch Hunter").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hunter = scenario.creature("Duskwatch Hunter")
    scenario.attack_with(hunter)

    (token,) = create_tokens(
        scenario.game,
        TokenDefinition(power=2, toughness=2, subtypes=("Bear",)),
        "bob",
    )

    assert not scenario.game.can_block(token, hunter)
    assert "token" in (scenario.game.why_cannot_block(token, hunter) or "").lower()


def test_a_nontoken_blocker_of_equal_power_is_permitted():
    """A plain, non-token Grizzly Bears of the identical power/toughness as
    the token above is not refused - the restriction is about token-ness (CR
    111.1), not about size."""
    scenario = duel("Duskwatch Hunter", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hunter = scenario.creature("Duskwatch Hunter")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(hunter)

    assert scenario.game.can_block(bears, hunter)
    scenario.block(hunter, bears)
    assert scenario.game.is_blocked(hunter)


def test_no_evasion_notice_is_recorded_for_the_read_shape():
    """This shape is read, not merely recognised - `looks_like_unparsed_
    evasion_restriction` must not also flag it, or a legitimate refusal would
    carry a spurious "this engine could not read the rest" notice beside it."""
    scenario = duel("Duskwatch Hunter").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hunter = scenario.creature("Duskwatch Hunter")
    scenario.attack_with(hunter)
    (token,) = create_tokens(
        scenario.game,
        TokenDefinition(power=2, toughness=2, subtypes=("Bear",)),
        "bob",
    )

    scenario.game.can_block(token, hunter)

    assert scenario.game.evasion_notices == []


# -- Old Fat Spider: can't be blocked by creatures with power 2 or less -----


def test_a_low_power_blocker_is_refused_on_old_fat_spider():
    scenario = duel("Old Fat Spider", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    spider = scenario.creature("Old Fat Spider")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(spider)

    assert not scenario.game.can_block(bears, spider)


def test_a_higher_power_blocker_is_permitted_on_old_fat_spider():
    scenario = duel("Old Fat Spider", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    spider = scenario.creature("Old Fat Spider")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(spider)

    assert scenario.game.can_block(wurm, spider)
    scenario.block(spider, wurm)
    assert scenario.game.is_blocked(spider)


# -- Gollum the Abandoned: "Gollum can't block." -----------------------------


def test_gollum_himself_cannot_block():
    scenario = duel("Wurmcoil Engine", "Gollum the Abandoned").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wurm = scenario.creature("Wurmcoil Engine")
    gollum = scenario.creature("Gollum the Abandoned", "bob")
    scenario.attack_with(wurm)

    assert not scenario.game.can_block(gollum, wurm)


def test_rimrock_knight_cannot_block_either_a_second_real_printing():
    """Rimrock Knight // Boulder Rush's front face prints the same
    restriction with the pronoun wording ("This creature can't block.")
    instead of Gollum's own short-name wording ("Gollum can't block.") - the
    same CR 509.1b machinery reading two differently worded printings."""
    scenario = duel("Wurmcoil Engine", "Rimrock Knight").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wurm = scenario.creature("Wurmcoil Engine")
    knight = scenario.creature("Rimrock Knight", "bob")
    scenario.attack_with(wurm)

    assert not scenario.game.can_block(knight, wurm)


def test_gollum_can_still_be_blocked_normally_when_he_attacks():
    """The restriction is one-directional (CR 509.1b is about *this creature*
    blocking, not about blocking *it*) - Gollum attacking is refused by
    nothing here."""
    scenario = duel("Gollum the Abandoned", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    gollum = scenario.creature("Gollum the Abandoned")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(gollum)

    assert scenario.game.can_block(wurm, gollum)
    scenario.block(gollum, wurm)
    assert scenario.game.is_blocked(gollum)
    assert scenario.game.evasion_notices == []

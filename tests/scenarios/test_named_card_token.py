"""Mutable Explorer: "When this creature enters, create a tapped Mutavault
token. (It's a land with "{T}: Add {C}" and "{1}: This token becomes a 2/2
creature with all creature types until end of turn. It's still a land.")"

CR 111.4: "A spell or ability that creates a token sets both its name and
its subtype(s)." Here the whole definition - land type, both activated
abilities, word for word - comes from the ability's own reminder text
rather than from any bare descriptor ("2/2 black Zombie creature") this
file's other token readers already parse. The read is entirely structural:
any capitalized name, any one of CR 205.2a's three permanent types that
print reminder-defined tokens this way (land/artifact/creature), any number
of quoted abilities - never "Mutavault" by name, which `CLAUDE.md` bans as a
card-name-to-characteristics row.

Two things had to change together:

1. **The reader itself** (`_parse_create_named_permanent_token_clause`) -
   new, since nothing previously built a `TokenDefinition` from a
   parenthetical's own quoted abilities.
2. **The reminder text had to survive to reach it.** Every other trigger's
   own CR 207.2a reminder is dropped before an effect is ever dispatched
   (it only restates a rule read elsewhere, so keeping it would be pure
   noise to every other reader in this file) - here it is the token's own
   data, so `effect_text_with_named_token_reminder` puts it back for this
   one shape, in both the real resolution path (`Game._etb_x_effect_text`)
   and the static sweep (`support.py`), which call `trigger_effect_for`
   from two different places with two different notions of "the effect
   text" and would otherwise silently disagree about what this ability even
   says.

**No second Modern/Pioneer/Standard-legal printing carries this exact
"create a token named for a nontoken permanent, its whole definition given
in reminder text" idiom** - a Scryfall full-text search this session ran for
"token. (It's a" and for Mutavault's own printed activation line (both
verbatim substrings any second printing sharing the *shape* would have to
contain) returned only Mutable Explorer and the real, separate Mutavault
land itself. Recorded as a dated line in `MEMORY.md` rather than silently
asserting a generality this session could not find a second printing to
demonstrate; the reader's own genericity (no name, type word, or ability
count is hardcoded) is argued in the docstrings above instead.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 111.4** - a token's name and subtype(s) come from the effect that
  creates it.
- **CR 111.2** - the creating player is the token's owner and controller.
- **CR 205.2a / CR 110.4a** - land is one of the seven card types.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

MUTABLE_EXPLORER = "Mutable Explorer"


def test_mutable_explorer_is_fully_handled():
    bad = [c for c in card_support(card(MUTABLE_EXPLORER)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_mutable_explorer_creates_a_tapped_mutavault_token():
    scenario = (
        Scenario()
        .player("alice", hand=[MUTABLE_EXPLORER], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve(MUTABLE_EXPLORER, *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    token = scenario.find("Mutavault", Zone.BATTLEFIELD, "alice")
    assert token.token, "CR 111: a created token, not a printed Mutavault card"
    assert token.types == (Type.LAND,)
    assert token.tapped, "the printed 'tapped' rider"
    assert token.power is None and token.toughness is None, (
        "no power/toughness until its own granted ability makes it a creature"
    )
    assert token.owner == "alice" and token.controller == "alice"

    lines = list(parse_abilities(token.card))
    activated_texts = {line.text for line in lines if line.kind.value == "activated"}
    assert "{T}: Add {C}" in activated_texts
    assert any(
        text.startswith("{1}: This token becomes a 2/2 creature") for text in activated_texts
    ), "both quoted abilities from the reminder text, parsed as real activated abilities"


def test_mutable_explorers_own_token_can_tap_for_colorless_mana():
    """The reminder-derived ability is a genuine, activatable mana ability -
    not just text that happens to sit in `oracle_text`."""
    scenario = (
        Scenario()
        .player("alice", hand=[MUTABLE_EXPLORER], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve(MUTABLE_EXPLORER, *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    token = scenario.find("Mutavault", Zone.BATTLEFIELD, "alice")
    token.tapped = False  # it entered tapped; untap it to prove the ability itself

    scenario.activate(token, index=0)

    alice = scenario.player("alice")
    assert token.tapped, "the ability's own {T} cost"
    assert alice.mana_pool.floating.get(Color.COLORLESS, 0) >= 1, "{T}: Add {C} actually adds mana"

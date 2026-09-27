"""Scenario: "Activate only if this creature is blocked" (CR 602.5b, CR
509.1h) - Cinder Crawler's own activation restriction, read off `Game.
is_blocked` (already CR 509.1h-correct: "A creature remains blocked even if
all the creatures blocking it are removed from combat") through a new
"blocked"/"unblocked" pair on `machines/conditions/objects.py`'s existing
"<subject> is <state>" reader, next to "attacking"/"blocking" rather than
hardcoded to Cinder Crawler's own sentence.

Verified with `mise run rules:find` in this session:

- **CR 509.1h**: "An attacking creature with one or more creatures declared
  as blockers for it becomes a blocked creature; one with no creatures
  declared as blockers for it becomes an unblocked creature. This remains
  unchanged until the creature is removed from combat, an effect says that
  it becomes blocked or unblocked, or the combat phase ends ... A creature
  remains blocked even if all the creatures blocking it are removed from
  combat."
- **CR 602.5b**: the activation restriction rule.

Oracle text pulled with `scripts/add_card.py`:

- **Cinder Crawler** (the reported card): "{R}: This creature gets +1/+0
  until end of turn. Activate only if this creature is blocked."
- **Cunning Giant** (the second printing of the template, the opposite
  polarity and a different rules path - a damage-assignment replacement
  rather than an activation restriction): "If this creature is unblocked,
  you may have it assign its combat damage to a creature defending player
  controls." Neither Cinder Crawler nor Cunning Giant is Modern/Pioneer/
  Standard legal, and an exhaustive Scryfall search (`o:"is blocked"`,
  `o:"is unblocked"`, `o:"isn't blocked"`, each combined with `legal:modern`/
  `legal:pioneer`/`legal:standard`) turns up no third printing of this
  present-tense CR 509.1h state check on any legal card at all - only
  "isn't blocked" as an *event qualifier* on the ATTACKS trigger itself
  (Master of Cruelties' "attacks and isn't blocked"), a different code path
  (`machines/triggers.py`'s own event-qualifier reading) this file does not
  touch. Genericity is instead demonstrated by both polarities of the same
  new state word reading correctly off the identical combat state
  (`test_the_state_word_reads_both_polarities_off_one_combat` below).
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_cinder_crawler_cannot_pump_before_blockers_are_declared():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cinder Crawler", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crawler = scenario.creature("Cinder Crawler", "alice")
    scenario.attack_with(crawler)

    assert scenario.why_cannot_activate(crawler, index=0) is not None


def test_cinder_crawler_activates_once_blocked():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cinder Crawler", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crawler = scenario.creature("Cinder Crawler", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(crawler)
    scenario.block(crawler, bears)

    assert scenario.why_cannot_activate(crawler, index=0) is None


def test_cinder_crawler_stays_blocked_after_its_blocker_leaves_combat():
    """CR 509.1h: removed from combat, not un-blocked."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cinder Crawler", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crawler = scenario.creature("Cinder Crawler", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(crawler)
    scenario.block(crawler, bears)
    scenario.game.destroy(bears)

    assert scenario.why_cannot_activate(crawler, index=0) is None


def test_cinder_crawler_unblocked_attacker_cannot_activate():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cinder Crawler", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crawler = scenario.creature("Cinder Crawler", "alice")
    scenario.attack_with(crawler)
    scenario.no_blocks()

    assert scenario.why_cannot_activate(crawler, index=0) is not None


def test_the_state_word_reads_both_polarities_off_one_combat():
    """The same new "blocked"/"unblocked" state word, off the identical
    combat: Cunning Giant unblocked, Cinder Crawler blocked."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cinder Crawler", "Cunning Giant", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crawler = scenario.creature("Cinder Crawler", "alice")
    giant = scenario.creature("Cunning Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(crawler, giant)
    scenario.block(crawler, bears)

    assert scenario.game.condition_holds("alice", "this creature is blocked", source=crawler)
    assert scenario.game.condition_holds("alice", "this creature is unblocked", source=giant)
    assert not scenario.game.condition_holds("alice", "this creature is blocked", source=giant)
    assert not scenario.game.condition_holds("alice", "this creature is unblocked", source=crawler)

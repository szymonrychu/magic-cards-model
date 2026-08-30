"""Scenario: `"you may <clause>."` inside the wave-1/wave-2 effect parsers.

`machines/effects.py`'s `parse_player_effect` (untargeted player clauses:
gain/lose life, energy, draw, mill, surveil, scry) and `parse_targeted_effect`
(destroy/exile/return/tap/untap/counters/damage-target) used to refuse any
clause containing "you may" outright - a card with no table row and only an
optional clause resolved and did nothing. This file is the sweep that unlocks
"You may <clause>.", wrapping it in a `Game.may` question (CR 608.2d) around
whichever clause the parser already understands.

A survey of `tests/fixtures/cards/` and the wider card pool (via
`card_search(oracle_text=...)`) turned up 110 "you may" sentences and 13 "if
you do" sentences. Of those, the ones landing on a clause this wave's parsers
already read - a plain life/energy/draw/mill/surveil/scry, or a single
destroy/exile/return/tap/untap/counters/damage-target - are:

- **"You may `<clause>`."** alone: Dragon Appeasement ("you may draw a
  card"), Ajani's Mantra ("you may gain 1 life") for the player-effect wave;
  Batterhorn ("you may destroy target artifact"), Act of Authority ("you may
  exile target artifact or enchantment"), Angler Drake ("you may return
  target creature to its owner's hand"), Alaborn Cavalier ("you may tap
  target creature") for the targeted wave.
- **"You may `<A>`. If you do, `<B>`."**: none. Every real "if you do" chain
  in the pool - Academy Raider, Abandon Attachments, Aegis Sculptor, Sanctum
  of Ugin, Necrodominance, and the rest found by `card_search` - gates the
  second clause behind discarding, sacrificing, paying life, or a
  variable-X action, none of which either parser's clause vocabulary covers.
  Chaining two clauses this wave *can* both read never comes up on a real
  card, so implementing the CR 118.12 "if you do" link would be untested,
  unexercised code - it is deliberately **not** implemented here. Formidable
  Speaker below is the fail-closed proof: its "if you do" continuation is
  unparseable, so the whole ability - "you may" included - is refused.

CR numbers, looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file:

- **CR 608.2d** - "If an effect of a spell or ability offers any choices ...
  the player announces these while applying the effect. The player can't
  choose an option that's illegal or impossible" - `Game.may` is this
  question, already exercised end to end in
  `test_decisions_during_resolution.py`.
- **CR 603.5** - "Some triggered abilities' effects are optional (they
  contain 'may,' as in 'At the beginning of your upkeep, you may draw a
  card'). These abilities go on the stack when they trigger, regardless..."
  - the search tool truncates the rule here; the untruncated portion is
    enough to confirm an optional trigger still goes on the stack rather
    than being skipped, which is what lets it still ask its question.
- **CR 118.12** - "Some spells, activated abilities, and triggered abilities
  read, '[Do something]. If [a player] [does, doesn't, or can't], [effect].'
  Or '[A player] may [do something]. If [that player] [does...'" - the search
  tool truncates this rule past the point quoted; what survives confirms "if
  you do" is conditioned on whether the described action actually happened,
  which is the CR basis for not executing a chained clause when the "you
  may" it follows was declined - but the exact wording of what "happened"
  covers (e.g. a fizzled or partially-illegal action) could **not** be
  verified from the truncated excerpt, which is one more reason the shape is
  left unimplemented rather than guessed at.

`machines/decisions.default_answer` already answers `MAY` with "take it"
whenever it is legal (CR 608.2d's only illegal branch is `PAY_LIFE`'s, which
`MAY` does not have), and that default is unchanged by this file - it is the
reason Dragon Appeasement, Ajani's Mantra, Batterhorn, Act of Authority,
Angler Drake, and Alaborn Cavalier all take their option with nobody
scripting an answer, below.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

# --------------------------------------------------------------------------
# Player-effect wave: "you may <gain/lose life, energy, draw, mill, surveil,
# scry>." (`parse_player_effect` / `parse_player_effect_for_spell`)
# --------------------------------------------------------------------------


def test_taking_the_may_draws_a_card_dragon_appeasement():
    """ "Whenever you sacrifice a creature, you may draw a card." Taken."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dragon Appeasement", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(True, source="Dragon Appeasement")

    scenario.game.sacrifice(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert [state.name for state in alice.hand] == ["Forest"]


def test_declining_the_may_draws_nothing_dragon_appeasement():
    """The same trigger, declined - on the same card, so accepting and
    declining cannot look alike by accident.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dragon Appeasement", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(False, source="Dragon Appeasement")

    scenario.game.sacrifice(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert alice.hand == []
    assert {state.name for state in alice.library} == {"Forest"}


def test_dragon_appeasement_defaults_to_taking_it_unscripted():
    """No answer queued: `default_answer` takes `MAY`'s affirmative branch,
    which is new behaviour for this card - before this file it had no
    registry entry and its trigger resolved doing nothing at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dragon Appeasement", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.sacrifice(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert [state.name for state in alice.hand] == ["Forest"]


def test_taking_the_may_gains_life_ajanis_mantra():
    """ "At the beginning of your upkeep, you may gain 1 life." A second real
    card on the same "You may `<clause>`." shape, proving the fix is on the
    shape and not on Dragon Appeasement specifically.
    """
    scenario = Scenario().player("alice", life=20, battlefield=["Ajani's Mantra"]).build()
    scenario.will_take_the_may(True, source="Ajani's Mantra")

    # `start_at` jumps the bare turn pointer and skips beginning-of-step
    # triggers on the way (see `Game.advance_to`'s docstring); `advance()`
    # is the one that emits "the beginning of your upkeep" and puts what it
    # triggers on the stack, so it is what a scenario about an upkeep
    # trigger has to call instead.
    scenario.game.untap_step()
    scenario.advance()  # untap -> upkeep
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_declining_the_may_leaves_life_untouched_ajanis_mantra():
    scenario = Scenario().player("alice", life=20, battlefield=["Ajani's Mantra"]).build()
    scenario.will_take_the_may(False, source="Ajani's Mantra")

    # `start_at` jumps the bare turn pointer and skips beginning-of-step
    # triggers on the way (see `Game.advance_to`'s docstring); `advance()`
    # is the one that emits "the beginning of your upkeep" and puts what it
    # triggers on the stack, so it is what a scenario about an upkeep
    # trigger has to call instead.
    scenario.game.untap_step()
    scenario.advance()  # untap -> upkeep
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# Targeted wave: "you may <destroy/exile/return/tap target X>."
# (`parse_targeted_effect` / `parse_targeted_effect_for_spell`)
# --------------------------------------------------------------------------


def test_taking_the_may_destroys_the_target_batterhorn():
    """ "When this creature enters, you may destroy target artifact." Taken."""
    scenario = (
        Scenario()
        .player("alice", hand=["Batterhorn"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Sol Ring", "bob")
    scenario.choose_trigger_targets("Batterhorn", [ring])
    scenario.will_take_the_may(True, source="Batterhorn")

    scenario.cast_and_resolve("Batterhorn", *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.pass_until_resolved()

    assert ring.zone is Zone.GRAVEYARD


def test_declining_the_may_leaves_the_target_alone_batterhorn():
    """The same card, declined - Sol Ring survives untouched."""
    scenario = (
        Scenario()
        .player("alice", hand=["Batterhorn"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Sol Ring", "bob")
    scenario.choose_trigger_targets("Batterhorn", [ring])
    scenario.will_take_the_may(False, source="Batterhorn")

    scenario.cast_and_resolve("Batterhorn", *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.pass_until_resolved()

    assert ring.zone is Zone.BATTLEFIELD


def test_batterhorn_defaults_to_taking_it_unscripted():
    scenario = (
        Scenario()
        .player("alice", hand=["Batterhorn"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Sol Ring", "bob")
    scenario.choose_trigger_targets("Batterhorn", [ring])

    scenario.cast_and_resolve("Batterhorn", *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.pass_until_resolved()

    assert ring.zone is Zone.GRAVEYARD


def test_taking_the_may_exiles_the_target_act_of_authority():
    """ "When this enchantment enters, you may exile target artifact or
    enchantment." A second real card on the targeted "You may `<clause>`."
    shape, this time exile rather than destroy.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Act of Authority"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Sol Ring", "bob")
    scenario.choose_trigger_targets("Act of Authority", [ring])
    scenario.will_take_the_may(True, source="Act of Authority")

    scenario.cast_and_resolve(
        "Act of Authority", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    scenario.pass_until_resolved()

    assert ring.zone is Zone.EXILE


def test_declining_the_may_leaves_the_target_alone_act_of_authority():
    scenario = (
        Scenario()
        .player("alice", hand=["Act of Authority"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Sol Ring", "bob")
    scenario.choose_trigger_targets("Act of Authority", [ring])
    scenario.will_take_the_may(False, source="Act of Authority")

    scenario.cast_and_resolve(
        "Act of Authority", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    scenario.pass_until_resolved()

    assert ring.zone is Zone.BATTLEFIELD


def test_taking_the_may_returns_the_target_angler_drake():
    """ "When this creature enters, you may return target creature to its
    owner's hand." A third real card, this time "return".
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Angler Drake"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.choose_trigger_targets("Angler Drake", [mystic])
    scenario.will_take_the_may(True, source="Angler Drake")

    scenario.cast_and_resolve("Angler Drake", *scenario.untapped_sources(*["Island"] * 6))
    scenario.pass_until_resolved()

    assert mystic.zone is Zone.HAND


def test_declining_the_may_leaves_the_target_alone_angler_drake():
    scenario = (
        Scenario()
        .player("alice", hand=["Angler Drake"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.choose_trigger_targets("Angler Drake", [mystic])
    scenario.will_take_the_may(False, source="Angler Drake")

    scenario.cast_and_resolve("Angler Drake", *scenario.untapped_sources(*["Island"] * 6))
    scenario.pass_until_resolved()

    assert mystic.zone is Zone.BATTLEFIELD


def test_taking_the_may_taps_the_target_alaborn_cavalier():
    """ "Whenever this creature attacks, you may tap target creature." A
    fourth real card, and the only one whose trigger is CR 508.3c's
    `ATTACKS` rather than `ENTERS_THE_BATTLEFIELD`.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Alaborn Cavalier"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    # A first turn: `Game.begin_turn_for` clears summoning sickness for
    # every permanent alice already controls once her turn begins, so the
    # Cavalier can attack with no separate haste-adjacent staging.
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cavalier = scenario.creature("Alaborn Cavalier", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.choose_trigger_targets("Alaborn Cavalier", [mystic])
    scenario.will_take_the_may(True, source="Alaborn Cavalier")

    scenario.attack_with(cavalier)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert mystic.tapped


def test_declining_the_may_leaves_the_target_untapped_alaborn_cavalier():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Alaborn Cavalier"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cavalier = scenario.creature("Alaborn Cavalier", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.choose_trigger_targets("Alaborn Cavalier", [mystic])
    scenario.will_take_the_may(False, source="Alaborn Cavalier")

    scenario.attack_with(cavalier)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not mystic.tapped


# --------------------------------------------------------------------------
# Fail-closed: an optional clause wrapping something this wave cannot read
# --------------------------------------------------------------------------


def test_an_unparseable_you_may_asks_nothing_and_does_nothing():
    """Formidable Speaker: "you may discard a card. If you do, search your
    library for a creature card, reveal it, put it into your hand, then
    shuffle." Discarding is not in this wave's clause vocabulary, so
    `parse_clause_effect` refuses the inner clause, `_parse_optional_player_clause`
    refuses the "you may" wrapper around it, and `_parse_player_clauses`
    throws away the whole ability - the second sentence ("if you do") never
    even gets a chance to matter, because nothing is ever asked.

    Fail-closed, not "ask and then ignore the answer": `questions_asked()` is
    empty, proving no `Game.may` question reached the player at all.
    """
    scenario = (
        Scenario().player("alice", hand=["Formidable Speaker"], battlefield=["Forest"] * 3).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    before = [state.name for state in alice.hand if state.name != "Formidable Speaker"]

    scenario.cast_and_resolve("Formidable Speaker", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert [state.name for state in alice.hand] == before
    assert [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY] == []

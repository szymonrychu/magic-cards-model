"""Cast-from-hand exile-and-free-cast: Knowledge Pool and Possibility Storm.

Card text, confirmed with `resolve_cards` in the session that wrote this file:

Knowledge Pool ({6} Artifact, Modern legal):
    Imprint - When this artifact enters, each player exiles the top three
    cards of their library.
    Whenever a player casts a spell from their hand, that player exiles it.
    If the player does, they may cast a spell from among other cards exiled
    with this artifact without paying its mana cost.

Possibility Storm ({3}{R}{R} Enchantment, Modern legal):
    Whenever a player casts a spell from their hand, that player exiles it,
    then exiles cards from the top of their library until they exile a card
    that shares a card type with it. That player may cast that card without
    paying its mana cost. Then they put all cards exiled with this
    enchantment on the bottom of their library in a random order.

Three defects, fixed together because the third makes the first two unsafe to
ship on their own:

- **Ability 2 was unparsed** (`machines/effects.py`'s `_parse_cast_from_hand_
  then_exile_clause`, dispatched from `_ability_effect_or_notice` against the
  whole, unsplit effect text - `_prepare_effect_clauses` would otherwise cut
  Knowledge Pool's "If the player does" away from what it is anaphora for,
  CR 118.12). The trigger used to resolve and do nothing: no exile, no
  `Notice`, the cast spell stayed on the stack forever.
- **The ETB never linked the exiled cards to the permanent** (CR 607.2a).
  `_merge_each_player_clauses`'s own closure in `machines/effects.py` now
  annotates whatever a step moves into the shared exile zone, so ability 2's
  pool is never empty just because ability 1 filled it.
- **`TriggerEvent.CAST_SPELL` ignored the card's origin zone.** Without
  `GameEvent.origin_zone` (`machines/triggers.py`), "casts a spell from their
  hand" matched a cast from anywhere, including the free cast from exile
  ability 2 itself grants - which reads as an infinite loop the instant
  ability 1's defect above is fixed: the free cast is itself a cast, would
  re-trigger the Pool, get exiled, and free-cast again forever.

Every CR number here was looked up with `knowledge_search(q="...", type=
"rules")` and, where truncated, `mise run rules:find <n>`, in the session
that wrote this file:

- **CR 601.2a** - a spell "remains there until it resolves, it's countered,
  or a rule or effect moves it elsewhere" - exiling it is that third thing.
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence."
- **CR 701.6a** - "To counter a spell or ability means to cancel it, removing
  it from the stack ... A countered spell is put into its owner's graveyard."
  A different verb from exiling, which is why a spell that says nothing about
  countering is exiled all the same.
- **CR 113.6g** - "An object's ability that states it can't be countered ...
  functions on the stack" - only against CR 701.6a's own verb.
- **CR 118.12** - "[Do something]. If [a player] [does, doesn't, or can't],
  [effect]." "The 'If [a player] [does ...]' clause checks whether the
  player chose to pay an optional cost or started to pay a mandatory cost" -
  read here as "was the mandatory exile actually performed", which is false
  when the spell was already gone (a second Knowledge Pool's own trigger, or
  a counterspell resolving first).
- **CR 603.4** - the intervening *if* only applies when "if [condition]"
  immediately follows the trigger event; Knowledge Pool's "If the player
  does" sits well into the effect, which is why `parse_abilities` already
  reads `intervening_if=None` for it and CR 118.12 is the rule that actually
  governs it.
- **CR 608.2g** - "If an effect specifically instructs or allows a player to
  cast a spell during resolution, they do so ... except no player receives
  priority after it's cast." No timing check is named, so a sorcery-speed
  spell may be free-cast on the opponent's turn.
- **CR 117.2e** - "no player has priority while a spell or ability is
  resolving," confirming there is no window for anyone to object to CR
  608.2g's cast.
- **CR 118.9 / 118.9a / 118.9d** - the alternative-cost family: "without
  paying its mana cost" is CR 118.9's alternative cost, one per spell
  (118.9a), with any additional costs or increases still applied (118.9d;
  moot here - nothing in the pool adds one to these candidates).
- **CR 607.2a / 607.1c / 607.3** - the linked-ability family: an object that
  exiles cards and later refers to "cards exiled with [this object]" links
  the two (607.2a); an ability is linked to itself when it fulfills both
  halves (607.1c - ability 2 exiles *and* reads "other cards exiled with
  this artifact"); and the plural CR 607.3 names is `Game.cards_imprinted_
  on`.
- **CR 406.3 / 406.3a** - exile is face-up by default, and this ability names
  no other visibility, so everything it exiles is public.
- **CR 608.2d / 101.3** - a resolving effect's choices are announced while
  applying it, and an impossible option can't be chosen - an empty pool makes
  "yes" illegal, not merely a bad idea.
- **CR 302.1** - a creature is normally castable only "during a main phase of
  [the caster's] turn when the stack is empty" - the timing check CR 608.2g
  says nothing here bypasses.
- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers" - read for
  `_origin_zone_matches`'s "no restriction matches anything" default.

Fixtures used: `knowledge_pool`, `possibility_storm` (both added this
session - neither existed in the pool before), `lightning_bolt`, `mountain`,
`llanowar_elves`, `grizzly_bears`, `giant_growth`, `forest`, `island`,
`swamp`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.triggers import _required_cast_origin_zone
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker

from .harness import PlayedScenario, Scenario

# --------------------------------------------------------------------------
# Board builders
# --------------------------------------------------------------------------


def cast_knowledge_pool(
    scenario: PlayedScenario, controller: str = "alice", *, lands: str = "Forest"
):
    """Cast Knowledge Pool for real (so its ETB actually fires) and resolve
    both the spell and the ETB trigger. Returns the permanent.

    `battlefield=["Knowledge Pool"]` staging (`docs/scenario-tests.md`) skips
    `Game.enter_the_battlefield` entirely, so it never fires an ETB at all -
    the ETB-linking regression this file exists to catch needs a real cast.

    Pays with Forests by default - Knowledge Pool's `{6}` is generic, so any
    color works, and reserving Forest for its payment keeps `board()`'s six
    base lands out of the way of whatever colored mana a test's *other*
    spell needs afterward.
    """
    sources = scenario.untapped_sources(*([lands] * 6), username=controller)
    scenario.cast_and_resolve("Knowledge Pool", *sources, username=controller)
    scenario.resolve_top()  # the ETB: each player exiles their top three
    return scenario.find("Knowledge Pool", Zone.BATTLEFIELD, controller)


def board(
    *,
    alice_hand=(),
    alice_library=(),
    alice_battlefield=(),
    alice_exile=(),
    bob_hand=(),
    bob_library=(),
    bob_battlefield=(),
) -> PlayedScenario:
    """Alice always has six Forests to cast Knowledge Pool with, plus
    whatever a test adds on top for its own spells."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Knowledge Pool", *alice_hand],
            library=list(alice_library),
            battlefield=["Forest"] * 6 + list(alice_battlefield),
            exile=list(alice_exile),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            library=list(bob_library),
            battlefield=list(bob_battlefield),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# --------------------------------------------------------------------------
# 1. The ETB actually links what it exiles (CR 607.2a, 406.6) - defect 2
# --------------------------------------------------------------------------


def test_the_etb_exiles_three_from_each_library_linked_to_the_pool():
    scenario = board(
        alice_library=["Forest", "Island", "Swamp", "Mountain"],
        bob_library=["Forest", "Island", "Swamp", "Mountain"],
    )
    pool = cast_knowledge_pool(scenario)

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert [state.name for state in alice.library] == ["Mountain"]
    assert [state.name for state in bob.library] == ["Mountain"]

    assert len(scenario.game.exile) == 6, "three from each of two players' libraries"
    for state in scenario.game.exile:
        annotation = state.exile_annotation
        assert annotation is not None
        assert annotation.marker is ExileMarker.IMPRINTED
        assert annotation.linked_permanent_id == pool.id
        assert state.face_up, "CR 406.3: exiled face up by default"


# --------------------------------------------------------------------------
# 2, 3, 4. Casting from hand exiles the spell off the stack (CR 601.2a),
# not countered (CR 701.6a vs 113.6g), no targets or cast record (CR 400.7)
# --------------------------------------------------------------------------


def test_casting_from_hand_exiles_the_spell_off_the_stack_unresolved():
    scenario = board(alice_hand=["Lightning Bolt"], alice_battlefield=["Mountain"])
    cast_knowledge_pool(scenario)
    bob = scenario.player("bob")
    life_before = bob.life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.will_take_the_may(False, times=None)  # decline every free cast in this test
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # ability 2

    assert bolt.zone is Zone.EXILE, "CR 601.2a: exiled, never resolved"
    assert bolt not in scenario.game.stack
    assert bob.life == life_before, "the Bolt never dealt its damage"


def test_a_cant_be_countered_spell_is_exiled_all_the_same():
    """Abrupt Decay: "This spell can't be countered." CR 113.6g's own
    restriction functions only against CR 701.6a's counter verb - exiling is
    a different verb, so this is exiled regardless.

    This is also the decisive regression test against the tempting wrong
    implementation, `Game.counter(spell, to_exile=True)`: that method's
    `cannot_be_countered` guard sits *above* the `to_exile` branch, so it
    would refuse to move Abrupt Decay at all, leaving it sitting on the
    stack (see this method's own docstring).
    """
    scenario = board(
        alice_hand=["Abrupt Decay"],
        alice_battlefield=["Llanowar Elves", "Swamp", "Forest"],
    )
    cast_knowledge_pool(scenario)
    scenario.will_take_the_may(False, times=None)

    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    decay = scenario.cast_onto_stack(
        "Abrupt Decay",
        *scenario.untapped_sources("Swamp", "Forest", username="alice"),
        username="alice",
        targets=[elves],
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # ability 2

    assert decay.zone is Zone.EXILE, "a spell that can't be countered is exiled all the same"
    assert elves.zone is Zone.BATTLEFIELD, "Abrupt Decay never resolved, so the Elves survive"


def test_the_exiled_spell_keeps_no_targets_and_no_cast_record():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Llanowar Elves", "Mountain"],
    )
    cast_knowledge_pool(scenario)
    scenario.will_take_the_may(False, times=None)

    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[elves])
    assert bolt.targets, "sanity: the Bolt really was announced at a target"
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert bolt.targets == [], "CR 400.7: a new object, no targets"
    assert scenario.game.cast_records.get(bolt.id) is None, "CR 400.7: no cast record either"


# --------------------------------------------------------------------------
# 5, 6. The free cast: only the other linked cards, and no mana cost
# --------------------------------------------------------------------------


def test_the_free_cast_offers_only_the_other_linked_cards_never_the_just_exiled_spell():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_library=[],
    )
    cast_knowledge_pool(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()

    scenario.will_take_the_may(True, source="Knowledge Pool")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    scenario.will_choose_cards(bears, username="alice", source="Knowledge Pool")
    scenario.resolve_top()  # ability 2

    (may,) = [
        q
        for q in scenario.questions_asked()
        if q.source == "Knowledge Pool" and q.kind is DecisionKind.MAY
    ]
    assert bolt.id not in may.cards, "the spell this trigger just exiled is not 'other'"
    assert bears.id in may.cards
    assert bears.zone is Zone.STACK, "the free cast actually happened"


def test_the_free_cast_pays_no_mana_cost_and_the_caster_stays_tapped_out():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],  # exactly enough for the Bolt, on top of KP's six
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_library=[],
    )
    cast_knowledge_pool(scenario)  # spends all six Forests

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    remaining_untapped = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.untapped and state.card.is_land
    ]
    assert remaining_untapped == [], "alice is tapped out after paying for the Bolt alone"

    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, source="Knowledge Pool")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    scenario.will_choose_cards(bears, username="alice", source="Knowledge Pool")
    scenario.resolve_top()  # ability 2
    scenario.resolve_top()  # Grizzly Bears itself

    creature = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert creature.zone is Zone.BATTLEFIELD, "CR 118.9: cast for free, with no mana available"


# --------------------------------------------------------------------------
# 7. The opponent's own cast is exiled by the opponent, who gets the free
# cast - never the Pool's controller (the most valuable test in the file)
# --------------------------------------------------------------------------


def test_the_opponents_cast_is_exiled_by_the_opponent_who_gets_the_free_cast():
    scenario = board(
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Mountain"],
    )
    cast_knowledge_pool(scenario)  # alice's Knowledge Pool, alice's controller
    scenario.pass_priority("alice")  # bob needs priority before he may cast anything

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.game.put_triggers_on_stack()

    scenario.will_take_the_may(True, source="Knowledge Pool", username="bob")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    scenario.will_choose_cards(bears, username="bob", source="Knowledge Pool")
    scenario.resolve_top()  # ability 2
    scenario.resolve_top()  # Grizzly Bears itself

    assert bolt.zone is Zone.EXILE, "bob exiled his own cast Bolt"
    creature = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    assert creature.controller == "bob", (
        "the exiler and free-caster is GameEvent.player (whoever cast the spell), "
        "not AbilityOnStack.controller (Knowledge Pool's controller, alice)"
    )


# --------------------------------------------------------------------------
# 8. The free cast does not re-trigger the Pool - defect 3's regression
# --------------------------------------------------------------------------


def test_the_free_cast_does_not_retrigger_the_pool():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_library=[],
    )
    cast_knowledge_pool(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 2, "sanity: trigger above Bolt, nothing else queued yet"

    scenario.will_take_the_may(True, source="Knowledge Pool")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    scenario.will_choose_cards(bears, username="alice", source="Knowledge Pool")
    scenario.resolve_top()  # ability 2: exiles Bolt, frees Grizzly Bears onto the stack

    # If the free cast wrongly re-triggered the Pool, a *second* copy of
    # ability 2 would now be pending or on the stack above the freed Bears.
    assert scenario.game.pending_triggers == []
    assert scenario.stack_names() == ["Grizzly Bears"]
    scenario.resolve_top()  # Grizzly Bears resolves onto the battlefield

    assert scenario.game.pending_triggers == []
    assert scenario.game.stack == []
    bears_permanent = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert bears_permanent.zone is Zone.BATTLEFIELD


def test_a_flashback_cast_from_the_graveyard_does_not_trigger_the_pool_but_a_hand_cast_does():
    """Defect 3's own regression, named directly rather than only exercised
    indirectly by the free-cast test above: Knowledge Pool's condition is
    "casts a spell **from their hand**" (CR 603.2, `GameEvent.origin_zone`).

    Faithless Looting's flashback (CR 702.34a) casts it from the graveyard -
    a real report from this same session found `stack == ['Faithless
    Looting', 'Knowledge Pool']` for exactly this cast, before `GameEvent.
    origin_zone` existed to tell the trigger the difference. A second copy
    cast from hand, right afterward, proves the fix is a *restriction* and
    not simply "never trigger again."
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Knowledge Pool", "Faithless Looting"],
            # The first three are Knowledge Pool's own ETB fodder (CR
            # 607.2a's "each player exiles the top three cards of their
            # library") - the Islands underneath are what the flashback
            # copy's own "draw two, then discard two" actually draws.
            library=["Swamp", "Swamp", "Swamp", "Island", "Island"],
            graveyard=["Faithless Looting"],
            battlefield=["Forest"] * 6 + ["Mountain"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island1, island2 = scenario.player("alice").library[3:5]
    cast_knowledge_pool(scenario)

    flashback_sources = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", username="alice"
    )
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *flashback_sources)
    scenario.put_on_stack(casting)

    assert scenario.game.pending_triggers == [], (
        "a flashback cast from the graveyard is not 'from hand'"
    )
    assert scenario.stack_names() == ["Faithless Looting"]
    scenario.will_discard(island1, island2, username="alice")
    scenario.resolve_top()  # Faithless Looting resolves untouched
    assert [c.name for c in scenario.player("alice").hand] == ["Faithless Looting"], (
        "the hand copy survives the flashback copy's own draw-then-discard"
    )

    (hand_mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.will_take_the_may(False, times=None)
    scenario.cast_onto_stack("Faithless Looting", hand_mountain, username="alice")
    assert scenario.stack_names() == [
        "Faithless Looting",
        "Knowledge Pool's triggered ability",
    ], "the same card, cast from hand this time, does trigger the Pool"


# --------------------------------------------------------------------------
# 9. CR 608.2g: no timing check on a cast made during resolution
# --------------------------------------------------------------------------


def test_a_sorcery_speed_spell_may_be_free_cast_during_the_opponents_turn():
    """Grizzly Bears is a creature - CR 302.1 lets it be cast only during its
    own caster's main phase with an empty stack. Bob free-casts it during
    ALICE's turn, with ability 2 itself on the stack - both violations any
    `PlayPermission`-based fix would refuse (that machinery still checks CR
    117.1a's ordinary timing), and CR 608.2g explicitly waives.
    """
    scenario = board(
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Mountain"],
    )
    cast_knowledge_pool(scenario)
    assert scenario.turn.active_player == "alice"
    scenario.pass_priority("alice")  # bob responds during alice's own turn

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.game.put_triggers_on_stack()

    scenario.will_take_the_may(True, source="Knowledge Pool", username="bob")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    scenario.will_choose_cards(bears, username="bob", source="Knowledge Pool")
    scenario.resolve_top()  # ability 2, still alice's turn, the Bolt trigger's own resolution

    assert bears.zone is Zone.STACK, "CR 608.2g: cast with no timing check, mid-resolution"
    scenario.resolve_top()
    creature = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    assert creature.controller == "bob"
    assert scenario.turn.active_player == "alice", "still not bob's turn"


# --------------------------------------------------------------------------
# 10, 11. Declining is legal; an empty pool makes "yes" illegal (CR 608.2d)
# --------------------------------------------------------------------------


def test_declining_the_may_leaves_both_cards_in_exile():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        alice_library=["Grizzly Bears", "Forest", "Forest"],
        bob_library=[],
    )
    cast_knowledge_pool(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(False, source="Knowledge Pool")
    scenario.resolve_top()

    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE, "CR 608.2d: declining is legal; no fallback is printed"


def test_an_empty_pool_makes_the_free_cast_illegal_not_merely_declined():
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        alice_library=[],
        bob_library=[],
    )
    cast_knowledge_pool(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    asked = [
        q
        for q in scenario.questions_asked()
        if q.source == "Knowledge Pool" and q.kind is DecisionKind.MAY
    ]
    (may,) = asked
    assert may.affirmative_is_legal is False, "CR 608.2d, 101.3: impossible, not just declined"
    assert bolt.zone is Zone.EXILE, "the mandatory exile still happened"


# --------------------------------------------------------------------------
# 12. Two Pools: each has its own linked pool, and only the first trigger
# to resolve finds anything to exile (CR 118.12, 607.2a)
# --------------------------------------------------------------------------


def test_two_pools_each_offer_only_their_own_pool_and_the_second_offers_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Knowledge Pool", "Knowledge Pool", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pools = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Knowledge Pool"
    ]
    assert len(pools) == 2

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 3, "both Pool triggers, above the Bolt"

    scenario.will_take_the_may(False, times=None)
    scenario.resolve_top()  # the first trigger to resolve: exiles the Bolt
    assert bolt.zone is Zone.EXILE

    # The second trigger's own "that player exiles it" can no longer be
    # started - the spell is already gone - so CR 118.12's "if the player
    # does" is false and it offers nothing at all.
    before = len(scenario.questions_asked())
    scenario.resolve_top()
    assert len(scenario.questions_asked()) == before, "no MAY offered by the second trigger"


# --------------------------------------------------------------------------
# 13. A spell countered in response makes "if the player does" false
# --------------------------------------------------------------------------


def test_a_spell_countered_in_response_makes_if_the_player_does_false():
    """A hand-cast counterspell does not work as the "something else counters
    it" half of this test: casting *any* spell from hand - a counterspell
    included - is itself a cast Knowledge Pool catches, so a hand-cast
    Counterspell aimed at the Bolt gets exiled by its *own*, second Knowledge
    Pool trigger before it ever resolves (verified directly while writing
    this file). Nor does an activated or triggered ability reach it:
    `machines/effects.py`'s own "Counter target spell" dispatcher refuses
    for anything but a resolving spell ("an ability naming this shape does
    not turn up in the pool, and guessing at one would be worse than
    refusing it") - this engine has no ability-based counter at all today.

    Saw It Coming's own Foretell (CR 702.143a) sidesteps both: cast from
    **exile**, not hand, so it is not itself a Knowledge Pool trigger, and it
    is a spell's own "Counter target spell." (the plain, modelled shape).
    The foretold state is staged directly (`ExileMarker.FORETOLD`,
    `turn_exiled` in the past) rather than played out turn by turn - CR
    702.143a's "any time a player has priority during their turn" and "a
    later turn" are `test_foretell.py`'s own mechanic, not this file's.
    """
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Island", "Island", "Mountain"],
        alice_exile=["Saw It Coming"],
    )
    saw_it_coming = scenario.find("Saw It Coming", Zone.EXILE, "alice")
    saw_it_coming.exile_annotation = ExileAnnotation(
        marker=ExileMarker.FORETOLD, owner="alice", turn_exiled=0
    )
    cast_knowledge_pool(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Knowledge Pool's triggered ability",
    ], "bottom first"

    # In response to the Pool's own trigger, alice casts her foretold Saw It
    # Coming from exile - not from hand, so this cast is not itself a
    # Knowledge Pool trigger - and counters the Bolt sitting underneath it
    # (still a legal target: CR 115.1, it is still on the stack, whatever
    # else sits above it).
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    casting = scenario.cast("Saw It Coming", from_zone=Zone.EXILE)
    casting.use_keyword("Foretell")
    casting.choose_targets([bolt])
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)
    assert scenario.game.pending_triggers == [], "cast from exile, not hand: no new Pool trigger"
    scenario.resolve_top()  # Saw It Coming resolves first (CR 608.1)
    assert bolt.zone is Zone.GRAVEYARD, "sanity: Saw It Coming actually countered it"

    before = scenario.questions_asked()
    scenario.resolve_top()  # the Pool's own trigger, now with nothing left to exile
    after = scenario.questions_asked()
    assert after == before, "CR 118.12: the mandatory exile was never started; no MAY asked"
    assert bolt.zone is Zone.GRAVEYARD, "Saw It Coming's own counter is untouched by the Pool"


# --------------------------------------------------------------------------
# 14. Possibility Storm shares the first clause, and does not loop either
# --------------------------------------------------------------------------


def test_possibility_storm_exiles_a_hand_cast_spell_and_digs_for_a_shared_type():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Possibility Storm"],
            battlefield=["Forest", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Mountain", "Giant Growth"],
            battlefield=["Mountain", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    storm = scenario.cast_and_resolve(
        "Possibility Storm",
        *scenario.untapped_sources("Forest", "Mountain", "Mountain", "Mountain", "Mountain"),
    )
    assert storm.zone is Zone.BATTLEFIELD
    scenario.pass_priority("alice")

    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Possibility Storm's triggered ability",
    ], "bottom first"

    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, source="Possibility Storm")
    # `cast_free_from_exile`'s own CHOOSE_TARGETS decision is asked with the
    # card being cast as its source (CR 601.2c), not the ability that grants
    # the cast.
    scenario.will_choose_targets(elves, username="bob", source="Giant Growth")
    scenario.resolve_top()  # Possibility Storm's own trigger

    bob = scenario.player("bob")
    assert bolt.zone is Zone.LIBRARY, "bottomed - CR 607.2a, exiled with the enchantment"
    assert bolt in bob.library
    mountain_dug = next(s for s in bob.library if s.name == "Mountain")
    assert mountain_dug.zone is Zone.LIBRARY, "the missed dig is bottomed too"
    assert len(bob.library) == 2, "the exiled spell and the missed dig, nothing else"

    assert scenario.stack_names() == ["Giant Growth"], (
        "the hit - Giant Growth, an instant sharing a type with the exiled instant Bolt - "
        "was cast for free"
    )
    assert scenario.game.pending_triggers == [], (
        "the free cast did not re-trigger Possibility Storm"
    )
    scenario.resolve_top()  # Giant Growth resolves

    assert scenario.game.pending_triggers == []
    assert scenario.game.stack == []
    assert elves.power == 4, "Giant Growth actually resolved: +3/+3 on a 1/1 Llanowar Elves"


def test_a_from_exile_cast_trigger_reads_its_zone_too():
    """The other printed origin-zone phrasing in the pool, and the one the
    zone-word table silently dropped.

    Appa, Steadfast Guardian (`resolve_cards`, this session) prints "Whenever
    you cast a spell **from exile**, create a 1/1 white Ally creature token."
    `_CAST_ORIGIN_ZONE_RE` matches the bare word - exile takes no possessive,
    being a shared zone (CR 400.1: "a normal game ... uses ... the exile
    zone") - but `_CAST_ORIGIN_ZONE_WORDS` had no `exile` row, so
    `_required_cast_origin_zone` answered `None`, which `_origin_zone_matches`
    reads as *no restriction at all*. Appa's trigger therefore fired on every
    cast from anywhere, a hand cast included: the exact inverse of the
    Knowledge Pool defect, and invisible because the docstring above the table
    already claimed this card was handled.

    Both directions are asserted here. A restriction that only ever says "no"
    is as wrong as one that only ever says "yes", and only the pair
    distinguishes a real zone read from a hardcoded refusal.
    """
    assert _required_cast_origin_zone("you cast a spell from exile") is Zone.EXILE
    assert _required_cast_origin_zone("a player casts a spell from their hand") is Zone.HAND
    assert _required_cast_origin_zone("you cast a spell") is None

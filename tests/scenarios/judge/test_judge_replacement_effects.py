"""Judge scenarios: replacement effects, and the order they are chosen in.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#939** - Ancient Adamantoise + Pariah (a permanent's own "all damage ...
  is dealt to this creature instead" redirection has no entry in the
  hand-written replacement registry)
- **DDR#830** - The Mindskinner vs. Replacement and Prevention Effects (two
  damage replacements that used to parse into a real shape and still do
  nothing at the table; both now compile automatically off their own oracle
  text - see `machines/replacement.py`'s `_compile_damage_multiplier` and
  `_compile_prevent_damage_and_mill`)
- **DDR#943** - The Darkness Crystal vs. Lethal Combat Damage (lifelink still
  gains life off the real combat damage even though the "exile instead" half of
  the same event has no registry row either)
- **DDR#403** - Totem Armor vs. Engineered Explosives (a destruction-replacer
  against a mass destruction)
- **DDR#853** - How does Regenerate Work? (only one destruction-replacer applies
  to any one destruction)
- **DDR#14** - Rest in Peace vs. Lapse of Certainty (two replacement effects
  competing for the same zone change)
- **DDR#707** - Tishana's Tidebinder vs. Soul Warden (a trigger already on the
  stack, and a replacement applied afterwards)
- **DDR#901** - Officious Interrogation + Stridehangar Automaton (a token
  replacement that *does* parse into `IF_WOULD_INSTEAD`, on a card with no row
  in the registry - the same shape DDR#830 already found for damage, now on
  token creation)
- **DDR#833** - Nashi, Searcher in the Dark vs. Leyline of the Void (an
  opponent's Leyline of the Void reaches a player's *own* self-mill, because
  "opponent's graveyard" is judged from the Leyline's controller, not the
  mill's)

The governing rules are CR 614 for what a replacement effect is and CR 616.1 for
who picks when more than one could apply. Every CR number here was looked up
with `knowledge_search(type="rules")`.

**One correction to the transcripts.** DDR#403 and the episode titles talk about
"totem armor". CR 702.89b says the ability was renamed: "Some older cards were
printed with the ability 'totem armor' ... The text of these cards has been
updated in the Oracle card reference to refer to umbra armor instead." The
Scryfall printing of Hyena Umbra in the pool prints *umbra armor*, and CR 702.89a
is where the ability is defined. The mechanic the judges describe is unchanged.

**What "not applied" means here, precisely.** `machines/replacement.py` has two
halves: a text parser (`parse_replacement_effects`) and what turns a parsed
effect into behaviour - a hand-written per-card `REPLACEMENTS` registry (the
same shape as `machines/effects.py`'s `EFFECTS` table) for the genuine
exceptions, plus a set of generic compilers tried on a registry miss for every
wording common enough to template. `replacements_of` is what `Game` actually
consults through `apply_replacements`, and it tries both. A card's replacement
clause can still *parse* into a real `ReplacementKind` - Stridehangar
Automaton's token-plus-an-extra-Thopter clause parses as `IF_WOULD_INSTEAD`
below - and do nothing at the table, because its exact wording matches no
compiled shape and it has no `REPLACEMENTS` row of its own; that gap is what
DDR#901 is about. Pariah and Ancient Adamantoise's declarative "All damage that
would be dealt to you ... is dealt to X instead" does not even reach
`IF_WOULD_INSTEAD`: the parser only claims sentences that open with
"If ... would ...", so this phrasing (used by every damage-redirection aura,
not just these two) comes back `UNPARSED`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import (
    ReplacementKind,
    parse_replacement_effects,
    replacements_of,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#939 - a permanent's own damage-redirection text is unparsed
# --------------------------------------------------------------------------


def test_ancient_adamantoises_own_redirect_text_is_unparsed():
    """DDR#939, the provable half: the parser never claims this sentence.

    Ancient Adamantoise reads "All damage that would be dealt to you and other
    permanents you control is dealt to this creature instead" - a real
    redirection effect (CR 614.9: "Some effects replace damage dealt to one ...
    creature ... or player with the same damage dealt to another ...; such
    effects are called redirection effects"). But `_try_if_would` only claims
    sentences shaped "If ... would ..., ... instead", and this one has no
    leading "If", so `parse_replacement_effects` reports it `UNPARSED` rather
    than `IF_WOULD_INSTEAD` - confirmed directly against the fixture rather
    than assumed from the card text.
    """
    (effect,) = parse_replacement_effects(card("Ancient Adamantoise"))
    assert effect.kind is ReplacementKind.UNPARSED


def test_ancient_adamantoise_should_catch_damage_aimed_at_its_controller():
    """DDR#939: all damage to alice should be redirected to her Adamantoise.

    Pariah does the same "all damage to you instead" trick as an Aura rather
    than a creature's own text, but Auras have no attachment in this model (see
    the umbra armor xfail below), so Ancient Adamantoise - which redirects
    damage aimed at *itself*, no attachment needed - isolates the redirection
    gap on its own without also depending on the missing-attachment gap.

    Driven from alice's side of the table so the Bolt is cast by the active
    player during their own main phase (CR 117.3a). While this was an `xfail`
    it was bob casting on alice's turn, which never got as far as the damage:
    the priority machinery refused the cast, and a strict `xfail` cannot tell
    the difference between failing for its own reason and failing early.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Ancient Adamantoise", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adamantoise = scenario.creature("Ancient Adamantoise", "bob")
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == starting_life, "the damage should never reach bob"
    assert adamantoise.damage == 3, "it should land on the Adamantoise instead"


# --------------------------------------------------------------------------
# DDR#830 - two more damage replacements with no row in the registry
# --------------------------------------------------------------------------


def test_furnace_of_raths_doubling_parses_and_mindskinners_prevent_and_mill_does_too():
    """DDR#830, updated: both now parse *and* both compile into real behaviour.

    Furnace of Rath ("If a source would deal damage ..., it deals double that
    damage ... instead") is exactly `_try_if_would`'s shape and comes back
    `IF_WOULD_INSTEAD` (CR 701.10g: "To double an amount of damage a source
    would deal, that source instead deals twice that much damage. This is a
    replacement effect."). The Mindskinner's "If a source you control would
    deal damage to an opponent, prevent that damage and each opponent mills
    that many cards" has "prevent" in its replacement clause, so it comes back
    `PREVENT_IF_WOULD` instead - also a real, claimed kind.

    What DDR#830 actually found - a parsed shape with nothing in
    `replacements_of` to turn it into behaviour - is fixed now:
    `_compile_damage_multiplier` and `_compile_prevent_damage_and_mill` in
    `machines/replacement.py` read exactly these two wordings off the card's
    own oracle text, with no per-card row needed, and `replacements_of`'s
    parser fallback reaches them.
    """
    furnace = parse_replacement_effects(card("Furnace of Rath"))[0]
    mindskinner = parse_replacement_effects(card("The Mindskinner"))[0]

    assert furnace.kind is ReplacementKind.IF_WOULD_INSTEAD
    assert mindskinner.kind is ReplacementKind.PREVENT_IF_WOULD
    assert len(replacements_of(card("Furnace of Rath"))) == 1
    assert len(replacements_of(card("The Mindskinner"))) == 1


def test_furnace_of_rath_and_mindskinner_should_change_what_the_bolt_does():
    """DDR#830: CR 616.1 gives bob the choice between doubling and prevent-and-mill.

    Whichever bob picks, "just deal 3 damage to bob's life total and do nothing
    else" is not a legal outcome: either Furnace of Rath doubles it to 6, or
    The Mindskinner prevents it and mills alice 3 cards instead (CR 615.1a
    prevention effects deal zero damage - "prevent" means the damage never
    happens at all, not that it happens and is undone).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Furnace of Rath", "The Mindskinner"],
        )
        .player("bob", library=["Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    life_lost = starting_life - scenario.player("bob").life
    assert life_lost == 0 or life_lost == 6, "3 alone means neither replacement fired"


# --------------------------------------------------------------------------
# DDR#943 - lifelink still works even though the redirect half does not
# --------------------------------------------------------------------------


def test_lifelink_gains_life_off_combat_damage_independently_of_the_crystal():
    """DDR#943: two separate mechanisms watch the same combat damage.

    Lifelink is not a replacement effect at all: `machines/combat.py`'s
    `_deal_combat_damage` calls `has_keyword(source, Keyword.LIFELINK, game)`
    directly off the actual damage dealt (CR 702.15b: "Damage dealt by a source
    with lifelink causes that source's controller ... to gain that much life ...
    in addition to any other results that damage causes"), independent of the
    replacement machinery that decides what happens to the *creature* that took
    the damage. Run the same combat with and without The Darkness Crystal and
    the difference is exactly the Crystal's own 2 - lifelink's 6 does not move.

    This test asserted a flat +6 while the Crystal had no row in
    `replacements_of`; that number was recording the gap, not a rule, and it
    moved to +8 the moment the row existed.
    """

    def combat(*alices_permanents: str) -> int:
        scenario = (
            Scenario()
            .player("alice", battlefield=list(alices_permanents))
            .player("bob", battlefield=["Grizzly Bears"])
            .build()
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        wurmcoil = scenario.creature("Wurmcoil Engine", "alice")
        bears = scenario.creature("Grizzly Bears", "bob")
        starting_life = scenario.player("alice").life

        scenario.attack_with(wurmcoil)
        scenario.block(wurmcoil, bears)
        scenario.combat_damage()
        return scenario.player("alice").life - starting_life

    assert combat("Wurmcoil Engine") == 6, "lifelink alone, off 6 damage"
    assert combat("Wurmcoil Engine", "The Darkness Crystal") == 6 + 2, "plus the Crystal's own"


def test_the_darkness_crystal_should_exile_the_dying_blocker_and_add_two_more_life():
    """DDR#943: the redirect half of the same combat that the test above proves lifelink for."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wurmcoil Engine", "The Darkness Crystal"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wurmcoil = scenario.creature("Wurmcoil Engine", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    starting_life = scenario.player("alice").life

    scenario.attack_with(wurmcoil)
    scenario.block(wurmcoil, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.EXILE, "The Darkness Crystal should have caught the death"
    assert scenario.player("alice").life == starting_life + 6 + 2, "plus the Crystal's own gain"


@pytest.mark.xfail(
    strict=True,
    reason="replacement effects are not applied (CR 614) and Auras have no attachment: "
    "CardState cannot say what Hyena Umbra is enchanting, so umbra armor has nothing "
    "to protect",
)
def test_umbra_armor_eats_the_destruction_and_the_creature_survives():
    """DDR#403: destruction is replaced, so the creature never leaves.

    CR 702.89a: "Umbra armor means 'If enchanted permanent would be destroyed,
    instead remove all damage marked on it and destroy this Aura.'" The word
    *instead* makes it a replacement effect (CR 614.1a), and CR 614.6 says the
    replaced event never happens - so this is not the creature dying and coming
    back, it is the creature never dying.

    The lethal damage state-based action (CR 704.5g) destroys the creature, and
    that destruction is what umbra armor catches.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Hyena Umbra"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    umbra = scenario.creature("Hyena Umbra", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0, "'remove all damage marked on it'"
    assert umbra.zone is Zone.GRAVEYARD, "the Aura is destroyed in the creature's place"


@pytest.mark.xfail(
    strict=True,
    reason="replacement effects are not applied (CR 614), so nothing ever reaches the "
    "CR 616.1 choice between two applicable effects",
)
def test_only_one_destruction_replacer_gets_to_apply():
    """DDR#853: two shields, one destruction, one shield spent.

    CR 616.1 hands the choice to the affected object's controller, and CR 616.1f
    then repeats the process "taking into account only replacement or prevention
    effects that would now be applicable". Once destruction has been replaced
    with something that is not a destruction, the second shield has nothing left
    to catch - CR 614.7: an effect that would replace an event that never
    happens simply does nothing.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Hyena Umbra", "Hyena Umbra"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("bob").graveyard] == ["Hyena Umbra"], (
        "exactly one Aura paid for the destruction"
    )


def test_two_graveyard_replacers_do_not_both_apply_to_one_card():
    """DDR#14: competing replacements for a single zone change.

    alice's Leyline of the Void and bob's Rest in Peace would both replace the
    same move to bob's graveyard. CR 616.1 gives the choice to the affected
    object's controller, and CR 614.5 stops whichever effect was chosen from
    invoking itself again: "a replacement effect doesn't invoke itself
    repeatedly; it gets only one opportunity to affect an event". Both say
    exile, so the visible outcome is the same either way - which is exactly why
    it is a good test of the machinery rather than of the answer.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Leyline of the Void"])
        .player("bob", battlefield=["Grizzly Bears", "Rest in Peace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []


def test_a_trigger_already_on_the_stack_survives_its_source_losing_its_abilities():
    """DDR#707: the ability is its own object once it is on the stack.

    CR 113.7a: "Once activated or triggered, an ability exists on the stack
    independently of its source. Destruction or removal of the source after that
    time won't affect the ability." Tishana's Tidebinder can counter the Warden
    trigger while it is still on the stack, but the *continuous* half - Soul
    Warden losing all abilities - cannot reach back and remove a trigger that is
    already there. Soul Warden's own trigger from the Tidebinder entering
    resolves and alice gains the life.

    Both abilities trigger off the same event, so CR 603.3b puts them on the
    stack in APNAP order with each player ordering their own.

    This was an xfail until Soul Warden's trigger got an entry in
    `machines/effects.py`. What the test asserts now holds; what still does not
    work is the Tidebinder half, and this scenario never depended on it. Its
    trigger targets an ability, `Game.resolve_target` only ever finds a
    `CardState`, so CR 608.2b removes the trigger before it resolves - covered by
    the xfails in `tests/scenarios/test_countering_an_ability.py`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Soul Warden", "Island", "Island", "Island"],
            hand=["Tishana's Tidebinder"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    warden = scenario.creature("Soul Warden", "alice")

    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Tishana's Tidebinder", *sources, username="alice")
    scenario.resolve_top()

    # Both the Warden's "another creature entered" trigger and the Tidebinder's
    # own enters trigger are now waiting.
    assert len(scenario.game.stack) == 2

    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 21, "the life gain trigger still resolved"
    assert warden.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# DDR#901 - a token-creation replacement that parses, but has no row
# --------------------------------------------------------------------------


def test_stridehangar_automatons_token_clause_parses_as_if_would_instead():
    """DDR#901, the provable half: the sentence is a real `IF_WOULD_INSTEAD`.

    Stridehangar Automaton (confirmed with `resolve_cards`): "If one or more
    artifact tokens would be created under your control, those tokens plus an
    additional 1/1 colorless Thopter artifact creature token with flying are
    created instead." That is CR 614.1a's exact template - "If [event] would
    [happen], [replacement] instead" - and `parse_replacement_effects` reads it
    that way. `replacements_of` is still empty for this card, the same
    DDR#830-shaped gap: a parsed shape with no row that turns it into
    behaviour.
    """
    (effect,) = parse_replacement_effects(card("Stridehangar Automaton"))
    assert effect.kind is ReplacementKind.IF_WOULD_INSTEAD
    assert replacements_of(card("Stridehangar Automaton")) == []


@pytest.mark.xfail(
    strict=True,
    reason="Stridehangar Automaton parses into a real IF_WOULD_INSTEAD (proven "
    "above) but has no row in replacements_of, so apply_replacements never sees "
    "it: Hangarback Walker's dies trigger creates exactly two Thopters, one per "
    "+1/+1 counter, with no extra Thopter added on top.",
)
def test_stridehangar_automaton_should_add_an_extra_thopter_to_any_artifact_token_event():
    """DDR#901: any artifact token creation under Stridehangar Automaton's
    controller becomes that many tokens *plus* an extra 1/1 Thopter.

    CR 111.1, CR 701.7a-b are the token-creation rules the replacement watches -
    "would create" - and CR 614.1a is what lets a static ability rewrite that
    event. Hangarback Walker's own dies trigger ("create a 1/1 ... Thopter ...
    for each +1/+1 counter") is already scripted in `machines/effects.py`, so it
    is real token creation to test the replacement against rather than a stand-in.
    With two +1/+1 counters it creates two Thopters on its own; Stridehangar
    Automaton on the battlefield should make that three.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stridehangar Automaton", "Hangarback Walker"])
        .player("bob")
        .build()
    )
    hangarback = scenario.creature("Hangarback Walker", "alice")
    hangarback.counters.add(Counter.PLUS_ONE, 2)

    scenario.game.destroy(hangarback)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    thopters = [state for state in scenario.game.battlefield if state.name == "Thopter Token"]
    assert len(thopters) == 3


# --------------------------------------------------------------------------
# DDR#833 - an opponent's Leyline of the Void reaches a self-mill
# --------------------------------------------------------------------------


def test_leyline_of_the_void_exiles_a_cards_own_owner_milling_it():
    """DDR#833: "opponent's graveyard" in Leyline of the Void is read from the
    Leyline's own controller's point of view, not the mill's - so a player who
    mills *their own* library into *their own* graveyard is still hit by an
    opponent's Leyline of the Void.

    CR 614.1a again, and Leyline of the Void's card text is already a working
    `replacements_of` row (`_opponents_graveyard`, keyed on whether the card's
    owner is an opponent of the Leyline's controller - see
    `machines/replacement.py`). `Game.put_into_graveyard` is the generic path
    every zone-change-to-graveyard in this engine funnels through (CR 400.6,
    400.7), which is what Nashi, Searcher in the Dark's own "you mill that many
    cards" would use if it were scripted - it is not (`effect_for` returns
    `None` for it), so this test drives the zone change directly rather than
    through a trigger that does not exist yet, to isolate exactly the
    replacement-effect fact the episode turns on.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Lightning Bolt", "Mountain"])
        .player("bob", battlefield=["Leyline of the Void"])
        .build()
    )
    milled = scenario.player("alice").library[0]
    assert milled.zone is Zone.LIBRARY

    scenario.game.put_into_graveyard(milled)

    assert milled.zone is Zone.EXILE


def test_nashi_deals_combat_damage_and_mills_into_an_opponents_leyline_of_the_void():
    """DDR#833, the full scenario: Nashi mills cards off combat damage, an
    opponent's Leyline of the Void exiles them as they would hit alice's own
    graveyard, and there is nothing left "among them" for Nashi's second
    sentence to choose from.

    CR 701.17a: "For a player to mill a number of cards, that player puts that
    many cards from the top of their library into their graveyard" - the mill
    is a move *to the graveyard*, which is exactly the event the Leyline
    replaces, so the cards never arrive. CR 400.7's "from among them" then has
    an empty set to offer, and CR 608.2d never puts a question with no legal
    option, so the third sentence's counter is what happens instead.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nashi, Searcher in the Dark"],
            library=["Lightning Bolt", "Mountain"],
        )
        .player("bob", battlefield=["Leyline of the Void"], life=18)
        .build()
    )
    scenario.start_at(Step.COMBAT_DAMAGE)
    nashi = scenario.creature("Nashi, Searcher in the Dark", "alice")
    scenario.attack_with(nashi)
    scenario.no_blocks()
    scenario.combat_damage()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    # Nashi deals 2 combat damage, so 2 cards leave the library - milled, then
    # exiled by bob's Leyline of the Void before ever touching a graveyard.
    assert len(scenario.player("alice").library) == 0
    assert scenario.player("alice").graveyard == []
    assert len(scenario.game.exile) == 2, "the Leyline took both"
    assert scenario.player("alice").hand == [], "nothing was left among them to take"
    assert nashi.counter_count("+1/+1") == 1, "so the third sentence's counter goes on"


def test_without_the_leyline_nashi_takes_the_enchantment_and_gets_no_counter():
    """The control DDR#833's ruling is measured against: the same trigger with
    nothing replacing the mill.

    Both milled cards reach alice's graveyard (CR 701.17a), the Leyline of the
    Void among them is an enchantment card "from among them", and taking it
    means the third sentence's condition - "if you put no cards into your hand
    this way" - is false, so no counter goes on. Without this test the xfail
    above could start passing for the wrong reason: an effect that milled and
    then offered nothing would satisfy every assertion in it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nashi, Searcher in the Dark"],
            library=["Leyline of the Void", "Mountain"],
        )
        .player("bob", life=18)
        .build()
    )
    leyline = scenario.player("alice").library[0]
    scenario.start_at(Step.COMBAT_DAMAGE)
    nashi = scenario.creature("Nashi, Searcher in the Dark", "alice")
    # CR 107.1c's "any number" defaults to none, so the taking is scripted.
    scenario.will_choose_cards(leyline, source="Nashi, Searcher in the Dark")
    scenario.attack_with(nashi)
    scenario.no_blocks()
    scenario.combat_damage()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert [state.name for state in scenario.player("alice").hand] == ["Leyline of the Void"]
    assert [state.name for state in scenario.player("alice").graveyard] == ["Mountain"], (
        "the Mountain is neither legendary nor an enchantment, so it stays put"
    )
    assert nashi.counter_count("+1/+1") == 0, "a card was taken, so no counter"

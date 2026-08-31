"""Amulet of Vigor (no CR-numbered card, just "Whenever a permanent you
control enters tapped, untap it.") and the Karoo-cycle bounce lands
(Gruul Turf, Simic Growth Chamber) it turns into a ramp engine - the deck
Amulet Titan is named for.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.1** - "Triggered abilities ... are written as '[When/Whenever/At]
  [trigger condition or event], [effect].'" Amulet of Vigor's own line opens
  with "Whenever", so it is a triggered ability, not a replacement effect -
  CR 614.1c/614.1d's replacement shapes are "[This] enters ...", "As [this]
  enters ...", or "[this] enters as ...", none of which this is.
- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield. These are written ... 'Whenever a [type] enters,
  ...'" - the condition half of Amulet's own trigger.
- **CR 701.26b** - "To untap a permanent, rotate it back to the upright
  position from a sideways position." What the trigger's effect does.
- **CR 614.1d** - "Continuous effects that read '[This permanent] enters
  . . .' or '[Objects] enter [the battlefield] . . .' are replacement
  effects." A bounce land's own "This land enters tapped." is this shape,
  already generalised by `machines/replacement.py`'s `ENTERS_TAPPED`.
- **CR 113.10** - a card gains no ability here; used only for contrast in
  earlier design notes, not asserted by these tests.
- **CR 608.2d** - "the player announces these while applying the effect" -
  a bounce land's own "return a land you control" names no target, so which
  land returns is a resolution-time choice, not a targeted one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario, mana_from


def test_amulet_untaps_a_permanent_that_entered_tapped():
    """The bare mechanic, off a card with no other text: Karplusan Forest
    prints no "enters tapped" line of its own to confuse the picture, so a
    plain "enters tapped" land (Gruul Turf, `ENTERS_TAPPED`) is what proves
    Amulet's own trigger, separate from anything the bounce land's second
    ability does."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gruul Turf"], battlefield=["Amulet of Vigor", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turf = scenario.play_land("Gruul Turf")
    assert turf.tapped, "Gruul Turf's own printed ENTERS_TAPPED replacement (CR 614.1c) tapped it"

    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Gruul Turf")
    while scenario.game.stack:
        scenario.resolve_top()

    assert not turf.tapped, "Amulet of Vigor's trigger (CR 701.26b) should have untapped it"


def test_amulet_plus_bounce_land_is_a_real_mana_ramp_loop():
    """The Amulet Titan combo, played through the engine end to end: Gruul
    Turf enters tapped, Amulet untaps it, its own ETB trigger returns a
    *different* land (the Forest, not itself) to hand, and the net result is
    a Gruul Turf that is untapped and can actually be tapped for {R}{G} the
    same turn it entered - which is the entire point of the interaction."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gruul Turf"], battlefield=["Amulet of Vigor", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turf = scenario.play_land("Gruul Turf")

    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Gruul Turf")
    while scenario.game.stack:
        scenario.resolve_top()

    assert not turf.tapped
    assert turf.zone is Zone.BATTLEFIELD, "Gruul Turf itself was not the land returned"
    assert forest.zone is Zone.HAND, "the Forest was returned instead, replayable for more ramp"

    # The mana is actually available this turn: an untapped Gruul Turf can be
    # tapped for its printed {T}: Add {R}{G} the moment the loop is done,
    # which is the entire reason Amulet Titan bothers with any of this.
    (turf_again,) = scenario.untapped_sources("Gruul Turf")
    payment = scenario.game.begin_activating(turf_again, 0, "alice")
    payment.tap_for_mana(turf_again, mana_from(turf_again))
    assert payment.pool.total == 2
    assert payment.pool.floating == {Color.RED: 1, Color.GREEN: 1}


def test_two_amulets_untap_the_same_land_twice_over_with_no_extra_effect():
    """Two Amulets of Vigor each carry their own `TriggeredAbility` and each
    independently matches Gruul Turf's own entering-tapped event (CR 603.3b:
    simultaneous triggers of the same controller, ordered at that
    controller's choice). Untapping an already-untapped permanent is not
    illegal for an effect (unlike the cost-side `tap`/`untap` special
    actions) - `CardState.untap` is idempotent - so the net effect of two
    Amulets is the same single untap, not a double one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gruul Turf"],
            battlefield=["Amulet of Vigor", "Amulet of Vigor", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turf = scenario.play_land("Gruul Turf")

    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Gruul Turf")
    while scenario.game.stack:
        scenario.resolve_top()

    assert not turf.tapped


def test_returning_the_bounce_land_itself_is_a_legal_choice():
    """ "Return a land you control" (CR 608.2d, no target) never excludes the
    resolving land itself - it is a land its controller controls by the time
    the ability resolves (CR 110.5) - even though doing so undoes the ramp a
    player would normally want. The engine must allow the choice, not
    silently substitute the better one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gruul Turf"], battlefield=["Amulet of Vigor", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turf = scenario.play_land("Gruul Turf")

    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(turf, source="Gruul Turf")
    while scenario.game.stack:
        scenario.resolve_top()

    assert turf.zone is Zone.HAND
    assert scenario.find("Forest", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_simic_growth_chamber_prints_the_identical_shape():
    """Simic Growth Chamber's oracle text is templated identically to Gruul
    Turf's own ("This land enters tapped. When this land enters, return a
    land you control to its owner's hand. {T}: Add {G}{U}."), so the same
    parser reaches it with no card-specific row - proof the shape generalised
    rather than being written for one printing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Simic Growth Chamber"], battlefield=["Amulet of Vigor", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chamber = scenario.play_land("Simic Growth Chamber")

    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Simic Growth Chamber")
    while scenario.game.stack:
        scenario.resolve_top()

    assert not chamber.tapped
    assert forest.zone is Zone.HAND


def test_a_bounce_land_with_no_amulet_still_returns_a_land_while_staying_tapped():
    """Without Amulet of Vigor in play, Gruul Turf's own ETB trigger still
    fires and still returns a land - the two abilities are independent - but
    nothing untaps it, so it stays tapped exactly as CR 614.1c's own
    replacement effect left it."""
    scenario = Scenario().player("alice", hand=["Gruul Turf"], battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turf = scenario.play_land("Gruul Turf")
    assert turf.tapped

    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Gruul Turf")
    while scenario.game.stack:
        scenario.resolve_top()

    assert turf.tapped
    assert forest.zone is Zone.HAND

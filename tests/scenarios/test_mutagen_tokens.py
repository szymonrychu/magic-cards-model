"""The Mutagen predefined token (CR 111.10v), and the shapes a TMT card
prints "create a Mutagen token" in:

- "When this creature enters, create a Mutagen token." - Crustacean Commando.
- "When `<Name>` enters, create a Mutagen token." (a self-named ETB) -
  Michelangelo, Weirdness to 11.
- "Whenever `<Name>` or another Mutant you control enters, create a Mutagen
  token." (self-or-another-subtype) - Genghis Frog, both halves: its own
  entry, and a second, unrelated Mutant's.
- "When this creature leaves the battlefield, create a Mutagen token." -
  Zoo Escapees.
- "create X Mutagen tokens" off an `{X}` creature's own ETB (CR 107.3m's X of
  the spell) - Mutagen Man, Living Ooze.
- The token's own printed ability - "{1}, {T}, Sacrifice this token: Put a
  +1/+1 counter on target creature. Activate only as a sorcery." - both that
  it puts the counter, and that CR 601.3b's "activate only as a sorcery"
  restriction is enforced on it exactly as on any other ability that prints
  it.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 111.10v** - "A Mutagen token is a colorless Mutagen artifact token
  with '{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target
  creature. Activate only as a sorcery.'"
- **CR 111.2** - the token's creator is its owner and controller.
- **CR 107.3m** - an enters-the-battlefield trigger's own bare X is the X
  chosen for the spell that became the permanent.
- **CR 603.6c** - "when this creature leaves the battlefield" reads the
  object as it existed immediately before that event (CR 603.10a's own
  look-back list names leaves-the-battlefield abilities explicitly).
- **CR 601.3b** - "activate only as a sorcery" restricts an activated ability
  to when its controller could cast a sorcery.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _mutagen_tokens(scenario: Scenario, username: str = "alice") -> list:
    return [
        p
        for p in scenario.game.battlefield
        if p.name == "Mutagen Token" and p.controller == username
    ]


def test_when_this_creature_enters_creates_a_mutagen_token() -> None:
    """Crustacean Commando's own "When this creature enters, create a
    Mutagen token." (CR 603.6a's plain enters trigger)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Crustacean Commando"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Crustacean Commando", auto=True)
    _resolve_all(scenario)

    tokens = _mutagen_tokens(scenario)
    assert len(tokens) == 1
    assert tokens[0].zone is Zone.BATTLEFIELD
    assert "Mutagen" in (tokens[0].card.type_line or "")


def test_when_name_enters_creates_a_mutagen_token() -> None:
    """Michelangelo, Weirdness to 11's own self-named "When Michelangelo
    enters, create a Mutagen token." (CR 201.5's own-name self-reference)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Michelangelo, Weirdness to 11"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Michelangelo, Weirdness to 11", "alice")
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 1


def test_genghis_frog_fires_off_its_own_entry() -> None:
    """ "Whenever Genghis Frog or another Mutant you control enters, create a
    Mutagen token." - the self half."""
    scenario = Scenario().player("alice", hand=["Genghis Frog"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Genghis Frog", "alice")
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 1


def test_genghis_frog_fires_off_another_mutant_entering() -> None:
    """The "or another Mutant you control" half - Twisted Abomination
    (Creature - Zombie Mutant, no ETB of its own, off-set and not this
    task's own reported card) entering also fires Genghis Frog's trigger."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Genghis Frog"], hand=["Twisted Abomination"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    frog = scenario.creature("Genghis Frog", "alice")
    scenario.put_onto_battlefield("Twisted Abomination", "alice")
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 1
    assert frog.zone is Zone.BATTLEFIELD


def test_genghis_frog_does_not_fire_off_a_non_mutant_entering() -> None:
    """A creature with no Mutant subtype - Mouser Mark III (Artifact
    Creature - Robot) - does not satisfy "another Mutant you control"."""
    scenario = (
        Scenario().player("alice", battlefield=["Genghis Frog"], hand=["Mouser Mark III"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mouser Mark III", "alice")
    _resolve_all(scenario)

    assert _mutagen_tokens(scenario) == []


def test_when_this_creature_leaves_the_battlefield_creates_a_mutagen_token() -> None:
    """Zoo Escapees' own "When this creature leaves the battlefield, create a
    Mutagen token." (CR 603.6c, CR 603.10a's look-back)."""
    scenario = Scenario().player("alice", battlefield=["Zoo Escapees"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    escapees = scenario.creature("Zoo Escapees", "alice")

    assert _mutagen_tokens(scenario) == []
    scenario.game.destroy(escapees)
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 1


def test_x_spell_etb_creates_that_many_mutagen_tokens() -> None:
    """Mutagen Man, Living Ooze's own "When Mutagen Man enters, create X
    Mutagen tokens." (CR 107.3m's ETB-trigger X, off the {X}{G}{G} spell that
    became this permanent)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mutagen Man, Living Ooze"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mutagen Man, Living Ooze")
    casting.x_value = 3
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 3


def test_x_zero_creates_no_mutagen_tokens() -> None:
    """X=0 is a legal announcement (CR 107.3a) that simply creates none."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mutagen Man, Living Ooze"], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mutagen Man, Living Ooze")
    casting.x_value = 0
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    _resolve_all(scenario)

    assert _mutagen_tokens(scenario) == []


def test_mutagen_tokens_own_ability_puts_a_counter_and_sacrifices_it() -> None:
    """The token's own printed ability: "{1}, {T}, Sacrifice this token: Put
    a +1/+1 counter on target creature." (CR 111.10v)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crustacean Commando"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Crustacean Commando", auto=True)
    _resolve_all(scenario)
    (token,) = _mutagen_tokens(scenario)

    scenario.activate(token, *scenario.untapped_sources("Island"), targets=[bears])
    scenario.resolve_top()

    assert bears.counters["+1/+1"] == 1
    assert token.zone is not Zone.BATTLEFIELD


def test_mutagen_tokens_ability_is_sorcery_speed_only() -> None:
    """ "Activate only as a sorcery" (CR 601.3b) refuses the Mutagen token's
    own ability with something else on the stack, off its own printed line -
    CR 601.3b: "A player may cast a sorcery only during a main phase of their
    turn when they have priority and the stack is empty," and an ability that
    restricts itself the same way is refused under the identical condition."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crustacean Commando", "Lightning Bolt"],
            battlefield=["Island", "Island", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Crustacean Commando", auto=True)
    _resolve_all(scenario)
    (token,) = _mutagen_tokens(scenario)

    assert scenario.why_cannot_activate(token, index=0) is None

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.why_cannot_activate(token, index=0) is not None

"""A DIES condition's own subtype and token/nontoken qualifiers, read
generally rather than only inside the "other `<X>`s you control" shape and
only on the ENTERS_THE_BATTLEFIELD path (CR 700.4, CR 205.3m, CR 111.1).

`condition_matches`'s `TriggerEvent.DIES` branch called `_required_subtype`,
which only ever read `_OTHER_SUBTYPE`'s "other `<X>`s you control" - so a
subtype named as the condition's own plain subject, with no "other"/"you
control" at all, was never read: `_types_match` finds no *card*-type word in
"a Food is put into a graveyard from the battlefield" (CR 700.4's own
wording for "dies") and answers True for lack of a restriction, and
`_subtype_matches(subtypes, None)` answers True too, so Ygra, Eater of All's
own trigger fired on *every* permanent's death - a land, an unrelated
artifact, anything - not only a Food's.

The DIES branch also never read `_NONTOKEN_WORD`/`_TOKEN_WORD` at all - both
were wired for `ENTERS_THE_BATTLEFIELD` only - so Lightning Coils' own
"Whenever a nontoken creature you control dies, ..." charged a counter off a
*token* creature's death too, exactly the shape "nontoken" exists to
exclude.

Both are read generally now: `_required_dying_subtype` mirrors
`_required_entering_subtype`'s own leading-subject-subtype reader (same
capitalization discriminator - Oracle templating never capitalizes a card
type or "nontoken", only a real subtype), and the DIES branch now runs the
identical `_NONTOKEN_WORD`/`_TOKEN_WORD` check `ENTERS_THE_BATTLEFIELD`
already ran.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 700.4 ("dies" = put into a graveyard from the battlefield),
CR 205.3m (creature subtypes), CR 111.1 (tokens).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario

#: A plain 2/2 Bear creature token, the same shape `Grizzly Bears` is printed
#: as - used only to prove a *token* creature's death does not satisfy
#: Lightning Coils' own "nontoken" restriction.
_BEAR_TOKEN = TokenDefinition(types=(Type.CREATURE,), subtypes=("Bear",), power=2, toughness=2)


def test_ygra_does_not_trigger_on_an_unrelated_artifacts_death():
    """The reported over-trigger: Ygra's own "a Food is put into a graveyard
    from the battlefield" must not fire off a plain artifact - Prophetic
    Prism, not a creature and so never granted Food status by Ygra's own
    static - dying."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ygra, Eater of All", "Prophetic Prism"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ygra = scenario.creature("Ygra, Eater of All", "alice")
    prism = scenario.find("Prophetic Prism", Zone.BATTLEFIELD, "alice")
    assert ygra.counter_count(Counter.PLUS_ONE) == 0

    scenario.game.destroy(prism)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert prism.zone is Zone.GRAVEYARD
    assert ygra.counter_count(Counter.PLUS_ONE) == 0


def test_ygra_still_triggers_on_a_real_foods_death():
    """The other side of the same fix: an actual Food dying still fires -
    the fix must not have refused every death outright."""
    scenario = Scenario().player("alice", battlefield=["Ygra, Eater of All"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ygra = scenario.creature("Ygra, Eater of All", "alice")
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")
    assert "Food" in food.subtypes

    scenario.game.destroy(food)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert food.zone is Zone.GRAVEYARD
    assert ygra.counter_count(Counter.PLUS_ONE) == 2


def test_lightning_coils_does_not_charge_off_a_token_creatures_death():
    """The reported over-trigger: Lightning Coils' own "a nontoken creature
    you control dies" must not fire off a token creature's death."""
    scenario = Scenario().player("alice", battlefield=["Lightning Coils"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coils = scenario.find("Lightning Coils", Zone.BATTLEFIELD, "alice")
    (token,) = create_tokens(scenario.game, _BEAR_TOKEN, "alice")
    assert token.token

    scenario.game.destroy(token)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert token.zone is Zone.GRAVEYARD
    assert coils.counter_count(Counter.CHARGE) == 0


def test_lightning_coils_still_charges_off_a_real_nontoken_creatures_death():
    """The other side: a genuine nontoken creature the controller controls
    still charges the artifact - the fix must not have refused every death."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lightning Coils", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coils = scenario.find("Lightning Coils", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert coils.counter_count(Counter.CHARGE) == 1

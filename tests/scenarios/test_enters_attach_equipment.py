""" "Whenever a `<description>` you control enters, you may attach this
Equipment to it." (CR 701.3a's attach, offered as CR 608.2d's ordinary "you
may") - Quintessential Katana's own trigger.

Unlike Cori-Steel Cutter's "create a token. You may attach this Equipment to
it." (already handled), "it" here is not something the same sentence just
created - it is CR 603.2's own trigger subject, the permanent whose entering
is what triggered the ability at all. The filter ("a Ninja", "a creature ...
with mana value 5 or greater") is no part of this effect body: it lives
entirely in the trigger's own condition, already read by the ordinary
`ENTERS_THE_BATTLEFIELD` machinery.

**Doc Ock's Tentacles** (Marvel Super Heroes, verified Modern/Pioneer/
Standard legal, not a listed tmt card, not in any `decks/*.txt`) - "Whenever
a creature you control with mana value 5 or greater enters, you may attach
this Equipment to it." A mana-value filter rather than a subtype one, proving
the effect reader (not the condition) is what generalises.

CR numbers verified this session with `mise run rules:find`:

- **CR 701.3a** - to attach means to take the Equipment from where it is and
  put it onto that object; it can't be attached to something it couldn't
  equip.
- **CR 301.5c/608.2d** - equipping is an ordinary optional ability effect,
  refused just as freely as any other "you may".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def settle(scenario) -> None:
    """Resolve everything on the stack, and everything that triggers along
    the way - Foot Ninjas' own "you gain 3 life" ETB and Quintessential
    Katana's "you may attach" are two separate triggered abilities off the
    same entering event (CR 603.3b), so one `pass_until_resolved()` only
    ever clears the first of them."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _katana_board(hand: list[str], *, extra_land: str | None = None) -> Scenario:
    lands = ["Plains"] * 6
    if extra_land:
        lands.append(extra_land)
    return (
        Scenario()
        .player("alice", hand=hand, battlefield=["Quintessential Katana", *lands])
        .player("bob")
    )


def test_a_ninja_entering_may_be_equipped():
    scenario = _katana_board(["Foot Ninjas"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    katana = scenario.find("Quintessential Katana", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Quintessential Katana")

    scenario.cast_and_resolve("Foot Ninjas", *scenario.untapped_sources(*["Plains"] * 6))
    settle(scenario)
    ninjas = scenario.find("Foot Ninjas", Zone.BATTLEFIELD, "alice")

    assert katana.attached_to == ninjas.id
    assert scenario.game.power_of(ninjas) == 6  # 5/5 base +1/+1 from the Equipment


def test_declining_the_may_leaves_it_unattached():
    scenario = _katana_board(["Foot Ninjas"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    katana = scenario.find("Quintessential Katana", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, source="Quintessential Katana")

    scenario.cast_and_resolve("Foot Ninjas", *scenario.untapped_sources(*["Plains"] * 6))
    settle(scenario)

    assert katana.attached_to is None


def test_a_non_ninja_entering_never_offers_the_attach_at_all():
    scenario = _katana_board(["Grizzly Bears"], extra_land="Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    katana = scenario.find("Quintessential Katana", Zone.BATTLEFIELD, "alice")

    (forest,) = scenario.untapped_sources("Forest")
    plains = scenario.untapped_sources(*["Plains"] * 6)[:1]
    scenario.cast_and_resolve("Grizzly Bears", forest, *plains)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    assert scenario.game.pending_triggers == []
    assert katana.attached_to is None
    assert scenario.game.power_of(bears) == 2  # no Equipment bonus


# -- Doc Ock's Tentacles: a second printing, a mana-value filter ------------


def _tentacles_board(hand: list[str], *, land: str = "Forest", count: int = 7) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=hand, battlefield=["Doc Ock's Tentacles", *([land] * count)])
        .player("bob")
    )


def test_a_creature_with_mana_value_five_or_more_may_be_equipped():
    scenario = _tentacles_board(["Craw Wurm"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tentacles = scenario.find("Doc Ock's Tentacles", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Doc Ock's Tentacles")

    scenario.cast_and_resolve("Craw Wurm", *scenario.untapped_sources(*["Forest"] * 6))
    settle(scenario)
    wurm = scenario.find("Craw Wurm", Zone.BATTLEFIELD, "alice")

    assert tentacles.attached_to == wurm.id
    assert scenario.game.power_of(wurm) == 10  # 6/4 base +4/+4 from the Equipment


def test_a_creature_below_the_mana_value_threshold_is_never_offered():
    scenario = _tentacles_board(["Hill Giant"], land="Mountain", count=4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tentacles = scenario.find("Doc Ock's Tentacles", Zone.BATTLEFIELD, "alice")

    scenario.cast_and_resolve("Hill Giant", *scenario.untapped_sources(*["Mountain"] * 4))
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "alice")

    assert scenario.game.pending_triggers == []
    assert tentacles.attached_to is None
    assert scenario.game.power_of(giant) == 3

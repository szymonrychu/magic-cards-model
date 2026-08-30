"""Harness for scenario tests: build a board state, then play it out.

See docs/scenario-tests.md for how to write one. The short version:

    scenario = (
        Scenario()
        .player("alice", library=["Questing Beast"], battlefield=["Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    scenario.draw()
    ...

Every card is a real Scryfall printing loaded from tests/fixtures/cards. To use
a card the pool does not have yet, add its Scryfall json there - do not hand-write
card data, since the point of these tests is that they run against real cards.
"""

from magic_cards_model.machines import Casting, CostPayment, PriorityOutcome, Step, TurnMachine
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.decisions import (
    CardSplit,
    Decision,
    DecisionKind,
    ScriptedAnswer,
)
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import CardState, Color, Game, Player, Zone
from magic_cards_model.models.card_state import TargetRef, counter_state_based_actions
from tests.cards import card_state

#: What a scenario may hand to `targets=`: a permanent, a player, or a
#: username. `TargetRef.coerce` works out which was meant, so a test can write
#: `targets=[bears]` or `targets=["bob"]` and mean the obvious thing.
Target = CardState | Player | str | TargetRef


def mana_from(source: CardState, color: Color | None = None) -> list[Color]:
    """What tapping this source adds to the pool.

    Read off the card's own `{T}: Add ...` text by the ability parser, so Sol
    Ring correctly makes two and a dual land insists the scenario says which
    colour it chose.
    """
    abilities = parse_mana_abilities(source.card)
    if not abilities:
        raise ValueError(f"{source.card.name} has no mana ability")

    if color is not None:
        for ability in abilities:
            try:
                return ability.produces(color)
            except ValueError:
                continue
        raise ValueError(f"{source.card.name} cannot add {color.value}")

    return abilities[0].produces()


class Scenario:
    """Builds a game with a known board state."""

    def __init__(self) -> None:
        self._players: list[Player] = []
        self._battlefield: list[tuple[str, list[str]]] = []
        self._exiled: list[tuple[str, list[str]]] = []
        self._automatic_turn_based_actions = True

    def automatic_turn_based_actions(self) -> "Scenario":
        """Explicitly ask for the turn-based actions. They are on by default."""
        self._automatic_turn_based_actions = True
        return self

    def manual_turn_based_actions(self) -> "Scenario":
        """Stop `advance()` performing each step's turn-based actions (CR 703.3).

        The engine does them by default, because the rules say they happen on
        their own. Turn them off for a scenario that drives one mechanic by
        hand - typically one whose board has a short or empty library, where an
        automatic draw would lose the game at the first `advance()` into the
        draw step (CR 704.5b) and drown the mechanic under test.
        """
        self._automatic_turn_based_actions = False
        return self

    def player(
        self,
        username: str,
        *,
        life: int = 20,
        library: list[str] | None = None,
        hand: list[str] | None = None,
        battlefield: list[str] | None = None,
        graveyard: list[str] | None = None,
        exile: list[str] | None = None,
        sideboard: list[str] | None = None,
    ) -> "Scenario":
        """Add a player, with the cards they start the scenario holding.

        Library order is top-first, so `library=["Questing Beast", "Forest"]`
        draws Questing Beast first.

        `sideboard` is the group of cards this player has **outside the game**
        (CR 400.11a) - the cards CR 103.2a set aside before the game began, and
        the only place a "from outside the game" ability may reach. See
        `models/zone.py` for why that is not an eighth zone.
        """
        player = Player(username=username, life=life)
        for zone, names in (
            (Zone.LIBRARY, library),
            (Zone.HAND, hand),
            (Zone.GRAVEYARD, graveyard),
            (Zone.SIDEBOARD, sideboard),
        ):
            for name in names or []:
                # CR 108.3's owner is stamped by `Player.add` now, which is
                # where a real deck becomes a library too, so a scenario board
                # and a loaded decklist agree about who owns what.
                player.add(card_state(name), zone)

        self._players.append(player)
        self._battlefield.append((username, list(battlefield or [])))
        self._exiled.append((username, list(exile or [])))
        return self

    def build(self) -> "PlayedScenario":
        if not self._players:
            raise ValueError("a scenario needs at least one player")

        game = Game(
            players=self._players,
            automatic_turn_based_actions=self._automatic_turn_based_actions,
        )
        for username, names in self._battlefield:
            for name in names:
                state = card_state(name, Zone.BATTLEFIELD, controller=username, owner=username)
                game.battlefield.append(state)
        for username, names in getattr(self, "_exiled", []):
            for name in names:
                game.exile.append(card_state(name, Zone.EXILE, controller=username, owner=username))
        return PlayedScenario(game)


class PlayedScenario:
    """A built game, with the moves a scenario needs to drive it."""

    def __init__(self, game: Game) -> None:
        self.game = game

    # -- state ------------------------------------------------------------

    @property
    def turn(self) -> TurnMachine:
        assert self.game.turn is not None
        return self.game.turn

    @property
    def step(self) -> Step:
        return self.turn.step

    def player(self, username: str | None = None) -> Player:
        """A player by name, defaulting to whoever's turn it is."""
        return self.game.player(username) if username else self.game.active_player

    def battlefield_names(self) -> list[str]:
        return [state.name for state in self.game.battlefield]

    def find(self, name: str, zone: Zone, username: str | None = None) -> CardState:
        """The first copy of `name` in `zone`. Raises if it is not there."""
        if zone in self.game.shared_zones:
            candidates = self.game.shared_zones[zone]
        else:
            candidates = self.player(username).cards_in(zone)

        for state in candidates:
            if state.name == name or state.name.startswith(f"{name} //"):
                return state
        raise AssertionError(
            f"{name} is not in {zone.value}; it holds {[s.name for s in candidates]}"
        )

    def zones_containing(self, card_state: CardState) -> list[str]:
        """Every zone in the whole game state that currently holds this object.

        A zone move that only checks the destination passes even when the
        object was left behind in its old zone too - `Game.put_on_stack` once
        had that exact bug for a card cast from a shared zone (an Adventure's
        exiled half, a foretold or plotted card). This is the assertion that
        catches duplication: after any move, `len(zones_containing(x)) == 1`
        should hold, naming shared zones as `"shared:<zone>"` and per-player
        ones as `"<username>:<zone>"` so a duplicate that spans a player zone
        and a shared zone is not mistaken for one hit.
        """
        found = []
        for zone, cards in self.game.shared_zones.items():
            if card_state in cards:
                found.append(f"shared:{zone.value}")
        for player in self.game.players:
            for zone, cards in player.zones.items():
                if card_state in cards:
                    found.append(f"{player.username}:{zone.value}")
        return found

    def creature(self, name: str, username: str | None = None) -> CardState:
        """A creature on the battlefield by name, narrowed to one controller.

        `find(name, Zone.BATTLEFIELD)` searches the shared battlefield, so it
        cannot tell alice's Grizzly Bears from bob's. Combat scenarios almost
        always need to.
        """
        controller = username or self.player().username
        for state in self.game.permanents_controlled_by(controller):
            if state.name == name:
                return state
        raise AssertionError(
            f"{controller} controls no {name}; they control "
            f"{[s.name for s in self.game.permanents_controlled_by(controller)]}"
        )

    def creatures(self, *names: str, username: str | None = None) -> list[CardState]:
        """Distinct creatures matching `names`, in order - two Bears are two objects."""
        controller = username or self.player().username
        available = self.game.permanents_controlled_by(controller)

        picked: list[CardState] = []
        for name in names:
            match = next((s for s in available if s.name == name and s not in picked), None)
            if match is None:
                raise AssertionError(
                    f"{controller} has no spare {name}; "
                    f"remaining: {[s.name for s in available if s not in picked]}"
                )
            picked.append(match)
        return picked

    def untapped_sources(self, *names: str, username: str | None = None) -> list[CardState]:
        """Untapped permanents matching `names`, in the order given.

        Repeating a name picks a different copy each time, so
        `untapped_sources("Forest", "Forest")` returns two distinct Forests.
        """
        controller = username or self.player().username
        available = [
            state for state in self.game.permanents_controlled_by(controller) if state.untapped
        ]

        picked: list[CardState] = []
        for name in names:
            match = next((s for s in available if s.name == name and s not in picked), None)
            if match is None:
                raise AssertionError(
                    f"no untapped {name} available; "
                    f"untapped: {[s.name for s in available if s not in picked]}"
                )
            picked.append(match)
        return picked

    # -- moves ------------------------------------------------------------

    def start_at(self, step: Step) -> Step:
        """Advance to `step`, running the untap step on the way if it is passed."""
        if self.step is Step.UNTAP and step is not Step.UNTAP:
            self.game.untap_step()
        return self.turn.advance_to(step)

    def advance(self, username: str | None = None) -> Step:
        """Advance the turn, as `username`'s own decision (or their controller's).

        Defaults to whoever is actually authorized right now - the active
        player, or the player controlling them under a CR 723 effect - so a
        scenario driving its own turn forward needs no boilerplate. Pass an
        explicit `username` to test the refusal `Game.advance` gives a player
        who is not that authorized decider.
        """
        player = username or self.game.controller_of_player(self.turn.active_player)
        return self.game.advance(player)

    def draw(self, count: int = 1, username: str | None = None) -> list[CardState]:
        return self.player(username).draw(count)

    def turn_based_actions(self) -> None:
        """Run the current step's turn-based actions by hand (CR 703.3).

        For a scenario that wants one step's automatic action without turning
        the whole thing on for the game.
        """
        self.game.turn_based_actions()

    # -- decisions made during resolution (CR 608.2d) -----------------------
    #
    # A resolving spell can ask its controller a question, and there is no
    # player agent to answer it. A scenario answers instead, in advance: the
    # answers queue up on the game and each is matched to the next question of
    # its kind. Nothing here fakes an effect - the engine performs the whole
    # consequence itself - so a scripted answer is staging in exactly the sense
    # a rigged library is.
    #
    # An answer left unqueued falls through to the documented default in
    # `machines/decisions.py`. A scenario that cares says so.

    def _queue(
        self,
        kind: DecisionKind,
        value: object,
        username: str | None,
        source: str | None,
        times: int | None,
    ) -> None:
        self.game.decisions.add(
            ScriptedAnswer(
                kind=kind,
                value=value,
                player=username,
                source=source,
                uses=times,
            )
        )

    def will_take_the_may(
        self,
        taken: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next plain "you may" (CR 608.2d).

        `times=None` answers every one of them for the rest of the game, which
        is what a scenario about a repeated optional trigger wants.
        """
        self._queue(DecisionKind.MAY, taken, username, source, times)

    def will_pay_the_life(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "you may pay N life" (CR 119.4, CR 608.2d).

        Refusing is always legal; paying is not, below the life total, and a
        scenario that asks to pay anyway gets a `ValueError` naming CR 608.2d
        rather than a silent life total going negative.
        """
        self._queue(DecisionKind.PAY_LIFE, paid, username, source, times)

    def will_pay_the_energy(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next fixed-amount "you may pay {E}..."/"...unless you
        pay {E}" (CR 107.14, CR 118.3, CR 608.2d).

        Refusing is always legal; paying is not, below the energy needed, and
        a scenario that asks to pay anyway gets a `ValueError` naming CR 608.2d,
        the same shape `will_pay_the_life` already holds for CR 119.4.
        """
        self._queue(DecisionKind.PAY_ENERGY, paid, username, source, times)

    def will_pay_the_mana_cost(
        self,
        paid: bool = True,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "unless its controller pays {N}" (CR 118.12a, CR
        608.2d) - Censor's and Mystical Dispute's shape.

        Refusing is always legal; paying is not when the pool does not already
        hold that much floating mana - see `DecisionKind.PAY_MANA`'s own
        docstring for why only the floating pool counts.
        """
        self._queue(DecisionKind.PAY_MANA, paid, username, source, times)

    def will_pay_energy_amount(
        self,
        amount: int,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "you may pay any amount of {E}" (CR 107.14, CR
        118.3, CR 608.2d) with exactly `amount`.

        `amount` is validated against however much energy the player actually
        has when asked, not against whatever a scenario expects up front - a
        scripted amount greater than that gets `Game.ask`'s `ValueError`
        naming CR 118.3, the same way an out-of-range `will_pay_the_life`
        would.
        """
        self._queue(DecisionKind.PAY_ENERGY_AMOUNT, amount, username, source, times)

    def will_choose(
        self,
        value: str,
        *,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next "as [this] enters, choose a color/card name/creature
        type" question (CR 614.1c, CR 614.12a) with `value`.

        A color is its letter code (`Color.BLUE.value`, i.e. `"U"`); a card
        name or creature type is the plain string. `source` is the card
        asking, which is how a scenario with several such choices in flight
        tells them apart - the same convention `will_take_the_may` and
        `will_pay_the_life` already use.
        """
        self._queue(DecisionKind.CHOOSE_A_QUALITY, value, username, source, times)

    def will_discard(
        self,
        *cards: CardState,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_CARDS` question - the cleanup discard is the
        first one - with exactly these cards (CR 514.1, CR 701.9b).

        `Game.ask` still checks the answer is the right size and drawn from the
        cards actually offered, so a scenario naming the wrong count or a card
        not in the zone gets `Game.ask`'s `ValueError`, not a silent mismatch.
        """
        self._queue(DecisionKind.CHOOSE_CARDS, tuple(c.id for c in cards), username, None, times)

    def will_choose_cards(
        self,
        *cards: CardState,
        username: str | None = None,
        source: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Answer the next `CHOOSE_CARDS` question with exactly these cards.

        `will_discard` is the same question asked by the cleanup step; this is
        the general one, for a "choose N of these cards" put by a card's own
        text - Karn, the Great Creator's `−2` choosing among the artifact cards
        its controller owns outside the game and face up in exile. `source`
        narrows the answer to the card asking, the way `will_take_the_may`
        already does.
        """
        self._queue(DecisionKind.CHOOSE_CARDS, tuple(c.id for c in cards), username, source, times)

    def scry_keeping_everything_on_top(
        self, *, username: str | None = None, times: int | None = 1
    ) -> None:
        """Bottom nothing on the next scry (CR 701.22a).

        "Put any number of them on the bottom" - none is a number, so this is a
        real answer and not a refusal to answer.
        """
        self._queue(DecisionKind.SCRY, CardSplit(), username, None, times)

    def scry_bottoming(
        self,
        *cards: CardState,
        top_order: list[CardState] | None = None,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Put these cards on the bottom on the next scry (CR 701.22a).

        The cards are named by identity, so a scenario says "bottom *this*
        Island" rather than "bottom the second card". Anything not named stays
        on top, in the order it was looked at unless `top_order` says otherwise
        - "the rest on top of your library in any order".

        Naming a card that is not among the ones looked at is refused, because
        CR 701.22a only lets a player move the cards they looked at.
        """
        self._queue(
            DecisionKind.SCRY,
            CardSplit(
                moved=tuple(state.id for state in cards),
                top_order=None if top_order is None else tuple(state.id for state in top_order),
            ),
            username,
            None,
            times,
        )

    def surveil_to_graveyard(
        self,
        *cards: CardState,
        top_order: list[CardState] | None = None,
        username: str | None = None,
        times: int | None = 1,
    ) -> None:
        """Put these cards into the graveyard on the next surveil (CR 701.25a)."""
        self._queue(
            DecisionKind.SURVEIL,
            CardSplit(
                moved=tuple(state.id for state in cards),
                top_order=None if top_order is None else tuple(state.id for state in top_order),
            ),
            username,
            None,
            times,
        )

    def surveil_keeping_everything_on_top(
        self, *, username: str | None = None, times: int | None = 1
    ) -> None:
        """Put nothing into the graveyard on the next surveil (CR 701.25a)."""
        self._queue(DecisionKind.SURVEIL, CardSplit(), username, None, times)

    def top_of_library(self, count: int = 1, username: str | None = None) -> list[CardState]:
        """The top `count` cards, without looking at them through an effect.

        For asserting where a scry or a surveil left things, and for naming the
        cards a scenario is about to answer a question about.
        """
        return list(self.player(username).library[:count])

    def questions_asked(self) -> list[Decision]:
        """Every question the engine has put to a player, in order.

        The only way to assert that a card asked *nothing*: CR 701.22b's
        "instructed to scry 0, no scry event occurs" and CR 701.25c's surveil
        equivalent are both about a question that was never put.
        """
        return list(self.game.decisions.asked)

    # -- priority ---------------------------------------------------------

    @property
    def priority_holder(self) -> str:
        assert self.game.priority is not None
        return self.game.priority.holder

    def pass_priority(self, username: str | None = None) -> PriorityOutcome:
        """Pass priority for one player. Defaults to whoever holds it."""
        return self.game.pass_priority(username or self.priority_holder)

    def pass_until_resolved(self) -> PriorityOutcome:
        """Every player still in the game passes in turn, resolving the top of the stack."""
        outcome = PriorityOutcome.PASSED
        for _ in range(len(self.game.players_in_game)):
            outcome = self.pass_priority()
            if outcome is not PriorityOutcome.PASSED:
                break
        return outcome

    # -- special actions --------------------------------------------------

    def play_land(
        self, name: str, username: str | None = None, from_zone: Zone = Zone.HAND
    ) -> CardState:
        """Play a land. A special action: no stack, no priority pass.

        `from_zone` is CR 701.18a's "from the zone it's in (usually the hand)":
        an effect can hand out permission to play a land from somewhere else
        (`Game.grant_play_permission` with `PlayAction.PLAY`), and `play_land`
        refuses any other zone without one.
        """
        player = self.player(username)
        land = self.find(name, from_zone, player.username)
        return self.game.play_land(land, player.username)

    # -- combat -----------------------------------------------------------

    def _default_defender(self) -> str:
        """The one opponent of the active player, when a scenario does not say."""
        active = self.player().username
        opponents = [p.username for p in self.game.players_in_game if p.username != active]
        if len(opponents) != 1:
            raise AssertionError(f"say who is being attacked; opponents are {opponents}")
        return opponents[0]

    def attack_with(
        self, *creatures: CardState, defending: CardState | Player | str | None = None
    ) -> None:
        """Declare these creatures as attackers (CR 508.1).

        `defending` is a player, a username, or a planeswalker or battle; it
        defaults to the active player's only opponent. Raises `ValueError` with
        the rule's reason when a declaration is illegal, so a scenario about an
        illegal attack asserts on that message.
        """
        defender = defending if defending is not None else self._default_defender()
        self.game.declare_attackers([(creature, defender) for creature in creatures])

    def can_attack(
        self, creature: CardState, defending: CardState | Player | str | None = None
    ) -> bool:
        defender = defending if defending is not None else self._default_defender()
        return self.game.can_attack(creature, defender)

    def block(self, attacker: CardState, *blockers: CardState) -> None:
        """Block one attacker with these creatures, in damage assignment order.

        Combines with earlier `block` calls, and the whole declaration is
        rechecked each time (CR 509.1), which is what makes a lone blocker on a
        creature with menace illegal.
        """
        pairs = [
            (blocker, attacker_state)
            for attacker_state in self.game.attacking_creatures()
            for blocker in self._blockers_on(attacker_state)
        ]
        pairs += [(blocker, attacker) for blocker in blockers]
        self.game.declare_blockers(pairs)

    def _blockers_on(self, attacker: CardState) -> list[CardState]:
        attack = self.game.combat.attack_by(attacker.id)
        if attack is None:
            return []
        found = (self.game.find_by_id(card_id) for card_id in attack.blockers)
        return [state for state in found if state is not None]

    def no_blocks(self) -> None:
        """The defending player declares no blockers (CR 509.1)."""
        self.game.declare_blockers([])

    def combat_damage(self) -> list[tuple[CardState | Player, int]]:
        """Deal combat damage, first-strike step included (CR 510).

        Returns the assignment as `(target, amount)` pairs, so a scenario can
        assert on how the damage was split rather than only on what died.
        """
        return self.game.combat_damage()

    def attackers(self) -> list[CardState]:
        return self.game.attacking_creatures()

    def blockers(self) -> list[CardState]:
        return self.game.blocking_creatures()

    # -- casting ----------------------------------------------------------

    def pay_with(self, payment: CostPayment, *sources: CardState) -> CostPayment:
        """Tap each source for mana and pay. Returns the settled payment.

        The overflow is left on the payment as `payment.overflow`.
        """
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))
        payment.pay()
        return payment

    def auto_pay(self, payment: CostPayment, username: str | None = None) -> CostPayment:
        """Let the payment solve its own mana, from every permanent `username`
        controls (`CostPayment.auto_tap`), then pay. This is the same
        auto-tap the API uses by default when a player gives no `--sources`.
        """
        controller = username or payment.payer or self.player().username
        payment.auto_tap(self.game.permanents_controlled_by(controller))
        payment.pay()
        return payment

    def put_on_stack(self, casting: Casting) -> CardState:
        """Finish casting and put the spell onto the stack.

        The caster keeps priority afterwards, as the rules give it back to
        whoever just cast something.
        """
        spell = casting.cast()
        on_stack = self.game.put_on_stack(spell, casting.caster)
        self.game.retain_priority(casting.caster)
        return on_stack

    def resolve_top(self):
        """Resolve the top of the stack. Returns a `CardState` or an `AbilityOnStack`."""
        return self.game.resolve_top()

    # -- abilities --------------------------------------------------------

    def stack_names(self) -> list[str]:
        """What is on the stack, bottom first. An ability names its source."""
        return [item.name for item in self.game.stack]

    @property
    def pending_triggers(self) -> list[AbilityOnStack]:
        """Abilities that have triggered but are not on the stack yet (CR 603.3)."""
        return self.game.pending_triggers

    def choose_trigger_targets(self, card_name: str, targets: list[Target]) -> None:
        """Say what a card's triggered ability aims at when it goes on the stack."""
        self.game.choose_trigger_targets(card_name, list(targets))

    def put_onto_battlefield(
        self,
        name: str,
        username: str | None = None,
        from_zone: Zone = Zone.HAND,
        *,
        tapped: bool = False,
    ) -> CardState:
        """Put a card straight onto the battlefield without casting it.

        The Tooth and Nail path: no stack, no cost, no casting event.
        """
        player = self.player(username)
        card = self.find(name, from_zone, player.username)
        return self.game.put_onto_battlefield(card, player.username, tapped=tapped)

    def activate(
        self,
        source: CardState,
        *mana_sources: CardState,
        index: int = 0,
        username: str | None = None,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        targets: list[Target] | None = None,
        color: Color | None = None,
        auto: bool = False,
        x_value: int = 0,
    ) -> AbilityOnStack | None:
        """Activate one of `source`'s abilities, paying with `mana_sources`.

        Returns the ability now on the stack, or None for a mana ability, which
        never goes on the stack at all (CR 605.3b). The activator keeps priority
        afterwards (CR 117.3c), as they do after casting a spell.

        `color` is the colour chosen for a mana ability that offers one - a
        dual land or an "any color" source. That is `game.activate_ability`'s
        own choice of what *this* ability produces, not the mana payment - it
        stays a plain argument even when `auto=True` lets `auto_pay` solve the
        cost of activating it.

        `x_value` is CR 107.3a's X (Fiend Artisan's `{X}{B/G}`), announced
        once here and threaded through both `begin_activating` and
        `activate_ability` - the same value has to reach both, exactly the
        way a spell's `x_value` reaches both `determine_cost` and `cast`.
        """
        controller = username or self.game.controller_of(source).username
        payment = self.game.begin_activating(
            source,
            index,
            controller,
            sacrificing=sacrificing,
            discarding=discarding,
            x_value=x_value,
        )
        if auto:
            payment.auto_tap(self.game.permanents_controlled_by(controller))
        else:
            for mana_source in mana_sources:
                payment.tap_for_mana(mana_source, mana_from(mana_source))
        payment.pay()
        ability = self.game.activate_ability(
            source, index, controller, targets=targets, color=color, x_value=x_value
        )
        self.game.retain_priority(controller)
        return ability

    def why_cannot_activate(
        self, source: CardState, index: int = 0, username: str | None = None
    ) -> str | None:
        return self.game.why_cannot_activate(source, index, username)

    def cast(
        self,
        name: str,
        username: str | None = None,
        from_zone: Zone = Zone.HAND,
        targets: list[Target] | None = None,
    ) -> Casting:
        """Begin casting a card, returning the casting machine mid-announcement.

        Targets may be permanents, players, or usernames, mixed freely - a
        Bolt aimed at a face is `targets=["bob"]`.
        """
        player = self.player(username)
        spell = self.find(name, from_zone, player.username)
        casting = Casting(
            spell=spell,
            caster=player.username,
            origin_zone=from_zone,
            game=self.game,
        )
        if targets is not None:
            casting.choose_targets(targets)
        return casting

    def cast_onto_stack(
        self,
        name: str,
        *sources: CardState,
        username: str | None = None,
        targets: list[Target] | None = None,
        auto: bool = False,
    ) -> CardState:
        """Cast a spell and leave it on the stack, unresolved.

        Use this when the scenario is about what happens while it sits there -
        responses, counterspells, resolution order.

        `auto=True` pays with `auto_pay` instead of `sources` - the same
        auto-tap path the API takes when a player gives no `--sources`.
        """
        casting = self.cast(name, username, targets=targets)
        payment = casting.begin_paying()
        if auto:
            self.auto_pay(payment, username=casting.caster)
        else:
            self.pay_with(payment, *sources)
        return self.put_on_stack(casting)

    # -- state-based actions ----------------------------------------------

    def state_based_actions(self) -> list[CardState]:
        """Check state-based actions, counters included (CR 704.3).

        `Game.check_state_based_actions` covers the CR 704.5 items it can
        express, but nothing in `Game` dispatches the two counter-driven ones -
        annihilation (CR 704.5q) and a planeswalker at zero loyalty
        (CR 704.5i). They are performed here first, the same way this harness
        drives the combat turn-based actions the turn machine does not.

        A creature killed by its -1/-1 counters needs no help: its toughness
        already counts them, so CR 704.5f fires inside `Game`.
        """
        leaving = counter_state_based_actions(self.game.battlefield)
        for state in leaving:
            self.game.destroy(state)
        return leaving + self.game.check_state_based_actions()

    def cast_and_resolve(
        self,
        name: str,
        *sources: CardState,
        username: str | None = None,
        targets: list[Target] | None = None,
        auto: bool = False,
    ) -> CardState:
        """The whole path for a spell nobody responds to.

        Announce it, pay with `sources`, put it on the stack, resolve it.
        Scenarios that care about a step in the middle should drive the parts
        themselves rather than call this. `auto=True` pays with `auto_pay`
        instead - see `cast_onto_stack`.
        """
        self.cast_onto_stack(name, *sources, username=username, targets=targets, auto=auto)
        return self.resolve_top()

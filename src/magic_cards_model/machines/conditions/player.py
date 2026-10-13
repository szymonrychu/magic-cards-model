"""Player-state conditions: hands, graveyards, exile, life totals, poison and
libraries.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps. They
share one grammar rather than one regex per printed sentence:

- a **subject** - "you", "that player"/"they" (the player the trigger event
  names), "defending player", "an opponent"/"a player" (any one of them),
  "each opponent"/"each player" (every one);
- a **count** - "no", "a", "exactly N [or M]", "N or more", "N or fewer",
  "fewer than N", "at least N" - read through `magic_cards_model.numbers`;
- or a **comparison** between players ("more cards in hand than each
  opponent", "the most life or tied for most life").

Card qualities go through `models/game.py`'s own `_card_quality` (a
graveyard card) and `_permanent_quality` (a permanent), never a word list of
this module's own.

Rules verified with `mise run rules:find`:

- CR 402.1: the hand is where a player holds cards that have been drawn.
- CR 404.1: a player's graveyard is their discard pile.
- CR 401.1: each player's deck becomes their library.
- CR 406.1: the exile zone; CR 108.3 makes a card's owner the player who
  started the game with it, which is who "you own a card in exile" asks about.
- CR 103.4 / CR 119.1: "Each player begins the game with a starting life total
  of 20. Some variant games have different starting life totals." - so the
  starting life total is read off `Player.starting_life`, recorded as the
  player is made, never assumed to be 20.
- CR 122.1f: 'A player is "poisoned" if they have one or more poison
  counters.'
- CR 202.3: an object's mana value, which "mana values among cards in your
  graveyard" collects the distinct values of.
- CR 201.2a: two objects have the same name if they have at least one name in
  common; an object with no name has the same name as nothing. CR 709.4: a
  split card outside the stack has both halves' names; CR 715.4: an adventurer
  card outside the stack has only its normal characteristics.
- CR 109.5: "you" is the controller of the triggered ability's source when it
  triggered, or the player who activated the ability.
- CR 506.2 / CR 508.5: the defending player - the nonactive player of a
  two-player combat, or the player an attack names.
- CR 700.7: "this [something]" is that particular object; CR 400.7 makes an
  object that changed zones a new one, so a recheck (CR 608.2a) reads the
  source only while it is still the object the ability came from.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.zone import Zone
    from . import ConditionContext

#: The players a condition can be about, as printed.
_SUBJECT = r"you|that player|they|defending player|an opponent|each opponent|a player|each player"

#: A printed count: "no", "a", "exactly N [or M]", "N or more", "fewer than
#: N", "at least N" - `_quantity_test` reads each one.
_QUANTITY = (
    rf"no|one or more|exactly {COUNT}(?: or {COUNT})?|(?:fewer|less|more|greater) than {COUNT}"
    rf"|at (?:least|most) {COUNT}|{COUNT} or (?:more|greater|fewer|less)|an?"
)

#: A graveyard card's quality: one or more words ("Zombie creature", Tomb
#: Tyrant's own "at least three Zombie creature cards in your graveyard"),
#: or spell mastery's "instant and/or sorcery" (`_card_quality` reads both).
#: A quality word is never one of the connective or counting words these
#: templates print around it, so a multi-word quality cannot swallow "mana
#: values among" (Sanguine Spy) or "instant card and a sorcery" (Flow State).
_QUALITY_WORD = r"(?!(?:among|and|or|an?|cards?|in|with|mana|values?|different)\b)[\w-]+"
_CARD_QUALITY = (
    rf"{_QUALITY_WORD}(?: {_QUALITY_WORD})*(?: and/or {_QUALITY_WORD}(?: {_QUALITY_WORD})*)?"
)

_POSSESSIVE = r"(?:your|their|his or her) "


def _quantity_test(text: str) -> Callable[[int], bool] | None:
    """A printed count as a test on a number, or None when a word in it does
    not parse (never raised)."""
    text = text.strip()
    if text == "no":
        return lambda n: n == 0
    if text in ("a", "an", "one or more"):
        return lambda n: n >= 1
    if match := re.fullmatch(rf"exactly ({COUNT})(?: or ({COUNT}))?", text):
        values = {parse_count(word) for word in match.groups() if word is not None}
        if None in values:
            return None
        return lambda n: n in values
    if match := re.fullmatch(rf"(fewer|less|more|greater) than ({COUNT})", text):
        bound = parse_count(match.group(2))
        if bound is None:
            return None
        if match.group(1) in ("fewer", "less"):
            return lambda n: n < bound
        return lambda n: n > bound
    if match := re.fullmatch(rf"at (least|most) ({COUNT})", text):
        bound = parse_count(match.group(2))
        if bound is None:
            return None
        if match.group(1) == "least":
            return lambda n: n >= bound
        return lambda n: n <= bound
    if match := re.fullmatch(rf"({COUNT}) or (more|greater|fewer|less)", text):
        bound = parse_count(match.group(1))
        if bound is None:
            return None
        if match.group(2) in ("more", "greater"):
            return lambda n: n >= bound
        return lambda n: n <= bound
    return None


def _everyone(context: "ConditionContext") -> list[str]:
    return [player.username for player in context.game.players_in_game]


def _defending_players(context: "ConditionContext") -> list[str]:
    """CR 506.2 / CR 508.5: the defending player the trigger event names, or
    else each player attacked in the current combat."""
    from ..combat import defending_player

    game = context.game
    event = context.event
    if event is not None and event.defender_controller is not None:
        return [event.defender_controller]
    if event is not None and event.defender is not None:
        found = defending_player(game, event.defender)
        return [found] if found is not None else []
    players: list[str] = []
    for attack in game.combat.attacks:
        found = defending_player(game, attack.defender)
        if found is not None and found not in players:
            players.append(found)
    return players


def _players(context: "ConditionContext", subject: str) -> tuple[list[str], bool]:
    """Who `subject` names, and whether the condition must hold for every one
    of them (True) or for any one (False). A subject that names one player
    ("you", "that player", "defending player") and finds nobody - no trigger
    event, no combat - comes back empty, which every reader answers False."""
    if subject == "you":
        return [context.controller], True
    if subject in ("that player", "they"):
        player = context.event.player if context.event is not None else None
        return ([player] if player is not None else []), True
    if subject == "defending player":
        return _defending_players(context), True
    everyone = _everyone(context)
    if subject in ("an opponent", "each opponent"):
        opponents = [name for name in everyone if name != context.controller]
        return opponents, subject == "each opponent"
    return everyone, subject == "each player"


def _for(context: "ConditionContext", subject: str, test: Callable[[str], bool]) -> bool:
    players, every = _players(context, subject)
    if not players:
        # "each opponent" of nobody is vacuous; a named player who is not
        # there is simply not holding anything.
        return every and subject in ("each opponent", "each player")
    return all(map(test, players)) if every else any(map(test, players))


def _zone_cards(context: "ConditionContext", username: str, zone: str) -> "list[CardState]":
    player = context.game.player(username)
    if zone == "hand":
        return list(player.hand)
    if zone == "library":
        return list(player.library)
    return list(player.graveyard)


def _stat(context: "ConditionContext", username: str, stat: str) -> int:
    """One player's life, poison counters, or card count in a zone."""
    player = context.game.player(username)
    if stat == "life":
        return player.life
    if stat.startswith("poison"):
        return player.poison
    return len(_zone_cards(context, username, stat.rsplit(" ", 1)[-1]))


# -- a count of cards in a zone ----------------------------------------------


def _player_has_cards(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has <count> [<quality>] cards in <their> hand / library /
    graveyard" - Lavaborn Muse's "that player has two or fewer cards in
    hand", Magus of the Library's "you have exactly seven cards in hand",
    Battle of Wits' "you have 200 or more cards in your library", Pit Keeper's
    "you have four or more creature cards in your graveyard"."""
    from ...models.game import _card_quality

    test = _quantity_test(match.group("quantity"))
    quality = _card_quality(match.group("quality"))
    if test is None or quality is None:
        return False
    zone = match.group("zone")
    return _for(
        context,
        match.group("subject"),
        lambda username: test(
            sum(1 for state in _zone_cards(context, username, zone) if quality(state))
        ),
    )


def _had_cards_in_hand_at_turn_start(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> had <count> cards in hand [at the beginning of this turn]" -
    Mindstorm Crown's two complementary sentences, read off the hand size the
    turn began with (`history.hand_size_at_turn_start`), never the hand as the
    ability resolves."""
    from .history import hand_size_at_turn_start

    test = _quantity_test(match.group("quantity"))
    if test is None:
        return False
    return _for(
        context,
        match.group("subject"),
        lambda username: test(hand_size_at_turn_start(context.game, username)),
    )


def _cards_in_your_zone(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "there is/are <count> [<quality>] cards in your graveyard" and "<count>
    [<quality>] cards are in your graveyard" - Walltop Sentries' "there's a
    Lesson card in your graveyard", Shadowborn Demon's "there are fewer than
    six creature cards in your graveyard"."""
    from ...models.game import _card_quality

    test = _quantity_test(match.group("quantity"))
    quality = _card_quality(match.group("quality"))
    if test is None or quality is None:
        return False
    cards = _zone_cards(context, context.controller, match.group("zone"))
    return test(sum(1 for state in cards if quality(state)))


def _two_card_qualities_in_your_zone(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "there is/are a[n] <quality1> card and a[n] <quality2> card in your
    <zone>" - Flow State's own "If there is an instant card and a sorcery
    card in your graveyard, instead put two of them into your hand".

    Not `_cards_in_your_zone`'s single-quality count: a card is not usually
    both of two distinct card types at once, so "an instant card and a
    sorcery card" is never one predicate to count matches of, but the
    logical AND of two independent existence checks (CR 608.2c's plain
    conjunction), each read the same `_card_quality` any other single
    quality word already is."""
    from ...models.game import _card_quality

    quality1 = _card_quality(match.group("quality1"))
    quality2 = _card_quality(match.group("quality2"))
    if quality1 is None or quality2 is None:
        return False
    cards = _zone_cards(context, context.controller, match.group("zone"))
    return any(quality1(state) for state in cards) and any(quality2(state) for state in cards)


def _mana_values_among(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "there are <count> mana values among [<quality>] cards in your
    graveyard" (Sanguine Spy) - the number of distinct CR 202.3 mana values."""
    from ...models.game import _card_quality

    test = _quantity_test(match.group("quantity"))
    quality = _card_quality(match.group("quality"))
    if test is None or quality is None:
        return False
    graveyard = context.game.player(context.controller).graveyard
    return test(len({state.mana_value for state in graveyard if quality(state)}))


def _owns_cards_in_exile(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you own <count> [<quality>] cards in exile" (Dreadlight Monstrosity):
    CR 108.3's owner, whoever exiled it."""
    from ...models.game import _card_quality

    test = _quantity_test(match.group("quantity"))
    quality = _card_quality(match.group("quality"))
    if test is None or quality is None:
        return False
    exile = context.game.exile
    return _for(
        context,
        match.group("subject"),
        lambda username: test(
            sum(1 for state in exile if state.owner == username and quality(state))
        ),
    )


# -- life and poison ------------------------------------------------------------


def _player_has_life(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has <count> life" - Felidar Sovereign's "you have 40 or more
    life", Near-Death Experience's "exactly 1 life", Cryptolith Fragment's
    "each player has 10 or less life"."""
    test = _quantity_test(match.group("quantity"))
    if test is None:
        return False
    return _for(context, match.group("subject"), lambda name: test(_stat(context, name, "life")))


def _starting_life(context: "ConditionContext", username: str) -> int:
    return context.game.player(username).starting_life


def _life_against_starting(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has at least N life more than your starting life total"
    (Speaker of the Heavens, Angel of Destiny): the difference between the
    life total and CR 103.4's starting life total, compared as printed."""
    test = _quantity_test(match.group("quantity"))
    if test is None:
        return False
    more = match.group("direction") == "more"

    def holds(username: str) -> bool:
        difference = _stat(context, username, "life") - _starting_life(context, username)
        return test(difference if more else -difference)

    return _for(context, match.group("subject"), holds)


#: "your life total" and its siblings, as the subject each names.
_LIFE_TOTAL_OWNER = {
    "your": "you",
    "their": "that player",
    "that player's": "that player",
    "defending player's": "defending player",
    "an opponent's": "an opponent",
    "each opponent's": "each opponent",
    "a player's": "a player",
    "each player's": "each player",
}


def _life_total_is(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "your life total is less than 7" (Elderscale Wurm), "your life total
    is less than your starting life total" (Resolute Archangel, CR 103.4) and
    "... greater than or equal to your starting life total" (Happily Ever
    After, Path of Bravery)."""
    subject = _LIFE_TOTAL_OWNER[match.group("owner")]
    direction = match.group("direction")
    number = match.group("number")
    bound = parse_count(number) if number is not None else None
    if number is not None and bound is None:
        return False

    or_equal = match.group("or_equal") is not None

    def holds(username: str) -> bool:
        life = _stat(context, username, "life")
        against = bound if bound is not None else _starting_life(context, username)
        if or_equal and life == against:
            return True
        if direction in ("less", "fewer"):
            return life < against
        if direction in ("more", "greater"):
            return life > against
        return life == against

    return _for(context, subject, holds)


def _poisoned(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "defending player is poisoned" (Septic Rats) - CR 122.1f: one or more
    poison counters."""
    negated = match.group("negated") is not None
    return _for(
        context,
        match.group("subject"),
        lambda username: (_stat(context, username, "poison") >= 1) != negated,
    )


def _is_the_monarch(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "if you're the monarch" (Grave Venerations), "you aren't the
    monarch" - CR 725.1's designation, `Game.monarch` holding at most one
    username rather than a per-player flag (see that field's own docstring),
    so this reads it against `subject` instead of a per-player stat."""
    negated = match.group("negated") is not None
    return _for(
        context,
        match.group("subject"),
        lambda username: (context.game.monarch == username) != negated,
    )


def _player_has_poison(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has <count> poison counters" (CR 122.1f)."""
    test = _quantity_test(match.group("quantity"))
    if test is None:
        return False
    return _for(context, match.group("subject"), lambda name: test(_stat(context, name, "poison")))


# -- comparisons between players -------------------------------------------


def _stat_name(printed: str) -> str:
    """ "cards in your hand" -> "hand", "poison counters" -> "poison", "life"."""
    if printed.startswith("cards in"):
        return printed.rsplit(" ", 1)[-1]
    return printed.split(" ", 1)[0]


def _more_than(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has more <stat> than <other>" - Kitsune Bonesetter's "you
    have more cards in hand than each opponent", Robber of the Rich's
    "defending player has more cards in hand than you", Sokenzan Renegade's
    "a player has more cards in hand than each other player", Glorious
    Enforcer's "you have more life than an opponent". "More" is strict: a tie
    is not more."""
    stat = _stat_name(match.group("stat"))
    more = match.group("direction") == "more"
    other = match.group("other")

    def beats(mine: str, theirs: str) -> bool:
        a, b = _stat(context, mine, stat), _stat(context, theirs, stat)
        return a > b if more else a < b

    def holds(username: str) -> bool:
        if other == "each other player":
            rivals, every = [name for name in _everyone(context) if name != username], True
        elif other == "any other player":
            rivals, every = [name for name in _everyone(context) if name != username], False
        else:
            rivals, every = _players(context, other)
            rivals = [name for name in rivals if name != username]
            if not rivals:
                return every and other in ("each opponent", "each player")
        results = [beats(username, rival) for rival in rivals]
        return all(results) if every else any(results)

    return _for(context, match.group("subject"), holds)


def _the_most(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you have the most life or are tied for most life" (Preacher of the
    Schism): the subject's stat against every other player's - strictly
    ahead of each of them, or level with the leader when the tie is printed."""
    stat = _stat_name(match.group("stat"))
    most = match.group("which") == "most"
    tied = match.group("tied") is not None

    def holds(username: str) -> bool:
        mine = _stat(context, username, stat)
        others = [_stat(context, name, stat) for name in _everyone(context) if name != username]
        if most:
            return all(mine >= value if tied else mine > value for value in others)
        return all(mine <= value if tied else mine < value for value in others)

    return _for(context, match.group("subject"), holds)


# -- the source's own zone ----------------------------------------------------------


def _still_the_source(context: "ConditionContext") -> "CardState | None":
    """The source, while it is still the object the ability came from (CR
    400.7) - None once it has changed zones since, or when there is none."""
    source = context.source
    if source is None:
        return None
    if context.source_stamp is not None and source.zone_change_stamp != context.source_stamp:
        return None
    return source


def _names_self(context: "ConditionContext", subject: str) -> "CardState | None":
    from ...models.game import _names_the_source

    source = _still_the_source(context)
    if source is None or not _names_the_source(subject, source):
        return None
    return source


def _in_place(context: "ConditionContext", source: "CardState", place: str) -> bool:
    from ...models.zone import Zone

    place = place.strip()
    if place == "on the battlefield":
        return source.zone is Zone.BATTLEFIELD
    if place == "on the stack":
        return source.zone is Zone.STACK
    if place in ("in exile", "exiled"):
        return source.zone is Zone.EXILE
    where, _, zone_word = place.rpartition(" ")
    zone = {"graveyard": Zone.GRAVEYARD, "hand": Zone.HAND, "library": Zone.LIBRARY}[zone_word]
    if source.zone is not zone:
        return False
    if where == "in a":
        return True
    # "your graveyard": the player the condition is asked for; "its owner's":
    # the card's owner - the same pile, since a card only goes to its owner's.
    owner = context.controller if where == "in your" else source.owner
    return any(state.id == source.id for state in _zone_cards(context, owner, zone_word))


def _self_in_zone(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this card is in your graveyard" (Master of Death, Bridge from Below),
    "Firemane Angel is in your graveyard or on the battlefield", "Skyblade's
    Boon is on the battlefield or in your graveyard" - CR 700.7's this
    object, in any one of the places named."""
    source = _names_self(context, match.group("self"))
    if source is None:
        return False
    places = re.split(r" or ", match.group("places"))
    return any(_in_place(context, source, place) for place in places)


def _self_only_card_in_graveyard(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this card is the only creature card in your graveyard" (Nether
    Spirit): it is there, and no other card there has the quality."""
    from ...models.game import _card_quality

    source = _names_self(context, match.group("self"))
    quality = _card_quality(match.group("quality"))
    if source is None or quality is None:
        return False
    if not _in_place(context, source, "in your graveyard") or not quality(source):
        return False
    graveyard = context.game.player(context.controller).graveyard
    return all(state.id == source.id for state in graveyard if quality(state))


# -- "the number of X plus the number of Y is N or greater" ------------------


_COUNTED_PERMANENTS = re.compile(r"(?P<other>other )?(?P<quality>[\w -]+?) you control")
_COUNTED_CARDS = re.compile(
    rf"(?:(?P<quality>{_CARD_QUALITY}) )?cards in {_POSSESSIVE}(?P<zone>graveyard|hand|library)"
)


def _counted(context: "ConditionContext", phrase: str) -> int | None:
    """One "the number of <phrase>": permanents you control with a quality
    (`_permanent_quality`, on the computed board, CR 613.5), "other" leaving
    the source out, or cards with a quality in your zone (`_card_quality`)."""
    from ...models.game import _card_quality, _permanent_quality

    if match := _COUNTED_CARDS.fullmatch(phrase):
        quality = _card_quality(match.group("quality"))
        if quality is None:
            return None
        cards = _zone_cards(context, context.controller, match.group("zone"))
        return sum(1 for state in cards if quality(state))
    if match := _COUNTED_PERMANENTS.fullmatch(phrase):
        permanent_quality = _permanent_quality(match.group("quality"))
        if permanent_quality is None:
            return None
        game = context.game
        board = game.computed_board()
        excluded = context.source.id if match.group("other") and context.source else None
        return sum(
            1
            for state in game.permanents_controlled_by(context.controller)
            if state.id != excluded and permanent_quality(board.of(state))
        )
    return None


def _sum_of_counts(context: "ConditionContext", match: re.Match[str]) -> bool:
    """Cavernous Maw's "the number of other Caves you control plus the number
    of Cave cards in your graveyard is three or greater" - each count read on
    its own, then added. A count whose quality is not read makes the whole
    clause false rather than guessed."""
    test = _quantity_test(match.group("quantity"))
    first = _counted(context, match.group("first"))
    second = _counted(context, match.group("second"))
    if test is None or first is None or second is None:
        return False
    return test(first + second)


# -- "it doesn't have the same name as ..." ----------------------------------


def _names_of(state: "CardState", name: str | None = None) -> set[str]:
    """CR 201.2a / CR 709.4: every name an object has - both halves of a split
    card outside the stack, otherwise the one it has."""
    from ...models.zone import Zone

    printed = name if name is not None else state.name
    if not printed:
        return set()
    layout = str(getattr(state.card, "layout", "") or "").lower()
    if "split" in layout and state.zone is not Zone.STACK and " // " in (state.card.name or ""):
        return {half.strip().lower() for half in state.card.name.split(" // ")}
    return {printed.lower()}


_SAME_NAME_OBJECT = re.compile(
    r"(?P<another>another|an?) (?:(?P<quality>[\w -]+?) you control"
    r"|(?:(?P<card_quality>[\w-]+) )?card in your graveyard)"
)


def _same_name_as(context: "ConditionContext", match: re.Match[str]) -> bool:
    """Guardian Project's "it doesn't have the same name as another creature
    you control or a creature card in your graveyard" (CR 201.2a). "It" is the
    trigger event's subject - the creature that entered - read by last known
    information once it has left; with no event it is the source."""
    from ...models.game import _card_quality, _permanent_quality

    game = context.game
    event = context.event
    subject: CardState | None = None
    name: str | None = None
    if match.group("subject") == "it" and event is not None and event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)
        name = event.subject_name
    else:
        subject = _names_self(context, match.group("subject"))
    if subject is None and name is None:
        return False
    if subject is not None:
        from ...models.zone import Zone

        if subject.zone is Zone.BATTLEFIELD:
            name = game.computed_board().of(subject).name
        names = _names_of(subject, name)
    else:
        names = {name.lower()} if name else set()
    board = game.computed_board()
    shared = False
    for printed in re.split(r" or ", match.group("objects")):
        found = _SAME_NAME_OBJECT.fullmatch(printed.strip())
        if found is None:
            return False
        if found.group("quality") is not None:
            permanent_quality = _permanent_quality(found.group("quality"))
            if permanent_quality is None:
                return False
            excluded = subject.id if subject is not None and found.group("another") else None
            candidates = [
                (state, board.of(state).name)
                for state in game.permanents_controlled_by(context.controller)
                if state.id != excluded and permanent_quality(board.of(state))
            ]
        else:
            card_quality = _card_quality(found.group("card_quality"))
            if card_quality is None:
                return False
            candidates = [
                (state, None)
                for state in game.player(context.controller).graveyard
                if card_quality(state)
            ]
        if any(names & _names_of(state, other) for state, other in candidates):
            shared = True
    return shared != (match.group("negated") is not None)


#: A subject that could be the source's own name or "this <something>" -
#: never a determiner phrase naming some other object, and never a whole
#: compound (a subject with "or"/"and"/"you" in it is two conditions, which
#: the combinator reads half by half).
_SELF = (
    r"(?!(?:enchanted|equipped|target|that|another|each|an?|the|it|there|one|any) )"
    r"(?P<self>(?:(?!\b(?:or|and|you|if|there)\b)[^,.])+?)"
)
_PLACE = (
    r"in (?:your|its owner's|a) (?:graveyard|hand|library)"
    r"|on the battlefield|on the stack|in exile|exiled"
)


_SELF_IN_PLACES = re.compile(
    rf"{_SELF} is (?:still )?(?P<places>(?:{_PLACE})(?: or (?:{_PLACE}))*)"
)
#: Darigaaz Reincarnated's "if this card is exiled with an egg counter on it":
#: the counter rider narrows the condition, it does not move the zone. Read for
#: the zones the source functions in only - the counter itself is judged by the
#: dedicated counter reader, which `_SELF_IN_PLACES` must not shadow.
_SELF_IN_PLACES_WITH_COUNTER = re.compile(
    rf"{_SELF} is (?:still )?(?P<places>(?:{_PLACE})(?: or (?:{_PLACE}))*)"
    r"(?: with (?:an?|\w+) [\w+/-]+ counters? on it)?"
)
_SELF_ONLY_IN_GRAVEYARD = re.compile(
    rf"{_SELF} is the only (?:(?P<quality>{_CARD_QUALITY}) )?card in your graveyard"
)


def _place_zone(place: str) -> "Zone":
    from ...models.zone import Zone

    if place == "on the battlefield":
        return Zone.BATTLEFIELD
    if place in ("in exile", "exiled"):
        return Zone.EXILE
    return {"graveyard": Zone.GRAVEYARD, "hand": Zone.HAND, "library": Zone.LIBRARY}[
        place.rpartition(" ")[2]
    ]


def zones_the_source_names(clause: str, source: "CardState") -> "frozenset[Zone] | None":
    """The zones an intervening if says its own source is in - CR 113.6b's
    "An ability that states which zones it functions in functions only from
    those zones": Master of Death's "if this card is in your graveyard",
    Firemane Angel's "if Firemane Angel is in your graveyard or on the
    battlefield", Nether Spirit's "if this card is the only creature card in
    your graveyard". None when the clause names no place for the source -
    Sanguine Spy's "among cards in your graveyard" counts a pile and says
    nothing about where the Spy itself functions."""
    from ...models.game import _names_the_source
    from ...models.zone import Zone

    text = " ".join(clause.strip().rstrip(".").strip().split()).lower()
    if (match := _SELF_IN_PLACES_WITH_COUNTER.fullmatch(text)) and _names_the_source(
        match.group("self"), source
    ):
        return frozenset(_place_zone(place) for place in match.group("places").split(" or "))
    if (match := _SELF_ONLY_IN_GRAVEYARD.fullmatch(text)) and _names_the_source(
        match.group("self"), source
    ):
        return frozenset({Zone.GRAVEYARD})
    # A conjunction that places the source in one conjunct ("if this card is in
    # your graveyard and it's your turn" - Skyclave Shade): that conjunct is
    # the zone statement, the rest is an ordinary condition.
    if " and " in text:
        head, _, rest = text.partition(" and ")
        return zones_the_source_names(head, source) or zones_the_source_names(rest, source)
    return None


#: The alternatives of a disjunctive restriction: "X or if Y" / "X or Y".
_ALTERNATIVE_JOINER = re.compile(r",? or (?:if )?")
#: One alternative's leading "<self> is <place>", any "and ..." tail after it.
_SELF_IN_PLACE_THEN = re.compile(rf"{_SELF} is (?:still )?(?P<place>{_PLACE})(?: and .+)?")


def zones_the_source_names_any(clause: str, source: "CardState") -> "frozenset[Zone] | None":
    """`zones_the_source_names` for a disjunction each of whose alternatives
    opens by placing the source - Quakebringer's "Quakebringer is on the
    battlefield or if Quakebringer is in your graveyard and you control a
    Giant": CR 113.6b's zones are the union of the places named. None unless
    every alternative names one."""
    from ...models.game import _names_the_source

    whole = zones_the_source_names(clause, source)
    if whole is not None:
        return whole
    text = " ".join(clause.strip().rstrip(".").strip().split()).lower()
    zones = set()
    for alternative in _ALTERNATIVE_JOINER.split(text):
        match = _SELF_IN_PLACE_THEN.fullmatch(alternative.strip())
        if match is None or not _names_the_source(match.group("self"), source):
            return None
        zones.add(_place_zone(match.group("place")))
    return frozenset(zones) if zones else None


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) "
            rf"(?:(?P<quality>{_CARD_QUALITY}) )?cards? in (?:{_POSSESSIVE})?"
            r"(?P<zone>hand|library|graveyard)"
        ),
        _player_has_cards,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) had (?P<quantity>{_QUANTITY}) cards? in "
            rf"(?:{_POSSESSIVE})?hand(?: at the beginning of (?:this|the) turn)?"
        ),
        _had_cards_in_hand_at_turn_start,
    ),
    ConditionReader(
        re.compile(
            rf"there(?:'s| is| are) (?P<quantity>{_QUANTITY}) "
            rf"(?:(?P<quality>{_CARD_QUALITY}) )?cards? in your (?P<zone>graveyard|hand|library)"
        ),
        _cards_in_your_zone,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<quantity>{_QUANTITY}) (?:(?P<quality>{_CARD_QUALITY}) )?cards? "
            r"(?:is|are) in your (?P<zone>graveyard|hand|library)"
        ),
        _cards_in_your_zone,
    ),
    ConditionReader(
        re.compile(
            rf"there (?:is|are) (?P<quantity>{_QUANTITY}) (?:different )?mana values among "
            rf"(?:(?P<quality>{_CARD_QUALITY}) )?cards in your graveyard"
        ),
        _mana_values_among,
    ),
    ConditionReader(
        re.compile(
            rf"there (?:is|are) an? (?P<quality1>{_CARD_QUALITY}) card and an? "
            rf"(?P<quality2>{_CARD_QUALITY}) card in your (?P<zone>graveyard|hand|library)"
        ),
        _two_card_qualities_in_your_zone,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) owns? (?P<quantity>{_QUANTITY}) "
            rf"(?:(?P<quality>{_CARD_QUALITY}) )?cards? in exile"
        ),
        _owns_cards_in_exile,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) life "
            rf"(?P<direction>more|less|fewer) than {_POSSESSIVE}starting life total"
        ),
        _life_against_starting,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) life"),
        _player_has_life,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<owner>{'|'.join(re.escape(owner) for owner in _LIFE_TOTAL_OWNER)}) "
            r"life total is (?:(?P<direction>less|fewer|more|greater) than"
            r"(?P<or_equal> or equal to)?|equal to) "
            rf"(?:(?P<number>{COUNT})|{_POSSESSIVE}starting life total)"
        ),
        _life_total_is,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{_SUBJECT}) (?:is|are) (?P<negated>not )?poisoned"),
        _poisoned,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT})(?:'re|'s|\s+is|\s+are)(?P<negated>n't|\s+not)?"
            r" the monarch"
        ),
        _is_the_monarch,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) poison counters?"
        ),
        _player_has_poison,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) (?:has|have) (?P<direction>more|fewer|less) "
            rf"(?P<stat>life|poison counters|cards in (?:{_POSSESSIVE})?hand"
            rf"|cards in {_POSSESSIVE}(?:graveyard|library)) than "
            rf"(?P<other>{_SUBJECT}|each other player|any other player)"
        ),
        _more_than,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{_SUBJECT}) (?:has|have) the (?P<which>most|least|fewest) "
            r"(?P<stat>life|poison counters|cards in hand)"
            r"(?P<tied> or (?:is|are) tied for (?:the )?(?:most|least|fewest)"
            r"(?: (?:life|poison counters|cards in hand))?)?"
        ),
        _the_most,
    ),
    ConditionReader(_SELF_IN_PLACES, _self_in_zone),
    ConditionReader(_SELF_ONLY_IN_GRAVEYARD, _self_only_card_in_graveyard),
    ConditionReader(
        re.compile(
            r"the number of (?P<first>.+?) plus the number of (?P<second>.+?) "
            rf"is (?P<quantity>{_QUANTITY})"
        ),
        _sum_of_counts,
    ),
    ConditionReader(
        re.compile(
            r"(?P<subject>it|this [a-z]+) (?:(?P<negated>doesn't|does not) have|has) "
            r"the same name as (?P<objects>(?:another|an?) .+)"
        ),
        _same_name_as,
    ),
)

"""Tokens: what one is, how it is created, and when it ceases to exist (CR 111).

Every rule number in this file was looked up with
`knowledge_search(q=..., type="rules")` in the session that wrote it and then
read **in full** out of the 2026-08-19 Comprehensive Rules, because the search
excerpts truncate at roughly 150 characters and CR 111 keeps its operative
clauses in the tail. The load-bearing ones:

- **CR 111.1** - "Some effects put tokens onto the battlefield. A token is a
  marker used to represent any permanent that isn't represented by a card."
- **CR 111.2** - "The player who creates a token is its owner. The token enters
  the battlefield under that player's control."
- **CR 111.3** - "The spell or ability that creates a token may define the values
  of any number of characteristics for the token. This becomes the token's
  'text.' The characteristic values defined this way are **functionally
  equivalent to the characteristic values that are printed on a card**; for
  example, they define the token's copiable values. A token doesn't have any
  characteristics not defined by the spell or ability that created it."

  That sentence is the whole design of this module. A token's stated
  characteristics *are* a printed card's characteristics as far as the rules are
  concerned, so a `TokenDefinition` is turned into a `Card` and a token is a
  `CardState` over it. That is not hand-written card data standing in for a real
  printing - there is no printing to stand in for. CR 111.6 keeps the line
  straight: "A token isn't a card (even if represented by a card that has a
  Magic back...)", which is what `TokenState.token` records.

- **CR 111.4** - "A spell or ability that creates a token sets both its name and
  its subtype(s). If the spell or ability doesn't specify the name of the token,
  its name is the same as its subtype(s) plus the word 'Token.'" So a "1/1 white
  Spirit creature token" is named `Spirit Token`, and Minsc's Boo is named `Boo`
  because the card says so.
- **CR 111.5** - a token whose characteristics a rule or effect forbids from
  entering the battlefield is *not created* at all.
- **CR 111.7** - "A token that's in a zone other than the battlefield ceases to
  exist. This is a state-based action; see rule 704. (Note that if a token
  changes zones, applicable triggered abilities will trigger before the token
  ceases to exist.)" The parenthesis matters: a token's dies trigger *does*
  happen. **CR 704.5d** states the same action from the state-based side: "If a
  token is in a zone other than the battlefield, it ceases to exist."
- **CR 111.8** - "A token that has left the battlefield can't move to another
  zone or come back onto the battlefield. If such a token would change zones, it
  remains in its current zone instead. It ceases to exist the next time
  state-based actions are checked."
- **CR 111.10** - the predefined tokens. Four are needed by the current pool:
  CR 111.10a's Treasure, CR 111.10b's Food, CR 111.10h's Powerstone, and
  CR 111.10k's Monster Role.
- **CR 111.13** - "A copy of a permanent spell becomes a token as it resolves."
  Not the same thing as *creating* a token copy, which is CR 707.2 copying plus
  CR 701.7a creating; the distinction is on `token_copy_of`.
- **CR 110.1** - "A permanent is a card **or token** on the battlefield", which is
  why a token needs no special case anywhere else in the engine.
- **CR 205.2c** - "Tokens have card types even though they aren't cards."
- **CR 109.3** - an object's characteristics are "name, mana cost, color, color
  indicator, card type, subtype, supertype, rules text, abilities, power,
  toughness, loyalty, defense, hand modifier, and life modifier". Rarity and set
  are *not* characteristics, so the values this module puts in those two `Card`
  fields carry no rules meaning.
- **CR 202.3a** - "The mana value of an object with no mana cost is 0."

## Where the rest of each rule lives

Three of the rules above are only half here, because the other half belongs to
`models/game.py` and `models/player.py`:

- **CR 704.5d** is a state-based action, dispatched by
  `Game._state_based_actions_once`, which calls `tokens_that_cease_to_exist`.
- **CR 111.8** needs both halves to agree: `TokenState.move_to` declines to
  change the token's `zone`, and every caller that moves a card between zone
  lists asks `move_refused` first so a refused move is not relisted.
- **CR 701.7b**'s creation event is raised by `create_tokens` and
  `token_copy_of` through `machines/replacement.py`, which is what Doubling
  Season's token half watches.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from pydantic import ConfigDict

from ..snapshot import EngineModel
from .card import Card, Color, Layout, Legalities, Legality, Rarity, Supertype, Type
from .card_state import CardState, CounterKind
from .zone import Zone

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the models
    from .card_state import TargetRef
    from .game import Game

#: A token is not a card, so it is legal in nothing. `Card.legalities` is a
#: deckbuilding field and not a characteristic (CR 109.3), so this is filler.
_NO_LEGALITY = Legalities(
    standard=Legality.NOT_LEGAL, pioneer=Legality.NOT_LEGAL, modern=Legality.NOT_LEGAL
)

#: Types in the order a type line prints them, so a synthesised line reads the
#: way the card that creates the token reads (CR 205.1a).
_TYPE_ORDER: tuple[Type, ...] = (
    Type.KINDRED,
    Type.ARTIFACT,
    Type.ENCHANTMENT,
    Type.LAND,
    Type.CREATURE,
    Type.PLANESWALKER,
    Type.BATTLE,
    Type.INSTANT,
    Type.SORCERY,
)

#: Namespaces `_token_card_id`'s content hash away from `Game._allocate_id`'s
#: own `uuid5(NAMESPACE_OID, f"{game_uid}:{n}")` ids: `game_uid` is always a
#: hyphenated UUID string, which this literal prefix can never equal, so a
#: token's `Card.id` and any `CardState`/effect id minted by the per-game
#: allocator can never collide even by coincidence.
_TOKEN_CARD_ID_PREFIX = "token-card"


def _token_card_id(definition: "TokenDefinition") -> UUID:
    """`Card.id` for a synthesised token, as a pure function of `definition`.

    Deliberately *not* `ids.new_id()`. That allocator is what makes replay
    deterministic (`ids.py`'s own docstring): inside a `Game._id_allocator_
    scope()`, it mints `uuid5(game_uid, objects_created)` - a function of
    *when* something is created, not of *what* it is. That is exactly right
    for a `CardState`'s or a `ContinuousEffect`'s id, which is this engine's
    own object identity and has no content of its own to be a function of.

    A token's `Card` is different: CR 111.3 makes its stated characteristics
    "functionally equivalent to the characteristic values that are printed on
    a card" - its copiable values, the same thing a Scryfall printing's own,
    permanently-fixed id identifies. `machines/abilities.py`'s `_ability_cache`
    and `machines/triggers.py`'s `_activated_abilities_cache` memoise a card's
    parsed abilities keyed on exactly that id, on the documented strength of
    `Card` being immutable so "two different printings ... can never collide".

    Minting a token's `Card.id` from the per-game counter broke that strength:
    two independent decodes of one snapshot share the same `game_uid` and the
    same starting `objects_created`, so the *first* token either one creates
    mints the identical id regardless of what characteristics it was given -
    a Spirit token in one decoded branch and a Goblin token in the other,
    same id, the second's abilities silently served back as the first's from
    the process-global cache (see `tests/test_token_card_id_collision.py`).

    Hashing `definition`'s own fields instead keeps the two guarantees this
    library owes intact where the per-game counter could not: it is still
    fully deterministic (a pure function of content has only one output, so
    two replays from the same decoded state - or two decoded branches that
    happen to create the *same* token - agree without needing to agree on
    `objects_created` first), and it restores the cache's actual precondition
    instead of merely working around its symptom, since two tokens with
    different stated characteristics now always get different ids by
    construction - the same way two different Scryfall printings do. Two
    tokens with the *same* stated characteristics sharing an id is not a bug:
    CR 111.3 makes identical stated characteristics the same copiable values,
    the same as two physical copies of one printing sharing that printing's id.
    """
    return uuid5(NAMESPACE_OID, f"{_TOKEN_CARD_ID_PREFIX}:{definition.model_dump_json()}")


class TokenDefinition(EngineModel):
    """What a spell or ability says a token is (CR 111.3).

    "The spell or ability that creates a token may define the values of any
    number of characteristics for the token. This becomes the token's 'text.'"
    Everything left unset is absent rather than defaulted, because CR 111.3 ends
    "A token doesn't have any characteristics not defined by the spell or ability
    that created it" - a 1/1 green Saproling has no mana cost, no supertypes, no
    rules text and no abilities.

    Frozen, because a definition is the printed text of the effect that creates
    the token and several tokens created by one resolution share it.
    """

    model_config = ConfigDict(frozen=True)

    types: tuple[Type, ...] = (Type.CREATURE,)
    subtypes: tuple[str, ...] = ()
    supertypes: tuple[Supertype, ...] = ()
    colors: tuple[Color, ...] = ()
    """Empty means colorless (CR 105.2). A token has no mana cost, so its colour
    is whatever the creating effect stated and nothing else."""

    power: int | None = None
    toughness: int | None = None

    loyalty: str | None = None
    """The printed loyalty a planeswalker token enters with (CR 306.5b), read
    by `CardState._enter_with_loyalty` exactly as a printed card's own
    `Card.loyalty` is - a string because `Card.loyalty` is one (Scryfall
    leaves room for a `*` characteristic-defining loyalty no token definition
    here actually uses). `None` for a token that is not a planeswalker."""

    name: str | None = None
    """Set only when the card names the token - "create Boo, a legendary 1/1 red
    Hamster creature token" (CR 111.9). Left None, CR 111.4 derives the name."""

    rules_text: str | None = None
    """The abilities the creating effect granted, as they would be printed."""

    keywords: tuple[str, ...] = ()
    """Keyword abilities, held the way a Scryfall printing holds them so that
    everything already reading `Card.keywords` - `machines/combat.py`'s
    `has_keyword` and `machines/abilities.parse_abilities`, for two - sees a
    token's flying or deathtouch.

    A keyword that takes a parameter is named here *and* printed in `rules_text`,
    exactly as a printing carries it: Hyena Umbra's Scryfall object lists
    `Enchant` in `keywords` and prints `Enchant creature` in its oracle text.
    `oracle_text` below does not print such a keyword twice."""

    @property
    def card_name(self) -> str:
        """The token's name (CR 111.4).

        "If the spell or ability doesn't specify the name of the token, its name
        is the same as its subtype(s) plus the word 'Token.'" A token with no
        subtypes and no stated name has nothing to build one out of, so it is
        called `Token`.
        """
        if self.name is not None:
            return self.name
        return " ".join([*self.subtypes, "Token"]).strip()

    @property
    def type_line(self) -> str:
        """The type line these characteristics would print as (CR 205.1a)."""
        left = [supertype.value.capitalize() for supertype in self.supertypes]
        left += [
            card_type.value.capitalize() for card_type in _TYPE_ORDER if card_type in self.types
        ]
        line = " ".join(left)
        return f"{line} — {' '.join(self.subtypes)}" if self.subtypes else line

    @property
    def oracle_text(self) -> str | None:
        """The token's rules text: its keywords, then whatever else it was given.

        Printed the way a real card prints them, so the ability parser reads a
        token's text the same way it reads a printing's. CR 111.3 is the licence:
        the stated characteristics "are functionally equivalent to the
        characteristic values that are printed on a card", so the text has to
        look like printed text or the readers that expect printed text will miss
        it.

        A keyword whose printed form the definition already spells out in
        `rules_text` is not printed a second time. CR 702.5a's "Enchant [object
        or player]" is the case that needs it: the Monster Role names `Enchant`
        as a keyword (CR 111.10k) and prints `Enchant creature` as the line, and
        a Scryfall printing of an Aura carries exactly that pair.
        """
        printed = [line.strip().lower() for line in (self.rules_text or "").splitlines()]
        bare = [
            keyword
            for keyword in self.keywords
            if not any(line.startswith(keyword.lower()) for line in printed)
        ]
        lines = [", ".join(bare)] if bare else []
        if self.rules_text:
            lines.append(self.rules_text)
        return "\n".join(lines) or None

    def to_card(self) -> Card:
        """These characteristics as the object the rest of the engine reads.

        CR 111.3 says a token's stated characteristics are "functionally
        equivalent to the characteristic values that are printed on a card", so
        this is the rule and not a shortcut. `layout` is `Layout.TOKEN`, which is
        both what Scryfall marks a token object with and the marker that survives
        a `model_dump`/`model_validate` round trip - see `is_token`.

        `cmc` is 0 by CR 202.3a, since a token has no mana cost. `rarity` and
        `set` are not characteristics (CR 109.3) and mean nothing here.

        `id` is `_token_card_id`, a pure function of these characteristics -
        deliberately *not* `ids.new_id()`. See that helper's own docstring for
        why: two tokens with different text must never share an id, no matter
        which `Game` or which decoded branch of one asked for them.
        """
        return Card(
            id=_token_card_id(self),
            name=self.card_name,
            type_line=self.type_line,
            mana_cost=None,
            cmc=0.0,
            oracle_text=self.oracle_text,
            colors=list(self.colors),
            color_identity=list(self.colors),
            keywords=list(self.keywords),
            power=None if self.power is None else str(self.power),
            toughness=None if self.toughness is None else str(self.toughness),
            loyalty=self.loyalty,
            layout=Layout.TOKEN,
            legalities=_NO_LEGALITY,
            rarity=Rarity.COMMON,
            set="token",
        )


class TokenState(CardState):
    """One token in a game (CR 111.1).

    A `CardState` over a synthesised `Card`, because CR 110.1 makes a token a
    permanent exactly like a card is one and CR 111.6 says it "is subject to
    anything that affects permanents in general". Everything the engine already
    does to a permanent - entering, tapping, attacking, dying, layers, counters -
    therefore works on a token without a single special case.

    Three things are its own:

    - `token` is `CardState`'s own flag (CR 111.6, CR 108.2b), defaulted to True
      here so a token cannot be built without it. `machines/targeting.py` reads
      the same flag for CR 111.1's "target token" and "target nontoken
      permanent".
    - `state_class` overrides `CardState`'s own default so a decode of this
      class - and only this class, regardless of what `token` says at that
      moment - rebuilds as `TokenState` (`CardState._resolve_token_subclass`'s
      own docstring, and `state_class`'s, have the full story: `token=True`
      or `token=False` on an object that is nonetheless this class, such as a
      copy of a permanent spell on the stack, must not change which Python
      class a decode produces).
    - `move_to` enforces CR 111.8, which nothing else in the engine does.
    """

    token: bool = True
    state_class: Literal["TokenState"] = "TokenState"

    left_the_battlefield: bool = False
    """True once this token has been on the battlefield and gone (CR 111.8).

    Not a rules concept of its own - it is what CR 111.8's "a token that has left
    the battlefield" needs somebody to remember, since the token's current zone
    cannot tell a token that died from one that was never put onto the
    battlefield in the first place.
    """

    def move_to(self, zone: Zone) -> None:
        """CR 111.8: a token that has left the battlefield does not move again.

        "A token that has left the battlefield can't move to another zone or come
        back onto the battlefield. If such a token would change zones, it remains
        in its current zone instead. It ceases to exist the next time state-based
        actions are checked."

        The *first* move off the battlefield is allowed - that is the move that
        makes it a token that has left - and CR 111.7's parenthesis is why it has
        to be: "if a token changes zones, applicable triggered abilities will
        trigger before the token ceases to exist", so a token really does reach
        the graveyard and really does fire its dies trigger.
        """
        if self.left_the_battlefield:
            return
        if self.zone is Zone.BATTLEFIELD and zone is not Zone.BATTLEFIELD:
            self.left_the_battlefield = True
        super().move_to(zone)


def move_refused(state: Any, zone: Zone) -> str | None:
    """Why CR 111.8 refuses to move this object, or None if it does not.

    "A token that has left the battlefield can't move to another zone or come
    back onto the battlefield. If such a token would change zones, it remains in
    its current zone instead. It ceases to exist the next time state-based
    actions are checked."

    `TokenState.move_to` enforces the *token's* half - it declines to change
    `zone` - but a zone is two things in this engine: the token's own `zone`
    attribute and the list it is sitting in. Every caller that moves a card
    between lists asks here first, so the two halves cannot disagree; a token
    that refused the move must not be relisted anywhere, or the game state says
    it is in a zone its own `zone` denies.

    Read through `getattr` rather than `isinstance(state, TokenState)` for the
    same reason `is_token` has two answers: `Game` holds its zones as
    `list[CardState]`, so a token round-tripped through `model_validate` comes
    back as a plain `CardState` and only the field survives.
    """
    if not getattr(state, "left_the_battlefield", False):
        return None
    return (
        f"{getattr(state, 'name', 'a token')} has left the battlefield and cannot move "
        f"to {zone.value} (CR 111.8)"
    )


def is_token(state: Any) -> bool:
    """Whether this object is a token rather than a card (CR 111.1, CR 111.6).

    Two answers, and they agree. `CardState.token` is the direct one, and it is
    what `machines/targeting.py` reads. The `Card.layout` one is the belt to that
    braces: `Game` holds its zones as `list[CardState]`, so a token that has been
    round-tripped through `model_validate` is rebuilt as a plain `CardState` and
    keeps the flag - but a caller that built a permanent from a token's `Card`
    without setting the flag is still caught, because the token's `Card` is
    synthesised with `Layout.TOKEN`, which is both what Scryfall marks a token
    object with and a value no real printing in the pool carries.
    """
    if getattr(state, "token", False):
        return True
    card = getattr(state, "card", None)
    return getattr(card, "layout", None) in (Layout.TOKEN, Layout.DOUBLE_FACED_TOKEN)


# --------------------------------------------------------------------------
# Predefined tokens (CR 111.10)
# --------------------------------------------------------------------------

#: CR 111.10a: "A Treasure token is a colorless Treasure artifact token with
#: '{T}, Sacrifice this token: Add one mana of any color.'"
TREASURE = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Treasure",),
    rules_text="{T}, Sacrifice this token: Add one mana of any color.",
)

#: CR 111.10b: "A Food token is a colorless Food artifact token with '{2}, {T},
#: Sacrifice this token: You gain 3 life.'" - Generous Ent.
FOOD = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Food",),
    rules_text="{2}, {T}, Sacrifice this token: You gain 3 life.",
)

#: CR 111.10f: "A Clue token is a colorless Clue artifact token with '{2},
#: {T}, Sacrifice this token: Draw a card.'" - CR 701.16a's "investigate".
CLUE = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Clue",),
    rules_text="{2}, {T}, Sacrifice this token: Draw a card.",
)

#: CR 111.10h: "A Powerstone token is a colorless Powerstone artifact token
#: with '{T}: Add {C}. This mana can't be spent to cast a nonartifact
#: spell.'" - Cityscape Leveler.
POWERSTONE = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Powerstone",),
    rules_text="{T}: Add {C}. This mana can't be spent to cast a nonartifact spell.",
)

#: CR 111.10k: "A Monster Role token is a colorless Aura Role enchantment token
#: named Monster with enchant creature and 'Enchanted creature gets +1/+1 and has
#: trample.'" The name is stated by the rule, so CR 111.4 does not derive one.
#:
#: `Enchant` is named as a keyword as well as printed, because that is how a
#: printing carries it and because CR 704.5m's reader
#: (`machines/keywords.enchant_restrictions`) finds an enchant ability by asking
#: `machines/abilities.parse_abilities`, which matches keywords against the
#: object's keyword list. A Role whose enchant ability nothing can see is an Aura
#: attached to an object nothing can call legal, and CR 704.5m bins it on sight.
MONSTER_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Monster",
    keywords=("Enchant",),
    rules_text="Enchant creature\nEnchanted creature gets +1/+1 and has trample.",
)

#: CR 111.10j-r: the rest of the CR 111.10 Role family, same shape as Monster
#: above - a colorless Aura Role enchantment token, named by the rule rather
#: than derived (CR 111.4), each granting its own static (and, for Wicked, a
#: triggered) ability to whatever it enchants. Spelled out here rather than
#: waiting for a second named card to need them, because CR 111.10 defines
#: every one of these the instant "Role token" is a keyword this engine reads
#: at all - a card printing a Role this dict doesn't have would otherwise
#: fail closed on a real predefined token the rule already states in full.
CURSED_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Cursed",
    keywords=("Enchant",),
    rules_text="Enchant creature\nEnchanted creature has base power and toughness 1/1.",
)

ROYAL_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Royal",
    keywords=("Enchant",),
    rules_text="Enchant creature\nEnchanted creature gets +1/+1 and has ward {1}.",
)

SORCERER_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Sorcerer",
    keywords=("Enchant",),
    rules_text=(
        "Enchant creature\n"
        'Enchanted creature gets +1/+1 and has "Whenever this creature attacks, scry 1."'
    ),
)

VIRTUOUS_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Virtuous",
    keywords=("Enchant",),
    rules_text="Enchant creature\nEnchanted creature gets +1/+1 for each enchantment you control.",
)

WICKED_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Wicked",
    keywords=("Enchant",),
    rules_text=(
        "Enchant creature\n"
        "Enchanted creature gets +1/+1.\n"
        "When this token is put into a graveyard from the battlefield, each opponent "
        "loses 1 life."
    ),
)

YOUNG_HERO_ROLE = TokenDefinition(
    types=(Type.ENCHANTMENT,),
    subtypes=("Aura", "Role"),
    name="Young Hero",
    keywords=("Enchant",),
    rules_text=(
        "Enchant creature\n"
        'Enchanted creature has "Whenever this creature attacks, if its toughness is 3 '
        'or less, put a +1/+1 counter on it."'
    ),
)

#: CR 111.10v: "A Mutagen token is a colorless Mutagen artifact token with
#: '{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target creature.
#: Activate only as a sorcery.'" - the Teenage Mutant Ninja Turtles set's own
#: predefined token, read the identical data-row way every other CR 111.10
#: entry is: a card that says "create a Mutagen token" needs no parser of its
#: own once this row exists, and every reader that already dispatches off
#: `PREDEFINED` (`_parse_token_clause`'s bare-name branch, `_etb_x_effect_text`'s
#: CR 107.3m substitution, `_parse_variable_count_token_clause`'s "where X is")
#: sees it everywhere a card prints it.
MUTAGEN = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Mutagen",),
    rules_text=(
        "{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target creature. "
        "Activate only as a sorcery."
    ),
)

#: CR 111.10x: "A Heartwood token is a red and green Heartwood artifact token
#: with '{T}: Add {R} or {G}.'" - Reality Fracture's own addition to CR 111.10,
#: read the same way every other predefined token is: as a data row, not a
#: card-specific parser. Aerid Konstrari, Hungering Puppetbeast, and Tenured
#: Tethermage each create one off their own printed text with no new code.
HEARTWOOD = TokenDefinition(
    types=(Type.ARTIFACT,),
    subtypes=("Heartwood",),
    colors=(Color.RED, Color.GREEN),
    rules_text="{T}: Add {R} or {G}.",
)

#: CR 701.71a's own token, minted by the "empower Jace N" keyword action
#: (`machines/effects.empower_jace`) rather than by any printed "create a
#: token" sentence a card carries on its own: "If you don't control a Jace
#: planeswalker token, create a blue Jace planeswalker token with 0 loyalty,
#: '[−1]: Surveil 1,' and '[−3]: Draw a card.'" Scryfall's own `tfra` printing
#: of the token confirms both the name (bare "Jace", not CR 111.4's fallback
#: "Jace Token" - the ability's own wording names it the way CR 111.9 names
#: Boo) and the exact ability wording, minus sign and all, which is what lets
#: `machines/abilities.py`'s ordinary loyalty-cost reader
#: (`_LOYALTY_SYMBOL`) parse the two lines with no code of their own. Not
#: legendary: CR 306.4 retired the planeswalker uniqueness rule, and this
#: printing carries no Legendary supertype, so nothing here needs the legend
#: rule to keep a second one off the battlefield - "if you don't control a
#: Jace planeswalker token" already stops `empower_jace` from creating a
#: second one under ordinary play.
JACE = TokenDefinition(
    types=(Type.PLANESWALKER,),
    subtypes=("Jace",),
    colors=(Color.BLUE,),
    name="Jace",
    loyalty="0",
    rules_text="−1: Surveil 1.\n−3: Draw a card.",
)

#: The predefined tokens this engine knows, by the name a card calls them
#: (CR 111.10). The list in the rules is much longer; these are the ones the
#: card pool reaches for.
PREDEFINED: dict[str, TokenDefinition] = {
    "Treasure": TREASURE,
    "Food": FOOD,
    "Clue": CLUE,
    "Powerstone": POWERSTONE,
    "Mutagen": MUTAGEN,
    "Heartwood": HEARTWOOD,
    "Jace": JACE,
    "Monster": MONSTER_ROLE,
    "Cursed": CURSED_ROLE,
    "Royal": ROYAL_ROLE,
    "Sorcerer": SORCERER_ROLE,
    "Virtuous": VIRTUOUS_ROLE,
    "Wicked": WICKED_ROLE,
    "Young Hero": YOUNG_HERO_ROLE,
}


# --------------------------------------------------------------------------
# Creating them (CR 701.7)
# --------------------------------------------------------------------------


def create_tokens(
    game: "Game",
    definition: TokenDefinition,
    controller: str,
    count: int = 1,
    *,
    tapped: bool = False,
    attacking: "TargetRef | str | Callable[[TokenState], TargetRef | str | None] | None" = None,
    counters: dict[CounterKind, int] | None = None,
    attached_to: CardState | None = None,
) -> list[TokenState]:
    """Create `count` tokens with these characteristics (CR 701.7a, CR 111.2).

    CR 701.7a: "To create one or more tokens with certain characteristics, put
    the specified number of tokens with the specified characteristics onto the
    battlefield." So this is `Game.put_onto_battlefield`, which means a token
    goes through the same replacement effects (CR 701.7b) and fires the same
    enters-the-battlefield triggers (CR 603.6a) any other permanent does.

    CR 111.2 puts it under the creating player's control, and CR 302.6 leaves it
    summoning sick like anything else that just arrived - a token creature cannot
    attack the turn it was created unless it was given haste.

    `attacking` is CR 508.4, and `tapped` with it is Dalkovan Encampment's "tapped
    and attacking": **"Such creatures are 'attacking' but, for the purposes of
    trigger events and effects, they never 'attacked.'"** That whole sentence is
    in the tail `knowledge_search` cuts off, and it is why nothing here emits an
    `ATTACKS` event. CR 508.4c adds that such a creature "isn't affected by
    requirements or restrictions that apply to the declaration of attackers", so
    summoning sickness (CR 302.6) does not stop it either.

    `attacking` may also be a function of the token, asked once per token as
    it enters: CR 508.4 has "its controller [choose] which defending player,
    planeswalker a defending player controls, or battle a defending player
    protects it's attacking as it enters the battlefield (unless the effect
    that put it onto the battlefield specifies what it's attacking)", and a
    function is the only shape that can ask per token after a replacement
    effect has settled how many there are. Returning `None` leaves that token
    not attacking.

    Two ways it does not become an attacker even so, both checked here:
    CR 506.3b, put onto the battlefield attacking "under the control of any
    player except an attacking player"; and CR 506.3c / CR 508.4a, attacking a
    player who is no longer in the game.

    `counters` are put on after the token has arrived, because CR 122.6 counts
    them as counters being put on the object - which is the second event inside
    the first that Doubling Season's counter half watches for.

    **How many** is a replaceable event of its own (CR 701.7b): "If a replacement
    effect applies to a token being created, that effect applies before
    considering any continuous effects that will modify the characteristics of
    that token. If a replacement effect applies to a token entering the
    battlefield, that effect applies after considering any continuous effects
    that will modify the characteristics of that token." The two sentences are
    two different events, and this is the first of them - raised here, before a
    single token has been built, which is what lets Doubling Season double the
    count while the characteristics are still nothing but a `TokenDefinition`.
    The second sentence is the ordinary `ENTERS_BATTLEFIELD` event that
    `Game.put_onto_battlefield` raises below, once per token.

    **What is not modelled**: CR 111.5, "if a spell or ability would create a
    token, but a rule or effect states that a permanent with one or more of that
    token's characteristics can't enter the battlefield, the token is not
    created". That is a check against the rules-modifying continuous effects of
    CR 611.3, which this engine does not have; a token is always created here.
    """
    with game._id_allocator_scope():
        if count <= 0:
            return []

        # Imported here rather than at module scope: `machines/replacement.py` reads
        # `is_token` off this module, so a top-level import would close the cycle.
        from ..machines.replacement import EventKind, ReplaceableEvent, apply_replacements

        creation = ReplaceableEvent(
            kind=EventKind.CREATE_TOKENS,
            player=game.player(controller),  # CR 111.2: the creator is the owner
            amount=count,
            definition=definition,
        )
        apply_replacements(game, creation)
        _note_token_creation(game, controller)
        count = creation.amount
        # CR 111.2 makes the creator the owner; a replacement may still move
        # who controls them (Crafty Cutpurse's "is created under your control
        # instead") without making anyone else their creator.
        owner = controller
        controller = creation.creating_controller or controller
        # A replacement effect may add tokens that are not more of `definition` -
        # Stridehangar Automaton's "those tokens plus an additional 1/1 ... Thopter
        # ... are created instead". CR 614.6 makes that one modified event, so they
        # are created here inside the same call and raise no creation event of
        # their own; a second event would give the same effect a second opportunity
        # against its own addition, which CR 614.5 refuses and which would not
        # terminate.
        extra_definitions = list(creation.extra)
        if count <= 0 and not extra_definitions:
            return []

        # A replacement effect may also replace *what* is created, not just
        # how many - Draconic Visitor's "that many 5/5 red Dragon creature
        # tokens ... are created instead" writes a new `TokenDefinition` onto
        # the event itself (CR 614.6: the modified event is what happens)
        # rather than appending to `extra` the way an additive effect does,
        # so the definition actually built from has to be read back off the
        # event rather than the original parameter. Mirrormind Crown's "that
        # many tokens that are copies of equipped creature" replaces it with a
        # copy instead: the original's printed card is its copiable values
        # (CR 707.2).
        card = (
            creation.copy_of.card
            if creation.copy_of is not None
            else (creation.definition or definition).to_card()
        )
        # CR 603.6a: "Each time an event puts one or more permanents onto the
        # battlefield, all permanents on the battlefield (including the
        # newcomers) are checked for any enters-the-battlefield triggers that
        # match the event" - every token one instruction creates enters in
        # one event, so a "one or more tokens ... enter" trigger (Kambal,
        # Profiteering Mayor) sees all of them as "them". The riders below
        # (attach, counters, attacking) happen once they are all there.
        arrived: list[TokenState] = []
        additions: list[TokenState] = []
        with game.entering_together():
            for _ in range(count):
                token = TokenState(card=card, zone=Zone.STACK, controller=controller, owner=owner)
                # `zone=Zone.STACK` is only where it is *before* it exists: nothing
                # holds it, and `enter_the_battlefield` calls `move_to(BATTLEFIELD)`
                # at once. It is never a token in a zone other than the battlefield
                # for the purposes of CR 111.7, because no state-based action is
                # checked in between (CR 704.3 checks only when a player would get
                # priority).
                game.put_onto_battlefield(token, controller, tapped=tapped)
                arrived.append(token)
            for extra in extra_definitions:
                # A different token with its own stated characteristics (CR
                # 111.3), so none of this call's `tapped`/`attacking`/`counters`/
                # `attached_to` applies to it: those describe how *these* tokens
                # were asked for, and the addition was asked for by somebody
                # else's card.
                addition = TokenState(
                    card=extra.to_card(), zone=Zone.STACK, controller=controller, owner=owner
                )
                game.put_onto_battlefield(addition, controller)
                additions.append(addition)

        created: list[TokenState] = []
        for token in arrived:
            if token.zone is not Zone.BATTLEFIELD:
                # A replacement effect sent it elsewhere (CR 614.6). CR 111.7 will
                # have it cease to exist; it is not attacking and takes no counters.
                created.append(token)
                continue
            if attached_to is not None:
                token.attach_to(attached_to)  # CR 701.3a
            for kind, amount in (counters or {}).items():
                game.add_counters(token, kind, amount)
            if attacking is not None:
                defender = attacking(token) if callable(attacking) else attacking
                if defender is not None:
                    _put_onto_the_battlefield_attacking(game, token, defender)
            created.append(token)
        return created + additions


def create_predefined_tokens(
    game: "Game", name: str, controller: str, count: int = 1, **options: Any
) -> list[TokenState]:
    """Create a token the rules define by name (CR 111.10).

    "Some effects instruct a player to create a predefined token. These effects
    use the definition below to determine the characteristics the token is
    created with." A name the rules do not define raises rather than inventing
    one: CR 111.11 would send an unknown name to the Oracle card reference, which
    this engine has no way to consult at runtime.
    """
    definition = PREDEFINED.get(name)
    if definition is None:
        raise ValueError(f"{name} is not a predefined token this engine knows (CR 111.10)")
    return create_tokens(game, definition, controller, count, **options)


#: The per-turn count (`Game.note_turn_count`) of CR 701.7b token-creation
#: events each player has had, noted once their replacement effects are done -
#: what "the first time you would create one or more tokens each turn"
#: (Mirrormind Crown, `machines/replacement._compile_first_time_token_copies`)
#: asks about.
TOKEN_CREATION_FACT = "token creation"


def _note_token_creation(game: "Game", creator: str) -> None:
    game.note_turn_count(TOKEN_CREATION_FACT, creator)


def copiable_card_with_added_abilities(printed: Card, added: Sequence[str]) -> Card:
    """`printed` plus `added`, as one `Card` - CR 707.9a's added ability.

    CR 707.9a: "Some copy effects cause the copy to gain an ability as part of
    the copying process. This ability becomes part of the copiable values for
    the copy, along with any other abilities that were copied."

    "Part of the copiable values" is the whole reason this returns a new `Card`
    rather than putting the line on `CardState.granted_ability_texts` or
    creating a layer 6 effect. A layer 6 grant (CR 613.1f) is applied *after*
    layer 1 and is not copiable at all, and `granted_ability_texts` is a
    battlefield-static channel reconciled by `machines/layers.
    sync_granted_ability_texts`. Neither is read by `triggered_abilities_of`,
    which parses the object's `Card` - so an added "When this token enters,
    ..." would never trigger. Appending the line to the printed oracle text is
    what CR 707.9a actually describes: the copy's *text* includes it.

    The `Card` this returns is a `model_copy` of a real Scryfall printing with
    a fresh `id` derived from `printed.id` and the new oracle text (CR 108.1
    keeps the oracle text authoritative; the id is this engine's own object
    identity, and two objects with different text must not share one) -
    `_token_card_id`'s own docstring is why this is a content hash rather than
    `ids.new_id()`: two decoded branches adding different lines to a copy of
    the same original must never mint the same id for two different results,
    which the per-game counter cannot promise across branches. Nothing is
    hand-written: every characteristic but the oracle text is the printing's
    own.

    `added` empty returns `printed` unchanged, so a plain CR 707.2 copy pays
    nothing for this rule existing.
    """
    lines = [line for line in (text.strip() for text in added) if line]
    if not lines:
        return printed
    body = "\n".join([*([printed.oracle_text] if printed.oracle_text else []), *lines])
    new_card_id = uuid5(NAMESPACE_OID, f"{_TOKEN_CARD_ID_PREFIX}:{printed.id}:{body}")
    return printed.model_copy(update={"id": new_card_id, "oracle_text": body})


def _type_line_without_legendary(type_line: str) -> str:
    """`type_line` with the legendary supertype (CR 205.4d) taken off its left
    side - CR 707.9b's "except it isn't legendary"."""
    left, dash, right = type_line.partition("\u2014")
    new_left = " ".join(word for word in left.split() if word != "Legendary")
    return f"{new_left} {dash}{right}" if dash else new_left


def _type_line_with_added_creature_type(type_line: str, subtype: str) -> str:
    """`type_line` plus `subtype`, as a creature "in addition to its other
    types" (CR 205.1b) - Astral Dragon's own "except they're 3/3 Dragon
    creatures in addition to their other types" reads a noncreature
    permanent's type line and needs it back with "Creature" added on the left
    of the dash (if it is not there already) and the named subtype added on
    the right, every other printed type and subtype kept exactly as they
    were. "Land" becomes "Land Creature \u2014 Forest Dragon"; "Artifact"
    with no subtype at all becomes "Artifact Creature \u2014 Dragon".

    `subtype` is `""` (never omitted; see `token_copy_of`'s own docstring)
    for Rebuild the City's own "3/3 creatures", which names no subtype at
    all - CR 707.9b's Creature type is still added, only the subtype half
    is skipped, and `""` is deliberately never written to `right_words`,
    or every land copy would carry a stray empty subtype token.
    """
    left, _, right = type_line.partition("\u2014")
    left_words = left.split()
    if "Creature" not in left_words:
        left_words.append("Creature")
    right_words = right.split()
    if subtype and subtype not in right_words:
        right_words.append(subtype)
    new_left = " ".join(left_words)
    return f"{new_left} \u2014 {' '.join(right_words)}" if right_words else new_left


def _type_line_with_creature_types(type_line: str, creature_types: Sequence[str]) -> str:
    """`type_line` with its creature types replaced by `creature_types` (CR
    205.1a: setting a subtype replaces the old subtypes of that kind, and
    only that kind) - Croaking Counterpart's "except it's a 1/1 green Frog".
    Every card type, supertype and non-creature subtype (a land type on Dryad
    Arbor, an artifact type) is kept; "Creature" is added on the left when
    the copied object was not one, since only a creature has creature
    types."""
    from ..data.subtypes import creature_type_vocabulary

    vocabulary = creature_type_vocabulary()
    left, _, right = type_line.partition("\u2014")
    left_words = left.split()
    if "Creature" not in left_words:
        left_words.append("Creature")
    kept = [word for word in right.split() if word not in vocabulary]
    right_words = [*kept, *(subtype for subtype in creature_types if subtype not in kept)]
    new_left = " ".join(left_words)
    return f"{new_left} \u2014 {' '.join(right_words)}" if right_words else new_left


def token_copy_of(
    game: "Game",
    original: CardState,
    controller: str,
    count: int = 1,
    added_abilities: Sequence[str] = (),
    power: int | None = None,
    toughness: int | None = None,
    added_creature_type: str | None = None,
    not_legendary: bool = False,
    colors: Sequence[Color] | None = None,
    creature_types: Sequence[str] | None = None,
    **options: Any,
) -> list[TokenState]:
    """ "Create a token that's a copy of [something]" (CR 701.7a, CR 707.2).

    CR 707.2: "the copy acquires the copiable values of the original object's
    characteristics ... The copiable values are the values derived from the text
    printed on the object ... Other effects (including type-changing and
    text-changing effects), status, counters, and stickers are not copied."

    Sharing the original's `Card` object is exactly that: the `Card` is the
    printed text and nothing else, so the copy gets the name, types, power and
    abilities and gets none of the counters, damage, tapped status or continuous
    effects the original is carrying. It works on a token original too, because
    CR 111.3 makes a token's stated characteristics its copiable values.

    CR 111.4's last example is the naming consequence: a token copy of Doomed
    Dissenter is named Doomed Dissenter, not "Human Token".

    **This is not CR 111.13.** That rule is about a copy of a permanent *spell*,
    which "becomes a token as it resolves" and is explicitly "not 'created' for
    the purposes of any replacement effects or triggered abilities that refer to
    creating a token". This is a created token and does count.

    A token copy is still a token being created, so CR 701.7b's creation event is
    raised here too and Doubling Season doubles a token copy exactly as it
    doubles any other.

    `added_abilities` is CR 707.9a's "except they have '<ability>'" channel -
    Aggressive Biomancy's "except they have 'When this token enters, it fights
    up to one target creature you don't control.'" Each line becomes part of
    the copy's *copiable values*, not a grant on top of them; see
    `copiable_card_with_added_abilities` for why that distinction decides
    whether the added trigger ever fires.

    `power`/`toughness` is CR 707.9b's other "except" channel ("some copy
    effects modify a characteristic as part of the copying process") -
    Offspring's own "create a token that's a copy of it, except it's 1/1"
    (CR 702.175a). Unlike `added_abilities`, which only ever adds a line,
    this *replaces* the printed values - the copy's copiable P/T is 1/1, not
    "1/1 in addition to its own".

    `added_creature_type` is CR 707.9b again, for the "except they're `<P>`/
    `<T>` [`<subtype>`] creatures in addition to their other types" shape
    (Astral Dragon's own "3/3 Dragon creatures", Rebuild the City's own bare
    "3/3 creatures") - CR 205.1b's "in addition to" is what keeps the
    original's own types and subtypes rather than replacing them, which
    `_type_line_with_added_creature_type` reads off `type_line` directly
    since this is a copiable-values change, not a continuous layer-4 effect
    (`earthbend`/`amass` above use that channel instead, because those
    animate an existing permanent rather than build a token's own printed
    text). `None` means no type change at all; `""` still adds CR 707.9b's
    Creature type with no named subtype, the shape Rebuild the City prints -
    a real, distinct value from "no exception clause was printed", not an
    edge case squeezed into `None`.

    `not_legendary` is CR 707.9b once more - "except the tokens aren't
    legendary" (The Notary Hobbits, Impostor Syndrome, Multiversal
    Incursion): the legendary supertype is taken off the copiable type line,
    so the copy is never subject to the legend rule alongside its original.

    `colors` and `creature_types` are CR 707.9b's *replacing* exception -
    Croaking Counterpart's "except it's a 1/1 green Frog": the copiable colour
    is set to exactly `colors` and the creature types to exactly
    `creature_types` (CR 205.1a), every other copiable value kept.

    **Not modelled**: CR 707.2's "as ... enters" power-and-toughness setting
    (a *different* rule from the "except" override above - that one reads a
    characteristic off the object as it arrives, this one is stated by the
    copy effect itself) and face-down status, and CR 111.12's "a copy of a
    nonexistent object" - the caller has an object in hand, so there is
    nothing nonexistent to copy.
    """
    with game._id_allocator_scope():
        if count <= 0:
            return []
        from ..machines.replacement import EventKind, ReplaceableEvent, apply_replacements

        creation = ReplaceableEvent(
            kind=EventKind.CREATE_TOKENS,
            player=game.player(controller),
            amount=count,
            # No `TokenDefinition` here: a token copy's characteristics are the
            # original's copiable values (CR 707.2), not a set of values some
            # effect stated (CR 111.3). `card` carries the original so a
            # replacement effect that asks *what kind* of token is being created -
            # Stridehangar Automaton's "artifact tokens" - has something to read.
            card=original,
        )
        apply_replacements(game, creation)
        _note_token_creation(game, controller)
        count = creation.amount
        owner = controller  # CR 111.2 - see `create_tokens`
        controller = creation.creating_controller or controller
        extra_definitions = list(creation.extra)
        if creation.copy_of is not None and creation.copy_of is not original:
            # Mirrormind Crown replaced *what* the tokens copy (CR 614.1a): plain
            # copies of the new original, none of this call's own exceptions.
            original = creation.copy_of
            added_abilities = ()
            power = toughness = None
            added_creature_type = None
            not_legendary = False
            colors = creature_types = None

        copiable = copiable_card_with_added_abilities(original.card, added_abilities)
        if (
            power is not None
            or toughness is not None
            or added_creature_type is not None
            or not_legendary
            or colors is not None
            or creature_types is not None
        ):
            update: dict[str, Any] = {}
            if power is not None:
                update["power"] = str(power)
            if toughness is not None:
                update["toughness"] = str(toughness)
            if added_creature_type is not None:
                update["type_line"] = _type_line_with_added_creature_type(
                    copiable.type_line, added_creature_type
                )
            if creature_types is not None:
                update["type_line"] = _type_line_with_creature_types(
                    update.get("type_line", copiable.type_line), creature_types
                )
            if colors is not None:
                update["colors"] = list(colors)
            if copiable.card_faces and (colors is not None or creature_types is not None):
                # A double-faced original reads its characteristics off the
                # face that is up (CR 712.8d), so each face takes the
                # replacing exception too.
                update["card_faces"] = [
                    face.model_copy(
                        update={
                            **({"colors": list(colors)} if colors is not None else {}),
                            **(
                                {
                                    "type_line": _type_line_with_creature_types(
                                        face.type_line, creature_types
                                    )
                                }
                                if creature_types is not None and face.type_line
                                else {}
                            ),
                        }
                    )
                    for face in copiable.card_faces
                ]
            if not_legendary:
                update["type_line"] = " // ".join(
                    _type_line_without_legendary(half)
                    for half in update.get("type_line", copiable.type_line).split(" // ")
                )
                if copiable.card_faces:
                    # A double-faced original's own face type lines are what
                    # its characteristics read (CR 712.8d), so each loses it.
                    update["card_faces"] = [
                        face.model_copy(
                            update={"type_line": _type_line_without_legendary(face.type_line)}
                        )
                        if face.type_line
                        else face
                        for face in update.get("card_faces", copiable.card_faces)
                    ]
            new_card_id = uuid5(
                NAMESPACE_OID,
                f"{_TOKEN_CARD_ID_PREFIX}:{copiable.id}:pt:{power}/{toughness}:type:{added_creature_type}"
                + (":nonlegendary" if not_legendary else "")
                + (f":colors:{''.join(c.value for c in colors)}" if colors is not None else "")
                + (f":types:{' '.join(creature_types)}" if creature_types is not None else ""),
            )
            copiable = copiable.model_copy(update={"id": new_card_id, **update})

        created: list[TokenState] = []
        with game.entering_together():  # CR 603.6a: one instruction, one enters event
            for _ in range(count):
                copy = TokenState(
                    card=copiable, zone=Zone.STACK, controller=controller, owner=owner
                )
                game.put_onto_battlefield(copy, controller, tapped=bool(options.get("tapped")))
                created.append(copy)
            for extra in extra_definitions:
                addition = TokenState(
                    card=extra.to_card(), zone=Zone.STACK, controller=controller, owner=owner
                )
                game.put_onto_battlefield(addition, controller)
                created.append(addition)
        return created


def _put_onto_the_battlefield_attacking(
    game: "Game", permanent: CardState, attacking: "TargetRef | str"
) -> None:
    """CR 508.4: a creature put onto the battlefield already in combat.

    CR 506.3a keeps a noncreature permanent out of it; CR 506.3b keeps out
    anything not controlled by an attacking player; CR 506.3c and CR 508.4a keep
    out an attack on a player who has left the game. In each case "that creature
    does enter the battlefield, but it's never considered to be an attacking
    creature", which is why every branch here returns rather than raising.

    `permanent.is_creature` reads the printed definition (CR 613.1's starting
    point) - wrong here, because every caller of this function has already
    verified the permanent is on the battlefield (`Game.put_onto_battlefield`
    ran and the zone was checked before this was ever called), which is what
    makes `game.characteristics_of` the CR 613.5 answer instead: a
    noncreature token some other permanent's static ability made a creature
    "in addition to its other types" (CR 205.1b) is still a creature for
    CR 506.3a's purposes.

    Despite the name (kept for every existing call site rather than renamed
    for its own sake), `permanent` is any `CardState` on the battlefield, not
    only a `TokenState`: `create_tokens`'s own "enters attacking" option was
    this function's first caller, but a real card returning to the
    battlefield already attacking - a reanimated creature (`machines/effects.
    _parse_return_target_from_graveyard_tapped_and_attacking_clause`) or a
    flickered one (The Neutrinos, TMT) - is the identical CR 508.4 event on a
    non-token object, and nothing below reads a token-only field.
    """
    from ..machines.combat import Attack  # local: combat imports the models
    from .card_state import TargetRef

    if not game.characteristics_of(permanent).is_creature:
        return  # CR 506.3a
    if permanent.controller != game.active_player.username:
        return  # CR 506.3b
    defender = TargetRef.coerce(attacking)
    if defender.is_player and not game.is_in_game(str(defender.username)):
        return  # CR 506.3c, CR 508.4a
    if defender.is_card and game.find_by_id(defender.card_id) is None:  # type: ignore[arg-type]
        return  # CR 506.3c
    # CR 508.8 is a two-clause condition - "If no creatures are declared as
    # attackers **or put onto the battlefield attacking**, skip the declare
    # blockers and combat damage steps" - and this is the second clause. The
    # creature was never *declared* (CR 508.4c), so setting this alongside
    # `declare_attacker` is not a claim that it was; the flag records that
    # CR 508.8's condition was met, which either half of the rule does.
    game.combat.attacked_this_combat = True
    game.combat.attacks.append(Attack(attacker_id=permanent.id, defender=defender))


# --------------------------------------------------------------------------
# Ceasing to exist (CR 111.7, CR 704.5d)
# --------------------------------------------------------------------------


def tokens_that_cease_to_exist(game: "Game") -> list[CardState]:
    """The state-based action of CR 704.5d, performed (CR 111.7).

    "If a token is in a zone other than the battlefield, it ceases to exist."
    Ceasing to exist is not going to a graveyard and not being exiled - the token
    is simply removed from wherever it is and is gone. Returns what went, so a
    caller can report it alongside the permanents CR 704.5f and CR 704.5g took.

    CR 111.7's parenthesis is honoured by *where* this runs rather than by
    anything in it: "if a token changes zones, applicable triggered abilities
    will trigger before the token ceases to exist", and CR 704.3 only checks
    state-based actions when a player would receive priority, by which time
    `Game.put_into_graveyard` has already emitted the dies event.

    `Game._state_based_actions_once` calls this at the **start** of a round, not
    the end, which is CR 704.3 read literally: "the game checks for any of the
    listed conditions for state-based actions, then performs all applicable
    state-based actions simultaneously as a single event". A token that CR 704.5g
    kills in this round was on the battlefield when the conditions were checked,
    so CR 704.5d did not apply to it yet; it applies on the repeat check, which
    CR 704.3 guarantees happens because an action was performed. The final state
    is the same either way, and this ordering is the one the rule describes.
    """
    gone: list[CardState] = []
    battlefield = game.shared_zones[Zone.BATTLEFIELD]
    for zone, cards in game.shared_zones.items():
        if zone is Zone.BATTLEFIELD:
            continue
        gone.extend(_remove_tokens(cards))
    for player in game.players:
        for cards in player.zones.values():
            if cards is battlefield:  # pragma: no cover - players hold no battlefield
                continue
            gone.extend(_remove_tokens(cards))
    return gone


def _remove_tokens(cards: list[Any]) -> list[CardState]:
    """Take every token out of one zone's list, returning them."""
    doomed = [state for state in cards if isinstance(state, CardState) and is_token(state)]
    for state in doomed:
        cards.remove(state)
    return doomed


def tokens_among(permanents: Iterable[CardState]) -> list[CardState]:
    """The tokens in a collection of permanents (CR 111.1).

    Note what does *not* belong here: a token that ceases to exist does not die.
    CR 700.4 makes "dies" mean "is put into a graveyard from the battlefield",
    and that already happened in `Game.put_into_graveyard` before CR 704.5d ran.
    Ceasing to exist is not a zone change and triggers nothing.
    """
    return [state for state in permanents if is_token(state)]

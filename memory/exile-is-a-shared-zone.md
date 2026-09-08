# Exile is a shared zone - never `player.add(state, Zone.EXILE)`

2026-09-07. Devourer of Destiny's first-upkeep trigger ("Exile the rest")
resolved into `Player.zones[Zone.EXILE]`, a per-player pile that does not
exist in the rules. CR 400.1: "There are normally seven zones: library, hand,
battlefield, graveyard, stack, exile, and command ... Each player has their
own library, hand, and graveyard. The other zones are shared by all players."
CR 406.2: "To exile an object is to put it into the exile zone from whatever
zone it's currently in."

The bug was invisible from inside the engine's own tests, because
`Player.cards_in(Zone.EXILE)` is `zones.setdefault(zone, [])` - it happily
returns the bogus pile, and `CardState.zone` reads `EXILE` either way. Two
tests asserted on exactly that read and so pinned the defect. What actually
broke was everything that walks the real zone: `Game.exile`,
`Game.all_targetables` (which walks `shared_zones` for the battlefield and
exile precisely because "`Player.zones` never holds either one"), and the api's
board view - so a player who declined the "you may put one back" saw four
cards leave the top of their library and *nothing* appear in exile, which is
neither of the ability's two legal outcomes.

The doors are `Game.exile_cards` (batch, raises CR 603.2c's one
leaves-a-graveyard event per instruction) and `Game.exile_permanent`. Hand,
library, graveyard and sideboard are the only zones `Player.add`/`Player.move`
may name.

## The full sweep, 2026-09-08

`src/` was swept for every write of a card into a player-scoped shared zone
and for every read of one. **Nine sites**, not the five the first pass listed:

Live defects, all fixed:

1. `machines/opening_hand.py` `_gemstone_caverns_rider` - the exiled card went
   into a pile of its holder's own and nowhere else. Now `Game.exile_cards`.
2. `machines/keywords.py` `cascade` - `owner.move(state, Zone.EXILE)` **and**
   `game.exile.append(state)`, so every cascaded card was listed in two zones
   at once. When the "you may cast it" was declined, CR 702.85a's bottoming
   emptied the real exile zone and left the phantom one holding cards that
   were on the bottom of a library. Now `Game.exile_cards`.
3. `machines/effects.py` `_possibility_storm_effect` - same double-listing on
   every dug card. Now `Game.exile_cards`.
4. `machines/effects.py` `_parse_outside_the_game_play_clause` (Wish) -
   `Player.bring_into_the_game(chosen, Zone.EXILE)` plus an append.
   `bring_into_the_game` now keeps CR 108.3b's ownership gate and routes the
   move itself through `Game.exile_cards`.
5. `machines/effects.py` `_parse_exile_hand_draw_then_play_until_next_turn_
   clause` (Hex Magic) - same double-listing for the whole hand.
6. `machines/effects.py` `_parse_exile_top_then_play_until_next_turn`
   (Interdimensional Web Watch) - same, for the top two.

Latent, fixed defensively:

7. `machines/effects.py` `_parse_self_return_clause` - "return this card from
   your X to your Y", read generically off the words. `_ZONE_BY_NAME` can
   name the battlefield and exile, so a printing that used either would have
   built a per-player pile of it. Routed to `Game.put_onto_battlefield` /
   `Game.exile_permanent` / `Game.return_to_hand` instead. No printing in the
   pool reaches it (real templating is "to **the** battlefield", which this
   regex does not match), so it has no scenario of its own - writing one
   would need card text nothing prints.
8. `machines/casting.py` `SpecialAction._take_impl` and `exile_adventured` -
   both read `cards_in(card.zone)` for a card whose zone can be a shared one
   (a resolving Adventure is on the stack). Both now use
   `Game._take_out_of_every_zone`, which `exile_adventured` was already half
   doing by hand.
9. `machines/delayed.py` `ReflexiveExileCopiedCard` - read
   `cards_in(zone_when_copied)`, which the copy makes a shared zone. Now
   `Game.exile_permanent`.

False positives, left alone: `machines/keywords.py:699`,
`machines/legal_actions.py:211` and `machines/cost.py:2340` all branch on the
shared zones explicitly before touching `Player`; `machines/effects.py:16517`
and `Game.search_library`'s callers only ever name graveyard, hand or library;
`machines/casting.py`'s announcement rewind already checks
`announced_zone in game.shared_zones`.

## The hole that hid all nine

`Player.cards_in` was `zones.setdefault(zone, [])` - a **read** that minted the
pile it then returned. `Player.zones` is now a `PlayerZones`, a dict that
refuses a shared key on `__getitem__`, `__setitem__`, `__missing__`,
`setdefault` and `update`, and an `AfterValidator` refuses one at decode too
(`dict.__init__` fills at C level and never goes through `__setitem__`, so
wrapping alone would have let a persisted bogus pile back in). `cards_in`,
`add` and `move` refuse as well - `move` at **both** ends, since a card in a
shared zone is not a player's to lift out either. The refusal is
`models/zone.SharedZoneError`, a `RuntimeError` rather than a `ValueError`
for the same reason `SchemaVersionMismatch` is: `machines/` catches
`ValueError` in dozens of places around effect resolution and would have
turned this into "the effect did nothing".

`get` and `in` are deliberately still allowed: neither mints anything, and
`Zone.EXILE not in player.zones` is the assertion a test wants.

Seven existing tests were repointed at the shared zone - five in
`tests/scenarios/test_opening_hand_actions.py` (including
`test_a_seeded_replay_reproduces_the_same_opening_hand_actions`, which pinned
the Gemstone Caverns bug), one in `test_broodscale_bloodchief_deck.py`, one in
`test_costs.py` whose `all(state.tapped for state in elves)` was passing
vacuously over an empty phantom battlefield. `tests/scenarios/
test_exile_is_a_shared_zone.py` is the new file.

`tests/scenarios/harness.py`'s `zones_containing` /
`assert_in_exactly_one_zone` is the assertion that catches this class - it
names a per-player pile as `"<username>:<zone>"` alongside `"shared:<zone>"`,
so a doubly-listed card shows up as two zones rather than one.

**The api had the same defect.** `magic_cards_model_api.affordances.
_all_targetables` walked `CANDIDATE_ZONES` (battlefield, graveyard, exile)
over `game.shared_zones` **and then again** over every `player.cards_in(...)`,
minting two spurious keys per player on every affordance query - a pure query
mutating the game it was asked about. `Game.targetable_objects` had already
been fixed the same way; the api's copy had drifted.

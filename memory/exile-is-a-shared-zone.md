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

Still wrong at the time of writing, same defect class, other cards:
`machines/opening_hand.py:266` (Gemstone Caverns' rider, and
`test_a_seeded_replay_reproduces_the_same_opening_hand_actions` pins it),
`machines/keywords.py:1794`, `machines/effects.py:4817`, `:18098`, `:19170`.

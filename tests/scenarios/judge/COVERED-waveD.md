# DDR episodes covered - wave D

Staging file for wave D of the DDR conversion loop, to be merged into
`COVERED.md`. Same format; kept separate because several waves ran at once.

This wave worked from the **raw transcripts on disk**
(`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/`) rather than from
`knowledge_search` excerpts, so nothing here was built from a truncated
paraphrase. Every CR number cited in the tests was verified with
`knowledge_search(q="...", type="rules")` in the session that wrote them, and
every card was checked with `resolve_cards` before being added to the pool.

| Episode | Ruling | Where |
|---|---|---|
| DDR#976 | APNAP (CR 101.4): every state-based action is one simultaneous event (CR 704.3), so two players' extra legends are binned by the same check; and CR 603.3b's APNAP trigger ordering starts at the *active* player, not the first seat | `test_judge_apnap.py` (4 passing + xfail on the legend rule never asking its controller which copy to keep) |
| DDR#975 | a draw replacement really applies (`ReplacementKind.DRAW`), but CR 614.5's "each effect gets one opportunity" second copy does not, and neither of the episode's own cards compiles to a replacement at all | `test_judge_draw_replacements.py` (1 passing + 2 xfail) |
| DDR#974 | exchanging life totals with a player who can't gain life: CR 119.7 stops the gain and CR 701.12a/701.12g stop the whole exchange - nothing is modelled, and Screaming Nemesis's "whenever this creature is dealt damage" has no `TriggerEvent` shape either | `test_judge_life_exchange.py` (2 passing + 2 xfail) |
| DDR#973 | mana spent paying a ward trigger (CR 702.21a) is not mana spent to cast the spell (CR 601.2h), so Prismatic Ending's Converge does not count it - the engine gets this right | `test_judge_ward_and_mana_spent.py` (4 passing) |
| DDR#972 | suspending is a special action (CR 116.2f, CR 405.6d) with nothing on the stack to respond to, and a resolved Orim's Chant still stops it through CR 702.62c's "could begin to cast" gate | `test_judge_suspend_special_action.py` (4 passing) |
| DDR#970 | Gollum's "Return this card from your graveyard to your hand" ability functions only in a graveyard (CR 113.6m), so it cannot be activated on the battlefield by sacrificing Gollum to itself | `test_judge_ability_zones.py` (3 passing + xfail on `Game.activate_ability` not enforcing the zone) |
| DDR#969 | Breeding Pool's "as this land enters, you may pay 2 life" (CR 614.1c, CR 614.12a) works both ways; Lakeside Shack's conditional "enters tapped unless a player has 13 or less life" is not modelled, so CR 616.1's single-object scope has nothing to demonstrate | `test_judge_entering_replacements.py` (2 passing + 2 xfail) |
| DDR#968 | drawing from an empty library loses at the next check (CR 121.4, CR 704.5b) and an unpayable cast is reversed with its payments (CR 733.1, CR 733.2); but CR 601.2a's "first moves that card ... to the stack" is not how announcement works here | `test_judge_illegal_play_win.py` (3 passing + xfail); the IPG half is `policy`, below |
| DDR#967 | the cleanup discard to maximum hand size (CR 703.4n, CR 514.1) happens in a step where no player receives priority (CR 514.3), so flash does not help; mayhem (CR 702.187b) is not modelled | `test_judge_cleanup_discard.py` (3 passing + xfail) |
| DDR#31 | modal double-faced cards *can* transform now (CR 712.3) and a single-faced permanent simply does not (CR 701.27c); a back face that is an instant should also do nothing (CR 701.27d) and does not | `test_judge_transform.py` (3 passing + 2 xfail) |
| DDR#966 | Blood Moon reaches only nonbasic *lands*, so a Hydro-Man that is still a creature is untouched, and a nonbasic land loses its abilities in layer 4 along with its subtypes | `test_judge_blood_moon_layers.py` (4 passing + xfail on Hydro-Man's own type-changing trigger and the CR 613.8a dependency it would create) |

## Policy episodes - no rules test possible

- **DDR#968** (Winning the Game with an Illegal Play) - the episode's actual
  question is an IPG one: is starting a game action you know you cannot finish
  cheating, and what is the infraction and fix. Its answer is that the IPG's
  definition of cheating requires a broken rule and no rule was broken, so
  nothing is done. There is no game state that can hold "was this an
  infraction". The *rules* chain the setup rides on is tested (see the table);
  the policy conclusion is recorded here.
- **DDR#973** (Prismatic Ending vs. Ward) - roughly half the episode is policy:
  regular-REL take-backs, whether the ward trigger was missed, the game-rule
  violation warning to both players, and when a judge should intervene at all.
  None of that is game state. The rules half is a full passing test file.

## Reviewed and skipped this wave

(nothing was skipped; every episode in the slice produced a test file)

## Conflicts between episodes

- **DDR#31 vs. its own earlier version.** The episode is an explicit re-shoot
  of a much older DDR because the rules changed: modal double-faced cards used
  to be unable to transform, and since the Spider-Man set they can (CR 712.3,
  verified this session). Anything in `COVERED.md` written from the older
  ruling is superseded. No existing test in this repo asserted the old
  behaviour, so nothing was rewritten.
- **DDR#973's card name.** The transcript says "Lava Spike Boots"; no such card
  exists. `resolve_cards` and `card_search` identify the real printing as
  **Lavaspur Boots** ("Equipped creature gets +1/+0 and has haste and ward
  {1}"). The test does not use it: this engine reads ward off the printing and
  models no Equipment attachment, so the board uses **Gavony Dawnguard**, a
  real printing with `Ward {1}` and the mana value 3 the episode specifies.
  Nothing in the ruling depends on where the ward came from.

## Engine defects this wave surfaced

Recorded here because each is a live `xfail` with a named cause, not a vague
gap:

1. `Game.activate_ability` ignores `ActivatedAbility.zone`, so a graveyard-only
   ability can be activated from the battlefield. `machines/keywords.
   off_battlefield_activation` enforces CR 113.6m correctly; the two paths
   disagree. (DDR#970)
2. `CardState.transform` turns a permanent into a back face that is an Instant,
   which CR 701.27d / CR 712.10 say must do nothing. (DDR#31)
3. `Casting.cast` does not move the card to the stack at CR 601.2a's
   announcement; it stays in its origin zone until `put_on_stack`. (DDR#968)
4. Only one replacement effect is applied per draw, so CR 614.5's "each effect
   gets one opportunity" is not honoured for a second identical permanent.
   (DDR#975)
5. Lakeside Shack's "enters tapped unless a player has 13 or less life"
   compiles to no replacement effect. (DDR#969)
6. "Whenever this creature is dealt damage" has no `TriggerEvent`, so Screaming
   Nemesis never triggers. (DDR#974)
7. The legend rule (CR 704.5j) never asks its controller which copy to keep, so
   CR 101.4's APNAP ordering of that choice is unobservable. (DDR#976)
8. Mayhem (CR 702.187) parses as a keyword and grants nothing. (DDR#967)

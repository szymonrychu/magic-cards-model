# Scourge (scg)

- Expansion: 044
- Set code: `scg`
- Release date: 2003-05-26
- Cards in scope (Modern/Pioneer/Standard-legal): 24

## Legality

| Format | Legal cards |
|---|---|
| Modern | 24 |
| Pioneer | 5 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 11 | 45.8% |
| Works (untested) | 10 | 41.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 3 | 12.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Decree of Justice | silent | When you cycle this card, you may pay {X}. If you do, create X 1/1 white Soldier creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Frozen Solid | silent | When enchanted creature is dealt damage, destroy it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Zealous Inquisitor | silent | {1}{W}: The next 1 damage that would be dealt to this creature this turn is dealt to target creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dragon Mage | handled | Whenever this creature deals combat damage to a player, each player discards their hand, then draws seven cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dragonstorm | handled | Search your library for a Dragon permanent card, put it onto the battlefield, then shuffle. Storm (When you cast this spell, copy it for each spell cast before  | the engine reads this text and performs it | Y/-/- | not_tested |
| Gilded Light | handled | You gain shroud until end of turn. (You can't be the target of spells or abilities.) Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Hunting Pack | handled | Create a 4/4 green Beast creature token. Storm (When you cast this spell, copy it for each spell cast before it this turn.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Siege-Gang Commander | handled | When this creature enters, create three 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul Collector | handled | Whenever a creature dealt damage by this creature this turn dies, return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Unburden | handled | Target player discards two cards. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Undead Warchief | handled | Zombie spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wing Shards | handled | Target player sacrifices an attacking creature of their choice. Storm (When you cast this spell, copy it for each spell cast before it this turn. You may choose | the engine reads this text and performs it | Y/-/- | not_tested |
| Wirewood Symbiote | handled | Return an Elf you control to its owner's hand: Untap target creature. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>11 cards</summary>

- Call to the Grave
- Carrion Feeder
- Enrage
- Fierce Empath
- Final Punishment
- Form of the Dragon
- Goblin Brigand
- Goblin Warchief
- Rain of Blades
- Twisted Abomination
- Upwelling

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when enchanted creature is dealt damage, destroy it. | 1 | Frozen Solid | scg |
| when you cycle ~, you may pay {M}. if you do, create N N/N white soldier creature tokens. | 1 | Decree of Justice | scg |
| {M}{M}: the next N damage that would be dealt to ~ ~ is dealt to target creature instead. | 1 | Zealous Inquisitor | scg |

## Notes



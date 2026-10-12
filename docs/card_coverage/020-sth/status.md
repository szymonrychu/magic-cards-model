# Stronghold (sth)

- Expansion: 020
- Set code: `sth`
- Release date: 1998-03-02
- Cards in scope (Modern/Pioneer/Standard-legal): 31

## Legality

| Format | Legal cards |
|---|---|
| Modern | 31 |
| Pioneer | 9 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 12 | 38.7% |
| Works (untested) | 11 | 35.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 8 | 25.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Conviction | silent | {W}: Return this Aura to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Duct Crawler | silent | {1}{R}: Target creature can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grave Pact | silent | Whenever a creature you control dies, each other player sacrifices a creature of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rolling Stones | silent | Wall creatures can attack as though they didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sacred Ground | silent | Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Smite | silent | Destroy target blocked creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Spined Sliver | silent | Whenever a Sliver becomes blocked, that Sliver gets +1/+1 until end of turn for each creature blocking it. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Wall of Essence | silent | Whenever this creature is dealt combat damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Evacuation | handled | Return all creatures to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flowstone Shambler | handled | {R}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Foul Imp | handled | When this creature enters, you lose 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Honor Guard | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Megrim | handled | Whenever an opponent discards a card, this enchantment deals 2 damage to that player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Primal Rage | handled | Creatures you control have trample. | the engine reads this text and performs it | Y/-/- | not_tested |
| Revenant | handled | Revenant's power and toughness are each equal to the number of creature cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shard Phoenix | handled | Sacrifice this creature: It deals 2 damage to each creature without flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sift | handled | Draw three cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spike Feeder | handled | This creature enters with two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Blossoms | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>12 cards</summary>

- Bandage
- Dream Prowler
- Ensnaring Bridge
- Flame Wave
- Fling
- Intruder Alarm
- Mana Leak
- Mogg Flunkies
- Mulch
- Overgrowth
- Shock
- Youthful Knight

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| destroy target blocked creature. | 1 | Smite | sth |
| wall creatures can attack as though they didn't have defender. | 1 | Rolling Stones | sth |
| whenever a creature you control dies, each other player sacrifices a creature of their choice. | 1 | Grave Pact | sth |
| whenever a sliver becomes blocked, that sliver gets +N/+N until end of turn for each creature blocking it. | 1 | Spined Sliver | sth |
| whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield. | 1 | Sacred Ground | sth |
| whenever ~ is dealt combat damage, you gain that much life. | 1 | Wall of Essence | sth |
| {M}: return ~ to its owner's hand. | 1 | Conviction | sth |
| {M}{M}: target creature can't block ~ ~. | 1 | Duct Crawler | sth |

## Notes



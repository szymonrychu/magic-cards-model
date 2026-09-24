# Stronghold (sth)

- Expansion: 020
- Set code: `sth`
- Release date: 1998-03-02
- Cards in scope (Modern/Pioneer/Standard-legal): 30

## Legality

| Format | Legal cards |
|---|---|
| Modern | 30 |
| Pioneer | 8 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 9 | 30.0% |
| Partial (unaudited) | 2 | 6.7% |
| Not tested (handled, untested) | 10 | 33.3% |
| Not working (silent / notice / error) | 9 | 30.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Conviction | silent | {W}: Return this Aura to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Duct Crawler | silent | {1}{R}: Target creature can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grave Pact | silent | Whenever a creature you control dies, each other player sacrifices a creature of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Intruder Alarm | silent | Whenever a creature enters, untap all creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rolling Stones | silent | Wall creatures can attack as though they didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sacred Ground | silent | Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Smite | silent | Destroy target blocked creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Spined Sliver | silent | Whenever a Sliver becomes blocked, that Sliver gets +1/+1 until end of turn for each creature blocking it. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Wall of Essence | silent | Whenever this creature is dealt combat damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dream Prowler | unaudited | This creature can't be blocked as long as it's attacking alone. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Mogg Flunkies | unaudited | This creature can't attack or block alone. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Evacuation | handled | Return all creatures to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flowstone Shambler | handled | {R}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Foul Imp | handled | When this creature enters, you lose 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Honor Guard | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Megrim | handled | Whenever an opponent discards a card, this enchantment deals 2 damage to that player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Primal Rage | handled | Creatures you control have trample. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shard Phoenix | handled | Sacrifice this creature: It deals 2 damage to each creature without flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sift | handled | Draw three cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spike Feeder | handled | This creature enters with two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Blossoms | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>9 cards</summary>

- Bandage
- Ensnaring Bridge
- Flame Wave
- Fling
- Mana Leak
- Mulch
- Overgrowth
- Shock
- Youthful Knight

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Destroy target blocked creature. | Smite | 1 |
| {W}: Return this Aura to its owner's hand. | Conviction | 1 |
| {1}{R}: Target creature can't block this creature this turn. | Duct Crawler | 1 |
| This creature can't be blocked as long as it's attacking alone. | Dream Prowler | 1 |
| This creature can't attack or block alone. | Mogg Flunkies | 1 |
| Wall creatures can attack as though they didn't have defender. | Rolling Stones | 1 |
| Whenever a creature enters, untap all creatures. | Intruder Alarm | 1 |
| Whenever a creature you control dies, each other player sacrifices a creature of their choice. | Grave Pact | 1 |
| Whenever a Sliver becomes blocked, that Sliver gets +1/+1 until end of turn for each creature blocking it. | Spined Sliver | 1 |
| Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield. | Sacred Ground | 1 |
| Whenever this creature is dealt combat damage, you gain that much life. | Wall of Essence | 1 |

## Notes



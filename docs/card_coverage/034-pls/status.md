# Planeshift (pls)

- Expansion: 034
- Set code: `pls`
- Release date: 2001-02-05
- Cards in scope (Modern/Pioneer/Standard-legal): 21

## Legality

| Format | Legal cards |
|---|---|
| Modern | 21 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 5 | 23.8% |
| Works (untested) | 12 | 57.1% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 4 | 19.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Quirion Dryad | silent | Whenever you cast a spell that's white, blue, black, or red, put a +1/+1 counter on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shifting Sky | silent | All nonland permanents are the chosen color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sunken Hope | silent | At the beginning of each player's upkeep, that player returns a creature they control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Warped Devotion | silent | Whenever a permanent is returned to a player's hand, that player discards a card. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Diabolic Intent | handled | As an additional cost to cast this spell, sacrifice a creature. Search your library for a card, put that card into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eladamri's Call | handled | Search your library for a creature card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gaea's Might | handled | Domain — Target creature gets +1/+1 until end of turn for each basic land type among lands you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gainsay | handled | Counter target blue spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lord of the Undead | handled | Other Zombie creatures get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Maggot Carrier | handled | When this creature enters, each player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mana Cylix | handled |  |  | Y/-/- | not_tested |
| Mogg Sentry | handled | Whenever an opponent casts a spell, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slay | handled | Destroy target green creature. It can't be regenerated. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Star Compass | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stormscape Familiar | handled | White spells and black spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Terminate | handled | Destroy target creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>5 cards</summary>

- Gaea's Herald
- Meddling Mage
- Orim's Chant
- Thornscape Battlemage
- Voice of All

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| all nonland permanents are the chosen color. | 1 | Shifting Sky | pls |
| at the beginning of each player"..."s hand. | 1 | Sunken Hope | pls |
| whenever a permanent is returned to a player's hand, that player discards a card. | 1 | Warped Devotion | pls |
| whenever you cast a spell that's white, blue, black, or red, put a +N/+N counter on ~. | 1 | Quirion Dryad | pls |

## Notes



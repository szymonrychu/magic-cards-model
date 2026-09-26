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
| Tested | 3 | 14.3% |
| Works (untested) | 10 | 47.6% |
| Partial (unaudited) | 2 | 9.5% |
| Not working | 6 | 28.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Gaea's Might | silent | Domain — Target creature gets +1/+1 until end of turn for each basic land type among lands you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Lord of the Undead | silent | Other Zombie creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quirion Dryad | silent | Whenever you cast a spell that's white, blue, black, or red, put a +1/+1 counter on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shifting Sky | silent | All nonland permanents are the chosen color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sunken Hope | silent | At the beginning of each player's upkeep, that player returns a creature they control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Warped Devotion | silent | Whenever a permanent is returned to a player's hand, that player discards a card. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Gaea's Herald | unaudited | Creature spells can't be countered. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Meddling Mage | unaudited | Spells with the chosen name can't be cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Diabolic Intent | handled | As an additional cost to cast this spell, sacrifice a creature. Search your library for a card, put that card into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eladamri's Call | handled | Search your library for a creature card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gainsay | handled | Counter target blue spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Maggot Carrier | handled | When this creature enters, each player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mana Cylix | handled |  |  | Y/-/- | not_tested |
| Mogg Sentry | handled | Whenever an opponent casts a spell, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slay | handled | Destroy target green creature. It can't be regenerated. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Star Compass | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stormscape Familiar | handled | White spells and black spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Terminate | handled | Destroy target creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Orim's Chant
- Thornscape Battlemage
- Voice of All

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Domain | 1 | Gaea's Might | pls |
| all nonland permanents are the chosen color. | 1 | Shifting Sky | pls |
| at the beginning of each player"..."s hand. | 1 | Sunken Hope | pls |
| creature spells can't be countered. | 1 | Gaea's Herald | pls |
| other zombie creatures get +N/+N. | 1 | Lord of the Undead | pls |
| spells with the chosen name can't be cast. | 1 | Meddling Mage | pls |
| whenever a permanent is returned to a player's hand, that player discards a card. | 1 | Warped Devotion | pls |
| whenever you cast a spell that's white, blue, black, or red, put a +N/+N counter on ~. | 1 | Quirion Dryad | pls |

## Notes



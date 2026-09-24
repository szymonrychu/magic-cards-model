# Journey into Nyx Promos (pjou)

- Expansion: 148
- Set code: `pjou`
- Release date: 2014-04-26
- Cards in scope (Modern/Pioneer/Standard-legal): 10

## Legality

| Format | Legal cards |
|---|---|
| Modern | 10 |
| Pioneer | 10 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 2 | 20.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 7 | 70.0% |
| Not working (silent / notice / error) | 1 | 10.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Scourge of Fleets | silent | When this creature enters, return each creature your opponents control with toughness X or less to its owner's hand, where X is the number of Islands you contro | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dawnbringer Charioteers | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dictate of Kruphix | handled | At the beginning of each player's draw step, that player draws an additional card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dictate of the Twin Gods | handled | If a source would deal damage to a permanent or player, it deals double that damage to that permanent or player instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Doomwake Giant | handled | Constellation — Whenever this creature or another enchantment you control enters, creatures your opponents control get -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eidolon of Blossoms | handled | Constellation — Whenever this creature or another enchantment you control enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spawn of Thraxes | handled | When this creature enters, it deals damage to any target equal to the number of Mountains you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Squelching Leeches | handled | Squelching Leeches's power and toughness are each equal to the number of Swamps you control. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Hall of Triumph
- Heroes' Bane

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| When this creature enters, return each creature your opponents control with toughness X or less to its owner's hand, where X is the number of Islands you contro | Scourge of Fleets | 1 |

## Notes



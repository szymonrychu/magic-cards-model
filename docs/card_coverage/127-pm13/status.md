# Magic 2013 Promos (pm13)

- Expansion: 127
- Set code: `pm13`
- Release date: 2012-07-12
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 1 | 20.0% |
| Not working (silent / notice / error) | 4 | 80.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Cathedral of War | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Magmaquake | silent | Magmaquake deals X damage to each creature without flying and each planeswalker. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mwonvuli Beast Tracker | silent | When this creature enters, search your library for a creature card with deathtouch, hexproof, reach, or trample and reveal it. Shuffle and put that card on top. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Xathrid Gorgon | notice | {2}{B}, {T}: Put a petrification counter on target creature. It gains defender and becomes a colorless artifact in addition to its other types. Its activated ab | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Staff of Nin | handled | At the beginning of your upkeep, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Exalted | Cathedral of War | 1 |
| Magmaquake deals X damage to each creature without flying and each planeswalker. | Magmaquake | 1 |
| {2}{B}, {T}: Put a petrification counter on target creature. It gains defender and becomes a colorless artifact in addition to its other types. Its activated ab | Xathrid Gorgon | 1 |
| When this creature enters, search your library for a creature card with deathtouch, hexproof, reach, or trample and reveal it. Shuffle and put that card on top. | Mwonvuli Beast Tracker | 1 |

## Notes



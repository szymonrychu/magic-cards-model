# Starter 1999 (s99)

- Expansion: 028
- Set code: `s99`
- Release date: 1999-07-01
- Cards in scope (Modern/Pioneer/Standard-legal): 9

## Legality

| Format | Legal cards |
|---|---|
| Modern | 9 |
| Pioneer | 1 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 8 | 88.9% |
| Not working (silent / notice / error) | 1 | 11.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Loyal Sentry | silent | When this creature blocks a creature, destroy that creature and this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Eager Cadet | handled |  |  | Y/-/- | not_tested |
| Goblin Chariot | handled | Haste | machines/combat.py | Y/-/- | not_tested |
| Grim Tutor | handled | Search your library for a card, put that card into your hand, then shuffle. You lose 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sea Eagle | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Silverback Ape | handled |  |  | Y/-/- | not_tested |
| Tidings | handled | Draw four cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Veteran Cavalier | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Vizzerdrix | handled |  |  | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ blocks a creature, destroy that creature and ~. | 1 | Loyal Sentry | s99 |

## Notes



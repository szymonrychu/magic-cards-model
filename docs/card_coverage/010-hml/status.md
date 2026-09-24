# Homelands (hml)

- Expansion: 010
- Set code: `hml`
- Release date: 1995-10-01
- Cards in scope (Modern/Pioneer/Standard-legal): 8

## Legality

| Format | Legal cards |
|---|---|
| Modern | 8 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 5 | 62.5% |
| Not working (silent / notice / error) | 3 | 37.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Giant Oyster | silent | {T}: For as long as this creature remains tapped, target tapped creature doesn't untap during its controller's untap step, and at the beginning of each of your  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sengir Autocrat | silent | When this creature leaves the battlefield, exile all Serf tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Torture | silent | {1}{B}: Put a -1/-1 counter on enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Anaba Bodyguard | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Anaba Shaman | handled | {R}, {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eron the Relentless | handled | {R}{R}{R}: Regenerate Eron. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merchant Scroll | handled | Search your library for a blue instant card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serrated Arrows | handled | This artifact enters with three arrowhead counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| {T}: For as long as this creature remains tapped, target tapped creature doesn't untap during its controller's untap step, and at the beginning of each of your  | Giant Oyster | 1 |
| {1}{B}: Put a -1/-1 counter on enchanted creature. | Torture | 1 |
| When this creature leaves the battlefield, exile all Serf tokens. | Sengir Autocrat | 1 |

## Notes



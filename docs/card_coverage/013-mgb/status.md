# Multiverse Gift Box (mgb)

- Expansion: 013
- Set code: `mgb`
- Release date: 1996-11-01
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 0 | 0.0% |
| Works (untested) | 2 | 66.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ovinomancer | silent | When this creature enters, sacrifice it unless you return three basic lands you control to their owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| King Cheetah | handled | Flash | machines/casting.py (timing) | Y/-/- | not_tested |
| Viashino Sandstalker | handled | At the beginning of the end step, return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ enters, sacrifice it unless you return three basic lands you control to their owner's hand. | 1 | Ovinomancer | mgb |

## Notes



# Conspiracy: Take the Crown (cn2)

- Expansion: 173
- Set code: `cn2`
- Release date: 2016-08-26
- Cards in scope (Modern/Pioneer/Standard-legal): 2

## Legality

| Format | Legal cards |
|---|---|
| Modern | 2 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 0 | 0.0% |
| Works (untested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 50.0% |
| Not working | 1 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Recruiter of the Guard | silent | When this creature enters, you may search your library for a creature card with toughness 2 or less, reveal it, put it into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sanctum Prelate | unaudited | Noncreature spells with mana value equal to the chosen number can't be cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| noncreature spells with mana value equal to the chosen number can't be cast. | 1 | Sanctum Prelate | cn2 |
| when ~ enters, you may search your library for a creature card with toughness N or less, reveal it, put it into your hand, then shuffle. | 1 | Recruiter of the Guard | cn2 |

## Notes



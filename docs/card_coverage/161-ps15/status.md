# San Diego Comic-Con 2015 (ps15)

- Expansion: 161
- Set code: `ps15`
- Release date: 2015-07-09
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 5 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 20.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 0 | 0.0% |
| Not working (silent / notice / error) | 4 | 80.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Chandra, Fire of Kaladesh // Chandra, Roaring Flame | silent | {T}: Chandra deals 1 damage to target player or planeswalker. If Chandra has dealt 3 or more damage this turn, exile her, then return her to the battlefield tra | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kytheon, Hero of Akros // Gideon, Battle-Forged | silent | At end of combat, if Kytheon and at least two other creatures attacked this combat, exile Kytheon, then return him to the battlefield transformed under his owne | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Liliana, Heretical Healer // Liliana, Defiant Necromancer | silent | Whenever another nontoken creature you control dies, exile Liliana, Heretical Healer, then return her to the battlefield transformed under her owner's control.  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nissa, Vastwood Seer // Nissa, Sage Animist | silent | −2: Create Ashaya, the Awoken World, a legendary 4/4 green Elemental creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |

## Fully supported

<details>
<summary>1 cards</summary>

- Jace, Vryn's Prodigy // Jace, Telepath Unbound

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At end of combat, if Kytheon and at least two other creatures attacked this combat, exile Kytheon, then return him to the battlefield transformed under his owne | Kytheon, Hero of Akros // Gideon, Battle-Forged | 1 |
| {T}: Chandra deals 1 damage to target player or planeswalker. If Chandra has dealt 3 or more damage this turn, exile her, then return her to the battlefield tra | Chandra, Fire of Kaladesh // Chandra, Roaring Flame | 1 |
| −2: Create Ashaya, the Awoken World, a legendary 4/4 green Elemental creature token. | Nissa, Vastwood Seer // Nissa, Sage Animist | 1 |
| Whenever another nontoken creature you control dies, exile Liliana, Heretical Healer, then return her to the battlefield transformed under her owner's control.  | Liliana, Heretical Healer // Liliana, Defiant Necromancer | 1 |

## Notes



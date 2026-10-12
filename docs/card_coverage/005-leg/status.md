# Legends (leg)

- Expansion: 005
- Set code: `leg`
- Release date: 1994-06-01
- Cards in scope (Modern/Pioneer/Standard-legal): 29

## Legality

| Format | Legal cards |
|---|---|
| Modern | 29 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 8 | 27.6% |
| Works (untested) | 18 | 62.1% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 3 | 10.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Craw Giant | silent | Rampage | no machine in the engine executes this keyword | Y/-/- | not_working |
| Pendelhaven | silent | {T}: Target 1/1 creature gets +1/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spirit Link | silent | Whenever enchanted creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Avoid Fate | handled | Counter target instant or Aura spell that targets a permanent you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Azure Drake | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Darkness | handled | Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fallen Angel | handled | Sacrifice a creature: This creature gets +2/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flash Counter | handled | Counter target instant spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greed | handled | {B}, Pay 2 life: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Holy Day | handled | Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horror of Horrors | handled | Sacrifice a Swamp: Regenerate target black creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Immolation | handled | Enchanted creature gets +2/-2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jasmine Boreal | handled |  |  | Y/-/- | not_tested |
| Kobold Taskmaster | handled | Other Kobold creatures you control get +1/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moss Monster | handled |  |  | Y/-/- | not_tested |
| Nicol Bolas | handled | At the beginning of your upkeep, sacrifice Nicol Bolas unless you pay {U}{B}{R}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Relic Barrier | handled | {T}: Tap target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Remove Soul | handled | Counter target creature spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sol'kanar the Swamp King | handled | Whenever a player casts a black spell, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tundra Wolves | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Underworld Dreams | handled | Whenever an opponent draws a card, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>8 cards</summary>

- Boomerang
- Divine Offering
- Elven Riders
- Evil Eye of Orms-by-Gore
- Hell's Caretaker
- Pyrotechnics
- Vampire Bats
- Whirling Dervish

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| rampage | 1 | Craw Giant | leg |
| whenever enchanted creature deals damage, you gain that much life. | 1 | Spirit Link | leg |
| {M}: target N/N creature gets +N/+N until end of turn. | 1 | Pendelhaven | leg |

## Notes



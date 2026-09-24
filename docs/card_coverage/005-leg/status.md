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
| Full (handled + tested) | 2 | 6.9% |
| Partial (unaudited) | 2 | 6.9% |
| Not tested (handled, untested) | 18 | 62.1% |
| Not working (silent / notice / error) | 7 | 24.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Avoid Fate | silent | Counter target instant or Aura spell that targets a permanent you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Craw Giant | silent | Rampage | no machine in the engine executes this keyword | Y/-/- | not_working |
| Divine Offering | silent | Destroy target artifact. You gain life equal to its mana value. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kobold Taskmaster | silent | Other Kobold creatures you control get +1/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nicol Bolas | silent | At the beginning of your upkeep, sacrifice Nicol Bolas unless you pay {U}{B}{R}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pendelhaven | silent | {T}: Target 1/1 creature gets +1/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spirit Link | silent | Whenever enchanted creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elven Riders | unaudited | This creature can't be blocked except by Walls and/or creatures with flying. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Evil Eye of Orms-by-Gore | unaudited | Non-Eye creatures you control can't attack. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Azure Drake | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Boomerang | handled | Return target permanent to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darkness | handled | Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fallen Angel | handled | Sacrifice a creature: This creature gets +2/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flash Counter | handled | Counter target instant spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greed | handled | {B}, Pay 2 life: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hell's Caretaker | handled | {T}, Sacrifice a creature: Return target creature card from your graveyard to the battlefield. Activate only during your upkeep. | the engine reads this text and performs it | Y/-/- | not_tested |
| Holy Day | handled | Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horror of Horrors | handled | Sacrifice a Swamp: Regenerate target black creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Immolation | handled | Enchanted creature gets +2/-2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jasmine Boreal | handled |  |  | Y/-/- | not_tested |
| Moss Monster | handled |  |  | Y/-/- | not_tested |
| Relic Barrier | handled | {T}: Tap target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Remove Soul | handled | Counter target creature spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sol'kanar the Swamp King | handled | Whenever a player casts a black spell, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tundra Wolves | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Underworld Dreams | handled | Whenever an opponent draws a card, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Whirling Dervish | handled | At the beginning of each end step, if this creature dealt damage to an opponent this turn, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Pyrotechnics
- Vampire Bats

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, sacrifice Nicol Bolas unless you pay {U}{B}{R}. | Nicol Bolas | 1 |
| Counter target instant or Aura spell that targets a permanent you control. | Avoid Fate | 1 |
| Destroy target artifact. You gain life equal to its mana value. | Divine Offering | 1 |
| Non-Eye creatures you control can't attack. | Evil Eye of Orms-by-Gore | 1 |
| Other Kobold creatures you control get +1/+0. | Kobold Taskmaster | 1 |
| Rampage | Craw Giant | 1 |
| {T}: Target 1/1 creature gets +1/+2 until end of turn. | Pendelhaven | 1 |
| This creature can't be blocked except by Walls and/or creatures with flying. | Elven Riders | 1 |
| Whenever enchanted creature deals damage, you gain that much life. | Spirit Link | 1 |

## Notes



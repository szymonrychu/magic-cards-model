# Nemesis (nem)

- Expansion: 030
- Set code: `nem`
- Release date: 2000-02-14
- Cards in scope (Modern/Pioneer/Standard-legal): 23

## Legality

| Format | Legal cards |
|---|---|
| Modern | 23 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 3 | 13.0% |
| Works (untested) | 16 | 69.6% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 4 | 17.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Blinding Angel | silent | Whenever this creature deals combat damage to a player, that player skips their next combat phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Oracle's Attendants | silent | {T}: All damage that would be dealt to target creature this turn by a source of your choice is dealt to this creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Treetop Bracers | silent | Enchanted creature gets +1/+1 and can't be blocked except by creatures with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Defiant Vanguard | notice | When this creature blocks, at end of combat, destroy it and all creatures it blocked this turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Ascendant Evincar | handled | Other black creatures get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Carrion Wall | handled | {1}{B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flame Rift | handled | Flame Rift deals 4 damage to each player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flowstone Crusher | handled | {R}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flowstone Slide | handled | All creatures get +X/-X until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mind Slash | handled | {B}, Sacrifice a creature: Target opponent reveals their hand. You choose a card from it. That player discards that card. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mogg Salvage | handled | If an opponent controls an Island and you control a Mountain, you may cast this spell without paying its mana cost. Destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Murderous Betrayal | handled | {B}{B}, Pay half your life, rounded up: Destroy target nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rootwater Commando | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Seal of Cleansing | handled | Sacrifice this enchantment: Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seal of Doom | handled | Sacrifice this enchantment: Destroy target nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seal of Fire | handled | Sacrifice this enchantment: It deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seal of Removal | handled | Sacrifice this enchantment: Return target creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sneaky Homunculus | handled | This creature can't block or be blocked by creatures with power 2 or greater. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spineless Thug | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vicious Hunger | handled | Vicious Hunger deals 2 damage to target creature and you gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Death Pit Offering
- Rhox
- Stronghold Discipline

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| enchanted creature gets +N/+N and can't be blocked except by creatures with flying. | 1 | Treetop Bracers | nem |
| when ~ blocks, at end of combat, destroy it and all creatures it blocked ~. | 1 | Defiant Vanguard | nem |
| whenever ~ deals combat damage to a player, that player skips their next combat phase. | 1 | Blinding Angel | nem |
| {M}: all damage that would be dealt to target creature ~ by a source of your choice is dealt to ~ instead. | 1 | Oracle's Attendants | nem |

## Notes



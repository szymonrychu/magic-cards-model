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
| Tested | 0 | 0.0% |
| Works (untested) | 15 | 65.2% |
| Partial (unaudited) | 1 | 4.3% |
| Not working | 7 | 30.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ascendant Evincar | silent | Other black creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blinding Angel | silent | Whenever this creature deals combat damage to a player, that player skips their next combat phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Death Pit Offering | silent | When this enchantment enters, sacrifice all creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Oracle's Attendants | silent | {T}: All damage that would be dealt to target creature this turn by a source of your choice is dealt to this creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stronghold Discipline | silent | Each player loses 1 life for each creature they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Treetop Bracers | silent | Enchanted creature gets +1/+1 and can't be blocked except by creatures with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Defiant Vanguard | notice | When this creature blocks, at end of combat, destroy it and all creatures it blocked this turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Rhox | unaudited | You may have this creature assign its combat damage as though it weren't blocked. | a static ability no support check audits - not verified either way | Y/-/- | partial |
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
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| each player loses N life for each creature they control. | 1 | Stronghold Discipline | nem |
| enchanted creature gets +N/+N and can't be blocked except by creatures with flying. | 1 | Treetop Bracers | nem |
| other black creatures get +N/+N. | 1 | Ascendant Evincar | nem |
| when ~ blocks, at end of combat, destroy it and all creatures it blocked ~. | 1 | Defiant Vanguard | nem |
| when ~ enters, sacrifice all creatures you control. | 1 | Death Pit Offering | nem |
| whenever ~ deals combat damage to a player, that player skips their next combat phase. | 1 | Blinding Angel | nem |
| you may have ~ assign its combat damage as though it weren't blocked. | 1 | Rhox | nem |
| {M}: all damage that would be dealt to target creature ~ by a source of your choice is dealt to ~ instead. | 1 | Oracle's Attendants | nem |

## Notes



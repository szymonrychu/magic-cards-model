# Salvat 2005 (psal)

- Expansion: 059
- Set code: `psal`
- Release date: 2005-08-22
- Cards in scope (Modern/Pioneer/Standard-legal): 79

## Legality

| Format | Legal cards |
|---|---|
| Modern | 79 |
| Pioneer | 4 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 2.5% |
| Works (untested) | 45 | 57.0% |
| Partial (unaudited) | 5 | 6.3% |
| Not working | 27 | 34.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Auratouched Mage | silent | When this creature enters, search your library for an Aura card that could enchant it. If this creature is still on the battlefield, put that Aura card onto the | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Belltower Sphinx | silent | Whenever a source deals damage to this creature, that source's controller mills that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bramble Elemental | silent | Whenever an Aura becomes attached to this creature, create two 1/1 green Saproling creature tokens. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Burning-Tree Bloodscale | silent | {2}{R}: Target creature can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Clutch of the Undercity | silent | Return target permanent to its owner's hand. Its controller loses 3 life. Transmute {1}{U}{B} ({1}{U}{B}, Discard this card: Search your library for a card with | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fertile Imagination | silent | Choose a card type. Target opponent reveals their hand. Create two 1/1 green Saproling creature tokens for each card of the chosen type revealed this way. (Arti | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Guardian's Magemark | silent | Creatures you control that are enchanted get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Infiltrator's Magemark | silent | Creatures you control that are enchanted get +1/+1 and can't be blocked except by creatures with defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jedit Ojanen of Efrava | silent | Whenever Jedit Ojanen attacks or blocks, create a 2/2 green Cat Warrior creature token with forestwalk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Leyline of the Meek | silent | Creature tokens get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lovisa Coldeyes | silent | Each creature that's a Barbarian, a Warrior, or a Berserker gets +2/+2 and has haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Martyr of Frost | silent | {2}, Reveal X blue cards from your hand, Sacrifice this creature: Counter target spell unless its controller pays {X}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Plumes of Peace | silent | Forecast | no machine in the engine executes this keyword | Y/-/- | not_working |
| Sanguine Praetor | silent | {B}, Sacrifice a creature: Destroy each creature with the same mana value as the sacrificed creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Seed Spark | silent | Destroy target artifact or enchantment. If {G} was spent to cast this spell, create two 1/1 green Saproling creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Seht's Tiger | silent | When this creature enters, you gain protection from the color of your choice until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stalking Vengeance | silent | Whenever another creature you control dies, it deals damage equal to its power to target player or planeswalker. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thelonite Hermit | silent | All Saprolings get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tolsimir Wolfblood | silent | Other green creatures you control get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Undying Rage | silent | Enchanted creature gets +2/+2 and can't block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vedalken Dismisser | silent | When this creature enters, put target creature on top of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Whitemane Lion | silent | When this creature enters, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wojek Apothecary | silent | Radiance — {T}: Prevent the next 1 damage that would be dealt to target creature and each other creature that shares a color with it this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Balduvian Rage | notice | Target attacking creature gets +X/+0 until end of turn. Draw a card at the beginning of the next turn's upkeep. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Helldozer | notice | {B}{B}{B}, {T}: Destroy target land. If that land was nonbasic, untap this creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Skyrider Trainee | notice | This creature has flying as long as it's enchanted. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Strength in Numbers | notice | Until end of turn, target creature gains trample and gets +X/+X, where X is the number of attacking creatures. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Detainment Spell | unaudited | Enchanted creature's activated abilities can't be activated. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Freewind Equenaut | unaudited | As long as this creature is enchanted, it has "{T}: This creature deals 2 damage to target attacking or blocking creature." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Goblin Fire Fiend | unaudited | This creature must be blocked if able. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Grifter's Blade | unaudited | As this Equipment enters, choose a creature you control it could be attached to. If you do, it enters attached to that creature. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Nacatl War-Pride | unaudited | This creature must be blocked by exactly one creature if able. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Carrion Howler | handled | Pay 1 life: This creature gets +2/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dimir Guildmage | handled | {3}{U}: Target player draws a card. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dimir Infiltrator | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flight of Fancy | handled | When this Aura enters, draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghor-Clan Savage | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Golgari Guildmage | handled | {4}{B}, Sacrifice a creature: Return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gruul Nodorog | handled | {R}: This creature gains menace until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gruul Scrapper | handled | When this creature enters, if {R} was spent to cast it, it gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Herd Gnarr | handled | Whenever another creature you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Indrik Stomphowler | handled | When this creature enters, destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jedit's Dragoons | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Juniper Order Ranger | handled | Whenever another creature you control enters, put a +1/+1 counter on that creature and a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Karplusan Wolverine | handled | Whenever this creature becomes blocked, you may have it deal 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Keening Banshee | handled | When this creature enters, target creature gets -2/-2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Necromantic Thirst | handled | Whenever enchanted creature deals combat damage to a player, you may return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nightguard Patrol | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Nullmage Shepherd | handled | Tap four untapped creatures you control: Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Overwhelm | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Creatures y | the engine reads this text and performs it | Y/Y/- | not_tested |
| Plagued Rusalka | handled | {B}, Sacrifice a creature: Target creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Primal Forcemage | handled | Whenever another creature you control enters, that creature gets +3/+3 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Saltblast | handled | Destroy target nonwhite permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sandsower | handled | Tap three untapped creatures you control: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Savage Thallid | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scab-Clan Mauler | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Scatter the Seeds | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Create thre | the engine reads this text and performs it | Y/-/- | not_tested |
| Selesnya Evangel | handled | {1}, {T}, Tap an untapped creature you control: Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Selesnya Guildmage | handled | {3}{G}: Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Selesnya Sanctuary | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Selesnya Signet | handled |  |  | Y/-/- | not_tested |
| Sinstriker's Will | handled | Enchanted creature has "{T}: This creature deals damage equal to its power to target attacking or blocking creature." | the engine reads this text and performs it | Y/-/- | not_tested |
| Skarrg, the Rage Pits | handled | {R}{G}, {T}: Target creature gets +1/+1 and gains trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soulsworn Jury | handled | {1}{U}, Sacrifice this creature: Counter target creature spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sporesower Thallid | handled | At the beginning of your upkeep, put a spore counter on each Fungus you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sprout | handled | Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Supply // Demand | handled | Create X 1/1 green Saproling creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Terramorphic Expanse | handled | {T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Terrarion | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thallid Germinator | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thallid Shell-Dweller | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Three Dreams | handled | Search your library for up to three Aura cards with different names, reveal them, put them into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Twilight Drover | handled | Whenever a creature token leaves the battlefield, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ursapine | handled | {G}: Target creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vacuumelt | handled | Replicate {2}{U} (When you cast this spell, copy it for each time you paid its replicate cost. You may choose new targets for the copies.) Return target creatur | the engine reads this text and performs it | Y/-/- | not_tested |
| Vedalken Entrancer | handled | {U}, {T}: Target player mills two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vesper Ghoul | handled |  |  | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Arctic Nishoba
- Frenzied Goblin

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Radiance | 1 | Wojek Apothecary | psal |
| all saprolings get +N/+N. | 1 | Thelonite Hermit | psal |
| as long as ~ is enchanted, it has "..." | 1 | Freewind Equenaut | psal |
| as ~ enters, choose a creature you control it could be attached to. if you do, it enters attached to that creature. | 1 | Grifter's Blade | psal |
| choose a card type. target opponent reveals their hand. create two N/N green saproling creature tokens for each card of the chosen type revealed ~. (artifact, b | 1 | Fertile Imagination | psal |
| creature tokens get +N/+N. | 1 | Leyline of the Meek | psal |
| creatures you control that are enchanted get +N/+N and can't be blocked except by creatures with defender. | 1 | Infiltrator's Magemark | psal |
| creatures you control that are enchanted get +N/+N. | 1 | Guardian's Magemark | psal |
| destroy target artifact or enchantment. if {M} was spent to cast ~, create two N/N green saproling creature tokens. | 1 | Seed Spark | psal |
| each creature that's a barbarian, a warrior, or a berserker gets +N/+N and has haste. | 1 | Lovisa Coldeyes | psal |
| enchanted creature gets +N/+N and can't block. | 1 | Undying Rage | psal |
| enchanted creature"..."t be activated. | 1 | Detainment Spell | psal |
| forecast | 1 | Plumes of Peace | psal |
| other green creatures you control get +N/+N. | 1 | Tolsimir Wolfblood | psal |
| return target permanent to its owner's hand. its controller loses N life. transmute {M}{M}{M} ({M}{M}{M}, discard ~: search your library for a card with the sam | 1 | Clutch of the Undercity | psal |
| target attacking creature gets +N/+N until end of turn. draw a card at the beginning of the next turn's upkeep. | 1 | Balduvian Rage | psal |
| until end of turn, target creature gains trample and gets +N/+N, where N is the number of attacking creatures. | 1 | Strength in Numbers | psal |
| when ~ enters, put target creature on top of its owner's library. | 1 | Vedalken Dismisser | psal |
| when ~ enters, return a creature you control to its owner's hand. | 1 | Whitemane Lion | psal |
| when ~ enters, search your library for an aura card that could enchant it. if ~ is still on the battlefield, put that aura card onto the battlefield attached to | 1 | Auratouched Mage | psal |
| when ~ enters, you gain protection from the color of your choice until end of turn. | 1 | Seht's Tiger | psal |
| whenever a source deals damage to ~, that source's controller mills that many cards. | 1 | Belltower Sphinx | psal |
| whenever an aura becomes attached to ~, create two N/N green saproling creature tokens. | 1 | Bramble Elemental | psal |
| whenever another creature you control dies, it deals damage equal to its power to target player or planeswalker. | 1 | Stalking Vengeance | psal |
| whenever jedit ojanen attacks or blocks, create a N/N green cat warrior creature token with forestwalk. | 1 | Jedit Ojanen of Efrava | psal |
| {M}, reveal N blue cards from your hand, sacrifice ~: counter target spell unless its controller pays {M}. | 1 | Martyr of Frost | psal |
| {M}, sacrifice a creature: destroy each creature with the same mana value as the sacrificed creature. | 1 | Sanguine Praetor | psal |
| {M}{M}: target creature can't block ~ ~. | 1 | Burning-Tree Bloodscale | psal |
| {M}{M}{M}, {M}: destroy target land. if that land was nonbasic, untap ~. | 1 | Helldozer | psal |
| ~ has flying as long as it's enchanted. | 1 | Skyrider Trainee | psal |
| ~ must be blocked by exactly one creature if able. | 1 | Nacatl War-Pride | psal |
| ~ must be blocked if able. | 1 | Goblin Fire Fiend | psal |

## Notes



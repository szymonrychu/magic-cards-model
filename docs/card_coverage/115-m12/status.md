# Magic 2012 (m12)

- Expansion: 115
- Set code: `m12`
- Release date: 2011-07-15
- Cards in scope (Modern/Pioneer/Standard-legal): 93

## Legality

| Format | Legal cards |
|---|---|
| Modern | 93 |
| Pioneer | 19 |
| Standard | 6 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 7 | 7.5% |
| Partial (unaudited) | 3 | 3.2% |
| Not tested (handled, untested) | 42 | 45.2% |
| Not working (silent / notice / error) | 41 | 44.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Adaptive Automaton | silent | This creature is the chosen type in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Angelic Destiny | silent | Enchanted creature gets +4/+4, has flying and first strike, and is an Angel in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Arachnus Spinner | silent | Tap an untapped Spider you control: Search your graveyard and/or library for a card named Arachnus Web and put it onto the battlefield attached to target creatu | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arachnus Web | silent | At the beginning of the end step, if enchanted creature's power is 4 or greater, destroy this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arbalest Elite | silent | {2}{W}, {T}: This creature deals 3 damage to target attacking or blocking creature. This creature doesn't untap during your next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blood Ogre | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Bloodrage Vampire | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Carnage Wurm | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Circle of Flame | silent | Whenever a creature without flying attacks you or a planeswalker you control, this enchantment deals 1 damage to that creature. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Doubling Chant | silent | For each creature you control, you may search your library for a creature card with the same name as that creature. Put those cards onto the battlefield, then s | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Druidic Satchel | silent | {2}, {T}: Reveal the top card of your library. If it's a creature card, create a 1/1 green Saproling creature token. If it's a land card, put that card onto the | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Duskhunter Bat | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Furyborn Hellkite | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Gideon's Avenger | silent | Whenever a creature an opponent controls becomes tapped, put a +1/+1 counter on this creature. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Goblin Bangchuckers | silent | {T}: Flip a coin. If you win the flip, this creature deals 2 damage to any target. If you lose the flip, this creature deals 2 damage to itself. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gorehorn Minotaurs | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Griffin Rider | silent | As long as you control a Griffin creature, this creature gets +3/+3 and has flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Guardians' Pledge | silent | White creatures you control get +2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunter's Insight | silent | Choose target creature you control. Whenever that creature deals combat damage to a player or planeswalker this turn, draw that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jace's Archivist | silent | {U}, {T}: Each player discards their hand, then draws cards equal to the greatest number of cards a player discarded this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jace, Memory Adept | silent | −7: Any number of target players each draw twenty cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Lord of the Unreal | silent | Illusion creatures you control get +1/+1 and have hexproof. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lurking Crocodile | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Master Thief | silent | When this creature enters, gain control of target artifact for as long as you control this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Monomania | silent | Target player chooses a card in their hand and discards the rest. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scepter of Empires | silent | {T}: This artifact deals 1 damage to target player or planeswalker. It deals 3 damage instead if you control artifacts named Crown of Empires and Throne of Empi | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scrambleverse | silent | For each nonland permanent, choose a player at random. Then each player gains control of each permanent for which they were chosen. Untap those permanents. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Skinshifter | silent | {G}: Choose one. Activate only once each turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sphinx of Uthuun | silent | When this creature enters, reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the othe | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stonehorn Dignitary | silent | When this creature enters, target opponent skips their next combat phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stormblood Berserker | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Tectonic Rift | silent | Destroy target land. Creatures without flying can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Throne of Empires | silent | {1}, {T}: Create a 1/1 white Soldier creature token. Create five of those tokens instead if you control artifacts named Crown of Empires and Scepter of Empires. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Timely Reinforcements | silent | If you have less life than an opponent, you gain 6 life. If you control fewer creatures than an opponent, create three 1/1 white Soldier creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vampire Outcasts | silent | Bloodthirst | no machine in the engine executes this keyword | Y/-/- | not_working |
| Vengeful Pharaoh | silent | Whenever combat damage is dealt to you or a planeswalker you control, if this card is in your graveyard, destroy target attacking creature, then put this card o | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Visions of Beyond | silent | Draw a card. If a graveyard has twenty or more cards in it, draw three cards instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Warstorm Surge | silent | Whenever a creature you control enters, it deals damage equal to its power to any target. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Crown of Empires | notice | {3}, {T}: Tap target creature. Gain control of that creature instead if you control artifacts named Scepter of Empires and Throne of Empires. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Crumbling Colossus | notice | When this creature attacks, sacrifice it at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Primordial Hydra | notice | This creature has trample as long as it has ten or more +1/+1 counters on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Grand Abolisher | unaudited | During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Personal Sanctuary | unaudited | During your turn, prevent all damage that would be dealt to you. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Skywinder Drake | unaudited | This creature can block only creatures with flying. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Alabaster Mage | handled | {1}{W}: Target creature you control gains lifelink until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Amphin Cutthroat | handled |  |  | Y/-/- | not_tested |
| Armored Warhorse | handled |  |  | Y/-/- | not_tested |
| Aven Fleetwing | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Azure Mage | handled | {3}{U}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Benalish Veteran | handled | Whenever this creature attacks, it gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bonebreaker Giant | handled |  |  | Y/-/- | not_tested |
| Buried Ruin | handled | {2}, {T}, Sacrifice this land: Return target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chandra, the Firebrand | handled | +1: Chandra deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chasm Drake | handled | Whenever this creature attacks, target creature you control gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crimson Mage | handled | {R}: Target creature you control gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dark Favor | handled | When this Aura enters, you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Devouring Swarm | handled | Sacrifice a creature: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Divine Favor | handled | When this Aura enters, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drifting Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Garruk, Primal Hunter | handled | +1: Create a 3/3 green Beast creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gideon's Lawkeeper | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Fireslinger | handled | {T}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greatsword | handled | Equipped creature gets +3/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hideous Visage | handled | Creatures you control gain intimidate until end of turn. (Each of those creatures can't be blocked except by artifact creatures and/or creatures that share a co | the engine reads this text and performs it | Y/-/- | not_tested |
| Jade Mage | handled | {2}{G}: Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kite Shield | handled | Equipped creature gets +0/+3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Manalith | handled |  |  | Y/Y/- | not_tested |
| Merfolk Mesmerist | handled | {U}, {T}: Target player mills two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mind Unbound | handled | At the beginning of your upkeep, put a lore counter on this enchantment, then draw a card for each lore counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Onyx Mage | handled | {1}{B}: Target creature you control gains deathtouch until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Peregrine Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Phantasmal Bear | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pride Guardian | handled | Whenever this creature blocks, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rune-Scarred Demon | handled | When this creature enters, search your library for a card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rusted Sentinel | handled | This creature enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sorin's Thirst | handled | Sorin's Thirst deals 2 damage to target creature and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sorin's Vengeance | handled | Sorin's Vengeance deals 10 damage to target player or planeswalker and you gain 10 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spirit Mantle | handled | Enchanted creature gets +1/+1 and has protection from creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stave Off | handled | Target creature gains protection from the color of your choice until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stingerfling Spider | handled | When this creature enters, you may destroy target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Swiftfoot Boots | handled | Equipped creature has hexproof and haste. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Taste of Blood | handled | Taste of Blood deals 1 damage to target player or planeswalker and you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Titanic Growth | handled | Target creature gets +4/+4 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Trollhide | handled | Enchanted creature gets +2/+2 and has "{1}{G}: Regenerate this creature." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wall of Torches | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Wring Flesh | handled | Target creature gets -3/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>7 cards</summary>

- Aegis Angel
- Dungrove Elder
- Frost Breath
- Gladecover Scout
- Phantasmal Image
- Sundial of the Infinite
- Turn to Frog

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Bloodthirst | Blood Ogre, Bloodrage Vampire, Carnage Wurm, Duskhunter Bat, Furyborn Hellkite, Gorehorn Minotaurs, Lurking Crocodile, Stormblood Berserker, Vampire Outcasts | 9 |
| −7: Any number of target players each draw twenty cards. | Jace, Memory Adept | 1 |
| As long as you control a Griffin creature, this creature gets +3/+3 and has flying. | Griffin Rider | 1 |
| At the beginning of the end step, if enchanted creature's power is 4 or greater, destroy this Aura. | Arachnus Web | 1 |
| {G}: Choose one. Activate only once each turn. | Skinshifter | 1 |
| Choose target creature you control. Whenever that creature deals combat damage to a player or planeswalker this turn, draw that many cards. | Hunter's Insight | 1 |
| {1}, {T}: Create a 1/1 white Soldier creature token. Create five of those tokens instead if you control artifacts named Crown of Empires and Scepter of Empires. | Throne of Empires | 1 |
| Destroy target land. Creatures without flying can't block this turn. | Tectonic Rift | 1 |
| Draw a card. If a graveyard has twenty or more cards in it, draw three cards instead. | Visions of Beyond | 1 |
| During your turn, prevent all damage that would be dealt to you. | Personal Sanctuary | 1 |
| During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments. | Grand Abolisher | 1 |
| {U}, {T}: Each player discards their hand, then draws cards equal to the greatest number of cards a player discarded this way. | Jace's Archivist | 1 |
| Enchanted creature gets +4/+4, has flying and first strike, and is an Angel in addition to its other types. | Angelic Destiny | 1 |
| {T}: Flip a coin. If you win the flip, this creature deals 2 damage to any target. If you lose the flip, this creature deals 2 damage to itself. | Goblin Bangchuckers | 1 |
| For each creature you control, you may search your library for a creature card with the same name as that creature. Put those cards onto the battlefield, then s | Doubling Chant | 1 |
| For each nonland permanent, choose a player at random. Then each player gains control of each permanent for which they were chosen. Untap those permanents. | Scrambleverse | 1 |
| If you have less life than an opponent, you gain 6 life. If you control fewer creatures than an opponent, create three 1/1 white Soldier creature tokens. | Timely Reinforcements | 1 |
| Illusion creatures you control get +1/+1 and have hexproof. | Lord of the Unreal | 1 |
| {2}, {T}: Reveal the top card of your library. If it's a creature card, create a 1/1 green Saproling creature token. If it's a land card, put that card onto the | Druidic Satchel | 1 |
| Tap an untapped Spider you control: Search your graveyard and/or library for a card named Arachnus Web and put it onto the battlefield attached to target creatu | Arachnus Spinner | 1 |
| {3}, {T}: Tap target creature. Gain control of that creature instead if you control artifacts named Scepter of Empires and Throne of Empires. | Crown of Empires | 1 |
| Target player chooses a card in their hand and discards the rest. | Monomania | 1 |
| {T}: This artifact deals 1 damage to target player or planeswalker. It deals 3 damage instead if you control artifacts named Crown of Empires and Throne of Empi | Scepter of Empires | 1 |
| This creature can block only creatures with flying. | Skywinder Drake | 1 |
| {2}{W}, {T}: This creature deals 3 damage to target attacking or blocking creature. This creature doesn't untap during your next untap step. | Arbalest Elite | 1 |
| This creature has trample as long as it has ten or more +1/+1 counters on it. | Primordial Hydra | 1 |
| This creature is the chosen type in addition to its other types. | Adaptive Automaton | 1 |
| When this creature attacks, sacrifice it at end of combat. | Crumbling Colossus | 1 |
| When this creature enters, gain control of target artifact for as long as you control this creature. | Master Thief | 1 |
| When this creature enters, reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the othe | Sphinx of Uthuun | 1 |
| When this creature enters, target opponent skips their next combat phase. | Stonehorn Dignitary | 1 |
| Whenever a creature an opponent controls becomes tapped, put a +1/+1 counter on this creature. | Gideon's Avenger | 1 |
| Whenever a creature without flying attacks you or a planeswalker you control, this enchantment deals 1 damage to that creature. | Circle of Flame | 1 |
| Whenever a creature you control enters, it deals damage equal to its power to any target. | Warstorm Surge | 1 |
| Whenever combat damage is dealt to you or a planeswalker you control, if this card is in your graveyard, destroy target attacking creature, then put this card o | Vengeful Pharaoh | 1 |
| White creatures you control get +2/+2 until end of turn. | Guardians' Pledge | 1 |

## Notes



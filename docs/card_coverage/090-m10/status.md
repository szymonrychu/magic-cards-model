# Magic 2010 (m10)

- Expansion: 090
- Set code: `m10`
- Release date: 2009-07-17
- Cards in scope (Modern/Pioneer/Standard-legal): 111

## Legality

| Format | Legal cards |
|---|---|
| Modern | 111 |
| Pioneer | 39 |
| Standard | 3 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 11 | 9.9% |
| Works (untested) | 67 | 60.4% |
| Partial (unaudited) | 8 | 7.2% |
| Not working | 25 | 22.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Alluring Siren | silent | {T}: Target creature an opponent controls attacks you this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Awakener Druid | silent | When this creature enters, target Forest becomes a 4/5 green Treefolk creature for as long as this creature remains on the battlefield. It's still a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Capricious Efreet | silent | At the beginning of your upkeep, choose target nonland permanent you control and up to two target nonland permanents you don't control. Destroy one of them at r | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Captain of the Watch | silent | Other Soldier creatures you control get +1/+1 and have vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Goblin Chieftain | silent | Other Goblin creatures you control get +1/+1 and have haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Harm's Way | silent | The next 2 damage that a source of your choice would deal to you and/or permanents you control this turn is dealt to any target instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hive Mind | silent | Whenever a player casts an instant or sorcery spell, each other player copies that spell. Each of those players may choose new targets for their copy. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Honor of the Pure | silent | White creatures you control get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ice Cage | silent | When enchanted creature becomes the target of a spell or ability, destroy this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Inferno Elemental | silent | Whenever this creature blocks or becomes blocked by a creature, this creature deals 3 damage to that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magebane Armor | silent | Equipped creature gets +2/+4 and loses flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Master of the Wild Hunt | silent | {T}: Tap all untapped Wolf creatures you control. Each Wolf tapped this way deals damage equal to its power to target creature. That creature deals damage equal | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mirror of Fate | silent | {T}, Sacrifice this artifact: Choose up to seven face-up exiled cards you own. Exile all the cards from your library, then put the chosen cards on top of your l | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Open the Vaults | silent | Return all artifact and enchantment cards from all graveyards to the battlefield under their owners' control. (Auras with nothing to enchant remain in graveyard | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Protean Hydra | silent | Whenever a +1/+1 counter is removed from this creature, put two +1/+1 counters on it at the beginning of the next end step. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Rhox Pikemaster | silent | Other Soldier creatures you control have first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Safe Passage | silent | Prevent all damage that would be dealt to you and creatures you control this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sleep | silent | Tap all creatures target player controls. Those creatures don't untap during that player's next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sphinx Ambassador | silent | Whenever this creature deals combat damage to a player, search that player's library for a card, then that player chooses a card name. If you searched for a cre | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vampire Nocturnus | silent | As long as the top card of your library is black, this creature and other Vampire creatures you control get +2/+1 and have flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Baneslayer Angel | notice | Protection | protection from a quality the engine does not read: Demons, Dragons | Y/Y/- | not_working |
| Djinn of Wishes | notice | {2}{U}{U}, Remove a wish counter from this creature: Reveal the top card of your library. You may play that card without paying its mana cost. If you don't, exi | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Great Sable Stag | notice | Protection | protection from a quality the engine does not read: black (This creature can't be blocked | Y/-/- | not_working |
| Rise from the Grave | notice | Put target creature card from a graveyard onto the battlefield under your control. That creature is a black Zombie in addition to its other colors and types. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Xathrid Demon | notice | At the beginning of your upkeep, sacrifice a creature other than this creature, then each opponent loses life equal to the sacrificed creature's power. If you c | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Convincing Mirage | unaudited | Enchanted land is the chosen type. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Dread Warlock | unaudited | This creature can't be blocked except by black creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Guardian Seraph | unaudited | If a source an opponent controls would deal damage to you, prevent 1 of that damage. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Indestructibility | unaudited | Enchanted permanent has indestructible. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Jackal Familiar | unaudited | This creature can't attack or block alone. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Palace Guard | unaudited | This creature can block any number of creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Prized Unicorn | unaudited | All creatures able to block this creature do so. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Serpent of the Endless Sea | unaudited | This creature can't attack unless defending player controls an Island. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Acolyte of Xathrid | handled | {1}{B}, {T}: Target player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Angel's Mercy | handled | You gain 7 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ant Queen | handled | {1}{G}: Create a 1/1 green Insect creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Berserkers of Blood Ridge | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blinding Mage | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Borderland Ranger | handled | When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bountiful Harvest | handled | You gain 1 life for each land you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bramble Creeper | handled | Whenever this creature attacks, it gets +5/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Burst of Speed | handled | Creatures you control gain haste until end of turn. (They can attack and {T} even if they just came under your control.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Cemetery Reaper | handled | Other Zombie creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Centaur Courser | handled |  |  | Y/Y/- | not_tested |
| Child of Night | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Cudgel Troll | handled | {G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deadly Recluse | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Disentomb | handled | Return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Disorient | handled | Target creature gets -7/-0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Divine Verdict | handled | Destroy target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Doom Blade | handled | Destroy target nonblack creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dragonskull Summit | handled | This land enters tapped unless you control a Swamp or a Mountain. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drowned Catacomb | handled | This land enters tapped unless you control an Island or a Swamp. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Elvish Archdruid | handled | Other Elf creatures you control get +1/+1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Emerald Oryx | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Entangling Vines | handled | Enchanted creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fiery Hellhound | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gargoyle Castle | handled | {5}, {T}, Sacrifice this land: Create a 3/4 colorless Gargoyle artifact creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glacial Fortress | handled | This land enters tapped unless you control a Plains or an Island. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glorious Charge | handled | Creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Artillery | handled | {T}: This creature deals 2 damage to any target and 3 damage to you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gorgon Flail | handled | Equipped creature gets +1/+1 and has deathtouch. | the engine reads this text and performs it | Y/-/- | not_tested |
| Griffin Sentinel | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Howling Banshee | handled | When this creature enters, each player loses 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Illusionary Servant | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kalonian Behemoth | handled | Shroud | models/game.py (Game.shroud_refusal), machines/targeting.py (TargetingProfile._check_shroud, CR 702.18a) | Y/-/- | not_tested |
| Kelinore Bat | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Lightwielder Paladin | handled | Whenever this creature deals combat damage to a player, you may exile target black or red permanent that player controls. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lurking Predators | handled | Whenever an opponent casts a spell, reveal the top card of your library. If it's a creature card, put it onto the battlefield. Otherwise, you may put that card  | the engine reads this text and performs it | Y/-/- | not_tested |
| Magma Phoenix | handled | When this creature dies, it deals 3 damage to each creature and each player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk Sovereign | handled | Other Merfolk creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mind Control | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mist Leopard | handled | Shroud | models/game.py (Game.shroud_refusal), machines/targeting.py (TargetingProfile._check_shroud, CR 702.18a) | Y/-/- | not_tested |
| Mold Adder | handled | Whenever an opponent casts a blue or black spell, you may put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Nature's Spiral | handled | Return target permanent card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oakenform | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Planar Cleansing | handled | Destroy all nonland permanents. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Regenerate | handled | Regenerate target creature. (The next time that creature would be destroyed this turn, instead tap it, remove it from combat, and heal all damage on it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Rootbound Crag | handled | This land enters tapped unless you control a Mountain or a Forest. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanguine Bond | handled | Whenever you gain life, target opponent loses that much life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seismic Strike | handled | Seismic Strike deals damage to target creature equal to the number of Mountains you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Siege Mastodon | handled |  |  | Y/Y/- | not_tested |
| Silvercoat Lion | handled |  |  | Y/-/- | not_tested |
| Solemn Offering | handled | Destroy target artifact or enchantment. You gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul Bleed | handled | At the beginning of the upkeep of enchanted creature's controller, that player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stampeding Rhino | handled | Trample | machines/combat.py | Y/Y/- | not_tested |
| Stormfront Pegasus | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Sunpetal Grove | handled | This land enters tapped unless you control a Forest or a Plains. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tome Scour | handled | Target player mills five cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Undead Slayer | handled | {W}, {T}: Exile target Skeleton, Vampire, or Zombie. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vampire Aristocrat | handled | Sacrifice a creature: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Veteran Armorsmith | handled | Other Soldier creatures you control get +0/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Veteran Swordsmith | handled | Other Soldier creatures you control get +1/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Spearhunter | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Wall of Faith | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Frost | handled | Whenever this creature blocks a creature, that creature doesn't untap during its controller's next untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Warpath Ghoul | handled |  |  | Y/-/- | not_tested |
| Windstorm | handled | Windstorm deals X damage to each creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zephyr Sprite | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Zombie Goliath | handled |  |  | Y/-/- | not_tested |

## Fully supported

<details>
<summary>11 cards</summary>

- Acidic Slime
- Act of Treason
- Burning Inquiry
- Divination
- Elite Vanguard
- Essence Scatter
- Lifelink
- Runeclaw Bear
- Sign in Blood
- Silence
- Yawning Fissure

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| protection | 2 | Baneslayer Angel, Great Sable Stag | m10 |
| all creatures able to block ~ do so. | 1 | Prized Unicorn | m10 |
| as long as the top card of your library is black, ~ and other vampire creatures you control get +N/+N and have flying. | 1 | Vampire Nocturnus | m10 |
| at the beginning of your upkeep, choose target nonland permanent you control and up to two target nonland permanents you don't control. destroy one of them at r | 1 | Capricious Efreet | m10 |
| at the beginning of your upkeep, sacrifice a creature other than ~, then each opponent loses life equal to the sacrificed creature"..."t sacrifice a creature, t | 1 | Xathrid Demon | m10 |
| enchanted land is the chosen type. | 1 | Convincing Mirage | m10 |
| enchanted permanent has indestructible. | 1 | Indestructibility | m10 |
| equipped creature gets +N/+N and loses flying. | 1 | Magebane Armor | m10 |
| if a source an opponent controls would deal damage to you, prevent N of that damage. | 1 | Guardian Seraph | m10 |
| other goblin creatures you control get +N/+N and have haste. | 1 | Goblin Chieftain | m10 |
| other soldier creatures you control get +N/+N and have vigilance. | 1 | Captain of the Watch | m10 |
| other soldier creatures you control have first strike. | 1 | Rhox Pikemaster | m10 |
| prevent all damage that would be dealt to you and creatures you control ~. | 1 | Safe Passage | m10 |
| put target creature card from a graveyard onto the battlefield under your control. that creature is a black zombie in addition to its other colors and types. | 1 | Rise from the Grave | m10 |
| return all artifact and enchantment cards from all graveyards to the battlefield under their owners' control. (auras with nothing to enchant remain in graveyard | 1 | Open the Vaults | m10 |
| tap all creatures target player controls. those creatures don"..."s next untap step. | 1 | Sleep | m10 |
| the next N damage that a source of your choice would deal to you and/or permanents you control ~ is dealt to any target instead. | 1 | Harm's Way | m10 |
| when enchanted creature becomes the target of a spell or ability, destroy ~. | 1 | Ice Cage | m10 |
| when ~ enters, target forest becomes a N/N green treefolk creature for as long as ~ remains on the battlefield. it's still a land. | 1 | Awakener Druid | m10 |
| whenever a +N/+N counter is removed from ~, put two +N/+N counters on it at the beginning of the next end step. | 1 | Protean Hydra | m10 |
| whenever a player casts an instant or sorcery spell, each other player copies that spell. each of those players may choose new targets for their copy. | 1 | Hive Mind | m10 |
| whenever ~ blocks or becomes blocked by a creature, ~ deals N damage to that creature. | 1 | Inferno Elemental | m10 |
| whenever ~ deals combat damage to a player, search that player"..."t have that name, you may put it onto the battlefield under your control. then that player sh | 1 | Sphinx Ambassador | m10 |
| white creatures you control get +N/+N. | 1 | Honor of the Pure | m10 |
| {M}, sacrifice ~: choose up to seven face-up exiled cards you own. exile all the cards from your library, then put the chosen cards on top of your library. | 1 | Mirror of Fate | m10 |
| {M}: tap all untapped wolf creatures you control. each wolf tapped ~ deals damage equal to its power to target creature. that creature deals damage equal to its | 1 | Master of the Wild Hunt | m10 |
| {M}: target creature an opponent controls attacks you ~ if able. | 1 | Alluring Siren | m10 |
| {M}{M}{M}, remove a wish counter from ~: reveal the top card of your library. you may play that card without paying its mana cost. if you don't, exile it. | 1 | Djinn of Wishes | m10 |
| ~ can block any number of creatures. | 1 | Palace Guard | m10 |
| ~ can't attack or block alone. | 1 | Jackal Familiar | m10 |
| ~ can't attack unless defending player controls an island. | 1 | Serpent of the Endless Sea | m10 |
| ~ can't be blocked except by black creatures. | 1 | Dread Warlock | m10 |

## Notes



# Worldwake (wwk)

- Expansion: 098
- Set code: `wwk`
- Release date: 2010-02-05
- Cards in scope (Modern/Pioneer/Standard-legal): 142

## Legality

| Format | Legal cards |
|---|---|
| Modern | 142 |
| Pioneer | 9 |
| Standard | 4 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 48 | 33.8% |
| Works (untested) | 67 | 47.2% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 27 | 19.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Admonition Angel | silent | When this creature leaves the battlefield, return all cards exiled with it to the battlefield under their owners' control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aether Tradewinds | silent | Return target permanent you control and target permanent you don't control to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Agadeem Occultist | silent | {T}: Put target creature card from an opponent's graveyard onto the battlefield under your control if its mana value is less than or equal to the number of Alli | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Akoum Battlesinger | silent | Whenever this creature or another Ally you control enters, you may have Ally creatures you control get +1/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Avenger of Zendikar | silent | Landfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bazaar Trader | silent | {T}: Target player gains control of target artifact, creature, or land you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bloodhusk Ritualist | silent | When this creature enters, target opponent discards a card for each time it was kicked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Calcite Snapper | silent | Landfall — Whenever a land you control enters, you may switch this creature's power and toughness until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Caustic Crawler | silent | Landfall — Whenever a land you control enters, you may have target creature get -1/-1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jwari Shapeshifter | silent | You may have this creature enter as a copy of any Ally creature on the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kazuul, Tyrant of the Cliffs | silent | Whenever a creature an opponent controls attacks, if you're the defending player, create a 3/3 red Ogre creature token unless that creature's controller pays {3 | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lightkeeper of Emeria | silent | When this creature enters, you gain 2 life for each time it was kicked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quest for Ula's Temple | silent | At the beginning of your upkeep, you may look at the top card of your library. If it's a creature card, you may reveal it and put a quest counter on this enchan | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rumbling Aftershocks | silent | Whenever you cast a kicked spell, you may have this enchantment deal damage to any target equal to the number of times that spell was kicked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Selective Memory | silent | Search your library for any number of nonland cards, exile them, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spell Contortion | silent | Multikicker {1}{U} (You may pay an additional {1}{U} any number of times as you cast this spell.) Counter target spell unless its controller pays {2}. Draw a ca | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stone Idol Trap | silent | This spell costs {1} less to cast for each attacking creature. Create a 6/12 colorless Construct artifact creature token with trample. Exile it at the beginning | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Talus Paladin | silent | Whenever this creature or another Ally you control enters, you may have Allies you control gain lifelink until end of turn, and you may put a +1/+1 counter on t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vapor Snare | silent | At the beginning of your upkeep, sacrifice this Aura unless you return a land you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Voyager Drake | silent | When this creature enters, up to X target creatures gain flying until end of turn, where X is the number of times this creature was kicked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wolfbriar Elemental | silent | When this creature enters, create a 2/2 green Wolf creature token for each time it was kicked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wrexial, the Risen Deep | silent | Whenever Wrexial deals combat damage to a player, you may cast target instant or sorcery card from that player's graveyard without paying its mana cost. If that | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Death's Shadow | notice | This creature gets -X/-X, where X is your life total. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Feral Contest | notice | Put a +1/+1 counter on target creature you control. Another target creature blocks it this turn if able. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Nemesis Trap | notice | If a white creature is attacking, you may pay {B}{B} rather than pay this spell's mana cost. Exile target attacking creature. Create a token that's a copy of th | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Thada Adel, Acquisitor | notice | Whenever Thada Adel deals combat damage to a player, search that player's library for an artifact card and exile it. Then that player shuffles. Until end of tur | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Urge to Feed | notice | Target creature gets -3/-3 until end of turn. You may tap any number of untapped Vampire creatures you control. If you do, put a +1/+1 counter on each of those  | unparsed remainder: You may tap any number of untapped Vampire creatures you control. If you do, put a +1/+1 counter on each of those Vampires. | Y/-/- | not_working |
| Anowon, the Ruin Sage | handled | At the beginning of your upkeep, each player sacrifices a non-Vampire creature of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Arbor Elf | handled | {T}: Untap target Forest. | the engine reads this text and performs it | Y/-/- | not_tested |
| Battle Hurda | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Bojuka Brigand | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brink of Disaster | handled | When enchanted permanent becomes tapped, destroy it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bull Rush | handled | Target creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Butcher of Malakir | handled | Whenever this creature or another creature you control dies, each opponent sacrifices a creature of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Claws of Valakut | handled | Enchanted creature gets +1/+0 for each Mountain you control and has first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cosi's Ravager | handled | Landfall — Whenever a land you control enters, you may have this creature deal 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Creeping Tar Pit | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cunning Sparkmage | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dispel | handled | Counter target instant spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dragonmaster Outcast | handled | At the beginning of your upkeep, if you control six or more lands, create a 5/5 red Dragon creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dread Statuary | handled | {4}: This land becomes a 4/2 Golem artifact creature until end of turn. It's still a land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eye of Ugin | handled | Colorless Eldrazi spells you cast cost {2} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fledgling Griffin | handled | Landfall — Whenever a land you control enters, this creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Roughrider | handled |  |  | Y/Y/- | not_tested |
| Goliath Sphinx | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Grappler Spider | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Graypelt Hunter | handled | Whenever this creature or another Ally you control enters, you may put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grotag Thrasher | handled | Whenever this creature attacks, target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Groundswell | handled | Target creature gets +2/+2 until end of turn. Landfall — If you had a land enter the battlefield under your control this turn, that creature gets +4/+4 until en | the engine reads this text and performs it | Y/-/- | not_tested |
| Halimar Depths | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hammer of Ruin | handled | Equipped creature gets +2/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hedron Rover | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horizon Drake | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Iona's Judgment | handled | Exile target creature or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jagwasp Swarm | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Join the Ranks | handled | Create two 1/1 white Soldier Ally creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kalastria Highborn | handled | Whenever this creature or another Vampire you control dies, you may pay {B}. If you do, target player loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Khalni Garden | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kitesail | handled | Equipped creature gets +1/+0 and has flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kitesail Apprentice | handled | As long as this creature is equipped, it gets +1/+1 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lavaclaw Reaches | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Leatherback Baloth | handled |  |  | Y/-/- | not_tested |
| Loam Lion | handled | This creature gets +1/+2 as long as you control a Forest. | the engine reads this text and performs it | Y/-/- | not_tested |
| Marsh Threader | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Marshal's Anthem | handled | Creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mysteries of the Deep | handled | Draw two cards. Landfall — If you had a land enter the battlefield under your control this turn, draw three cards instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Perimeter Captain | handled | Whenever a creature you control with defender blocks, you may gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Permafrost Trap | handled | If an opponent had a green creature enter the battlefield under their control this turn, you may pay {U} rather than pay this spell's mana cost. Tap up to two t | the engine reads this text and performs it | Y/-/- | not_tested |
| Pilgrim's Eye | handled | When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pulse Tracker | handled | Whenever this creature attacks, each opponent loses 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Quest for the Goblin Lord | handled | Whenever a Goblin you control enters, you may put a quest counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Quest for the Nihil Stone | handled | Whenever an opponent discards a card, you may put a quest counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Raging Ravine | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razor Boomerang | handled | Equipped creature has "{T}, Unattach Razor Boomerang: It deals 1 damage to any target. Return Razor Boomerang to its owner's hand." | the engine reads this text and performs it | Y/-/- | not_tested |
| Rest for the Weary | handled | Target player gains 4 life. Landfall — If you had a land enter the battlefield under your control this turn, that player gains 8 life instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ruin Ghost | handled | {W}, {T}: Exile target land you control, then return it to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scrib Nibblers | handled | {T}: Exile the top card of target player's library. If it's a land card, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seer's Sundial | handled | Landfall — Whenever a land you control enters, you may pay {2}. If you do, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sejiri Merfolk | handled | As long as you control a Plains, this creature has first strike and lifelink. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sejiri Steppe | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shoreline Salvager | handled | Whenever this creature deals combat damage to a player, if you control an Island, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slavering Nulls | handled | Whenever this creature deals combat damage to a player, if you control a Swamp, you may have that player discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slingbow Trap | handled | If a black creature with flying is attacking, you may pay {G} rather than pay this spell's mana cost. Destroy target attacking creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Smoldering Spires | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Snapping Creeper | handled | Landfall — Whenever a land you control enters, this creature gains vigilance until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stirring Wildwood | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stoneforge Mystic | handled | When this creature enters, you may search your library for an Equipment card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Summit Apes | handled | As long as you control a Mountain, this creature has menace. | the engine reads this text and performs it | Y/-/- | not_tested |
| Surrakar Banisher | handled | When this creature enters, you may return target tapped creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tideforce Elemental | handled | {U}, {T}: You may tap or untap another target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tomb Hex | handled | Target creature gets -2/-2 until end of turn. Landfall — If you had a land enter the battlefield under your control this turn, that creature gets -4/-4 until en | the engine reads this text and performs it | Y/-/- | not_tested |
| Treasure Hunt | handled | Reveal cards from the top of your library until you reveal a nonland card, then put all cards revealed this way into your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Veteran's Reflexes | handled | Target creature gets +1/+1 until end of turn. Untap that creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Walking Atlas | handled | {T}: You may put a land card from your hand onto the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>48 cards</summary>

- Abyssal Persecutor
- Amulet of Vigor
- Apex Hawks
- Archon of Redemption
- Basilisk Collar
- Bestial Menace
- Bojuka Bog
- Canopy Cover
- Celestial Colonnade
- Chain Reaction
- Comet Storm
- Corrupted Zendikon
- Crusher Zendikon
- Dead Reckoning
- Deathforge Shaman
- Enclave Elite
- Everflowing Chalice
- Explore
- Gnarlid Pack
- Guardian Zendikon
- Hada Freeblade
- Halimar Excavator
- Harabaz Druid
- Jace, the Mind Sculptor
- Joraga Warcaller
- Kor Firewalker
- Lodestone Golem
- Mire's Toll
- Mordant Dragon
- Nature's Claim
- Novablast Wurm
- Omnath, Locus of Mana
- Quag Vampires
- Quest for Renewal
- Refraction Trap
- Ricochet Trap
- Roiling Terrain
- Ruthless Cullblade
- Searing Blaze
- Skitter of Lizards
- Strength of the Tajuru
- Tectonic Edge
- Terastodon
- Terra Eternal
- Tuktuk Scrapper
- Vastwood Animist
- Vastwood Zendikon
- Wind Zendikon

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Landfall | 3 | Avenger of Zendikar, Calcite Snapper, Caustic Crawler | wwk |
| at the beginning of your upkeep, sacrifice ~ unless you return a land you control to its owner's hand. | 1 | Vapor Snare | wwk |
| at the beginning of your upkeep, you may look at the top card of your library. if it's a creature card, you may reveal it and put a quest counter on ~. | 1 | Quest for Ula's Temple | wwk |
| if a white creature is attacking, you may pay {M}{M} rather than pay ~ mana cost. exile target attacking creature. create a token that's a copy of that creature | 1 | Nemesis Trap | wwk |
| multikicker {M}{M} (you may pay an additional {M}{M} any number of times as you cast ~.) counter target spell unless its controller pays {M}. draw a card for ea | 1 | Spell Contortion | wwk |
| put a +N/+N counter on target creature you control. another target creature blocks it ~ if able. | 1 | Feral Contest | wwk |
| return target permanent you control and target permanent you don"..." hands. | 1 | Aether Tradewinds | wwk |
| search your library for any number of nonland cards, exile them, then shuffle. | 1 | Selective Memory | wwk |
| target creature gets -N/-N until end of turn. you may tap any number of untapped vampire creatures you control. if you do, put a +N/+N counter on each of those  | 1 | Urge to Feed | wwk |
| when ~ enters, create a N/N green wolf creature token for each time it was kicked. | 1 | Wolfbriar Elemental | wwk |
| when ~ enters, target opponent discards a card for each time it was kicked. | 1 | Bloodhusk Ritualist | wwk |
| when ~ enters, up to N target creatures gain flying until end of turn, where N is the number of times ~ was kicked. | 1 | Voyager Drake | wwk |
| when ~ enters, you gain N life for each time it was kicked. | 1 | Lightkeeper of Emeria | wwk |
| when ~ leaves the battlefield, return all cards exiled with it to the battlefield under their owners' control. | 1 | Admonition Angel | wwk |
| whenever a creature an opponent controls attacks, if you"..."s controller pays {M}. | 1 | Kazuul, Tyrant of the Cliffs | wwk |
| whenever thada adel deals combat damage to a player, search that player's library for an artifact card and exile it. then that player shuffles. until end of tur | 1 | Thada Adel, Acquisitor | wwk |
| whenever wrexial deals combat damage to a player, you may cast target instant or sorcery card from that player's graveyard without paying its mana cost. if that | 1 | Wrexial, the Risen Deep | wwk |
| whenever you cast a kicked spell, you may have ~ deal damage to any target equal to the number of times that spell was kicked. | 1 | Rumbling Aftershocks | wwk |
| whenever ~ or another ally you control enters, you may have allies you control gain lifelink until end of turn, and you may put a +N/+N counter on ~. | 1 | Talus Paladin | wwk |
| whenever ~ or another ally you control enters, you may have ally creatures you control get +N/+N until end of turn. | 1 | Akoum Battlesinger | wwk |
| you may have ~ enter as a copy of any ally creature on the battlefield. | 1 | Jwari Shapeshifter | wwk |
| {M}: put target creature card from an opponent's graveyard onto the battlefield under your control if its mana value is less than or equal to the number of alli | 1 | Agadeem Occultist | wwk |
| {M}: target player gains control of target artifact, creature, or land you control. | 1 | Bazaar Trader | wwk |
| ~ costs {M} less to cast for each attacking creature. create a N/N colorless construct artifact creature token with trample. exile it at the beginning of your n | 1 | Stone Idol Trap | wwk |
| ~ gets -N/-N, where N is your life total. | 1 | Death's Shadow | wwk |

## Notes



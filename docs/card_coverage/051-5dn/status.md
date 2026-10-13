# Fifth Dawn (5dn)

- Expansion: 051
- Set code: `5dn`
- Release date: 2004-06-04
- Cards in scope (Modern/Pioneer/Standard-legal): 162

## Legality

| Format | Legal cards |
|---|---|
| Modern | 162 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 29 | 17.9% |
| Works (untested) | 104 | 64.2% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 29 | 17.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Acquire | silent | Search target opponent's library for an artifact card and put that card onto the battlefield under your control. Then that player shuffles. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| All Suns' Dawn | silent | For each color, return up to one target card of that color from your graveyard to your hand. Exile All Suns' Dawn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Avarice Totem | silent | {5}: Exchange control of this artifact and target nonland permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Beacon of Immortality | silent | Double target player's life total. Shuffle Beacon of Immortality into its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Beacon of Tomorrows | silent | Target player takes an extra turn after this one. Shuffle Beacon of Tomorrows into its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cosmic Larva | silent | At the beginning of your upkeep, sacrifice this creature unless you sacrifice two lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Door to Nothingness | silent | {W}{W}{U}{U}{B}{B}{R}{R}{G}{G}, {T}, Sacrifice this artifact: Target player loses the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Doubling Cube | silent | {3}, {T}: Double the amount of each type of unspent mana you have. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ferropede | silent | Whenever this creature deals combat damage to a player, you may remove a counter from target permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fold into Aether | silent | Counter target spell. If that spell is countered this way, its controller may put a creature card from their hand onto the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grafted Wargear | silent | Whenever this Equipment becomes unattached from a permanent, sacrifice that permanent. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Helm of Kaldra | silent | {1}: If you control Equipment named Helm of Kaldra, Sword of Kaldra, and Shield of Kaldra, create Kaldra, a legendary 4/4 colorless Avatar creature token. Attac | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magnetic Theft | silent | Attach target Equipment to target creature. (Control of the Equipment doesn't change.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mephidross Vampire | silent | Each creature you control is a Vampire in addition to its other creature types and has "Whenever this creature deals damage to a creature, put a +1/+1 counter o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Myr Quadropod | silent | {3}: Switch this creature's power and toughness until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Myr Servitor | silent | At the beginning of your upkeep, if this creature is on the battlefield, each player returns all cards named Myr Servitor from their graveyard to the battlefiel | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Possessed Portal | silent | At the beginning of each end step, each player sacrifices a permanent of their choice unless they discard a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Retaliate | silent | Destroy all creatures that dealt damage to you this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reversal of Fortune | silent | Target opponent reveals their hand. You may copy an instant or sorcery card in it. If you do, you may cast the copy without paying its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Roar of Reclamation | silent | Each player returns all artifact cards from their graveyard to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Skullcage | silent | At the beginning of each opponent's upkeep, this artifact deals 2 damage to that player unless they have exactly three or exactly four cards in hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spinal Parasite | silent | Remove two +1/+1 counters from this creature: Remove a counter from target permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Summoner's Egg | silent | Imprint — When this creature enters, you may exile a card from your hand face down. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bringer of the Red Dawn | notice | At the beginning of your upkeep, you may untap target creature and gain control of it until end of turn. That creature gains haste until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Chimeric Coils | notice | {X}{1}: This artifact becomes an X/X Construct artifact creature. Sacrifice it at the beginning of the next end step. | unparsed remainder: Sacrifice it at the beginning of the next end step. | Y/-/- | not_working |
| Plunge into Darkness | notice | Choose one — • Sacrifice any number of creatures. You gain 3 life for each creature sacrificed this way. • Pay any amount of life, then look at that many cards  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Rude Awakening | notice | Choose one — • Untap all lands you control. • Until end of turn, lands you control become 2/2 creatures that are still lands. Entwine {2}{G} (Choose both if you | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Spectral Shift | notice | Choose one — • Change the text of target spell or permanent by replacing all instances of one basic land type with another. (This effect lasts indefinitely.) •  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Tangle Asp | notice | Whenever this creature blocks or becomes blocked by a creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Abuna's Chant | handled | Choose one — • You gain 5 life. • Prevent the next 5 damage that would be dealt to target creature this turn. Entwine {2} (Choose both if you pay the entwine co | the engine reads this text and performs it | Y/-/- | not_tested |
| Advanced Hoverguard | handled | {U}: This creature gains shroud until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Anodet Lurker | handled | When this creature dies, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Arachnoid | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Arcbound Wanderer | handled | Modular | machines/keywords.py | Y/-/- | not_tested |
| Armed Response | handled | Armed Response deals damage to target attacking creature equal to the number of Equipment you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Artificer's Intuition | handled | {U}, Discard an artifact card: Search your library for an artifact card with mana value 1 or less, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auriok Champion | handled | Whenever another creature enters, you may gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auriok Salvagers | handled | {1}{W}: Return target artifact card with mana value 1 or less from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auriok Windwalker | handled | {T}: Attach target Equipment you control to target creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Baton of Courage | handled | Remove a charge counter from this artifact: Target creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Battered Golem | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Beacon of Creation | handled | Create a 1/1 green Insect creature token for each Forest you control. Shuffle Beacon of Creation into its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Beacon of Destruction | handled | Beacon of Destruction deals 5 damage to any target. Shuffle Beacon of Destruction into its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blasting Station | handled | {T}, Sacrifice a creature: This artifact deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blind Creeper | handled | Whenever a player casts a spell, this creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blinkmoth Infusion | handled | Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.) Untap all artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bringer of the Black Dawn | handled | You may pay {W}{U}{B}{R}{G} rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bringer of the Blue Dawn | handled | You may pay {W}{U}{B}{R}{G} rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bringer of the Green Dawn | handled | You may pay {W}{U}{B}{R}{G} rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bringer of the White Dawn | handled | You may pay {W}{U}{B}{R}{G} rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cackling Imp | handled | {T}: Target player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Channel the Suns | handled | Add {W}{U}{B}{R}{G}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Clearwater Goblet | handled | At the beginning of your upkeep, you may gain life equal to the number of charge counters on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Clock of Omens | handled | Tap two untapped artifacts you control: Untap target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Composite Golem | handled |  |  | Y/-/- | not_tested |
| Condescend | handled | Counter target spell unless its controller pays {X}. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest  | the engine reads this text and performs it | Y/-/- | not_tested |
| Conjurer's Bauble | handled | {T}, Sacrifice this artifact: Put up to one target card from your graveyard on the bottom of your library. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dawn's Reflection | handled | Whenever enchanted land is tapped for mana, its controller adds an additional two mana in any combination of colors. | the engine reads this text and performs it | Y/-/- | not_tested |
| Desecration Elemental | handled | Whenever a player casts a spell, sacrifice a creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Disruption Aura | handled | Enchanted artifact has "At the beginning of your upkeep, sacrifice this artifact unless you pay its mana cost." | the engine reads this text and performs it | Y/-/- | not_tested |
| Dross Crocodile | handled |  |  | Y/-/- | not_tested |
| Early Frost | handled | Tap up to three target lands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ebon Drake | handled | Whenever a player casts a spell, you lose 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Endless Whispers | handled | Each creature has "When this creature dies, choose target opponent. That player puts this card from its owner's graveyard onto the battlefield under their contr | the engine reads this text and performs it | Y/-/- | not_tested |
| Energy Chamber | handled | At the beginning of your upkeep, choose one — • Put a +1/+1 counter on target artifact creature. • Put a charge counter on target noncreature artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ensouled Scimitar | handled | {3}: This artifact becomes a 1/5 Spirit artifact creature with flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Etched Oracle | handled | {1}, Remove four +1/+1 counters from this creature: Target player draws three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eyes of the Watcher | handled | Whenever you cast an instant or sorcery spell, you may pay {1}. If you do, scry 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fangren Pathcutter | handled | Whenever this creature attacks, attacking creatures gain trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Feedback Bolt | handled | Feedback Bolt deals damage to target player or planeswalker equal to the number of artifacts you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ferocious Charge | handled | Target creature gets +4/+4 until end of turn. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top  | the engine reads this text and performs it | Y/-/- | not_tested |
| Fill with Fright | handled | Target player discards two cards. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order | the engine reads this text and performs it | Y/-/- | not_tested |
| Fleshgrafter | handled | Discard an artifact card: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Furnace Whelp | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gemstone Array | handled | {2}: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Cannon | handled | {2}: This artifact deals 1 damage to any target. Sacrifice this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Granulate | handled | Destroy each nonland artifact with mana value 4 or less. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guardian Idol | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Healer's Headdress | handled | Equipped creature gets +0/+2 and has "{T}: Prevent the next 1 damage that would be dealt to any target this turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Heliophial | handled | {2}, Sacrifice this artifact: It deals damage equal to the number of charge counters on it to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horned Helm | handled | Equipped creature gets +1/+1 and has trample. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hoverguard Sweepers | handled | When this creature enters, you may return up to two target creatures to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Infused Arrows | handled | {T}, Remove X charge counters from this artifact: Target creature gets -X/-X until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into Thin Air | handled | Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.) Return target artifact to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ion Storm | handled | {1}{R}, Remove a +1/+1 counter or a charge counter from a permanent you control: This enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Iron-Barb Hellion | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Joiner Adept | handled | Lands you control have "{T}: Add one mana of any color." | the engine reads this text and performs it | Y/-/- | not_tested |
| Krark-Clan Engineers | handled | {R}, Sacrifice two artifacts: Destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Krark-Clan Ironworks | handled |  |  | Y/-/- | not_tested |
| Krark-Clan Ogre | handled | {R}, Sacrifice an artifact: Target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Leonin Squire | handled | When this creature enters, return target artifact card with mana value 1 or less from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lose Hope | handled | Target creature gets -1/-1 until end of turn. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top  | the engine reads this text and performs it | Y/-/- | not_tested |
| Loxodon Anchorite | handled | {T}: Prevent the next 2 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Loxodon Stalwart | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lunar Avenger | handled | Remove a +1/+1 counter from this creature: This creature gains your choice of flying, first strike, or haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moriok Rigger | handled | Whenever an artifact is put into a graveyard from the battlefield, you may put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Neurok Stealthsuit | handled | Equipped creature has shroud. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nim Grotesque | handled | This creature gets +1/+0 for each artifact you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ouphe Vandals | handled | {G}, Sacrifice this creature: Counter target activated ability from an artifact source and destroy that artifact if it's on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pentad Prism | handled | Sunburst | machines/replacement.py (_sunburst_modifier, CR 702.44a) | Y/-/- | not_tested |
| Plasma Elemental | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Qumulox | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Rain of Rust | handled | Choose one — • Destroy target artifact. • Destroy target land. Entwine {3}{R} (Choose both if you pay the entwine cost.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Raksha Golden Cub | handled | As long as Raksha Golden Cub is equipped, Cat creatures you control get +2/+2 and have double strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razormane Masticore | handled | At the beginning of your upkeep, sacrifice this creature unless you discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Salvaging Station | handled | {T}: Return target noncreature artifact card with mana value 1 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sawtooth Thresher | handled | Remove two +1/+1 counters from this creature: It gets +4/+4 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Screaming Fury | handled | Target creature gets +5/+0 and gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serum Visions | handled | Draw a card. Scry 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shattered Dreams | handled | Target opponent reveals their hand. You choose an artifact card from it. That player discards that card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skyhunter Prowler | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Skyhunter Skirmisher | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Skyreach Manta | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Spark Elemental | handled | At the beginning of the end step, sacrifice this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sparring Collar | handled | Equipped creature has first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Staff of Domination | handled | {1}: Untap this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stand Firm | handled | Target creature gets +1/+1 until end of turn. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top  | the engine reads this text and performs it | Y/-/- | not_tested |
| Steelshaper's Gift | handled | Search your library for an Equipment card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Summoning Station | handled | {T}: Create a 2/2 colorless Pincher creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Suncrusher | handled | {4}, {T}, Remove a +1/+1 counter from this creature: Destroy target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Suntouched Myr | handled | Sunburst | machines/replacement.py (_sunburst_modifier, CR 702.44a) | Y/-/- | not_tested |
| Sylvok Explorer | handled |  |  | Y/-/- | not_tested |
| Tel-Jilad Justice | handled | Destroy target artifact. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Tel-Jilad Lifebreather | handled | {G}, {T}, Sacrifice a Forest: Regenerate target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thermal Navigator | handled | Sacrifice an artifact: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thought Courier | handled | {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tyrranax | handled | {1}{G}: This creature gets -1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vanquish | handled | Destroy target blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vedalken Mastermind | handled | {U}, {T}: Return target permanent you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vedalken Orrery | handled | You may cast spells as though they had flash. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viridian Scout | handled | {2}{G}, Sacrifice this creature: It deals 2 damage to target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vulshok Sorcerer | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wayfarer's Bauble | handled | {2}, {T}, Sacrifice this artifact: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>29 cards</summary>

- Beacon of Unrest
- Cranial Plating
- Crucible of Worlds
- Devour in Shadow
- Engineered Explosives
- Eon Hub
- Eternal Witness
- Fist of Suns
- Goblin Brawler
- Grinding Station
- Lantern of Insight
- Magma Jet
- Mana Geyser
- Mycosynth Golem
- Night's Whisper
- Opaline Bracers
- Paradise Mantle
- Razorgrass Screen
- Relentless Rats
- Rite of Passage
- Silent Arbiter
- Solarion
- Stasis Cocoon
- Synod Centurion
- Tornado Elemental
- Trinket Mage
- Vedalken Shackles
- Vicious Betrayal
- Viridian Lorebearers

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Choose one | 3 | Plunge into Darkness, Rude Awakening, Spectral Shift | 5dn |
| Imprint | 1 | Summoner's Egg | 5dn |
| at the beginning of each end step, each player sacrifices a permanent of their choice unless they discard a card. | 1 | Possessed Portal | 5dn |
| at the beginning of each opponent's upkeep, ~ deals N damage to that player unless they have exactly three or exactly four cards in hand. | 1 | Skullcage | 5dn |
| at the beginning of your upkeep, if ~ is on the battlefield, each player returns all cards named ~ from their graveyard to the battlefield. | 1 | Myr Servitor | 5dn |
| at the beginning of your upkeep, sacrifice ~ unless you sacrifice two lands. | 1 | Cosmic Larva | 5dn |
| at the beginning of your upkeep, you may untap target creature and gain control of it until end of turn. that creature gains haste until end of turn. | 1 | Bringer of the Red Dawn | 5dn |
| attach target equipment to target creature. (control of the equipment doesn't change.) | 1 | Magnetic Theft | 5dn |
| counter target spell. if that spell is countered ~, its controller may put a creature card from their hand onto the battlefield. | 1 | Fold into Aether | 5dn |
| destroy all creatures that dealt damage to you ~. | 1 | Retaliate | 5dn |
| double target player"..."s library. | 1 | Beacon of Immortality | 5dn |
| each creature you control is a vampire in addition to its other creature types and has "..." | 1 | Mephidross Vampire | 5dn |
| each player returns all artifact cards from their graveyard to the battlefield. | 1 | Roar of Reclamation | 5dn |
| for each color, return up to one target card of that color from your graveyard to your hand. exile ~. | 1 | All Suns' Dawn | 5dn |
| remove two +N/+N counters from ~: remove a counter from target permanent. | 1 | Spinal Parasite | 5dn |
| search target opponent's library for an artifact card and put that card onto the battlefield under your control. then that player shuffles. | 1 | Acquire | 5dn |
| target opponent reveals their hand. you may copy an instant or sorcery card in it. if you do, you may cast the copy without paying its mana cost. | 1 | Reversal of Fortune | 5dn |
| target player takes an extra turn after ~. shuffle ~ into its owner's library. | 1 | Beacon of Tomorrows | 5dn |
| whenever ~ becomes unattached from a permanent, sacrifice that permanent. | 1 | Grafted Wargear | 5dn |
| whenever ~ blocks or becomes blocked by a creature, destroy that creature at end of combat. | 1 | Tangle Asp | 5dn |
| whenever ~ deals combat damage to a player, you may remove a counter from target permanent. | 1 | Ferropede | 5dn |
| {M}, {M}: double the amount of each type of unspent mana you have. | 1 | Doubling Cube | 5dn |
| {M}: exchange control of ~ and target nonland permanent. | 1 | Avarice Totem | 5dn |
| {M}: if you control equipment named ~, sword of kaldra, and shield of kaldra, create kaldra, a legendary N/N colorless avatar creature token. attach those equip | 1 | Helm of Kaldra | 5dn |
| {M}: switch ~ power and toughness until end of turn. | 1 | Myr Quadropod | 5dn |
| {M}{M}: ~ becomes an N/N construct artifact creature. sacrifice it at the beginning of the next end step. | 1 | Chimeric Coils | 5dn |
| {M}{M}{M}{M}{M}{M}{M}{M}{M}{M}, {M}, sacrifice ~: target player loses the game. | 1 | Door to Nothingness | 5dn |

## Notes



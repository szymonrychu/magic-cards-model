# Journey into Nyx (jou)

- Expansion: 149
- Set code: `jou`
- Release date: 2014-05-02
- Cards in scope (Modern/Pioneer/Standard-legal): 161

## Legality

| Format | Legal cards |
|---|---|
| Modern | 161 |
| Pioneer | 161 |
| Standard | 5 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 32 | 19.9% |
| Works (untested) | 103 | 64.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 26 | 16.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Armament of Nyx | silent | Enchanted creature has double strike as long as it's an enchantment. Otherwise, prevent all damage that would be dealt by enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Athreos, God of Passage | silent | Whenever another creature you own dies, return it to your hand unless target opponent pays 3 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blinding Flare | silent | Strive — This spell costs {R} more to cast for each target beyond the first. Any number of target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dakra Mystic | silent | {U}, {T}: Each player reveals the top card of their library. You may put the revealed cards into their owners' graveyards. If you don't, each player draws a car | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Daring Thief | silent | Inspired — Whenever this creature becomes untapped, you may exchange control of target nonland permanent you control and target permanent an opponent controls t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Deicide | silent | Exile target enchantment. If the exiled card is a God card, search its controller's graveyard, hand, and library for any number of cards with the same name as t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Disciple of Deceit | silent | Inspired — Whenever this creature becomes untapped, you may discard a nonland card. If you do, search your library for a card with the same mana value as that c | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Goldenhide Ox | silent | Constellation — Whenever this creature or another enchantment you control enters, target creature must be blocked this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Harness by Force | silent | Strive — This spell costs {2}{R} more to cast for each target beyond the first. Gain control of any number of target creatures until end of turn. Untap those cr | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hydra Broodmaster | silent | When this creature becomes monstrous, create X X/X green Hydra creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| King Macar, the Gold-Cursed | silent | Inspired — Whenever King Macar becomes untapped, you may exile target creature. If you do, create a Gold token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kruphix's Insight | silent | Reveal the top six cards of your library. Put up to three enchantment cards from among them into your hand and the rest of the revealed cards into your graveyar | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nature's Panoply | silent | Strive — This spell costs {2}{G} more to cast for each target beyond the first. Choose any number of target creatures. Put a +1/+1 counter on each of them. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nyx Infusion | silent | Enchanted creature gets +2/+2 as long as it's an enchantment. Otherwise, it gets -2/-2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pharika, God of Affliction | silent | {B}{G}: Exile target creature card from a graveyard. Its owner creates a 1/1 black and green Snake enchantment creature token with deathtouch. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Polymorphous Rush | silent | Strive — This spell costs {1}{U} more to cast for each target beyond the first. Choose a creature on the battlefield. Any number of target creatures you control | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pull from the Deep | silent | Return up to one target instant card and up to one target sorcery card from your graveyard to your hand. Exile Pull from the Deep. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Renowned Weaver | silent | {1}{G}, Sacrifice this creature: Create a 1/3 green Spider enchantment creature token with reach. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rise of Eagles | silent | Create two 2/2 blue Bird enchantment creature tokens with flying. Scry 1. (Look at the top card of your library. You may put that card on the bottom.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sage of Hours | silent | Remove all +1/+1 counters from this creature: For each five counters removed this way, take an extra turn after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Stonewise Fortifier | silent | {4}{W}: Prevent all damage that would be dealt to this creature by target creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Swarmborn Giant | silent | When you're dealt combat damage, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Bearer of the Heavens | notice | When this creature dies, destroy all permanents at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Brain Maggot | notice | When this creature enters, target opponent reveals their hand and you choose a nonland card from it. Exile that card until this creature leaves the battlefield. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Colossal Heroics | notice | Strive — This spell costs {1}{G} more to cast for each target beyond the first. Any number of target creatures each get +2/+2 until end of turn. Untap those cre | unparsed remainder: Untap those creatures. | Y/Y/- | not_working |
| Silence the Believers | notice | Strive — This spell costs {2}{B} more to cast for each target beyond the first. Exile any number of target creatures and all Auras attached to them. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Agent of Erebos | handled | Constellation — Whenever this creature or another enchantment you control enters, exile target player's graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ajani's Presence | handled | Strive — This spell costs {2}{W} more to cast for each target beyond the first. Any number of target creatures each get +1/+1 and gain indestructible until end  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ajani, Mentor of Heroes | handled | +1: Distribute three +1/+1 counters among one, two, or three target creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Akroan Line Breaker | handled | Heroic — Whenever you cast a spell that targets this creature, this creature gets +2/+0 and gains intimidate until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Akroan Mastiff | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Armory of Iroas | handled | Whenever equipped creature attacks, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aspect of Gorgon | handled | Enchanted creature gets +1/+3 and has deathtouch. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Banishing Light | handled | When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bassara Tower Archer | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Cast into Darkness | handled | Enchanted creature gets -2/-0 and can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chariot of Victory | handled | Equipped creature has first strike, trample, and haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cloaked Siren | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Consign to Dust | handled | Strive — This spell costs {2}{G} more to cast for each target beyond the first. Destroy any number of target artifacts and/or enchantments. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cruel Feeding | handled | Strive — This spell costs {2}{B} more to cast for each target beyond the first. Any number of target creatures each get +1/+0 and gain lifelink until end of tur | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crystalline Nautilus | handled | When this permanent becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cyclops of Eternal Fury | handled | Creatures you control have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dawnbringer Charioteers | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desecration Plague | handled | Destroy target enchantment or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desperate Stand | handled | Strive — This spell costs {R}{W} more to cast for each target beyond the first. Any number of target creatures each get +2/+0 and gain first strike and vigilanc | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dictate of Erebos | handled | Whenever a creature you control dies, each opponent sacrifices a creature of their choice. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dictate of Heliod | handled | Creatures you control get +2/+2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dictate of Karametra | handled | Whenever a player taps a land for mana, that player adds one mana of any type that land produced. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dictate of Kruphix | handled | At the beginning of each player's draw step, that player draws an additional card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dictate of the Twin Gods | handled | If a source would deal damage to a permanent or player, it deals double that damage to that permanent or player instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Doomwake Giant | handled | Constellation — Whenever this creature or another enchantment you control enters, creatures your opponents control get -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dreadbringer Lampads | handled | Constellation — Whenever this creature or another enchantment you control enters, target creature gains intimidate until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eagle of the Watch | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Eidolon of Blossoms | handled | Constellation — Whenever this creature or another enchantment you control enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eidolon of Rhetoric | handled | Each player can't cast more than one spell each turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eidolon of the Great Revel | handled | Whenever a player casts a spell with mana value 3 or less, this creature deals 2 damage to that player. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Extinguish All Hope | handled | Destroy all nonenchantment creatures. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Feast of Dreams | handled | Destroy target enchanted creature or enchantment creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Felhide Petrifier | handled | Other Minotaur creatures you control have deathtouch. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flamespeaker's Will | handled | Enchanted creature gets +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fleetfeather Cockatrice | handled | {5}{G}{U}: Monstrosity 3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flurry of Horns | handled | Create two 2/3 red Minotaur creature tokens with haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Font of Fertility | handled | {1}{G}, Sacrifice this enchantment: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Font of Fortunes | handled | {1}{U}, Sacrifice this enchantment: Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Font of Ire | handled | {3}{R}, Sacrifice this enchantment: It deals 5 damage to target player or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Font of Return | handled | {3}{B}, Sacrifice this enchantment: Return up to three target creature cards from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Font of Vigor | handled | {2}{W}, Sacrifice this enchantment: You gain 7 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forgeborn Oreads | handled | Constellation — Whenever this creature or another enchantment you control enters, this creature deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gluttonous Cyclops | handled | {5}{R}{R}: Monstrosity 3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gnarled Scarhide | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gold-Forged Sentinel | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Golden Hind | handled |  |  | Y/Y/- | not_tested |
| Grim Guardian | handled | Constellation — Whenever this creature or another enchantment you control enters, each opponent loses 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harvestguard Alseids | handled | Constellation — Whenever this creature or another enchantment you control enters, prevent all damage that would be dealt to target creature this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Humbler of Mortals | handled | Constellation — Whenever this creature or another enchantment you control enters, creatures you control gain trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hypnotic Siren | handled | You control enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kiora's Dismissal | handled | Strive — This spell costs {U} more to cast for each target beyond the first. Return any number of target enchantments to their owners' hands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Knowledge and Power | handled | Whenever you scry, you may pay {2}. If you do, this enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lagonna-Band Trailblazer | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Leonin Iconoclast | handled | Heroic — Whenever you cast a spell that targets this creature, destroy target enchantment creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lightning Diadem | handled | When this Aura enters, it deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Market Festival | handled | Whenever enchanted land is tapped for mana, its controller adds an additional two mana in any combination of colors. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mogis's Warhound | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mortal Obstinacy | handled | Enchanted creature gets +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nightmarish End | handled | Target creature gets -X/-X until end of turn, where X is the number of cards in your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nyx Weaver | handled | At the beginning of your upkeep, mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nyx-Fleece Ram | handled | At the beginning of your upkeep, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oakheart Dryads | handled | Constellation — Whenever this creature or another enchantment you control enters, target creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oreskos Swiftclaw | handled |  |  | Y/Y/- | not_tested |
| Pensive Minotaur | handled |  |  | Y/Y/- | not_tested |
| Phalanx Formation | handled | Strive — This spell costs {1}{W} more to cast for each target beyond the first. Any number of target creatures each gain double strike until end of turn. (They  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pharika's Chosen | handled | Deathtouch | machines/combat.py | Y/Y/- | not_tested |
| Pheres-Band Thunderhoof | handled | Heroic — Whenever you cast a spell that targets this creature, put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pheres-Band Warchief | handled | Other Centaur creatures you control get +1/+1 and have vigilance and trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pin to the Earth | handled | Enchanted creature gets -6/-0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prophetic Flamespeaker | handled | Whenever this creature deals combat damage to a player, exile the top card of your library. You may play it this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ravenous Leucrocota | handled | {6}{G}: Monstrosity 3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Returned Reveler | handled | When this creature dies, each player mills three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Revel of the Fallen God | handled | Create four 2/2 red and green Satyr creature tokens with haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reviving Melody | handled | Choose one or both — • Return target creature card from your graveyard to your hand. • Return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Riptide Chimera | handled | At the beginning of your upkeep, return an enchantment you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rollick of Abandon | handled | All creatures get +2/-2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rotted Hulk | handled |  |  | Y/Y/- | not_tested |
| Rouse the Mob | handled | Strive — This spell costs {2}{R} more to cast for each target beyond the first. Any number of target creatures each get +2/+0 and gain trample until end of turn | the engine reads this text and performs it | Y/Y/- | not_tested |
| Satyr Grovedancer | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Satyr Hoplite | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sigiled Skink | handled | Whenever this creature attacks, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sigiled Starfish | handled | {T}: Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skybind | handled | Constellation — Whenever this enchantment or another enchantment you control enters, exile target nonenchantment permanent. Return that card to the battlefield  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skyspear Cavalry | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Spawn of Thraxes | handled | When this creature enters, it deals damage to any target equal to the number of Mountains you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spite of Mogis | handled | Spite of Mogis deals damage to target creature equal to the number of instant and sorcery cards in your graveyard. Scry 1. (Look at the top card of your library | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spiteful Blow | handled | Destroy target creature and target land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Squelching Leeches | handled | Squelching Leeches's power and toughness are each equal to the number of Swamps you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Starfall | handled | Starfall deals 3 damage to target creature. If that creature is an enchantment, Starfall deals 3 damage to that creature's controller. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Strength from the Fallen | handled | Constellation — Whenever this enchantment or another enchantment you control enters, target creature gets +X/+X until end of turn, where X is the number of crea | the engine reads this text and performs it | Y/Y/- | not_tested |
| Supply-Line Cranes | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Temple of Malady | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tethmos High Priest | handled | Heroic — Whenever you cast a spell that targets this creature, return target creature card with mana value 2 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thassa's Devourer | handled | Constellation — Whenever this creature or another enchantment you control enters, target player mills two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thassa's Ire | handled | {3}{U}: You may tap or untap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thoughtrender Lamia | handled | Constellation — Whenever this creature or another enchantment you control enters, each opponent discards a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Triton Cavalry | handled | Heroic — Whenever you cast a spell that targets this creature, you may return target enchantment to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Triton Shorestalker | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Underworld Coinsmith | handled | Constellation — Whenever this creature or another enchantment you control enters, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| War-Wing Siren | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Whitewater Naiads | handled | Constellation — Whenever this creature or another enchantment you control enters, target creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wildfire Cerberus | handled | {5}{R}{R}: Monstrosity 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Worst Fears | handled | You control target player during that player's next turn. Exile Worst Fears. (You see all cards that player could see and make all decisions for them.) | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>32 cards</summary>

- Aegis of the Gods
- Aerial Formation
- Battlefield Thaumaturge
- Bloodcrazed Hoplite
- Countermand
- Deserter's Quarters
- Godhunter Octopus
- Godsend
- Hall of Triumph
- Heroes' Bane
- Hour of Need
- Hubris
- Interpret the Signs
- Iroas, God of Victory
- Keranos, God of Storms
- Kruphix, God of Horizons
- Launch the Fleet
- Mana Confluence
- Master of the Feast
- Nessian Game Warden
- Oppressive Rays
- Quarry Colossus
- Ritual of the Returned
- Scourge of Fleets
- Setessan Tactics
- Sightless Brawler
- Solidarity of Heroes
- Spirespine
- Stormchaser Chimera
- Temple of Epiphany
- Tormented Thoughts
- Twinflame

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Strive | 6 | Blinding Flare, Colossal Heroics, Harness by Force, Nature's Panoply, Polymorphous Rush | jou |
| Inspired | 3 | Daring Thief, Disciple of Deceit, King Macar, the Gold-Cursed | jou |
| Constellation | 1 | Goldenhide Ox | jou |
| create two N/N blue bird enchantment creature tokens with flying. scry N. (look at the top card of your library. you may put that card on the bottom.) | 1 | Rise of Eagles | jou |
| enchanted creature gets +N/+N as long as it's an enchantment. otherwise, it gets -N/-N. | 1 | Nyx Infusion | jou |
| enchanted creature has double strike as long as it's an enchantment. otherwise, prevent all damage that would be dealt by enchanted creature. | 1 | Armament of Nyx | jou |
| exile target enchantment. if the exiled card is a god card, search its controller's graveyard, hand, and library for any number of cards with the same name as t | 1 | Deicide | jou |
| remove all +N/+N counters from ~: for each five counters removed ~, take an extra turn after ~. | 1 | Sage of Hours | jou |
| return up to one target instant card and up to one target sorcery card from your graveyard to your hand. exile ~. | 1 | Pull from the Deep | jou |
| reveal the top six cards of your library. put up to three enchantment cards from among them into your hand and the rest of the revealed cards into your graveyar | 1 | Kruphix's Insight | jou |
| when you're dealt combat damage, sacrifice ~. | 1 | Swarmborn Giant | jou |
| when ~ becomes monstrous, create N N/N green hydra creature tokens. | 1 | Hydra Broodmaster | jou |
| when ~ dies, destroy all permanents at the beginning of the next end step. | 1 | Bearer of the Heavens | jou |
| when ~ enters, target opponent reveals their hand and you choose a nonland card from it. exile that card until ~ leaves the battlefield. | 1 | Brain Maggot | jou |
| whenever another creature you own dies, return it to your hand unless target opponent pays N life. | 1 | Athreos, God of Passage | jou |
| {M}, {M}: each player reveals the top card of their library. you may put the revealed cards into their owners"..."t, each player draws a card. | 1 | Dakra Mystic | jou |
| {M}{M}, sacrifice ~: create a N/N green spider enchantment creature token with reach. | 1 | Renowned Weaver | jou |
| {M}{M}: exile target creature card from a graveyard. its owner creates a N/N black and green snake enchantment creature token with deathtouch. | 1 | Pharika, God of Affliction | jou |
| {M}{M}: prevent all damage that would be dealt to ~ by target creature ~. | 1 | Stonewise Fortifier | jou |

## Notes



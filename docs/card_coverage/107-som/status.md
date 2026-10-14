# Scars of Mirrodin (som)

- Expansion: 107
- Set code: `som`
- Release date: 2010-10-01
- Cards in scope (Modern/Pioneer/Standard-legal): 215

## Legality

| Format | Legal cards |
|---|---|
| Modern | 215 |
| Pioneer | 21 |
| Standard | 4 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 47 | 21.9% |
| Works (untested) | 139 | 64.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 29 | 13.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Auriok Replica | silent | {W}, Sacrifice this creature: Prevent all damage a source of your choice would deal to you this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Carnifex Demon | silent | {B}, Remove a -1/-1 counter from this creature: Put a -1/-1 counter on each other creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Clone Shell | silent | Imprint — When this creature enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom of your library in any ord | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elspeth Tirel | silent | −5: Destroy all other permanents except for lands and tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Engulfing Slagwurm | silent | Whenever this creature blocks or becomes blocked by a creature, destroy that creature. You gain life equal to that creature's toughness. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fulgent Distraction | silent | Choose two target creatures. Tap those creatures, then unattach all Equipment from them. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Genesis Wave | silent | Reveal the top X cards of your library. You may put any number of permanent cards with mana value X or less from among them onto the battlefield. Then put all c | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Geth, Lord of the Vault | silent | {X}{B}: Put target artifact or creature card with mana value X from an opponent's graveyard onto the battlefield tapped under your control. Then that player mil | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Glint Hawk | silent | When this creature enters, sacrifice it unless you return an artifact you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Glint Hawk Idol | silent | Whenever another artifact you control enters, you may have this artifact become a 2/2 Bird artifact creature with flying until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grafted Exoskeleton | silent | Whenever this Equipment becomes unattached from a permanent, sacrifice that permanent. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Liege of the Tangle | silent | Whenever this creature deals combat damage to a player, you may choose any number of target lands you control and put an awakening counter on each of them. Each | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Myr Battlesphere | silent | Whenever this creature attacks, you may tap X untapped Myr you control. If you do, this creature gets +X/+0 until end of turn and deals X damage to the player o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Myr Galvanizer | silent | {1}, {T}: Untap each other Myr you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nim Deathmantle | silent | Equipped creature gets +2/+2, has intimidate, and is a black Zombie. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ogre Geargrabber | silent | Whenever this creature attacks, gain control of target Equipment an opponent controls until end of turn. Attach it to this creature. When you lose control of th | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Painful Quandary | silent | Whenever an opponent casts a spell, that player loses 5 life unless they discard a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Painsmith | silent | Whenever you cast an artifact spell, you may have target creature get +2/+0 and gain deathtouch until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Precursor Golem | silent | Whenever a player casts an instant or sorcery spell that targets only a single Golem, that player copies that spell for each other Golem that spell could target | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Prototype Portal | silent | {X}, {T}: Create a token that's a copy of the exiled card. X is the mana value of that card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Psychic Miasma | silent | Target player discards a card. If a land card is discarded this way, return Psychic Miasma to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sunblast Angel | silent | When this creature enters, destroy all tapped creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Turn Aside | silent | Counter target spell that targets a permanent you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Venser, the Sojourner | silent | −1: Creatures can't be blocked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vigil for the Lost | silent | Whenever a creature you control dies, you may pay {X}. If you do, you gain X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Viridian Revel | silent | Whenever an artifact is put into an opponent's graveyard from the battlefield, you may draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Flesh Allergy | notice | As an additional cost to cast this spell, sacrifice a creature. Destroy target creature. Its controller loses life equal to the number of creatures that died th | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Quicksilver Gargantuan | notice | You may have this creature enter as a copy of any creature on the battlefield, except it's 7/7. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Turn to Slag | notice | Turn to Slag deals 5 damage to target creature. Destroy all Equipment attached to that creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Abuna Acolyte | handled | {T}: Prevent the next 1 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Accorder's Shield | handled | Equipped creature gets +0/+3 and has vigilance. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Acid Web Spider | handled | When this creature enters, you may destroy target Equipment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Alpha Tyrranax | handled |  |  | Y/-/- | not_tested |
| Argentum Armor | handled | Equipped creature gets +6/+6. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auriok Edgewright | handled | Metalcraft — This creature has double strike as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auriok Sunchaser | handled | Metalcraft — As long as you control three or more artifacts, this creature gets +2/+2 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Barbed Battlegear | handled | Equipped creature gets +4/-1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Barrage Ogre | handled | {T}, Sacrifice an artifact: This creature deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bellowing Tanglewurm | handled | Other green creatures you control have intimidate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blackcleave Cliffs | handled | This land enters tapped unless you control two or fewer other lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blackcleave Goblin | handled | Haste | machines/combat.py | Y/-/- | not_tested |
| Blade-Tribe Berserkers | handled | Metalcraft — When this creature enters, if you control three or more artifacts, this creature gets +3/+3 and gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bladed Pinions | handled | Equipped creature has flying and first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bleak Coven Vampires | handled | Metalcraft — When this creature enters, if you control three or more artifacts, target player loses 4 life and you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blight Mamba | handled | {1}{G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blistergrub | handled | When this creature dies, each opponent loses 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blunt the Assault | handled | You gain 1 life for each creature on the battlefield. Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bonds of Quicksilver | handled | Enchanted creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Carapace Forger | handled | Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chimeric Mass | handled | This artifact enters with X charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chrome Steed | handled | Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Contagious Nim | handled | Infect | machines/combat.py | Y/-/- | not_tested |
| Copperhorn Scout | handled | Whenever this creature attacks, untap each other creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Copperline Gorge | handled | This land enters tapped unless you control two or fewer other lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Corpse Cur | handled | When this creature enters, you may return target creature card with infect from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corrupted Harvester | handled | {B}, Sacrifice a creature: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Culling Dais | handled | {T}, Sacrifice a creature: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cystbearer | handled | Infect | machines/combat.py | Y/-/- | not_tested |
| Darkslick Drake | handled | When this creature dies, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darksteel Axe | handled | Equipped creature gets +2/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darksteel Juggernaut | handled | Darksteel Juggernaut's power and toughness are each equal to the number of artifacts you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darksteel Sentinel | handled | Indestructible | machines/keywords.py | Y/-/- | not_tested |
| Dispense Justice | handled | Target player sacrifices an attacking creature of their choice. Metalcraft — That player sacrifices two attacking creatures of their choice instead if you contr | the engine reads this text and performs it | Y/-/- | not_tested |
| Dissipation Field | handled | Whenever a permanent deals damage to you, return it to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dross Hopper | handled | Sacrifice a creature: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Embersmith | handled | Whenever you cast an artifact spell, you may pay {1}. If you do, this creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ezuri's Archers | handled | Whenever this creature blocks a creature with flying, this creature gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ezuri's Brigade | handled | Metalcraft — As long as you control three or more artifacts, this creature gets +4/+4 and has trample. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ferrovore | handled | {R}, Sacrifice an artifact: This creature gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flameborn Hellion | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flight Spellbomb | handled | {T}, Sacrifice this artifact: Target creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fume Spitter | handled | Sacrifice this creature: Put a -1/-1 counter on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Furnace Celebration | handled | Whenever you sacrifice another permanent, you may pay {2}. If you do, this enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghalma's Warden | handled | Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glimmerpoint Stag | handled | When this creature enters, exile another target permanent. Return that card to the battlefield under its owner's control at the beginning of the next end step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glimmerpost | handled | When this land enters, you gain 1 life for each Locus on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Gaveleer | handled | This creature gets +2/+0 for each Equipment attached to it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golden Urn | handled | At the beginning of your upkeep, you may put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golem Artisan | handled | {2}: Target artifact creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golem Foundry | handled | Whenever you cast an artifact spell, you may put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golem's Heart | handled | Whenever a player casts an artifact spell, you may gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grand Architect | handled | Other blue creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grasp of Darkness | handled | Target creature gets -4/-4 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Halt Order | handled | Counter target artifact spell. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hand of the Praetors | handled | Other creatures you control with infect get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heavy Arbalest | handled | Equipped creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horizon Spellbomb | handled | {2}, {T}, Sacrifice this artifact: Search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ichor Rats | handled | When this creature enters, each player gets a poison counter. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ichorclaw Myr | handled | Whenever this creature becomes blocked, it gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inexorable Tide | handled | Whenever you cast a spell, proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Infiltration Lens | handled | Whenever equipped creature becomes blocked by a creature, you may draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Instill Infection | handled | Put a -1/-1 counter on target creature. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kuldotha Forgemaster | handled | {T}, Sacrifice three artifacts: Search your library for an artifact card, put it onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kuldotha Rebirth | handled | As an additional cost to cast this spell, sacrifice an artifact. Create three 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lifesmith | handled | Whenever you cast an artifact spell, you may pay {1}. If you do, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Livewire Lash | handled | Equipped creature gets +2/+0 and has "Whenever this creature becomes the target of a spell, this creature deals 2 damage to any target." | the engine reads this text and performs it | Y/-/- | not_tested |
| Loxodon Wayfarer | handled |  |  | Y/-/- | not_tested |
| Lumengrid Drake | handled | Metalcraft — When this creature enters, if you control three or more artifacts, return target creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lux Cannon | handled | {T}: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Melt Terrain | handled | Destroy target land. Melt Terrain deals 2 damage to that land's controller. | the engine reads this text and performs it | Y/-/- | not_tested |
| Memoricide | handled | Choose a nonland card name. Search target player's graveyard, hand, and library for any number of cards with that name and exile them. Then that player shuffles | the engine reads this text and performs it | Y/-/- | not_tested |
| Molder Beast | handled | Whenever an artifact is put into a graveyard from the battlefield, this creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moriok Reaver | handled |  |  | Y/-/- | not_tested |
| Moriok Replica | handled | {1}{B}, Sacrifice this creature: You draw two cards and you lose 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myr Propagator | handled | {3}, {T}: Create a token that's a copy of this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myr Reservoir | handled | {3}, {T}: Return target Myr card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myrsmith | handled | Whenever you cast an artifact spell, you may pay {1}. If you do, create a 1/1 colorless Myr artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Necrogen Censer | handled | This artifact enters with two charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Necrogen Scudder | handled | When this creature enters, you lose 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Necropede | handled | When this creature dies, you may put a -1/-1 counter on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Neurok Invisimancer | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Neurok Replica | handled | {1}{U}, Sacrifice this creature: Return target creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Origin Spellbomb | handled | {1}, {T}, Sacrifice this artifact: Create a 1/1 colorless Myr artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Oxidda Daredevil | handled | Sacrifice an artifact: This creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Oxidda Scrapmelter | handled | When this creature enters, destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Palladium Myr | handled |  |  | Y/Y/- | not_tested |
| Panic Spellbomb | handled | {T}, Sacrifice this artifact: Target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Perilous Myr | handled | When this creature dies, it deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Plague Stinger | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Plated Seastrider | handled |  |  | Y/-/- | not_tested |
| Putrefax | handled | At the beginning of the end step, sacrifice this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ratchet Bomb | handled | {T}: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Razor Hippogriff | handled | When this creature enters, return target artifact card from your graveyard to your hand. You gain life equal to that card's mana value. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razorfield Thresher | handled |  |  | Y/-/- | not_tested |
| Razorverge Thicket | handled | This land enters tapped unless you control two or fewer other lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Relic Putrescence | handled | Whenever enchanted artifact becomes tapped, its controller gets a poison counter. | the engine reads this text and performs it | Y/-/- | not_tested |
| Revoke Existence | handled | Exile target artifact or enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Saberclaw Golem | handled | {R}: This creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Salvage Scout | handled | {W}, Sacrifice this creature: Return target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scoria Elemental | handled |  |  | Y/-/- | not_tested |
| Scrapdiver Serpent | handled | This creature can't be blocked as long as defending player controls an artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Screeching Silcaw | handled | Metalcraft — Whenever this creature deals combat damage to a player, if you control three or more artifacts, that player mills four cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seachrome Coast | handled | This land enters tapped unless you control two or fewer other lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seize the Initiative | handled | Target creature gets +1/+1 and gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skinrender | handled | When this creature enters, put three -1/-1 counters on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skithiryx, the Blight Dragon | handled | {B}: Skithiryx gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sky-Eel School | handled | When this creature enters, draw a card, then discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slice in Twain | handled | Destroy target artifact or enchantment. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snapsail Glider | handled | Metalcraft — This creature has flying as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soliton | handled | {U}: Untap this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Steady Progress | handled | Proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.) Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stoic Rebuttal | handled | Metalcraft — This spell costs {1} less to cast if you control three or more artifacts. Counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Strata Scythe | handled | Imprint — When this Equipment enters, search your library for a land card, exile it, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Strider Harness | handled | Equipped creature gets +1/+1 and has haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sunspear Shikari | handled | As long as this creature is equipped, it has first strike and lifelink. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sylvok Lifestaff | handled | Equipped creature gets +1/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sylvok Replica | handled | {G}, Sacrifice this creature: Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tel-Jilad Defiance | handled | Target creature gains protection from artifacts until end of turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tel-Jilad Fallen | handled | Protection | models/game.py | Y/-/- | not_tested |
| Tempered Steel | handled | Artifact creatures you control get +2/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Throne of Geth | handled | {T}, Sacrifice an artifact: Proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thrummingbird | handled | Whenever this creature deals combat damage to a player, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tower of Calamities | handled | {8}, {T}: This artifact deals 12 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trigon of Corruption | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trigon of Mending | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trigon of Rage | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trigon of Thought | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tumble Magnet | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Untamed Might | handled | Target creature gets +X/+X until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vault Skyward | handled | Target creature gains flying until end of turn. Untap it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vector Asp | handled | {B}: This creature gains infect until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vedalken Certarch | handled | Metalcraft — {T}: Tap target artifact, creature, or land. Activate only if you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vulshok Heartstoker | handled | When this creature enters, target creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vulshok Replica | handled | {1}{R}, Sacrifice this creature: It deals 3 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Tanglecord | handled | {G}: This creature gains reach until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Whitesun's Passage | handled | You gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wing Puncture | handled | Target creature you control deals damage equal to its power to target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Withstand Death | handled | Target creature gains indestructible until end of turn. (Damage and effects that say "destroy" don't destroy it. If its toughness is 0 or less, it still dies.) | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>47 cards</summary>

- Arc Trail
- Argent Sphinx
- Asceticism
- Assault Strobe
- Carrion Call
- Cerebral Eruption
- Contagion Engine
- Darkslick Shores
- Darksteel Myr
- Echo Circlet
- Etched Champion
- Exsanguinate
- Ezuri, Renegade Leader
- Galvanic Blast
- Grindclock
- Hoard-Smelter Dragon
- Indomitable Archangel
- Kemba, Kha Regent
- Koth of the Hammer
- Kuldotha Phoenix
- Leonin Arbiter
- Liquimetal Coating
- Memnite
- Mimic Vat
- Molten Psyche
- Molten-Tail Masticore
- Mox Opal
- Necrotic Ooze
- Nihil Spellbomb
- Platinum Emperion
- Riddlesmith
- Rust Tick
- Rusted Relic
- Semblance Anvil
- Shape Anew
- Soul Parry
- Spikeshot Elder
- Steel Hellkite
- Tainted Strike
- Tangle Angler
- Trigon of Infestation
- True Conviction
- Tunnel Ignus
- Twisted Image
- Venser's Journal
- Volition Reins
- Wurmcoil Engine

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Imprint | 1 | Clone Shell | som |
| as an additional cost to cast ~, sacrifice a creature. destroy target creature. its controller loses life equal to the number of creatures that died ~. | 1 | Flesh Allergy | som |
| choose two target creatures. tap those creatures, then unattach all equipment from them. | 1 | Fulgent Distraction | som |
| counter target spell that targets a permanent you control. | 1 | Turn Aside | som |
| equipped creature gets +N/+N, has intimidate, and is a black zombie. | 1 | Nim Deathmantle | som |
| reveal the top N cards of your library. you may put any number of permanent cards with mana value N or less from among them onto the battlefield. then put all c | 1 | Genesis Wave | som |
| target player discards a card. if a land card is discarded ~, return ~ to its owner's hand. | 1 | Psychic Miasma | som |
| when ~ enters, destroy all tapped creatures. | 1 | Sunblast Angel | som |
| when ~ enters, sacrifice it unless you return an artifact you control to its owner's hand. | 1 | Glint Hawk | som |
| whenever a creature you control dies, you may pay {M}. if you do, you gain N life. | 1 | Vigil for the Lost | som |
| whenever a player casts an instant or sorcery spell that targets only a single golem, that player copies that spell for each other golem that spell could target | 1 | Precursor Golem | som |
| whenever an artifact is put into an opponent's graveyard from the battlefield, you may draw a card. | 1 | Viridian Revel | som |
| whenever an opponent casts a spell, that player loses N life unless they discard a card. | 1 | Painful Quandary | som |
| whenever another artifact you control enters, you may have ~ become a N/N bird artifact creature with flying until end of turn. | 1 | Glint Hawk Idol | som |
| whenever you cast an artifact spell, you may have target creature get +N/+N and gain deathtouch until end of turn. | 1 | Painsmith | som |
| whenever ~ attacks, gain control of target equipment an opponent controls until end of turn. attach it to ~. when you lose control of that equipment, unattach i | 1 | Ogre Geargrabber | som |
| whenever ~ attacks, you may tap N untapped myr you control. if you do, ~ gets +N/+N until end of turn and deals N damage to the player or planeswalker it's atta | 1 | Myr Battlesphere | som |
| whenever ~ becomes unattached from a permanent, sacrifice that permanent. | 1 | Grafted Exoskeleton | som |
| whenever ~ blocks or becomes blocked by a creature, destroy that creature. you gain life equal to that creature's toughness. | 1 | Engulfing Slagwurm | som |
| whenever ~ deals combat damage to a player, you may choose any number of target lands you control and put an awakening counter on each of them. each of those la | 1 | Liege of the Tangle | som |
| you may have ~ enter as a copy of any creature on the battlefield, except it's N/N. | 1 | Quicksilver Gargantuan | som |
| {M}, remove a -N/-N counter from ~: put a -N/-N counter on each other creature. | 1 | Carnifex Demon | som |
| {M}, sacrifice ~: prevent all damage a source of your choice would deal to you ~. | 1 | Auriok Replica | som |
| {M}, {M}: create a token that's a copy of the exiled card. N is the mana value of that card. | 1 | Prototype Portal | som |
| {M}, {M}: untap each other myr you control. | 1 | Myr Galvanizer | som |
| {M}{M}: put target artifact or creature card with mana value N from an opponent's graveyard onto the battlefield tapped under your control. then that player mil | 1 | Geth, Lord of the Vault | som |
| ~ deals N damage to target creature. destroy all equipment attached to that creature. | 1 | Turn to Slag | som |
| −N: creatures can't be blocked ~. | 1 | Venser, the Sojourner | som |
| −N: destroy all other permanents except for lands and tokens. | 1 | Elspeth Tirel | som |

## Notes



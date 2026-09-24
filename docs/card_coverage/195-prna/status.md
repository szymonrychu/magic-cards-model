# Ravnica Allegiance Promos (prna)

- Expansion: 195
- Set code: `prna`
- Release date: 2019-01-25
- Cards in scope (Modern/Pioneer/Standard-legal): 51

## Legality

| Format | Legal cards |
|---|---|
| Modern | 51 |
| Pioneer | 51 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 3 | 5.9% |
| Partial (unaudited) | 3 | 5.9% |
| Not tested (handled, untested) | 16 | 31.4% |
| Not working (silent / notice / error) | 29 | 56.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Amplifire | silent | At the beginning of your upkeep, reveal cards from the top of your library until you reveal a creature card. Until your next turn, this creature's base power be | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Biomancer's Familiar | silent | {T}: The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Electrodominance | silent | Electrodominance deals X damage to any target. You may cast a spell with mana value X or less from your hand without paying its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Emergency Powers | silent | Each player shuffles their hand and graveyard into their library, then draws seven cards. Exile Emergency Powers. Addendum — If you cast this spell during your  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Font of Agonies | silent | Whenever you pay life, put that many blood counters on this enchantment. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Growth-Chamber Guardian | silent | Whenever one or more +1/+1 counters are put on this creature, you may search your library for a card named Growth-Chamber Guardian, reveal it, put it into your  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gruul Spellbreaker | silent | Riot | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Hydroid Krasis | silent | When you cast this spell, you gain half X life and draw half X cards. Round down each time. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kaya's Wrath | silent | Destroy all creatures. You gain life equal to the number of creatures you controlled that were destroyed this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Lumbering Battlement | silent | When this creature enters, exile any number of other nontoken creatures you control until it leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mass Manipulation | silent | Gain control of X target creatures and/or planeswalkers. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Plaza of Harmony | silent | {T}: Add one mana of any type that a Gate you control could produce. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Precognitive Perception | silent | Draw three cards. Addendum — If you cast this spell during your main phase, instead scry 3, then draw three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Priest of Forgotten Gods | silent | {T}, Sacrifice two other creatures: Any number of target players each lose 2 life and sacrifice a creature of their choice. You add {B}{B} and draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rakdos, the Showstopper | silent | When Rakdos enters, flip a coin for each creature that isn't a Demon, Devil, or Imp. Destroy each creature whose coin comes up tails. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rampage of the Clans | silent | Destroy all artifacts and enchantments. For each permanent destroyed this way, its controller creates a 3/3 green Centaur creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ravager Wurm | silent | When this creature enters, choose up to one — • This creature fights target creature you don't control. • Destroy target land with an activated ability that isn | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rix Maadi Reveler | silent | When this creature enters, discard a card, then draw a card. If this creature's spectacle cost was paid, instead discard your hand, then draw three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Seraph of the Scales | silent | Afterlife | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Simic Ascendancy | silent | At the beginning of your upkeep, if this enchantment has twenty or more growth counters on it, you win the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Skarrgan Hellkite | silent | Riot | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Smothering Tithe | silent | Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a Treasure token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Spawn of Mayhem | silent | At the beginning of your upkeep, this creature deals 1 damage to each player. Then if you have 10 or less life, put a +1/+1 counter on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Theater of Horrors | silent | At the beginning of your upkeep, exile the top card of your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tithe Taker | silent | Afterlife | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Deputy of Detention | notice | When this creature enters, exile target nonland permanent an opponent controls and all other nonland permanents that player controls with the same name as that  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Ethereal Absolution | notice | {2}{W}{B}: Exile target card from an opponent's graveyard. If it was a creature card, you create a 1/1 white and black Spirit creature token with flying. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Mirror March | notice | Whenever a nontoken creature you control enters, flip a coin until you lose a flip. For each flip you won, create a token that's a copy of that creature. Those  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Sphinx of Foresight | notice | You may reveal this card from your opening hand. If you do, scry 3 at the beginning of your first upkeep. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Lavinia, Azorius Renegade | unaudited | Each opponent can't cast noncreature spells with mana value greater than the number of lands that player controls. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Nikya of the Old Ways | unaudited | You can't cast noncreature spells. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Teysa Karlov | unaudited | If a creature dying causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Bedeck // Bedazzle | handled | Target creature gets +3/-3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bedevil | handled | Destroy target artifact, creature, or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Benthic Biomancer | handled | {1}{U}: Adapt 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Biogenic Ooze | handled | When this creature enters, create a 2/2 green Ooze creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cindervines | handled | Whenever an opponent casts a noncreature spell, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/Y/- | not_tested |
| End-Raze Forerunners | handled | When this creature enters, other creatures you control get +2/+2 and gain vigilance and trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gate Colossus | handled | This creature can't be blocked by creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Growth Spiral | handled | Draw a card. You may put a land card from your hand onto the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Guardian Project | handled | Whenever a nontoken creature you control enters, if it doesn't have the same name as another creature you control or a creature card in your graveyard, draw a c | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gutterbones | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hero of Precinct One | handled | Whenever you cast a multicolored spell, create a 1/1 white Human creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Incubation Druid | handled | {3}{G}{G}: Adapt 3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Judith, the Scourge Diva | handled | Other creatures you control get +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rakdos Firewheeler | handled | When this creature enters, it deals 2 damage to target opponent and 2 damage to up to one target creature or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Unbreakable Formation | handled | Creatures you control gain indestructible until end of turn. Addendum — If you cast this spell during your main phase, put a +1/+1 counter on each of those crea | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zegana, Utopian Speaker | handled | When Zegana enters, if you control another creature with a +1/+1 counter on it, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Awaken the Erstwhile
- Immolation Shaman
- Light Up the Stage

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, reveal cards from the top of your library until you reveal a creature card. Until your next turn, this creature's base power be | Amplifire, Simic Ascendancy, Spawn of Mayhem, Theater of Horrors | 4 |
| Afterlife | Seraph of the Scales, Tithe Taker | 2 |
| Riot | Gruul Spellbreaker, Skarrgan Hellkite | 2 |
| When this creature enters, exile target nonland permanent an opponent controls and all other nonland permanents that player controls with the same name as that  | Deputy of Detention, Lumbering Battlement | 2 |
| {T}: Add one mana of any type that a Gate you control could produce. | Plaza of Harmony | 1 |
| Destroy all artifacts and enchantments. For each permanent destroyed this way, its controller creates a 3/3 green Centaur creature token. | Rampage of the Clans | 1 |
| Destroy all creatures. You gain life equal to the number of creatures you controlled that were destroyed this way. | Kaya's Wrath | 1 |
| Draw three cards. Addendum — If you cast this spell during your main phase, instead scry 3, then draw three cards. | Precognitive Perception | 1 |
| Each opponent can't cast noncreature spells with mana value greater than the number of lands that player controls. | Lavinia, Azorius Renegade | 1 |
| Each player shuffles their hand and graveyard into their library, then draws seven cards. Exile Emergency Powers. Addendum — If you cast this spell during your  | Emergency Powers | 1 |
| Electrodominance deals X damage to any target. You may cast a spell with mana value X or less from your hand without paying its mana cost. | Electrodominance | 1 |
| {2}{W}{B}: Exile target card from an opponent's graveyard. If it was a creature card, you create a 1/1 white and black Spirit creature token with flying. | Ethereal Absolution | 1 |
| Gain control of X target creatures and/or planeswalkers. | Mass Manipulation | 1 |
| If a creature dying causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time. | Teysa Karlov | 1 |
| {T}, Sacrifice two other creatures: Any number of target players each lose 2 life and sacrifice a creature of their choice. You add {B}{B} and draw a card. | Priest of Forgotten Gods | 1 |
| {T}: The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it. | Biomancer's Familiar | 1 |
| When Rakdos enters, flip a coin for each creature that isn't a Demon, Devil, or Imp. Destroy each creature whose coin comes up tails. | Rakdos, the Showstopper | 1 |
| When this creature enters, choose up to one — • This creature fights target creature you don't control. • Destroy target land with an activated ability that isn | Ravager Wurm | 1 |
| When this creature enters, discard a card, then draw a card. If this creature's spectacle cost was paid, instead discard your hand, then draw three cards. | Rix Maadi Reveler | 1 |
| When you cast this spell, you gain half X life and draw half X cards. Round down each time. | Hydroid Krasis | 1 |
| Whenever a nontoken creature you control enters, flip a coin until you lose a flip. For each flip you won, create a token that's a copy of that creature. Those  | Mirror March | 1 |
| Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a Treasure token. | Smothering Tithe | 1 |
| Whenever one or more +1/+1 counters are put on this creature, you may search your library for a card named Growth-Chamber Guardian, reveal it, put it into your  | Growth-Chamber Guardian | 1 |
| Whenever you pay life, put that many blood counters on this enchantment. | Font of Agonies | 1 |
| You can't cast noncreature spells. | Nikya of the Old Ways | 1 |
| You may reveal this card from your opening hand. If you do, scry 3 at the beginning of your first upkeep. | Sphinx of Foresight | 1 |

## Notes



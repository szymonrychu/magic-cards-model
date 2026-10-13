"""EP-02 R3 T8: damage-pump-cost amounts (the `damage-pump-cost-amounts` shared part).

One facade over five part modules, each registering its own readers into the
dispatch ladders on import (the EP-02 R1/R2 convention):

- `_grants`: a graveyard instant or sorcery gains flashback / harmonize / jump-start.
- `_costs`: "costs {X} less to cast / activate, where X is ..." reductions.
- `_pumps`: "+X/+X / -X/-X until end of turn, where X is ..." and per-resolution pumps.
- `_damage`: "deals damage equal to ..." sentences and their riders.
- `_casts`: free casts / copies from a graveyard, cipher, flip, prototype.
"""

from . import ep02_r3_damage_cost_amounts_casts as casts  # noqa: F401
from . import ep02_r3_damage_cost_amounts_costs as costs  # noqa: F401
from . import ep02_r3_damage_cost_amounts_damage as damage  # noqa: F401
from . import ep02_r3_damage_cost_amounts_grants as grants  # noqa: F401
from . import ep02_r3_damage_cost_amounts_pumps as pumps  # noqa: F401

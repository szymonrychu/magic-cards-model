"""`python -m tests.golden <golden.json>...` - see `tests.golden.main`."""

import sys

from tests.golden import main

sys.exit(main(sys.argv[1:]))

"""Enable ``python -m praxis_dev``."""

from __future__ import annotations

import sys

from praxis_dev.cli import main

if __name__ == "__main__":
    sys.exit(main())

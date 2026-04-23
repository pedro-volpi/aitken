"""Entry point para ``python -m aitken``.

Delega à :func:`aitken.cli.main` para que ``python -m aitken`` e o
console script ``aitken`` (definido em pyproject.toml) tenham o mesmo
comportamento.
"""
from __future__ import annotations

import sys

from aitken.cli import main

if __name__ == "__main__":
    sys.exit(main())

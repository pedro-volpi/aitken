"""Entry point para ``python -m mentat``.

Delega à :func:`mentat.cli.main` para que ``python -m mentat`` e o
console script ``mentat`` (definido em pyproject.toml) tenham o mesmo
comportamento.
"""

import sys

from mentat.cli import main

if __name__ == "__main__":
    sys.exit(main())

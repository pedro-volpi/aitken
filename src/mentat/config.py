"""Configuração padrão (caminhos, constantes).

Separado de ``cli.py`` para que testes e outros entry points possam
importar defaults sem depender do parser de argumentos.

O banco vive em ``<raiz_do_projeto>/data/aitken.db``. Decisão deliberada:
o projeto é mantido em uma pasta sincronizada pelo OneDrive, então colocar
o banco dentro do próprio repo resolve portabilidade entre máquinas sem
precisar de env var, config file ou XDG. ``--db`` na CLI continua
disponível como escape hatch (principalmente para testes, que apontam
para um ``tmp_path``).
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH: Path = _REPO_ROOT / "data" / "aitken.db"
"""Caminho padrão do banco SQLite (relativo à raiz do projeto)."""

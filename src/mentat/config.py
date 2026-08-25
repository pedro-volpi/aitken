"""Configuração padrão (caminhos, constantes).

Separado de ``cli.py`` para que testes e outros entry points possam
importar defaults sem depender do parser de argumentos. Todo default
visível ao usuário mora aqui: mudar um valor abaixo muda o argparse, o
help e o dataclass de params correspondente de uma vez.

Módulo-folha: importa só stdlib, então qualquer camada (inclusive
``core/``) pode importá-lo sem violar o sentido único
``ui → session → storage → core``.

O banco vive em ``<raiz_do_projeto>/data/mentat.db``. Decisão deliberada:
o projeto é mantido em uma pasta sincronizada pelo OneDrive, então colocar
o banco dentro do próprio repo resolve portabilidade entre máquinas sem
precisar de env var, config file ou XDG. ``--db`` na CLI continua
disponível como escape hatch (principalmente para testes, que apontam
para um ``tmp_path``).
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH: Path = _REPO_ROOT / "data" / "mentat.db"
"""Caminho padrão do banco SQLite (relativo à raiz do projeto)."""

DEFAULT_TABLES_MIN_FACTOR: int = 2
"""Menor fator da tabuada de multiplicação (``mentat drill tables --min``)."""

DEFAULT_TABLES_MAX_FACTOR: int = 99
"""Maior fator da tabuada de multiplicação (``mentat drill tables --max``)."""

DEFAULT_SQUARES_MIN_BASE: int = 11
"""Menor base dos quadrados N² (``mentat drill squares --min``)."""

DEFAULT_SQUARES_MAX_BASE: int = 99
"""Maior base dos quadrados N² (``mentat drill squares --max``)."""

DEFAULT_CUBES_MIN_BASE: int = 3
"""Menor base dos cubos N³ (``mentat drill cubes --min``)."""

DEFAULT_CUBES_MAX_BASE: int = 10
"""Maior base dos cubos N³ (``mentat drill cubes --max``)."""

DEFAULT_DRILL_COUNT: int = 30
"""Problemas distintos a dominar por sessão de drill (``--count``/``-n``)."""

DEFAULT_FACTORIAL_COUNT: int = 20
"""``--count`` específico do factorial: o pool fixo de 11 itens não sustenta sessão de 30."""

"""Configuração padrão (caminhos, constantes).

Separado de ``cli.py`` para que testes e outros entry points possam
importar defaults sem depender do parser de argumentos.

O caminho do banco segue a convenção XDG: ``$XDG_DATA_HOME/aitken/`` se
a variável estiver definida, caso contrário ``~/.local/share/aitken/``.
Isto é padrão em sistemas Linux e funciona em macOS sem surpresas. O
usuário pode sempre sobrescrever via ``--db`` na linha de comando.
"""
from __future__ import annotations

import os
from pathlib import Path


def default_data_dir() -> Path:
    """Diretório de dados do usuário conforme XDG Base Directory Spec.

    Returns:
        Path para ``$XDG_DATA_HOME/aitken`` ou ``~/.local/share/aitken``.
        O diretório *não* é criado aqui — ``open_db`` faz isso sob demanda.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "aitken"
    return Path.home() / ".local" / "share" / "aitken"


DEFAULT_DB_PATH: Path = default_data_dir() / "aitken.db"
"""Caminho padrão do banco SQLite do usuário."""

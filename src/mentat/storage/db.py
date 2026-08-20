"""Abertura de conexão SQLite com pragmas seguros e migrações aplicadas.

O resto da aplicação nunca importa ``sqlite3`` diretamente — sempre passa
por ``open_db`` para garantir pragmas consistentes. Se um dia trocarmos o
backend de persistência, apenas ``storage/`` muda.
"""

import sqlite3
from pathlib import Path

from aitken.storage.migrations import migrate


def open_db(path: Path) -> sqlite3.Connection:
    """Abre (ou cria) um banco SQLite no caminho indicado.

    Configura pragmas razoáveis para uso interativo local:

    - ``journal_mode=DELETE``: rollback journal padrão. WAL seria mais
      rápido em cargas concorrentes, mas o repo vive numa pasta
      sincronizada pelo OneDrive — o provider ``CloudStorage`` do macOS
      interfere nos locks de ``*.db-wal``/``*.db-shm`` e provoca
      ``disk I/O error`` em escritas. Single-user CLI não precisa de WAL.
    - ``foreign_keys=ON``: respeita ``FOREIGN KEY`` (necessário porque
      SQLite desabilita por padrão).
    - ``synchronous=NORMAL``: equilíbrio razoável entre durabilidade e
      latência; perdemos a última transação apenas em crash do OS, não do
      processo.

    Aplica todas as migrações pendentes antes de retornar, garantindo que
    o schema está na versão mais recente. O diretório pai do arquivo é
    criado se não existir.

    Args:
        path: caminho do arquivo SQLite (criado se não existir).

    Returns:
        Uma conexão aberta em modo autocommit com ``row_factory`` de
        :class:`sqlite3.Row` para acesso tipo dict às colunas.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit. Simplifica porque só fazemos
    # operações pontuais; transações maiores seriam o caso de usar `with conn:`.
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    migrate(conn)
    return conn

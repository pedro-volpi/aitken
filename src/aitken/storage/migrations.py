"""Schema SQLite versionado e migração idempotente.

Mantemos um ``schema_version`` single-row (na verdade, uma linha por
migração aplicada) para permitir upgrades incrementais sem perder dados.
Cada migração é idempotente: rodar a função ``migrate`` em um banco já
atualizado não faz nada.

Schema atual (v2):
    attempts — histórico de tentativas, fonte de verdade para stats e
               heatmap de fraquezas.
    schedule — estado SM-2 por ``(module_id, problem_key)``: fator de
               facilidade e streak de acertos. Persistido entre sessões.
"""

import sqlite3

_SCHEMA_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

_MIGRATION_V1 = """
CREATE TABLE IF NOT EXISTS attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id       TEXT    NOT NULL,
    problem_key     TEXT    NOT NULL,
    prompt          TEXT    NOT NULL,
    expected_answer TEXT    NOT NULL,
    user_answer     TEXT    NOT NULL,
    correct         INTEGER NOT NULL CHECK (correct IN (0, 1)),
    elapsed_ms      INTEGER NOT NULL CHECK (elapsed_ms >= 0),
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_module_key
    ON attempts(module_id, problem_key);

CREATE INDEX IF NOT EXISTS idx_attempts_created
    ON attempts(created_at);
"""

_MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS schedule (
    module_id            TEXT    NOT NULL,
    problem_key          TEXT    NOT NULL,
    ease_factor          REAL    NOT NULL CHECK (ease_factor >= 1.3),
    consecutive_correct  INTEGER NOT NULL CHECK (consecutive_correct >= 0),
    updated_at           TEXT    NOT NULL,
    PRIMARY KEY (module_id, problem_key)
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Aplica todas as migrações pendentes.

    Idempotente: se o banco já está na última versão, é no-op. A ordem das
    migrações é determinada por ``_MIGRATIONS`` (abaixo), cada entrada uma
    tupla ``(versão, SQL)``.

    Args:
        conn: conexão SQLite aberta. A função não chama ``commit`` nem
            fecha a conexão — o chamador controla o lifecycle.
    """
    conn.executescript(_SCHEMA_BOOTSTRAP)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_version").fetchall()}
    for version, sql in _MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) "
            "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (version,),
        )


_MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_V1),
    (2, _MIGRATION_V2),
]

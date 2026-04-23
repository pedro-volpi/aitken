"""Repositórios de persistência sobre :mod:`sqlite3`.

Cada repositório encapsula acesso a uma tabela do schema; é *stateless*
além da conexão injetada. O padrão de injeção de conexão (em vez de
instância global) torna os testes triviais: ``tmp_path``-based.

Nesta iteração existe apenas :class:`AttemptRepo` — quando o scheduler
SM-2 e a progressão por nível forem implementados, eles ganharão repos
próprios (``ScheduleRepo``, ``LevelRepo``) seguindo o mesmo padrão.
"""

import sqlite3
from datetime import UTC, datetime

from aitken.core.problem import Attempt


class AttemptRepo:
    """Persistência de :class:`Attempt` na tabela ``attempts``.

    A conexão é de propriedade do chamador (quem abre, fecha). O repositório
    apenas emite comandos SQL sobre ela.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, attempt: Attempt) -> int:
        """Insere uma tentativa e devolve o ``id`` gerado.

        O timestamp ``created_at`` é atribuído aqui, em UTC com precisão de
        milissegundos — a sessão não precisa se preocupar com relógio.

        Returns:
            O ``rowid`` da linha inserida (>= 1).
        """
        now_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
        cursor = self._conn.execute(
            """
            INSERT INTO attempts(
                module_id, problem_key, prompt, expected_answer,
                user_answer, correct, elapsed_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.problem.module_id,
                attempt.problem.key,
                attempt.problem.prompt,
                attempt.problem.expected_answer,
                attempt.user_answer,
                1 if attempt.correct else 0,
                attempt.elapsed_ms,
                now_iso,
            ),
        )
        return int(cursor.lastrowid or 0)

    def count(self, module_id: str | None = None) -> int:
        """Conta tentativas registradas.

        Args:
            module_id: se informado, restringe a contagem ao módulo dado
                (ex.: ``"tables"``). Se ``None``, conta todas.
        """
        if module_id is None:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM attempts WHERE module_id = ?",
                (module_id,),
            ).fetchone()
        return int(row["n"])

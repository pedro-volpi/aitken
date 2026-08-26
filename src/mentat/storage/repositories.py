"""Repositórios de persistência sobre :mod:`sqlite3`.

Cada repositório encapsula acesso a uma tabela do schema; é *stateless*
além da conexão injetada. O padrão de injeção de conexão (em vez de
instância global) torna os testes triviais: ``tmp_path``-based.

Dois repositórios hoje:

- :class:`AttemptRepo` grava o log imutável de tentativas (tabela
  ``attempts``); é a fonte de verdade para estatísticas.
- :class:`ScheduleRepo` persiste o estado SM-2 corrente por chave (tabela
  ``schedule``); é mutável — um *upsert* por revisão.
"""

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from mentat.core.problem import Attempt
from mentat.core.scheduler import Card

_IN_CHUNK = 500
"""Chaves por consulta ``IN`` em :meth:`ScheduleRepo.load_for`.

Abaixo do limite histórico de 999 variáveis do SQLite
(``SQLITE_MAX_VARIABLE_NUMBER`` pré-3.32) — universos grandes (tabuada
até 99 tem ~5k chaves) são divididos em lotes em vez de estourar a query.
"""


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


class ScheduleRepo:
    """Persistência do estado SM-2 (tabela ``schedule``).

    Cada linha é um upsert: a chave primária é ``(module_id, problem_key)``
    e o ``Card`` atual sobrescreve o anterior. Ao abrir uma sessão, o
    chamador chama :meth:`load_for` com o universo do gerador para
    recuperar os ``Card`` correspondentes e passa o dicionário ao
    scheduler na memória.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def load_for(self, keys: Iterable[str]) -> dict[str, Card]:
        """Carrega os ``Card`` persistidos para exatamente as chaves dadas.

        É a pergunta que uma sessão realmente faz: "o estado SM-2 do
        universo *deste gerador*" — sem assumir que o universo cabe em um
        único ``module_id`` (um gerador composto atravessa vários). A
        consulta filtra por ``problem_key`` apenas: as chaves são
        globalmente únicas (invariante de
        :class:`~mentat.core.problem.Problem`), então o ``module_id`` não é
        necessário para desambiguar — ele permanece na tabela como
        partição explícita para proveniência e análise.

        Chaves sem linha persistida simplesmente não aparecem no resultado
        (o scheduler as trata como inéditas, peso máximo).
        """
        cards: dict[str, Card] = {}
        key_list = list(keys)
        for start in range(0, len(key_list), _IN_CHUNK):
            chunk = key_list[start : start + _IN_CHUNK]
            placeholders = ", ".join("?" * len(chunk))
            rows = self._conn.execute(
                f"""
                SELECT problem_key, ease_factor, consecutive_correct
                FROM schedule
                WHERE problem_key IN ({placeholders})
                """,  # f-string só injeta os "?"; os valores vão parametrizados
                chunk,
            ).fetchall()
            for row in rows:
                cards[row["problem_key"]] = Card(
                    ease_factor=float(row["ease_factor"]),
                    consecutive_correct=int(row["consecutive_correct"]),
                )
        return cards

    def load(self, module_id: str) -> dict[str, Card]:
        """Carrega todos os ``Card`` persistidos para o módulo dado.

        Visão por partição, útil para inspeção e ferramentas de análise;
        o caminho da sessão usa :meth:`load_for`, que não pressupõe módulo.
        """
        rows = self._conn.execute(
            """
            SELECT problem_key, ease_factor, consecutive_correct
            FROM schedule
            WHERE module_id = ?
            """,
            (module_id,),
        ).fetchall()
        return {
            row["problem_key"]: Card(
                ease_factor=float(row["ease_factor"]),
                consecutive_correct=int(row["consecutive_correct"]),
            )
            for row in rows
        }

    def upsert(self, module_id: str, problem_key: str, card: Card) -> None:
        """Grava (ou sobrescreve) o ``Card`` para a chave dada."""
        now_iso = datetime.now(UTC).isoformat(timespec="milliseconds")
        self._conn.execute(
            """
            INSERT INTO schedule(module_id, problem_key, ease_factor,
                                 consecutive_correct, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(module_id, problem_key) DO UPDATE SET
                ease_factor         = excluded.ease_factor,
                consecutive_correct = excluded.consecutive_correct,
                updated_at          = excluded.updated_at
            """,
            (
                module_id,
                problem_key,
                card.ease_factor,
                card.consecutive_correct,
                now_iso,
            ),
        )

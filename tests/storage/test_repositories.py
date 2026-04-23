"""Testes de :class:`AttemptRepo`, :class:`ScheduleRepo` e do pipeline de migração."""

from pathlib import Path

import pytest

from aitken.core.problem import Attempt, Problem
from aitken.core.scheduler import Card
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo, ScheduleRepo


@pytest.fixture
def repo(tmp_path: Path) -> AttemptRepo:
    """Repositório sobre um banco temporário por teste."""
    conn = open_db(tmp_path / "test.db")
    return AttemptRepo(conn)


def _problem(key: str = "tables:7x8", module: str = "tables") -> Problem:
    return Problem(
        module_id=module,
        key=key,
        prompt="7 × 8",
        expected_answer="56",
    )


def test_count_empty(repo: AttemptRepo) -> None:
    assert repo.count() == 0
    assert repo.count(module_id="tables") == 0


def test_record_returns_row_id(repo: AttemptRepo) -> None:
    a = Attempt(problem=_problem(), user_answer="56", elapsed_ms=1200, correct=True)
    row_id = repo.record(a)
    assert row_id > 0


def test_record_increments_count(repo: AttemptRepo) -> None:
    a = Attempt(problem=_problem(), user_answer="56", elapsed_ms=1200, correct=True)
    repo.record(a)
    repo.record(a)
    assert repo.count() == 2


def test_count_filters_by_module(repo: AttemptRepo) -> None:
    repo.record(
        Attempt(
            problem=_problem(module="tables"),
            user_answer="56",
            elapsed_ms=800,
            correct=True,
        )
    )
    repo.record(
        Attempt(
            problem=Problem("squares", "squares:7", "7²", "49"),
            user_answer="49",
            elapsed_ms=2000,
            correct=True,
        )
    )
    assert repo.count() == 2
    assert repo.count(module_id="tables") == 1
    assert repo.count(module_id="squares") == 1
    assert repo.count(module_id="missing") == 0


def test_record_persists_wrong_answer(repo: AttemptRepo) -> None:
    a = Attempt(
        problem=_problem(),
        user_answer="55",
        elapsed_ms=3400,
        correct=False,
    )
    repo.record(a)
    assert repo.count() == 1


def test_migrations_idempotent(tmp_path: Path) -> None:
    """Reabrir um banco existente não deve levantar nem duplicar schema."""
    db_path = tmp_path / "test.db"
    conn1 = open_db(db_path)
    conn1.close()
    conn2 = open_db(db_path)
    row = conn2.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    assert row["v"] == 2
    conn2.close()


def test_stored_columns_preserve_values(repo: AttemptRepo) -> None:
    """Round-trip básico: os valores gravados batem com os lidos."""
    a = Attempt(
        problem=_problem(),
        user_answer="56",
        elapsed_ms=1234,
        correct=True,
    )
    row_id = repo.record(a)
    row = repo._conn.execute(  # noqa: SLF001 — inspeção interna de teste
        "SELECT * FROM attempts WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["module_id"] == "tables"
    assert row["problem_key"] == "tables:7x8"
    assert row["prompt"] == "7 × 8"
    assert row["expected_answer"] == "56"
    assert row["user_answer"] == "56"
    assert row["correct"] == 1
    assert row["elapsed_ms"] == 1234
    assert row["created_at"]  # timestamp não-vazio


@pytest.fixture
def schedule(tmp_path: Path) -> ScheduleRepo:
    conn = open_db(tmp_path / "sched.db")
    return ScheduleRepo(conn)


def test_schedule_load_empty(schedule: ScheduleRepo) -> None:
    assert schedule.load("tables") == {}


def test_schedule_upsert_roundtrip(schedule: ScheduleRepo) -> None:
    schedule.upsert("tables", "tables:7x8", Card(ease_factor=2.3, consecutive_correct=2))
    loaded = schedule.load("tables")
    assert loaded["tables:7x8"].ease_factor == pytest.approx(2.3)
    assert loaded["tables:7x8"].consecutive_correct == 2


def test_schedule_upsert_overwrites(schedule: ScheduleRepo) -> None:
    schedule.upsert("tables", "tables:7x8", Card(ease_factor=2.5, consecutive_correct=1))
    schedule.upsert("tables", "tables:7x8", Card(ease_factor=2.1, consecutive_correct=0))
    loaded = schedule.load("tables")
    assert loaded["tables:7x8"].ease_factor == pytest.approx(2.1)
    assert loaded["tables:7x8"].consecutive_correct == 0


def test_schedule_isolates_modules(schedule: ScheduleRepo) -> None:
    schedule.upsert("tables", "tables:7x8", Card())
    schedule.upsert("squares", "squares:12", Card(ease_factor=1.7))
    assert "tables:7x8" in schedule.load("tables")
    assert "tables:7x8" not in schedule.load("squares")
    assert "squares:12" in schedule.load("squares")

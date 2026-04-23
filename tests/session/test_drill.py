"""Testes de :class:`DrillSession` — orquestração e persistência."""
from __future__ import annotations

from pathlib import Path
from random import Random

import pytest

from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo


def _session(
    *,
    repo: AttemptRepo | None = None,
    count: int = 5,
    seed: int = 0,
) -> DrillSession:
    return DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=repo,
        max_problems=count,
        rng=Random(seed),
    )


def test_iterates_exactly_max_problems() -> None:
    session = _session(count=7)
    problems = list(session)
    assert len(problems) == 7


def test_total_problems_property() -> None:
    assert _session(count=12).total_problems == 12


def test_record_appends_attempt() -> None:
    session = _session()
    problem = next(iter(session))
    attempt = session.record(problem, problem.expected_answer, elapsed_ms=500)
    assert attempt.correct
    assert attempt.user_answer == problem.expected_answer
    assert attempt.elapsed_ms == 500
    assert len(session.attempts) == 1


def test_record_captures_wrong_answer() -> None:
    session = _session()
    problem = next(iter(session))
    attempt = session.record(problem, "wrong", elapsed_ms=500)
    assert not attempt.correct
    assert attempt.user_answer == "wrong"


def test_attempts_returns_defensive_copy() -> None:
    session = _session()
    problem = next(iter(session))
    session.record(problem, problem.expected_answer, elapsed_ms=500)
    copy = session.attempts
    copy.clear()
    # A lista interna não deve ter sido afetada.
    assert len(session.attempts) == 1


def test_record_persists_to_repo(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "t.db")
    try:
        repo = AttemptRepo(conn)
        session = _session(repo=repo, count=3)
        for problem in session:
            session.record(problem, problem.expected_answer, elapsed_ms=500)
        assert repo.count() == 3
        assert repo.count(module_id="tables") == 3
    finally:
        conn.close()


def test_record_skips_persist_when_repo_none() -> None:
    session = _session(repo=None, count=3)
    for problem in session:
        session.record(problem, problem.expected_answer, elapsed_ms=500)
    # Sem exceção e sessão tem as 3 tentativas em memória.
    assert len(session.attempts) == 3


def test_record_rejects_negative_elapsed() -> None:
    session = _session()
    problem = next(iter(session))
    with pytest.raises(ValueError):
        session.record(problem, "0", elapsed_ms=-1)


def test_invalid_max_problems() -> None:
    with pytest.raises(ValueError):
        DrillSession(
            generator=TablesGenerator(TablesParams()),
            repo=None,
            max_problems=0,
            rng=Random(),
        )
    with pytest.raises(ValueError):
        DrillSession(
            generator=TablesGenerator(TablesParams()),
            repo=None,
            max_problems=-3,
            rng=Random(),
        )


def test_summary_reflects_attempts() -> None:
    session = _session(count=4)
    elapsed_values = [400, 600, 800, 1000]
    for i, problem in enumerate(session):
        ans = problem.expected_answer if i != 2 else "wrong"
        session.record(problem, ans, elapsed_ms=elapsed_values[i])

    s = session.summary()
    assert s.total == 4
    assert s.correct == 3
    assert s.wrong == 1
    # Latências [400, 600, 800, 1000] → mediana = 700.
    assert s.median_ms == 700.0
    assert s.slowest is not None
    assert s.slowest[1] == 1000


def test_breaking_early_preserves_recorded_attempts() -> None:
    session = _session(count=10)
    for i, problem in enumerate(session):
        session.record(problem, problem.expected_answer, elapsed_ms=500)
        if i == 2:
            break
    # Registradas 3 tentativas (i=0, 1, 2).
    assert len(session.attempts) == 3
    assert session.summary().total == 3


def test_end_to_end_with_storage(tmp_path: Path) -> None:
    """Run completo: cria banco, roda sessão pequena, verifica stats e contagem."""
    conn = open_db(tmp_path / "e2e.db")
    try:
        repo = AttemptRepo(conn)
        session = DrillSession(
            generator=TablesGenerator(TablesParams()),
            repo=repo,
            max_problems=5,
            rng=Random(1),
        )
        for problem in session:
            session.record(problem, problem.expected_answer, elapsed_ms=500)
        summary = session.summary()
        assert summary.total == 5
        assert summary.correct == 5
        assert summary.accuracy == 1.0
        assert repo.count() == 5
    finally:
        conn.close()

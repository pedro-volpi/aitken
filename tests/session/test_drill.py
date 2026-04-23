"""Testes de :class:`DrillSession` — orquestração, retry e SM-2."""

from pathlib import Path
from random import Random

import pytest

from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo, ScheduleRepo


def _session(
    *,
    attempt_repo: AttemptRepo | None = None,
    schedule_repo: ScheduleRepo | None = None,
    count: int = 5,
    seed: int = 0,
) -> DrillSession:
    return DrillSession(
        generator=TablesGenerator(TablesParams()),
        attempt_repo=attempt_repo,
        schedule_repo=schedule_repo,
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
        session = _session(attempt_repo=repo, count=3)
        for problem in session:
            session.record(problem, problem.expected_answer, elapsed_ms=500)
        assert repo.count() == 3
        assert repo.count(module_id="tables") == 3
    finally:
        conn.close()


def test_record_skips_persist_when_repo_none() -> None:
    session = _session(attempt_repo=None, count=3)
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
            attempt_repo=None,
            schedule_repo=None,
            max_problems=0,
            rng=Random(),
        )
    with pytest.raises(ValueError):
        DrillSession(
            generator=TablesGenerator(TablesParams()),
            attempt_repo=None,
            schedule_repo=None,
            max_problems=-3,
            rng=Random(),
        )


def test_summary_reflects_attempts() -> None:
    # Todas as respostas corretas na primeira tentativa: total == distintos.
    session = _session(count=4)
    elapsed_values = [400, 600, 800, 1000]
    for i, problem in enumerate(session):
        session.record(problem, problem.expected_answer, elapsed_ms=elapsed_values[i])

    s = session.summary()
    assert s.total == 4
    assert s.correct == 4
    assert s.wrong == 0
    # Latências [400, 600, 800, 1000] → mediana = 700.
    assert s.median_ms == 700.0
    assert s.slowest is not None
    assert s.slowest[1] == 1000


def test_wrong_answer_retries_same_problem() -> None:
    """Uma resposta errada faz o iterador reemitir o mesmo problema."""
    session = _session(count=3)
    iterator = iter(session)
    first = next(iterator)
    session.record(first, "wrong-answer", elapsed_ms=500)
    retry = next(iterator)
    assert retry == first, "sessão deveria reemitir o mesmo problema após erro"


def test_retry_does_not_advance_position() -> None:
    """`current_position` conta problemas distintos, não tentativas."""
    session = _session(count=3)
    iterator = iter(session)
    first = next(iterator)
    assert session.current_position == 1
    session.record(first, "wrong-answer", elapsed_ms=500)
    retry = next(iterator)
    assert session.current_position == 1, "posição não deve mudar no retry"
    session.record(retry, retry.expected_answer, elapsed_ms=500)
    second = next(iterator)
    assert second != first
    assert session.current_position == 2


def test_session_only_finishes_when_all_correct() -> None:
    """Sessão continua até cada um dos N distintos ser acertado ao menos uma vez."""
    session = _session(count=2)
    attempts_count = 0
    wrong_done = False
    for problem in session:
        # Erra o primeiro distinto uma vez, depois acerta tudo.
        if not wrong_done and session.current_position == 1:
            session.record(problem, "wrong", elapsed_ms=500)
            wrong_done = True
        else:
            session.record(problem, problem.expected_answer, elapsed_ms=500)
        attempts_count += 1

    assert attempts_count == 3  # 1 erro + 1 retry correto + 1 correto
    s = session.summary()
    assert s.total == 3
    assert s.correct == 2
    assert s.wrong == 1


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
        attempt_repo = AttemptRepo(conn)
        schedule_repo = ScheduleRepo(conn)
        session = DrillSession(
            generator=TablesGenerator(TablesParams()),
            attempt_repo=attempt_repo,
            schedule_repo=schedule_repo,
            max_problems=5,
            rng=Random(1),
        )
        for problem in session:
            session.record(problem, problem.expected_answer, elapsed_ms=500)
        summary = session.summary()
        assert summary.total == 5
        assert summary.correct == 5
        assert summary.accuracy == 1.0
        assert attempt_repo.count() == 5
        # Cada chave correta deve ter Card persistido.
        loaded = schedule_repo.load("tables")
        assert len(loaded) >= 1
    finally:
        conn.close()


def test_sm2_updates_card_on_correct() -> None:
    """Resposta correta rápida atualiza Card: streak sobe, EF sobe ou mantém."""
    session = _session(count=1)
    problem = next(iter(session))
    session.record(problem, problem.expected_answer, elapsed_ms=500)  # quality 5
    card = session.card_for(problem.key)
    assert card is not None
    assert card.consecutive_correct == 1
    assert card.ease_factor >= 2.5


def test_sm2_penalizes_after_error_in_cycle() -> None:
    """Erro no ciclo cobra quality <= 2 ao acerto final → zera streak, EF cai."""
    session = _session(count=1)
    problem = next(iter(session))
    session.record(problem, "wrong", elapsed_ms=500)  # erro, ciclo ainda aberto
    retry = next(iter(session))
    assert retry == problem
    session.record(retry, retry.expected_answer, elapsed_ms=500)  # fecha o ciclo
    card = session.card_for(problem.key)
    assert card is not None
    # quality foi truncada em 2 → path de recall failure → streak = 0
    assert card.consecutive_correct == 0
    assert card.ease_factor < 2.5  # caiu ao menos 0.2


def test_schedule_repo_persists_across_sessions(tmp_path: Path) -> None:
    """Card gravado em uma sessão reaparece em outra sobre o mesmo banco."""
    conn = open_db(tmp_path / "persist.db")
    try:
        sched = ScheduleRepo(conn)
        s1 = DrillSession(
            generator=TablesGenerator(TablesParams()),
            attempt_repo=None,
            schedule_repo=sched,
            max_problems=1,
            rng=Random(0),
        )
        p = next(iter(s1))
        s1.record(p, p.expected_answer, elapsed_ms=500)
        assert sched.load("tables")[p.key].consecutive_correct == 1

        # Sessão nova sobre o mesmo banco carrega o Card anterior.
        s2 = DrillSession(
            generator=TablesGenerator(TablesParams()),
            attempt_repo=None,
            schedule_repo=sched,
            max_problems=1,
            rng=Random(0),
        )
        assert s2.card_for(p.key) is not None
        assert s2.card_for(p.key).consecutive_correct == 1  # type: ignore[union-attr]
    finally:
        conn.close()

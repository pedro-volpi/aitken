"""Testes de :func:`aitken.core.stats.summarize`."""

from aitken.core.problem import Attempt, Problem
from aitken.core.stats import summarize


def _attempt(prompt: str, elapsed_ms: int, correct: bool) -> Attempt:
    """Helper: monta uma tentativa mínima para os testes."""
    problem = Problem(
        module_id="tables",
        key=f"tables:{prompt}",
        prompt=prompt,
        expected_answer="0",
    )
    return Attempt(
        problem=problem,
        user_answer="0" if correct else "1",
        elapsed_ms=elapsed_ms,
        correct=correct,
    )


def test_empty() -> None:
    s = summarize([])
    assert s.total == 0
    assert s.correct == 0
    assert s.accuracy == 0.0
    assert s.median_ms == 0.0
    assert s.p90_ms is None
    assert s.slowest is None
    assert s.wrong == 0


def test_single_attempt() -> None:
    s = summarize([_attempt("2 × 2", 1500, True)])
    assert s.total == 1
    assert s.correct == 1
    assert s.wrong == 0
    assert s.accuracy == 1.0
    assert s.median_ms == 1500.0
    assert s.p90_ms is None  # <10 amostras
    assert s.slowest == ("2 × 2", 1500)


def test_accuracy_mixed() -> None:
    attempts = [
        _attempt("2 × 2", 1000, True),
        _attempt("3 × 3", 1000, False),
        _attempt("4 × 4", 1000, True),
        _attempt("5 × 5", 1000, True),
    ]
    s = summarize(attempts)
    assert s.correct == 3
    assert s.total == 4
    assert s.wrong == 1
    assert s.accuracy == 0.75


def test_median_odd_count() -> None:
    attempts = [_attempt(f"{i}x{i}", i * 100, True) for i in range(1, 6)]
    # latências: 100, 200, 300, 400, 500 → mediana = 300
    assert summarize(attempts).median_ms == 300.0


def test_median_even_count() -> None:
    attempts = [_attempt(f"{i}x{i}", i * 100, True) for i in range(1, 5)]
    # latências: 100, 200, 300, 400 → mediana = 250
    assert summarize(attempts).median_ms == 250.0


def test_p90_requires_ten_samples() -> None:
    # 9 amostras → sem p90.
    assert summarize([_attempt(f"{i}", 100, True) for i in range(9)]).p90_ms is None

    # 10 amostras → p90 definido e > mediana.
    attempts = [_attempt(f"{i}", i * 100, True) for i in range(1, 11)]
    s = summarize(attempts)
    assert s.p90_ms is not None
    assert s.p90_ms > s.median_ms


def test_slowest_identifies_max() -> None:
    attempts = [
        _attempt("a", 100, True),
        _attempt("b", 5000, False),
        _attempt("c", 300, True),
    ]
    s = summarize(attempts)
    assert s.slowest == ("b", 5000)


def test_all_wrong() -> None:
    attempts = [_attempt("a", 500, False), _attempt("b", 700, False)]
    s = summarize(attempts)
    assert s.correct == 0
    assert s.accuracy == 0.0
    assert s.wrong == 2


def test_all_same_latency() -> None:
    attempts = [_attempt(f"{i}", 1000, True) for i in range(15)]
    s = summarize(attempts)
    assert s.median_ms == 1000.0
    # Com variância zero, p90 também é o mesmo valor.
    assert s.p90_ms == 1000.0

"""Testes da CLI: parser e integração ``main()`` ↔ filesystem."""

import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from aitken.cli import build_parser, main

_PROMPT_RE = re.compile(r"(\d+)\s*×\s*(\d+)")


def test_parser_requires_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_requires_module() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["drill"])


def test_parser_tables_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["drill", "tables"])
    assert args.module == "tables"
    assert args.min_factor == 2
    assert args.max_factor == 9
    assert args.count == 30
    assert args.include_trivial is False
    assert args.no_commutative is False
    assert args.no_persist is False


def test_parser_tables_overrides() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "drill",
            "tables",
            "--min",
            "3",
            "--max",
            "12",
            "-n",
            "15",
            "--include-trivial",
            "--no-commutative",
            "--seed",
            "42",
            "--no-persist",
        ]
    )
    assert args.min_factor == 3
    assert args.max_factor == 12
    assert args.count == 15
    assert args.include_trivial is True
    assert args.no_commutative is True
    assert args.seed == 42
    assert args.no_persist is True


def test_main_runs_drill_tables(tmp_path: Path) -> None:
    """Smoke test: a CLI completa com respostas auto-corretas termina em rc=0 e grava."""
    db_path = tmp_path / "cli.db"

    def fake_input(prompt: str = "") -> str:
        match = _PROMPT_RE.search(prompt)
        assert match is not None
        return str(int(match.group(1)) * int(match.group(2)))

    argv = [
        "drill",
        "tables",
        "--count",
        "3",
        "--seed",
        "42",
        "--db",
        str(db_path),
    ]

    with patch("builtins.input", fake_input):
        rc = main(argv)

    assert rc == 0
    # Banco foi criado e gravou as 3 tentativas + pelo menos 1 Card SM-2.
    conn = sqlite3.connect(str(db_path))
    try:
        attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()
        schedule = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()
        assert attempts[0] == 3
        assert schedule[0] >= 1
    finally:
        conn.close()


def test_parser_squares_defaults() -> None:
    args = build_parser().parse_args(["drill", "squares"])
    assert args.module == "squares"
    assert args.min_base == 2
    assert args.max_base == 25
    assert args.count == 30
    assert args.include_trivial is False


def test_parser_cubes_defaults() -> None:
    args = build_parser().parse_args(["drill", "cubes"])
    assert args.module == "cubes"
    assert args.min_base == 2
    assert args.max_base == 10


def test_parser_factorial_has_no_range_flags() -> None:
    args = build_parser().parse_args(["drill", "factorial"])
    assert args.module == "factorial"
    assert not hasattr(args, "min_base")
    assert not hasattr(args, "max_base")
    # default --count para factorial é 20 (pool de 11 itens)
    assert args.count == 20


def test_main_runs_drill_squares(tmp_path: Path) -> None:
    """Smoke test do squares com auto-correct e persistência SM-2."""
    db_path = tmp_path / "sq.db"

    def fake_input(prompt: str = "") -> str:
        m = re.search(r"(\d+)²", prompt)
        assert m is not None
        n = int(m.group(1))
        return str(n * n)

    argv = ["drill", "squares", "--count", "3", "--seed", "7", "--db", str(db_path)]
    with patch("builtins.input", fake_input):
        rc = main(argv)
    assert rc == 0
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 3
        module_rows = conn.execute("SELECT module_id FROM schedule").fetchall()
        assert all(r[0] == "squares" for r in module_rows)
    finally:
        conn.close()


def test_main_runs_drill_factorial(tmp_path: Path) -> None:
    db_path = tmp_path / "fac.db"
    from math import factorial as _fac

    def fake_input(prompt: str = "") -> str:
        m = re.search(r"(\d+)!", prompt)
        assert m is not None
        return str(_fac(int(m.group(1))))

    argv = ["drill", "factorial", "--count", "3", "--seed", "0", "--db", str(db_path)]
    with patch("builtins.input", fake_input):
        rc = main(argv)
    assert rc == 0


def test_main_reports_validation_error(capsys: pytest.CaptureFixture[str]) -> None:
    """``--min 5 --max 3`` deve falhar com exit code 1 e mensagem em stderr."""
    rc = main(
        [
            "drill",
            "tables",
            "--min",
            "5",
            "--max",
            "3",
            "--count",
            "1",
            "--no-persist",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "erro" in captured.err.lower()

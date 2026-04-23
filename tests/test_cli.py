"""Testes da CLI: parser e integração ``main()`` ↔ filesystem."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from random import Random
from typing import Any
from unittest.mock import patch

import pytest

from aitken.cli import build_parser, main
from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession


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
    args = parser.parse_args([
        "drill", "tables",
        "--min", "3", "--max", "12",
        "-n", "15",
        "--include-trivial",
        "--no-commutative",
        "--seed", "42",
        "--no-persist",
    ])
    assert args.min_factor == 3
    assert args.max_factor == 12
    assert args.count == 15
    assert args.include_trivial is True
    assert args.no_commutative is True
    assert args.seed == 42
    assert args.no_persist is True


def test_main_runs_drill_tables(tmp_path: Path) -> None:
    """Smoke test: a CLI completa com respostas piped termina com rc=0 e grava."""
    db_path = tmp_path / "cli.db"

    # Com seed fixo, reproduzimos a mesma sequência que a CLI vai gerar.
    preview = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=3,
        rng=Random(42),
    )
    answers_iter = iter([p.expected_answer for p in preview])

    def fake_input(prompt: str = "") -> str:
        return next(answers_iter)

    argv = [
        "drill", "tables",
        "--count", "3",
        "--seed", "42",
        "--db", str(db_path),
    ]

    with patch("builtins.input", fake_input):
        rc = main(argv)

    assert rc == 0
    # Banco foi criado e gravou as 3 tentativas.
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()
        assert row[0] == 3
    finally:
        conn.close()


def test_main_reports_validation_error(capsys: Any, tmp_path: Path) -> None:
    """``--min 5 --max 3`` deve falhar com exit code 1 e mensagem em stderr."""
    rc = main([
        "drill", "tables",
        "--min", "5", "--max", "3",
        "--count", "1",
        "--no-persist",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "erro" in captured.err.lower()

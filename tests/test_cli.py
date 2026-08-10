"""Testes da CLI: parser e integração ``main()`` ↔ filesystem."""

import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from aitken.cli import build_parser, main
from aitken.ui.layout import Layout

_PROMPT_RE = re.compile(r"(\d+)\s*×\s*(\d+)")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _bare(line: str) -> str:
    """Linha sem estilo nem alinhamento.

    ``main()`` escreve em ``sys.stdout``, que o pytest normalmente
    substitui por um buffer não-tty (contador cru, na coluna 0) mas que
    sob ``-s`` é o terminal de verdade (contador apagado, à direita).
    Estes testes olham a *estrutura* do prompt, então normalizam os dois
    casos em vez de depender do modo de captura.
    """
    return _ANSI_RE.sub("", line).strip()


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
    assert args.layout is Layout.VERTICAL


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
            "--no-persist",
        ]
    )
    assert args.min_factor == 3
    assert args.max_factor == 12
    assert args.count == 15
    assert args.include_trivial is True
    assert args.no_commutative is True
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
    assert args.min_base == 11
    assert args.max_base == 25
    assert args.count == 30
    assert args.include_trivial is False


def test_parser_cubes_defaults() -> None:
    args = build_parser().parse_args(["drill", "cubes"])
    assert args.module == "cubes"
    assert args.min_base == 3
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

    argv = ["drill", "squares", "--count", "3", "--db", str(db_path)]
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

    argv = ["drill", "factorial", "--count", "3", "--db", str(db_path)]
    with patch("builtins.input", fake_input):
        rc = main(argv)
    assert rc == 0


def test_parser_layout_defaults_to_vertical_in_every_module() -> None:
    """``--layout`` é flag comum: default vertical nos quatro módulos."""
    parser = build_parser()
    for module in ("tables", "squares", "cubes", "factorial"):
        args = parser.parse_args(["drill", module])
        assert args.layout is Layout.VERTICAL, module


def test_parser_layout_override() -> None:
    parser = build_parser()
    for module in ("tables", "squares", "cubes", "factorial"):
        args = parser.parse_args(["drill", module, "--layout", "horizontal"])
        assert args.layout is Layout.HORIZONTAL, module


def test_parser_rejects_unknown_layout() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["drill", "tables", "--layout", "diagonal"])
    assert exc.value.code == 2


def test_main_honors_layout_flag(tmp_path: Path) -> None:
    """A flag chega até a UI: com --layout horizontal a conta é uma linha só.

    O contador tem linha própria nos dois layouts (é cromo periférico, não
    parte da conta), então o que distingue os modos é o desenho abaixo dele.
    """
    seen: list[str] = []

    def fake_input(prompt: str = "") -> str:
        seen.append(prompt)
        match = _PROMPT_RE.search(prompt)
        assert match is not None
        return str(int(match.group(1)) * int(match.group(2)))

    argv = ["drill", "tables", "--count", "2", "--db", str(tmp_path / "layout.db")]
    with patch("builtins.input", fake_input):
        assert main([*argv, "--layout", "horizontal"]) == 0
    for prompt in seen:
        blank, header, operation = prompt.split("\n")
        assert blank == ""
        assert _bare(header).startswith("[")
        assert _PROMPT_RE.match(operation) is not None
        assert operation.endswith(" = ")

    seen.clear()
    with patch("builtins.input", fake_input):
        assert main(argv) == 0
    for prompt in seen:
        blank, header, left, right, equals = prompt.split("\n")
        assert blank == ""
        assert _bare(header).startswith("[")
        assert len(left) == len(right)
        assert right.startswith("× ")
        assert equals == "= "


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

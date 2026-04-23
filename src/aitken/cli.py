"""CLI baseada em :mod:`argparse` — composição de storage + session + UI.

A CLI é a única camada autorizada a criar instâncias concretas e ligá-las
umas às outras. Todas as outras camadas conversam via interfaces
(``Generator``, ``AttemptRepo``, ``DrillSession``). Adicionar um novo
módulo de drill (quadrados, soma, divisão, etc.) é só adicionar um
subparser e um ``cmd_*`` correspondente — o restante é reutilizado.

Convenção: cada módulo de drill vira um subcomando de ``drill``. Ex.:

    aitken drill tables --min 2 --max 9 --count 30
    aitken drill squares --max 25 --count 20     # futuro

Parser é devolvido pela :func:`build_parser` separadamente do
:func:`main` para permitir testes (``build_parser().parse_args([...])``).
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from random import Random

from aitken.config import DEFAULT_DB_PATH
from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo
from aitken.ui import plain


def build_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser raiz já com todos os subcomandos."""
    parser = argparse.ArgumentParser(
        prog="aitken",
        description="Treinador de aritmética mental por latência.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    drill = subparsers.add_parser(
        "drill",
        help="Executa uma sessão de treino.",
    )
    drill_sub = drill.add_subparsers(dest="module", required=True)

    _add_tables_subparser(drill_sub)
    return parser


def _add_tables_subparser(
    drill_sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Configura o subcomando ``drill tables``."""
    p = drill_sub.add_parser(
        "tables",
        help="Tabuada de multiplicação.",
        description=(
            "Sessão de tabuada: sorteia pares (a, b) na faixa "
            "[--min, --max] e cronometra cada resposta. "
            "Por padrão, 30 problemas sem pares triviais (×0, ×1)."
        ),
    )
    p.add_argument(
        "--min",
        type=int,
        default=2,
        dest="min_factor",
        help="Menor fator incluído (default: 2).",
    )
    p.add_argument(
        "--max",
        type=int,
        default=9,
        dest="max_factor",
        help="Maior fator incluído (default: 9).",
    )
    p.add_argument(
        "--count",
        "-n",
        type=int,
        default=30,
        dest="count",
        help="Número de problemas na sessão (default: 30).",
    )
    p.add_argument(
        "--include-trivial",
        action="store_true",
        help="Inclui pares com fator 0 ou 1 (default: exclui).",
    )
    p.add_argument(
        "--no-commutative",
        action="store_true",
        help="Trata 7×8 e 8×7 como pares distintos nas stats.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed do gerador aleatório (reprodutibilidade).",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Arquivo SQLite do histórico (default: {DEFAULT_DB_PATH}).",
    )
    p.add_argument(
        "--no-persist",
        action="store_true",
        help="Não grava esta sessão no banco.",
    )
    p.set_defaults(func=cmd_drill_tables)


def cmd_drill_tables(args: argparse.Namespace) -> int:
    """Executa o subcomando ``drill tables``.

    Fluxo:
        1. Monta :class:`TablesParams` a partir dos argumentos.
        2. Abre o banco (a não ser que ``--no-persist``).
        3. Cria :class:`DrillSession` com gerador, repo e RNG.
        4. Delega à UI em texto (:func:`aitken.ui.plain.run`).
        5. Fecha a conexão.

    Returns:
        ``0`` em sucesso. Erros de validação sobem como exceções e são
        tratados em :func:`main`.
    """
    params = TablesParams(
        min_factor=args.min_factor,
        max_factor=args.max_factor,
        commutative_pairs=not args.no_commutative,
        exclude_trivial=not args.include_trivial,
    )
    generator = TablesGenerator(params)
    rng = Random(args.seed)

    repo: AttemptRepo | None = None
    conn: sqlite3.Connection | None = None
    try:
        if not args.no_persist:
            conn = open_db(args.db)
            repo = AttemptRepo(conn)
        session = DrillSession(
            generator=generator,
            repo=repo,
            max_problems=args.count,
            rng=rng,
        )
        plain.run(session)
    finally:
        if conn is not None:
            conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point da CLI.

    Args:
        argv: lista de argumentos; ``None`` usa ``sys.argv[1:]``.

    Returns:
        Código de saída (0 = sucesso, 2 = erro de validação do parser,
        1 = erro de validação de parâmetros do módulo).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

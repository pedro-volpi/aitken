"""CLI baseada em :mod:`argparse` — composição de storage + session + UI.

A CLI é a única camada autorizada a criar instâncias concretas e ligá-las
umas às outras. Todas as outras camadas conversam via interfaces
(``Generator``, ``AttemptRepo``, ``ScheduleRepo``, ``DrillSession``).

Adicionar um novo módulo de drill (quadrados, cubos, fatoriais, etc.) é:

1. Implementar o ``Protocol`` em :mod:`aitken.core.generators.base`.
2. Registrar um subparser em ``build_parser`` via um ``_add_<module>_subparser``.
3. Escrever um ``cmd_drill_<module>(args)`` que constrói o gerador e
   delega a :func:`_run_drill` (que cuida do banco, sessão e UI).

A função :func:`build_parser` é separada de :func:`main` para permitir
testes (``build_parser().parse_args([...])``).
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from random import Random

from aitken import __version__
from aitken.config import DEFAULT_DB_PATH
from aitken.core.generators.base import Generator
from aitken.core.generators.cubes import CubesGenerator, CubesParams
from aitken.core.generators.factorial import FactorialGenerator
from aitken.core.generators.squares import SquaresGenerator, SquaresParams
from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo, ScheduleRepo
from aitken.ui import plain

_ROOT_DESCRIPTION = """\
Treinador CLI de aritmética mental com foco em fluência por latência.
Todo drill usa retry-on-wrong (erros reapresentam o problema) e SM-2
ponderado por latência (pares difíceis aparecem com mais frequência).
"""

_ROOT_EPILOG = """\
Módulos de drill disponíveis:
  tables      Tabuada de multiplicação (faixa configurável, default 2-9).
  squares     Quadrados N² (default 11-25; 2-10 já saem da tabuada).
  cubes       Cubos N³ (default 3-10).
  factorial   Fatoriais N! (pool fixo 0 a 10).

Exemplos:
  aitken drill tables                            # tabuada padrão, 30 problemas
  aitken drill tables --min 2 --max 19 -n 40     # tabuada estendida, 40 problemas
  aitken drill cubes -n 40                       # sessão maior de cubos
  aitken drill factorial --no-persist            # sessão descartável

Flags comuns a todo drill:
  --count/-n N   problemas distintos a dominar
  --no-persist   não grava tentativas nem estado SM-2

O banco padrão é data/aitken.db dentro do projeto. Use --db PATH para
apontar para outro arquivo (escape hatch; útil para testes).

Ajuda de cada módulo: aitken drill <módulo> --help
"""

_DRILL_EPILOG = """\
Módulos:
  tables      multiplicações (a × b)
  squares     quadrados (N²)
  cubes       cubos (N³)
  factorial   fatoriais (N!), pool fixo 0..10

Cada módulo expõe --help com suas flags específicas, além das comuns
(--count, --no-persist, --db).
"""


def build_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser raiz já com todos os subcomandos."""
    parser = argparse.ArgumentParser(
        prog="aitken",
        description=_ROOT_DESCRIPTION,
        epilog=_ROOT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"aitken {__version__}",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{drill}",
    )

    drill = subparsers.add_parser(
        "drill",
        help="Executa uma sessão de treino.",
        description="Executa uma sessão de treino em um dos módulos disponíveis.",
        epilog=_DRILL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    drill_sub = drill.add_subparsers(
        dest="module",
        required=True,
        metavar="{tables,squares,cubes,factorial}",
    )

    _add_tables_subparser(drill_sub)
    _add_squares_subparser(drill_sub)
    _add_cubes_subparser(drill_sub)
    _add_factorial_subparser(drill_sub)
    return parser


def _add_common_drill_args(p: argparse.ArgumentParser, *, default_count: int = 30) -> None:
    """Flags comuns a todos os subcomandos de drill.

    Cada chamada adiciona: ``--count/-n``, ``--db``, ``--no-persist``.
    Módulos individuais acrescentam flags específicas (faixa, exclusão de
    triviais etc.).
    """
    p.add_argument(
        "--count",
        "-n",
        type=int,
        default=default_count,
        dest="count",
        help=f"Número de problemas distintos a dominar (default: {default_count}).",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Banco alternativo; default é data/aitken.db na raiz do projeto.",
    )
    p.add_argument(
        "--no-persist",
        action="store_true",
        help="Não grava esta sessão nem o estado SM-2 no banco.",
    )


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
    _add_common_drill_args(p)
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
        "--include-trivial",
        action="store_true",
        help="Inclui pares com fator 0 ou 1 (default: exclui).",
    )
    p.add_argument(
        "--no-commutative",
        action="store_true",
        help="Trata 7×8 e 8×7 como pares distintos nas stats.",
    )
    p.set_defaults(func=cmd_drill_tables)


def _add_squares_subparser(
    drill_sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Configura o subcomando ``drill squares``."""
    p = drill_sub.add_parser(
        "squares",
        help="Quadrados (N²).",
        description=(
            "Sessão de quadrados: sorteia bases em [--min, --max] e "
            "cronometra cada N² até a resposta ser acertada."
        ),
    )
    _add_common_drill_args(p)
    p.add_argument(
        "--min",
        type=int,
        default=11,
        dest="min_base",
        help="Menor base incluída (default: 11).",
    )
    p.add_argument(
        "--max",
        type=int,
        default=25,
        dest="max_base",
        help="Maior base incluída (default: 25).",
    )
    p.add_argument(
        "--include-trivial",
        action="store_true",
        help="Inclui 0² e 1² (default: exclui).",
    )
    p.set_defaults(func=cmd_drill_squares)


def _add_cubes_subparser(
    drill_sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Configura o subcomando ``drill cubes``."""
    p = drill_sub.add_parser(
        "cubes",
        help="Cubos (N³).",
        description=(
            "Sessão de cubos: sorteia bases em [--min, --max] e "
            "cronometra cada N³ até a resposta ser acertada."
        ),
    )
    _add_common_drill_args(p)
    p.add_argument(
        "--min",
        type=int,
        default=3,
        dest="min_base",
        help="Menor base incluída (default: 3).",
    )
    p.add_argument(
        "--max",
        type=int,
        default=10,
        dest="max_base",
        help="Maior base incluída (default: 10).",
    )
    p.add_argument(
        "--include-trivial",
        action="store_true",
        help="Inclui 0³ e 1³ (default: exclui).",
    )
    p.set_defaults(func=cmd_drill_cubes)


def _add_factorial_subparser(
    drill_sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Configura o subcomando ``drill factorial``.

    Sem flags de faixa — o pool é fixo, de ``0!`` a ``10!``.
    """
    p = drill_sub.add_parser(
        "factorial",
        help="Fatoriais de 0! a 10!.",
        description=(
            "Sessão de fatoriais: amostra entre 0! e 10! (faixa fixa) "
            "e cronometra cada resposta até ser acertada."
        ),
    )
    _add_common_drill_args(p, default_count=20)
    p.set_defaults(func=cmd_drill_factorial)


def cmd_drill_tables(args: argparse.Namespace) -> int:
    """Executa o subcomando ``drill tables``."""
    params = TablesParams(
        min_factor=args.min_factor,
        max_factor=args.max_factor,
        commutative_pairs=not args.no_commutative,
        exclude_trivial=not args.include_trivial,
    )
    return _run_drill(args, TablesGenerator(params))


def cmd_drill_squares(args: argparse.Namespace) -> int:
    """Executa o subcomando ``drill squares``."""
    params = SquaresParams(
        min_base=args.min_base,
        max_base=args.max_base,
        exclude_trivial=not args.include_trivial,
    )
    return _run_drill(args, SquaresGenerator(params))


def cmd_drill_cubes(args: argparse.Namespace) -> int:
    """Executa o subcomando ``drill cubes``."""
    params = CubesParams(
        min_base=args.min_base,
        max_base=args.max_base,
        exclude_trivial=not args.include_trivial,
    )
    return _run_drill(args, CubesGenerator(params))


def cmd_drill_factorial(args: argparse.Namespace) -> int:
    """Executa o subcomando ``drill factorial``."""
    return _run_drill(args, FactorialGenerator())


def _run_drill(args: argparse.Namespace, generator: Generator) -> int:
    """Fluxo comum a todos os drills: abre DB, monta sessão, roda UI.

    Args:
        args: ``Namespace`` já com ``count``, ``db``, ``no_persist``.
        generator: gerador específico do módulo (tables, squares, ...).

    Returns:
        ``0`` em sucesso. Erros de validação sobem como ``ValueError`` e
        são tratados em :func:`main`.
    """
    rng = Random()
    attempt_repo: AttemptRepo | None = None
    schedule_repo: ScheduleRepo | None = None
    conn: sqlite3.Connection | None = None
    try:
        if not args.no_persist:
            conn = open_db(args.db)
            attempt_repo = AttemptRepo(conn)
            schedule_repo = ScheduleRepo(conn)
        session = DrillSession(
            generator=generator,
            attempt_repo=attempt_repo,
            schedule_repo=schedule_repo,
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

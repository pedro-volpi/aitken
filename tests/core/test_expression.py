"""Testes de :mod:`aitken.core.expression` e da property derivada ``Problem.prompt``.

O ponto sensível: ``prompt`` deixou de ser um campo e virou derivado da
estrutura. Estes testes fixam que a string derivada é *byte a byte* a mesma
de antes — é ela que vai para a coluna ``attempts.prompt`` do banco, então
uma mudança silenciosa de formato quebraria a continuidade do histórico.
"""

from random import Random

from aitken.core.expression import BinaryOp, Term
from aitken.core.generators.cubes import CubesGenerator, CubesParams
from aitken.core.generators.factorial import FactorialGenerator
from aitken.core.generators.squares import SquaresGenerator, SquaresParams
from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.core.problem import Problem


def test_term_inline_is_its_own_text() -> None:
    assert Term("17²").inline() == "17²"


def test_binary_op_inline_uses_spaced_operator() -> None:
    assert BinaryOp("17", "×", "86").inline() == "17 × 86"


def test_problem_prompt_is_derived_from_expression() -> None:
    p = Problem("tables", "tables:7x8", BinaryOp("7", "×", "8"), "56")
    assert p.prompt == "7 × 8"


def test_problem_prompt_is_not_a_field() -> None:
    """``prompt`` é property, não campo — não pode ser passado nem atribuído."""
    p = Problem("squares", "squares:17", Term("17²"), "289")
    assert "prompt" not in {f for f in Problem.__dataclass_fields__}
    assert p.prompt == "17²"


def test_tables_prompt_format_unchanged() -> None:
    """Formato histórico ``"a × b"`` preservado (compat. com o banco)."""
    gen = TablesGenerator(TablesParams(min_factor=7, max_factor=7))
    assert gen.next(Random(0)).prompt == "7 × 7"


def test_unary_prompt_formats_unchanged() -> None:
    """``N²``/``N³``/``N!`` continuam sem espaços nem separadores."""
    squares = SquaresGenerator(SquaresParams(min_base=12, max_base=12))
    cubes = CubesGenerator(CubesParams(min_base=6, max_base=6))
    assert squares.next(Random(0)).prompt == "12²"
    assert cubes.next(Random(0)).prompt == "6³"

    factorial = FactorialGenerator()
    prompt = factorial.next(Random(0)).prompt
    assert prompt.endswith("!")
    assert prompt[:-1].isdigit()


def test_generators_declare_the_right_structure() -> None:
    """tables é binário; os demais módulos são termos atômicos."""
    assert isinstance(TablesGenerator(TablesParams()).next(Random(0)).expression, BinaryOp)
    assert isinstance(SquaresGenerator(SquaresParams()).next(Random(0)).expression, Term)
    assert isinstance(CubesGenerator(CubesParams()).next(Random(0)).expression, Term)
    assert isinstance(FactorialGenerator().next(Random(0)).expression, Term)

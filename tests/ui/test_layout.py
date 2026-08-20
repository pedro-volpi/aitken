"""Testes de :mod:`mentat.ui.layout` — o arranjo das expressões em linhas.

O invariante central da conta armada é o alinhamento: todas as linhas têm a
mesma largura e as casas se correspondem coluna a coluna (unidade sob
unidade). Os testes verificam isso tanto pela string literal quanto por
propriedade, para pegar regressões em operandos de larguras diferentes.
"""

from mentat.core.expression import BinaryOp, Term
from mentat.ui.layout import DEFAULT_LAYOUT, Layout, render


def test_default_layout_is_vertical() -> None:
    """Política do projeto: conta armada é o padrão."""
    assert DEFAULT_LAYOUT is Layout.VERTICAL


def test_horizontal_binary_is_one_line() -> None:
    assert render(BinaryOp("17", "×", "86"), Layout.HORIZONTAL) == ["17 × 86"]


def test_vertical_binary_same_width_operands() -> None:
    assert render(BinaryOp("17", "×", "86"), Layout.VERTICAL) == [
        "  17",
        "× 86",
    ]


def test_vertical_binary_single_digit_operands() -> None:
    assert render(BinaryOp("7", "×", "8"), Layout.VERTICAL) == [
        "  7",
        "× 8",
    ]


def test_vertical_binary_aligns_operands_of_different_widths() -> None:
    """Operando mais curto é empurrado para a direita, casas alinhadas."""
    assert render(BinaryOp("9", "×", "125"), Layout.VERTICAL) == [
        "    9",
        "× 125",
    ]
    assert render(BinaryOp("482", "×", "7"), Layout.VERTICAL) == [
        "  482",
        "×   7",
    ]


def test_vertical_lines_have_equal_width() -> None:
    """Propriedade geral: as duas linhas ocupam exatamente as mesmas colunas."""
    for left, right in [("1", "1"), ("9", "125"), ("482", "7"), ("1234", "56789")]:
        lines = render(BinaryOp(left, "×", right), Layout.VERTICAL)
        assert len({len(line) for line in lines}) == 1


def test_vertical_aligns_units_column() -> None:
    """A última coluna carrega a unidade dos dois operandos."""
    lines = render(BinaryOp("9", "×", "125"), Layout.VERTICAL)
    assert lines[0][-1] == "9"
    assert lines[1][-1] == "5"


def test_vertical_operator_starts_the_second_line() -> None:
    lines = render(BinaryOp("17", "×", "86"), Layout.VERTICAL)
    assert lines[1][0] == "×"
    assert lines[0][0] == " "


def test_term_degrades_to_one_line_in_both_layouts() -> None:
    """Termos atômicos (N², N!, N³) não têm forma armada."""
    for layout in Layout:
        assert render(Term("17²"), layout) == ["17²"]
        assert render(Term("5!"), layout) == ["5!"]


def test_layout_is_a_str_enum_usable_as_cli_choice() -> None:
    """``StrEnum`` para servir direto de ``choices`` no argparse."""
    assert str(Layout.VERTICAL) == "vertical"
    assert Layout("horizontal") is Layout.HORIZONTAL

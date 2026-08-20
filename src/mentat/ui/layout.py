"""Arranjo visual de uma :mod:`~mentat.core.expression` em linhas de texto.

Separação deliberada: ``core/`` diz *o que* é a expressão (dois operandos e
um símbolo, ou um termo atômico); este módulo diz *como* ela ocupa a tela.
Nenhum gerador sabe que layouts existem, e trocar de layout não altera
:attr:`~mentat.core.problem.Problem.prompt` — a forma canônica de uma linha
que vai para o banco e para o resumo permanece a mesma nos dois modos.

O default é :attr:`Layout.VERTICAL` (conta armada). Alinhar unidade sob
unidade é o que torna o algoritmo de multiplicação visível: cada produto
parcial tem uma coluna própria. A forma horizontal continua disponível para
quem prefere a leitura compacta.

Este módulo é puro (``Expression -> list[str]``): não imprime, não lê,
não conhece :class:`~mentat.session.drill.DrillSession`. Quem junta as
linhas com o contador de posição e o ``= `` é :mod:`mentat.ui.plain`.
"""

from enum import StrEnum

from mentat.core.expression import BinaryOp, Expression, Term


class Layout(StrEnum):
    """Modo de disposição do problema na tela.

    ``StrEnum`` para que o valor sirva direto como escolha de ``argparse``
    (``choices=list(Layout)`` exibe ``{horizontal,vertical}``).
    """

    HORIZONTAL = "horizontal"
    """Uma linha: ``17 × 86``."""

    VERTICAL = "vertical"
    """Conta armada, operandos alinhados à direita::

        17
      × 86
    """


DEFAULT_LAYOUT = Layout.VERTICAL
"""Layout usado quando nada é especificado (política do projeto)."""


def render(expression: Expression, layout: Layout) -> list[str]:
    """Desenha ``expression`` como uma ou mais linhas de texto.

    Args:
        expression: a estrutura a desenhar.
        layout: o arranjo desejado.

    Returns:
        As linhas do desenho, sem quebra de linha final. Sempre ao menos
        uma. No modo vertical de uma :class:`~mentat.core.expression.BinaryOp`
        são duas, de largura idêntica.

    Exemplos:
        >>> render(BinaryOp("17", "×", "86"), Layout.HORIZONTAL)
        ['17 × 86']
        >>> render(BinaryOp("17", "×", "86"), Layout.VERTICAL)
        ['  17', '× 86']
        >>> render(BinaryOp("9", "×", "125"), Layout.VERTICAL)
        ['    9', '× 125']
        >>> render(Term("17²"), Layout.VERTICAL)
        ['17²']
    """
    match expression:
        case BinaryOp() as op if layout is Layout.VERTICAL:
            return _stack(op)
        case BinaryOp() | Term() as expr:
            return [expr.inline()]


def _stack(op: BinaryOp) -> list[str]:
    """Empilha os dois operandos alinhados pela direita, operador à esquerda.

    A largura comum é a do operando mais largo, e ambas as linhas recebem
    o mesmo recuo (``len(operador) + 1``). É isso que garante unidade sob
    unidade mesmo com operandos de contagens de dígitos diferentes — o
    alinhamento é o ponto inteiro da conta armada.
    """
    width = max(len(op.left), len(op.right))
    gutter = len(op.operator) + 1
    return [
        " " * gutter + op.left.rjust(width),
        f"{op.operator} " + op.right.rjust(width),
    ]

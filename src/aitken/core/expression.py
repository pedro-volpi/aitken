"""Descrição estrutural da expressão de um :class:`~aitken.core.problem.Problem`.

Um problema não carrega uma string já renderizada: carrega o que ele *é*.
``17 × 86`` é uma operação binária com dois operandos e um símbolo; ``17²``
é um termo único que não se decompõe em linhas. Essa distinção é de
domínio, não de apresentação — por isso mora em ``core/``.

Como *desenhar* cada forma (horizontal, armada, futuramente outras) é
decisão da UI e vive em :mod:`aitken.ui.layout`. Manter a estrutura aqui e
o arranjo lá é o que permite trocar o layout sem tocar nos geradores, e
adicionar um gerador sem saber nada sobre renderização.

Todo tipo de expressão expõe ``inline()`` — a forma canônica de uma linha,
usada como ``Problem.prompt`` (persistida no banco e exibida no resumo).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Term:
    """Expressão atômica, sem forma armada: ``17²``, ``5!``, ``√144``.

    O operador (se houver) já está embutido no texto. Empilhar não faria
    sentido — há um único operando —, então a renderização vertical
    degrada para a mesma linha da horizontal.

    Attributes:
        text: a expressão pronta, em uma linha.
    """

    text: str

    def inline(self) -> str:
        """Forma canônica de uma linha (idêntica ao próprio texto)."""
        return self.text


@dataclass(frozen=True, slots=True)
class BinaryOp:
    """Operação binária ``left <operator> right``: ``17 × 86``, ``91 − 47``.

    Operandos ficam como strings, não como ``int``: o que importa aqui é a
    largura em caracteres para alinhamento, e formas não-inteiras (frações,
    decimais) devem caber no mesmo tipo sem conversão.

    Attributes:
        left: operando da esquerda (linha de cima na forma armada).
        operator: símbolo da operação, tipicamente um caractere (``×``).
        right: operando da direita (linha de baixo na forma armada).
    """

    left: str
    operator: str
    right: str

    def inline(self) -> str:
        """Forma canônica de uma linha: ``"17 × 86"``."""
        return f"{self.left} {self.operator} {self.right}"


type Expression = Term | BinaryOp
"""Toda forma que um problema pode assumir. União fechada — a UI faz match
exaustivo sobre ela, então adicionar um membro obriga a atualizar o
renderizador (o mypy strict acusa)."""

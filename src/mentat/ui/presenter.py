"""Costura de apresentação — como um problema chega ao usuário.

As camadas de baixo já são agnósticas: o gerador declara a estrutura
(:class:`~mentat.core.expression.Expression`), a sessão não faz I/O e
``Problem.prompt`` (a forma canônica que vai ao banco) independe de como o
problema aparece. O que faltava era a costura na própria UI: o driver de
terminal (:mod:`mentat.ui.plain`) chamava ``layout.render`` diretamente,
soldando o loop de prompt/pausa/retry ao caminho visual.

:class:`Presenter` é essa costura. O driver pede ``present(problem)`` uma
vez por apresentação (retry re-apresenta; toggle de pausa não) e compõe as
linhas devolvidas no prompt. O contrato admite apresentação por efeito
colateral: um futuro presenter de voz fala os números e devolve lista
vazia (o prompt vira só cabeçalho + ``= ``); um flash anzan anima a tela e
idem. O retorno é o **resíduo visual** da apresentação, não a apresentação
em si — é isso que torna a implementação plugável sem tocar no driver.

Quem escolhe o presenter concreto é o ponto de composição
(:mod:`mentat.cli`): hoje sempre :class:`VisualPresenter`; um ``--voice``
futuro vira só outra escolha ali.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from mentat.core.problem import Problem
from mentat.ui.layout import DEFAULT_LAYOUT, Layout, render


class Presenter(Protocol):
    """Contrato de apresentação de um problema ao usuário."""

    def present(self, problem: Problem) -> Sequence[str]:
        """Apresenta ``problem`` e devolve as linhas visuais a compor no prompt.

        Pode ter efeito colateral (falar, animar); a lista devolvida — que
        pode ser vazia — é apenas o que deve permanecer na tela junto do
        ``= `` de resposta.
        """
        ...


@dataclass(frozen=True)
class VisualPresenter:
    """Apresentação visual clássica: desenha a expressão no prompt.

    Puro embrulho de :func:`mentat.ui.layout.render` — toda a política de
    arranjo (conta armada vs. linha única) continua em ``layout.py``.
    """

    layout: Layout = DEFAULT_LAYOUT

    def present(self, problem: Problem) -> Sequence[str]:
        """Devolve o desenho da expressão no layout configurado."""
        return render(problem.expression, self.layout)

"""Tipos de domínio imutáveis compartilhados por todas as camadas.

Estas dataclasses formam o vocabulário comum entre ``core``, ``storage``,
``session`` e ``ui``. São puras: não dependem de I/O, UI ou banco. Trocar a
UI de terminal por TUI/GUI não muda nada aqui.

- :class:`Problem` — um item apresentável ao usuário. Gerado por um módulo
  (ex.: ``tables``), identificado por uma ``key`` canônica estável entre
  sessões para agregação de estatísticas. Carrega a estrutura da expressão
  (:mod:`aitken.core.expression`), não uma string já formatada.
- :class:`Attempt` — a tentativa do usuário em resposta a um ``Problem``,
  com latência medida e veredito de correção.
"""

from dataclasses import dataclass

from aitken.core.expression import Expression


@dataclass(frozen=True, slots=True)
class Problem:
    """Um problema concreto pronto para ser mostrado ao usuário.

    Attributes:
        module_id: identificador do módulo gerador (ex.: ``"tables"``).
        key: chave canônica estável para agregação estatística. Dois
            problemas que devem compartilhar histórico (ex.: ``7 × 8`` e
            ``8 × 7`` sob ``commutative_pairs=True``) têm a mesma ``key``.
        expression: descrição *estrutural* do que é o problema (ver
            :mod:`aitken.core.expression`). O gerador declara a estrutura;
            a UI decide o arranjo (horizontal, armado, ...).
        expected_answer: forma canônica da resposta correta, em string
            (a verificação é delegada ao gerador, que sabe como interpretar
            a entrada do usuário).
    """

    module_id: str
    key: str
    expression: Expression
    expected_answer: str

    @property
    def prompt(self) -> str:
        """Forma canônica de uma linha (ex.: ``"7 × 8"``).

        Derivada de :attr:`expression`, nunca armazenada em separado — duas
        cópias da mesma verdade divergiriam. É esta string que vai para a
        coluna ``attempts.prompt`` e para o resumo de fim de sessão, e ela
        **não** muda com o layout escolhido na UI.
        """
        return self.expression.inline()


@dataclass(frozen=True, slots=True)
class Attempt:
    """Tentativa do usuário em resposta a um :class:`Problem`.

    Attributes:
        problem: o problema apresentado.
        user_answer: a string bruta que o usuário digitou.
        elapsed_ms: tempo decorrido entre apresentação e submissão, em
            milissegundos. Medido pela UI (só ela sabe quando renderizou
            de fato) e passado à sessão.
        correct: resultado da verificação feita pelo gerador.
    """

    problem: Problem
    user_answer: str
    elapsed_ms: int
    correct: bool

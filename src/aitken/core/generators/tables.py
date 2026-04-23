"""Gerador de tabuada de multiplicação.

O módulo mais fundamental do treinador: todo cálculo mental acima de uma
operação isolada depende de a tabuada ser consulta instantânea, não cálculo.
O gargalo típico concentra-se no quadrante 6-9 (6×7, 6×8, 7×8, 7×9, 8×9) e
em pares com 11-12 quando a faixa é estendida.

Parâmetros e invariantes estão em :class:`TablesParams`. O gerador em si
(:class:`TablesGenerator`) é *stateless* além dos parâmetros — toda a
aleatoriedade vem do ``Random`` passado em ``next()``, o que torna sessões
reprodutíveis quando a seed é fixada.
"""

from dataclasses import dataclass
from random import Random

from aitken.core.problem import Problem


@dataclass(frozen=True, slots=True)
class TablesParams:
    """Configuração do gerador de tabuada.

    Attributes:
        min_factor: menor fator amostrável (inclusivo). Padrão ``2``.
        max_factor: maior fator amostrável (inclusivo). Padrão ``9``.
        commutative_pairs: se ``True``, ``7 × 8`` e ``8 × 7`` compartilham
            a mesma :attr:`Problem.key`, agrupando estatísticas por par
            canônico ``(min, max)``. A ordem de apresentação ao usuário
            continua aleatória — só a chave é normalizada. Padrão ``True``.
        exclude_trivial: se ``True``, rejeita qualquer amostra em que algum
            fator seja ``< 2``. ``× 0`` e ``× 1`` são triviais e contaminam
            a latência mediana. Padrão ``True``.

    Invariantes (verificadas em ``__post_init__``):
        * ``min_factor >= 0``
        * ``min_factor <= max_factor``
        * após aplicar ``exclude_trivial``, o pool não fica vazio
    """

    min_factor: int = 2
    max_factor: int = 9
    commutative_pairs: bool = True
    exclude_trivial: bool = True

    def __post_init__(self) -> None:
        if self.min_factor < 0:
            raise ValueError(f"min_factor deve ser >= 0, recebeu {self.min_factor}")
        if self.min_factor > self.max_factor:
            raise ValueError(f"min_factor ({self.min_factor}) > max_factor ({self.max_factor})")
        if self.exclude_trivial:
            effective_min = max(self.min_factor, 2)
            if effective_min > self.max_factor:
                raise ValueError(
                    f"exclude_trivial=True deixa a faixa "
                    f"[{self.min_factor}, {self.max_factor}] vazia"
                )


class TablesGenerator:
    """Gerador uniforme de problemas de tabuada.

    Cada chamada a :meth:`next` amostra dois fatores independentes na faixa
    configurada, rejeitando pares triviais quando ``exclude_trivial=True``,
    e devolve um :class:`Problem` com chave canônica.

    Exemplo:
        >>> from random import Random
        >>> gen = TablesGenerator(TablesParams(min_factor=2, max_factor=9))
        >>> p = gen.next(Random(0))
        >>> gen.check(p, p.expected_answer)
        True

    Este gerador é *stateless* além dos parâmetros. Toda a aleatoriedade
    vem do ``Random`` injetado, permitindo reprodutibilidade com seed.
    """

    module_id = "tables"

    def __init__(self, params: TablesParams) -> None:
        self._params = params

    def next(self, rng: Random) -> Problem:
        """Produz um novo problema de tabuada.

        Usa amostragem por rejeição para filtrar pares triviais. O loop
        termina em número esperado de iterações O(1) porque a fração
        filtrada é pequena (<25% mesmo no pior caso prático).
        """
        a, b = self._draw(rng)
        if self._params.commutative_pairs:
            lo, hi = (a, b) if a <= b else (b, a)
            key = f"tables:{lo}x{hi}"
        else:
            key = f"tables:{a}x{b}"
        return Problem(
            module_id=self.module_id,
            key=key,
            prompt=f"{a} × {b}",
            expected_answer=str(a * b),
        )

    def check(self, problem: Problem, user_answer: str) -> bool:
        """Aceita somente inteiros (eventual whitespace ignorado)."""
        s = user_answer.strip()
        if not s:
            return False
        try:
            value = int(s)
        except ValueError:
            return False
        return value == int(problem.expected_answer)

    def _draw(self, rng: Random) -> tuple[int, int]:
        """Amostra um par (a, b) respeitando ``exclude_trivial``."""
        p = self._params
        while True:
            a = rng.randint(p.min_factor, p.max_factor)
            b = rng.randint(p.min_factor, p.max_factor)
            if p.exclude_trivial and (a < 2 or b < 2):
                continue
            return a, b

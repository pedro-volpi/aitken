"""Gerador de fatoriais de 0! a 10!.

Sem parâmetros de faixa: a função cresce rapidamente (10! = 3.628.800) e a
janela utilizável para memorização se esgota em 10. Por isso o pool é
fixo, enumerando todos os 11 valores.

Chave canônica: ``"factorial:N"``. Prompt: ``"N!"``. Resposta esperada:
``str(math.factorial(N))``.
"""

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from math import factorial
from random import Random

from mentat.core.expression import Term
from mentat.core.problem import Problem
from mentat.core.scheduler import weighted_choice

_MIN_N = 0
_MAX_N = 10


class FactorialGenerator:
    """Gerador de fatoriais com amostragem ponderada (SM-2).

    A faixa é fixa de ``0!`` a ``10!`` — os 11 itens do pool são mantidos
    em ``all_keys``. ``next`` amostra uniformemente ou por peso, conforme
    receba ``weights``.
    """

    module_id = "factorial"

    def __init__(self) -> None:
        self._bases: list[int] = list(range(_MIN_N, _MAX_N + 1))
        self._all_keys: list[str] = [f"factorial:{n}" for n in self._bases]

    def all_keys(self) -> Sequence[str]:
        return self._all_keys

    def next(
        self,
        rng: Random,
        *,
        weights: Mapping[str, float] | None = None,
        exclude: AbstractSet[str] = frozenset(),
    ) -> Problem:
        if weights is None:
            bases = (
                [n for n in self._bases if f"factorial:{n}" not in exclude]
                if exclude
                else self._bases
            )
            if not bases:
                bases = self._bases
            n = rng.choice(bases)
        else:
            n = self._base_from_key(weighted_choice(rng, self._all_keys, weights, exclude=exclude))
        return Problem(
            module_id=self.module_id,
            key=f"factorial:{n}",
            expression=Term(f"{n}!"),
            expected_answer=str(factorial(n)),
        )

    def check(self, problem: Problem, user_answer: str) -> bool:
        """Aceita inteiro; espaços ignorados, não-numérico vira False."""
        s = user_answer.strip()
        if not s:
            return False
        try:
            value = int(s)
        except ValueError:
            return False
        return value == int(problem.expected_answer)

    @staticmethod
    def _base_from_key(key: str) -> int:
        _, n = key.split(":", 1)
        return int(n)

"""Gerador de fatoriais de 0! a 10!.

Sem parâmetros de faixa: a função cresce rapidamente (10! = 3.628.800) e a
janela utilizável para memorização se esgota em 10. Por isso o pool é
fixo, enumerando todos os 11 valores.

Chave canônica: ``"factorial:N"``. Prompt: ``"N!"``. Resposta esperada:
``str(math.factorial(N))``.
"""

from collections.abc import Mapping, Sequence
from math import factorial
from random import Random

from aitken.core.problem import Problem
from aitken.core.scheduler import sampling_weight

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

    def next(self, rng: Random, *, weights: Mapping[str, float] | None = None) -> Problem:
        if weights is None:
            n = rng.choice(self._bases)
        else:
            default = sampling_weight(None)
            ws = [weights.get(k, default) for k in self._all_keys]
            [chosen] = rng.choices(self._all_keys, weights=ws, k=1)
            n = self._base_from_key(chosen)
        return Problem(
            module_id=self.module_id,
            key=f"factorial:{n}",
            prompt=f"{n}!",
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

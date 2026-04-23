"""Gerador de quadrados.

Cobre de 11² até o limite configurado (default 25²) por padrão — a faixa
2²–10² sai "de graça" da tabuada, então o valor do drill de quadrados
está nas bases maiores. ``0²`` e ``1²`` são triviais e ficam de fora
via ``exclude_trivial``.

Chave canônica: ``"squares:N"``. Prompt: ``"N²"``. Resposta esperada:
``str(N * N)``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from aitken.core.problem import Problem
from aitken.core.scheduler import sampling_weight


@dataclass(frozen=True, slots=True)
class SquaresParams:
    """Configuração do gerador de quadrados.

    Attributes:
        min_base: menor base amostrável (inclusivo). Padrão ``11``.
        max_base: maior base amostrável (inclusivo). Padrão ``25``.
        exclude_trivial: se ``True``, rejeita bases ``< 2``. Padrão ``True``.

    Invariantes (verificadas em ``__post_init__``):
        * ``min_base >= 0``
        * ``min_base <= max_base``
        * após aplicar ``exclude_trivial``, o pool não fica vazio
    """

    min_base: int = 11
    max_base: int = 25
    exclude_trivial: bool = True

    def __post_init__(self) -> None:
        if self.min_base < 0:
            raise ValueError(f"min_base deve ser >= 0, recebeu {self.min_base}")
        if self.min_base > self.max_base:
            raise ValueError(f"min_base ({self.min_base}) > max_base ({self.max_base})")
        if self.exclude_trivial:
            effective_min = max(self.min_base, 2)
            if effective_min > self.max_base:
                raise ValueError(
                    f"exclude_trivial=True deixa a faixa [{self.min_base}, {self.max_base}] vazia"
                )


class SquaresGenerator:
    """Gerador de quadrados com suporte a amostragem ponderada (SM-2)."""

    module_id = "squares"

    def __init__(self, params: SquaresParams) -> None:
        self._params = params
        effective_min = max(params.min_base, 2) if params.exclude_trivial else params.min_base
        self._bases: list[int] = list(range(effective_min, params.max_base + 1))
        self._all_keys: list[str] = [f"squares:{n}" for n in self._bases]

    def all_keys(self) -> Sequence[str]:
        return self._all_keys

    def next(self, rng: Random, *, weights: Mapping[str, float] | None = None) -> Problem:
        """Sorteia uma base na faixa e devolve o problema ``N²``.

        Com ``weights``, amostra por chave; sem eles, escolha uniforme.
        """
        if weights is None:
            n = rng.choice(self._bases)
        else:
            default = sampling_weight(None)
            ws = [weights.get(k, default) for k in self._all_keys]
            [chosen] = rng.choices(self._all_keys, weights=ws, k=1)
            n = self._base_from_key(chosen)
        return Problem(
            module_id=self.module_id,
            key=f"squares:{n}",
            prompt=f"{n}²",
            expected_answer=str(n * n),
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

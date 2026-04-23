"""Gerador de tabuada de multiplicação.

O módulo mais fundamental do treinador: todo cálculo mental acima de uma
operação isolada depende de a tabuada ser consulta instantânea, não cálculo.
O gargalo típico concentra-se no quadrante 6-9 (6×7, 6×8, 7×8, 7×9, 8×9) e
em pares com 11-12 quando a faixa é estendida.

Parâmetros e invariantes estão em :class:`TablesParams`. O gerador em si
(:class:`TablesGenerator`) é *stateless* além dos parâmetros — toda a
aleatoriedade vem do ``Random`` passado em ``next()``, o que torna sessões
reprodutíveis quando a seed é fixada.

Suporta amostragem uniforme (``next(rng)``) e ponderada (``next(rng,
weights=...)``), esta última usada pelo scheduler SM-2 para priorizar
pares com baixa facilidade. Ver :mod:`aitken.core.scheduler`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from aitken.core.problem import Problem
from aitken.core.scheduler import sampling_weight


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
    """Gerador de problemas de tabuada com suporte a amostragem ponderada.

    Exemplo uniforme:
        >>> from random import Random
        >>> gen = TablesGenerator(TablesParams(min_factor=2, max_factor=9))
        >>> p = gen.next(Random(0))
        >>> gen.check(p, p.expected_answer)
        True

    Exemplo ponderado (o scheduler SM-2 passa pesos derivados de
    ``ease_factor``):
        >>> weights = {k: 0.1 for k in gen.all_keys()}
        >>> weights["tables:7x8"] = 100.0
        >>> p = gen.next(Random(0), weights=weights)
        >>> p.key
        'tables:7x8'

    Este gerador é *stateless* além dos parâmetros. Toda a aleatoriedade
    vem do ``Random`` injetado, permitindo reprodutibilidade com seed.
    """

    module_id = "tables"

    def __init__(self, params: TablesParams) -> None:
        self._params = params
        self._effective_min = (
            max(params.min_factor, 2) if params.exclude_trivial else params.min_factor
        )
        self._all_keys: list[str] = self._enumerate_keys()

    def all_keys(self) -> Sequence[str]:
        """Lista imutável de todas as chaves distintas no pool configurado."""
        return self._all_keys

    def next(self, rng: Random, *, weights: Mapping[str, float] | None = None) -> Problem:
        """Produz um novo problema de tabuada.

        Sem ``weights``, usa amostragem por rejeição uniforme (filtrando
        pares triviais). Com ``weights``, escolhe entre :meth:`all_keys`
        proporcionalmente ao peso — chaves ausentes recebem o peso padrão
        de :func:`aitken.core.scheduler.sampling_weight` para ``None``.
        """
        if weights is None:
            a, b = self._draw(rng)
            return self._make_problem(a, b)
        keys = self._all_keys
        default = sampling_weight(None)
        ws = [weights.get(k, default) for k in keys]
        [chosen] = rng.choices(keys, weights=ws, k=1)
        a, b = self._parse_key(chosen)
        # Para pares comutativos não-diagonais, randomiza a ordem de
        # apresentação — a chave canônica é a mesma, mas o usuário vê
        # "7 × 8" e "8 × 7" alternando.
        if self._params.commutative_pairs and a != b and rng.random() < 0.5:
            a, b = b, a
        return self._make_problem(a, b)

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

    def _make_problem(self, a: int, b: int) -> Problem:
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

    def _draw(self, rng: Random) -> tuple[int, int]:
        """Amostra uniforme um par (a, b) respeitando ``exclude_trivial``."""
        p = self._params
        while True:
            a = rng.randint(p.min_factor, p.max_factor)
            b = rng.randint(p.min_factor, p.max_factor)
            if p.exclude_trivial and (a < 2 or b < 2):
                continue
            return a, b

    def _enumerate_keys(self) -> list[str]:
        """Enumera as chaves distintas no pool atual."""
        lo = self._effective_min
        hi = self._params.max_factor
        if self._params.commutative_pairs:
            return [f"tables:{i}x{j}" for i in range(lo, hi + 1) for j in range(i, hi + 1)]
        return [f"tables:{i}x{j}" for i in range(lo, hi + 1) for j in range(lo, hi + 1)]

    @staticmethod
    def _parse_key(key: str) -> tuple[int, int]:
        """Extrai ``(a, b)`` de uma chave no formato ``tables:AxB``."""
        _, pair = key.split(":", 1)
        a_str, b_str = pair.split("x")
        return int(a_str), int(b_str)

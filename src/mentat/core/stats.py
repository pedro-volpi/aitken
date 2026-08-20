"""Agregados estatísticos puros para sessões de drill.

Todas as funções aqui são puras: recebem sequências de :class:`Attempt` e
retornam dataclasses imutáveis. Nenhuma leitura de disco, nenhuma UI.
Isso permite testá-las sem fixtures e reutilizá-las entre a CLI atual e
futuras UIs (TUI, gráficos matplotlib) sem qualquer adaptação.

Percentis são reportados como ``None`` quando o número de amostras é
insuficiente para dar um sinal confiável (<10 para p90). Isso evita
relatar "p90 = 1.2s" baseado em 3 medidas.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median, quantiles

from aitken.core.problem import Attempt


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Resultado agregado de uma sessão de drill.

    Attributes:
        total: número de tentativas na sessão.
        correct: número de tentativas avaliadas como corretas.
        accuracy: razão ``correct / total``, entre 0 e 1. Zero se vazio.
        median_ms: latência mediana em milissegundos. Zero se vazio.
        p90_ms: latência no 90º percentil, ou ``None`` se ``total < 10``.
        slowest: tupla ``(prompt, elapsed_ms)`` do item mais lento, ou
            ``None`` se vazio.
    """

    total: int
    correct: int
    accuracy: float
    median_ms: float
    p90_ms: float | None
    slowest: tuple[str, int] | None

    @property
    def wrong(self) -> int:
        """Número de tentativas erradas."""
        return self.total - self.correct


def summarize(attempts: Sequence[Attempt]) -> SessionSummary:
    """Computa um :class:`SessionSummary` a partir de tentativas.

    Args:
        attempts: sequência (possivelmente vazia) de tentativas da sessão.

    Returns:
        O resumo agregado. Entrada vazia retorna campos numéricos em zero
        e campos opcionais em ``None``, sem exceções.
    """
    if not attempts:
        return SessionSummary(
            total=0,
            correct=0,
            accuracy=0.0,
            median_ms=0.0,
            p90_ms=None,
            slowest=None,
        )

    total = len(attempts)
    correct = sum(1 for a in attempts if a.correct)
    accuracy = correct / total
    latencies = [a.elapsed_ms for a in attempts]
    med = float(median(latencies))

    p90: float | None = None
    if total >= 10:
        # `quantiles(data, n=10)` devolve os 9 pontos de corte; o 9º (índice 8)
        # é p90 pelo método padrão (linear interpolation, exclusivo).
        p90 = quantiles(latencies, n=10)[8]

    slowest_attempt = max(attempts, key=lambda a: a.elapsed_ms)
    slowest = (slowest_attempt.problem.prompt, slowest_attempt.elapsed_ms)

    return SessionSummary(
        total=total,
        correct=correct,
        accuracy=accuracy,
        median_ms=med,
        p90_ms=p90,
        slowest=slowest,
    )

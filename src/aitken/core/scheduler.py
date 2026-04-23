"""Scheduler SM-2 ponderado por latência.

Núcleo puro. Define o :class:`Card` (estado SM-2 por ``problem_key``), a
função de atualização :func:`update_card`, o mapeamento
(correct, latência) → quality SM-2 em :func:`quality_from_attempt` e o
peso de amostragem em :func:`sampling_weight`.

Diferenças em relação ao SM-2 clássico:

- Não guardamos intervalo em dias — a amostragem acontece dentro da
  sessão, então o que importa é a *prioridade relativa* entre pares.
- Para ``quality < 3`` (falha de recall), o ``ease_factor`` cai 0.2 além
  de zerar o streak. SM-2 clássico apenas zera o intervalo; aqui somos
  mais agressivos porque a janela de aprendizado é curta (drills de ≤ 1h).
- Latência entra via :func:`quality_from_attempt`: uma resposta correta e
  lenta recebe ``quality`` baixa, o que empurra ``ease_factor`` para
  baixo e mantém o par sendo reapresentado.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Card:
    """Estado SM-2 persistente por ``problem_key``.

    Attributes:
        ease_factor: fator de facilidade SM-2. Começa em 2.5, mínimo 1.3.
            Valores baixos = par difícil = alta prioridade de amostragem.
        consecutive_correct: quantidade de acertos consecutivos (sem
            recall failure). Zera quando a qualidade cai abaixo de 3.
    """

    ease_factor: float = 2.5
    consecutive_correct: int = 0


_MIN_EF = 1.3
_INITIAL_EF = 2.5


def update_card(card: Card, quality: int) -> Card:
    """Aplica o update SM-2 à :class:`Card`.

    Args:
        card: estado anterior.
        quality: pontuação SM-2 em [0, 5]. Valores < 3 são tratados como
            *recall failure* (zera ``consecutive_correct``, penaliza EF).

    Returns:
        Nova ``Card`` (imutável; o original não é alterado).

    Raises:
        ValueError: se ``quality`` não estiver em [0, 5].
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"quality deve estar em [0, 5], recebeu {quality}")
    if quality < 3:
        return Card(
            ease_factor=max(_MIN_EF, card.ease_factor - 0.2),
            consecutive_correct=0,
        )
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return Card(
        ease_factor=max(_MIN_EF, card.ease_factor + delta),
        consecutive_correct=card.consecutive_correct + 1,
    )


def quality_from_attempt(
    *,
    correct: bool,
    elapsed_ms: int,
    target_ms: int = 2000,
    fail_ms: int = 8000,
) -> int:
    """Mapeia ``(correct, latência)`` para um quality score SM-2 em [0, 5].

    Args:
        correct: se a resposta foi validada como correta pelo gerador.
        elapsed_ms: tempo de resposta.
        target_ms: limite de "rápido". Respostas corretas abaixo disso
            pontuam 5 (máximo).
        fail_ms: limite de "muito lento". Acima disso, mesmo correto cai
            para 2 (qualidade de recall failure); errado cai para 0.

    Returns:
        Inteiro em [0, 5]. Regras:

        - errado + lento (>= fail_ms): 0
        - errado: 1
        - correto + muito lento: 2
        - correto + lento (target_ms .. 2*target_ms): 3-4
        - correto + rápido (< target_ms): 5
    """
    if elapsed_ms < 0:
        raise ValueError(f"elapsed_ms não pode ser negativo, recebeu {elapsed_ms}")
    if not correct:
        return 0 if elapsed_ms >= fail_ms else 1
    if elapsed_ms < target_ms:
        return 5
    if elapsed_ms < 2 * target_ms:
        return 4
    if elapsed_ms < fail_ms:
        return 3
    return 2


def sampling_weight(card: Card | None) -> float:
    """Peso de amostragem para uma chave com o ``card`` dado.

    Chaves nunca vistas (``card is None``) recebem peso máximo — o
    scheduler sempre prefere expor itens inéditos. Para chaves vistas,
    o peso decai com ``ease_factor`` alto (item dominado) e com streak
    de acertos.

    Returns:
        Peso > 0. Maior = mais provável de ser amostrado.
    """
    if card is None:
        return 4.0
    ease_penalty = max(0.5, 4.0 - card.ease_factor)
    streak_dampening = 1.0 / (1.0 + card.consecutive_correct * 0.4)
    return ease_penalty * streak_dampening


def weights_from_cards(cards: Mapping[str, Card]) -> dict[str, float]:
    """Computa o mapa ``{key: peso}`` para passar ao gerador.

    O gerador é responsável por enumerar a faixa e aplicar os pesos;
    chaves não presentes em ``cards`` são interpretadas pelo gerador
    como ainda não vistas (peso de :func:`sampling_weight` com ``None``).
    """
    return {k: sampling_weight(c) for k, c in cards.items()}

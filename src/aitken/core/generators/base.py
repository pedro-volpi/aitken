"""Protocolo comum a todos os geradores de drill.

Qualquer módulo de treino (tabuada, quadrados, divisão, frações...) expõe
uma implementação deste ``Protocol``. A sessão de treino opera apenas sobre
este contrato — não conhece detalhes de módulos específicos, o que permite
adicionar novos sem tocar em ``session/`` ou ``ui/``.

Separação de responsabilidades:

- ``next(rng)`` produz o próximo :class:`Problem`. O gerador é livre para
  usar ``rng`` uniformemente ou amostrar com peso (weakness-focused) — o
  cliente não precisa saber.
- ``check(problem, user_answer)`` interpreta e valida a resposta textual.
  Manter a interpretação dentro do gerador é deliberado: frações aceitam
  ``"a/b"``, decimais aceitam ``","`` ou ``"."``, etc. Cada módulo conhece
  suas próprias regras.
"""
from __future__ import annotations

from random import Random
from typing import Protocol, runtime_checkable

from aitken.core.problem import Problem


@runtime_checkable
class Generator(Protocol):
    """Contrato que todo gerador de drill deve satisfazer."""

    module_id: str
    """Identificador estável do módulo (ex.: ``"tables"``)."""

    def next(self, rng: Random) -> Problem:
        """Produz o próximo problema a ser apresentado.

        Args:
            rng: fonte de aleatoriedade; passar uma instância com seed fixo
                permite reprodutibilidade para benchmarks e testes.

        Returns:
            Um :class:`Problem` pronto para renderização.
        """

    def check(self, problem: Problem, user_answer: str) -> bool:
        """Avalia se ``user_answer`` é correto para ``problem``.

        A string é aceita em forma bruta: o gerador é responsável por
        normalizar (strip, separadores decimais, etc.) antes de comparar.

        Returns:
            True se a resposta é considerada correta, False caso contrário.
            Entrada vazia ou malformada sempre retorna False — nunca levanta.
        """

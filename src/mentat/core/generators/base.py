"""Protocolo comum a todos os geradores de drill.

Qualquer módulo de treino (tabuada, quadrados, divisão, frações...) expõe
uma implementação deste ``Protocol``. A sessão de treino opera apenas sobre
este contrato — não conhece detalhes de módulos específicos, o que permite
adicionar novos sem tocar em ``session/`` ou ``ui/``.

Separação de responsabilidades:

- ``next(rng, *, weights, exclude)`` produz o próximo :class:`Problem`.
  Quando ``weights`` é dado, o gerador faz amostragem ponderada por chave
  (integração com o scheduler SM-2 em :mod:`mentat.core.scheduler`). Sem
  ``weights``, a amostragem é uniforme. ``exclude`` carrega as chaves a
  evitar (política de não-repetição consecutiva da sessão).
- ``all_keys()`` enumera o universo de chaves distintas no pool — o
  scheduler usa isso para saber o que ainda não foi visto.
- ``check(problem, user_answer)`` interpreta e valida a resposta textual.
  Manter a interpretação dentro do gerador é deliberado: frações aceitam
  ``"a/b"``, decimais aceitam ``","`` ou ``"."``, etc. Cada módulo conhece
  suas próprias regras.

**O contrato é fechado sob composição.** Um gerador não precisa ser um
módulo único: um drill misto futuro é um gerador *composto* que embrulha
outros geradores e satisfaz este mesmo ``Protocol`` — ``all_keys()`` é a
união dos universos dos filhos, ``next()`` delega a um filho, ``check()``
despacha pelo ``module_id`` do :class:`Problem` recebido. Duas
propriedades sustentam isso:

1. **Chaves globalmente únicas**: toda ``key`` começa com
   ``"<module_id>:"`` (invariante verificada em
   :class:`~mentat.core.problem.Problem`), então ``weights``, ``exclude``
   e o estado SM-2 da sessão nunca colidem entre módulos.
2. **Nenhum membro identifica "o" módulo**: o contrato não exige
   ``module_id`` — a proveniência mora em cada ``Problem`` produzido, que
   sempre sabe de qual módulo veio, mesmo num gerador composto.
"""

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from random import Random
from typing import Protocol, runtime_checkable

from mentat.core.problem import Problem


@runtime_checkable
class Generator(Protocol):
    """Contrato que todo gerador de drill deve satisfazer.

    Deliberadamente sem ``module_id``: o identificador de módulo é detalhe
    dos geradores-folha (que o usam para construir seus ``Problem``), não
    exigência do contrato. Quem consome um gerador — a sessão — nunca
    precisa saber de *qual* módulo ele é, apenas do universo
    (:meth:`all_keys`), do sorteio (:meth:`next`) e da validação
    (:meth:`check`). É isso que deixa um gerador composto multi-módulo
    satisfazer o mesmo contrato sem inventar um módulo fictício.
    """

    def next(
        self,
        rng: Random,
        *,
        weights: Mapping[str, float] | None = None,
        exclude: AbstractSet[str] = frozenset(),
    ) -> Problem:
        """Produz o próximo problema a ser apresentado.

        Args:
            rng: fonte de aleatoriedade; passar uma instância com seed fixo
                permite reprodutibilidade para benchmarks e testes.
            weights: se fornecido, ``{key: peso}`` para amostragem
                ponderada. Chaves ausentes são tratadas como peso padrão
                (ver implementação). ``None`` = amostragem uniforme.
            exclude: chaves a evitar nesta amostragem. A sessão usa isso
                para impor "sem repetição consecutiva" (passa a chave do
                problema anterior). **Invariante**: a ``key`` do problema
                devolvido não está em ``exclude`` sempre que o pool tem
                alternativa; se ``exclude`` cobrir todo o universo (ex.:
                pool de uma única chave), a restrição é descartada
                (best-effort) e a repetição é permitida.

        Returns:
            Um :class:`Problem` pronto para renderização.
        """

    def all_keys(self) -> Sequence[str]:
        """Enumera todas as chaves distintas amostráveis no pool atual.

        O scheduler usa essa lista para (a) distinguir chaves inéditas
        (prioridade máxima) de chaves com histórico e (b) montar o mapa
        completo de pesos a passar para :meth:`next`.
        """

    def check(self, problem: Problem, user_answer: str) -> bool:
        """Avalia se ``user_answer`` é correto para ``problem``.

        A string é aceita em forma bruta: o gerador é responsável por
        normalizar (strip, separadores decimais, etc.) antes de comparar.

        Returns:
            True se a resposta é considerada correta, False caso contrário.
            Entrada vazia ou malformada sempre retorna False — nunca levanta.
        """

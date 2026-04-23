"""DrillSession — camada de aplicação (use case) do treino.

A sessão orquestra quatro colaboradores injetados:

- ``generator``: produz problemas e valida respostas (contrato em
  :class:`aitken.core.generators.base.Generator`).
- ``attempt_repo``: grava o histórico imutável de tentativas. Pode ser
  ``None`` em modo ``--no-persist``.
- ``schedule_repo``: persiste o estado SM-2 por chave. Pode ser ``None`` —
  a sessão ainda mantém os ``Card`` em memória e aplica SM-2 durante o
  run; apenas não sobrevive ao encerramento.
- ``rng``: fonte de aleatoriedade.

**Desacoplamento da UI**: a sessão não chama ``input()``, ``print()``,
``time.perf_counter()`` ou qualquer API de apresentação. Ela expõe duas
operações:

1. iteração (``for problem in session:``) que gera problemas até o limite
   configurado em ``max_problems`` ser atingido com todos corretos;
2. ``record(problem, user_answer, elapsed_ms)`` que avalia, persiste e
   devolve a tentativa resultante.

**Retry-on-wrong**: respostas incorretas fazem o mesmo problema voltar na
próxima iteração. ``max_problems`` conta *problemas distintos a dominar*.

**SM-2 ponderado por latência**: ao final de cada ciclo de retry (ou seja,
quando uma chave é finalmente respondida corretamente), o ``Card`` da
chave é atualizado com a quality derivada do tempo de resposta. Erros em
qualquer ponto do ciclo rebaixam a quality para 2 (recall failure), o que
zera o streak e reduz ``ease_factor``. Isso faz com que chaves difíceis
sejam amostradas com maior frequência na próxima sessão (e, se o mesmo
par recair durante *esta* sessão, também agora).
"""

from collections.abc import Iterator
from random import Random

from aitken.core.generators.base import Generator
from aitken.core.problem import Attempt, Problem
from aitken.core.scheduler import (
    Card,
    quality_from_attempt,
    update_card,
    weights_from_cards,
)
from aitken.core.stats import SessionSummary, summarize
from aitken.storage.repositories import AttemptRepo, ScheduleRepo


class DrillSession:
    """Uma sessão de treino com SM-2 + retry-on-wrong embutidos."""

    def __init__(
        self,
        generator: Generator,
        attempt_repo: AttemptRepo | None,
        schedule_repo: ScheduleRepo | None,
        max_problems: int,
        rng: Random,
    ) -> None:
        """Inicializa a sessão.

        Args:
            generator: gerador de problemas e validador de respostas.
            attempt_repo: log de tentativas, ou ``None`` para não gravar.
            schedule_repo: estado SM-2 persistido, ou ``None`` para rodar
                com scheduling apenas em memória (zerando a cada sessão).
            max_problems: número de problemas *distintos* a dominar;
                deve ser > 0. Erros disparam retry sem consumir do
                contador.
            rng: fonte de aleatoriedade. Injetada para reprodutibilidade.

        Raises:
            ValueError: se ``max_problems <= 0``.
        """
        if max_problems <= 0:
            raise ValueError(f"max_problems deve ser > 0, recebeu {max_problems}")
        self._generator = generator
        self._attempt_repo = attempt_repo
        self._schedule_repo = schedule_repo
        self._max_problems = max_problems
        self._rng = rng
        self._attempts: list[Attempt] = []
        self._remaining = max_problems
        self._pending_retry: Problem | None = None
        self._position = 0
        self._cycle_had_error = False
        self._cards: dict[str, Card] = (
            schedule_repo.load(generator.module_id) if schedule_repo is not None else {}
        )

    @property
    def total_problems(self) -> int:
        """Número total de problemas distintos que esta sessão produzirá."""
        return self._max_problems

    @property
    def current_position(self) -> int:
        """Posição 1-indexada do problema distinto atual (não avança em retry)."""
        return self._position

    @property
    def attempts(self) -> list[Attempt]:
        """Cópia defensiva da lista de tentativas feitas até agora."""
        return list(self._attempts)

    def card_for(self, key: str) -> Card | None:
        """Devolve o ``Card`` corrente para a chave (None se inédita)."""
        return self._cards.get(key)

    def __iter__(self) -> Iterator[Problem]:
        """Itera produzindo problemas até dominar ``max_problems`` distintos.

        A escolha do próximo problema passa pelo scheduler: pesos são
        computados a partir dos ``Card`` correntes e o gerador recebe o
        dicionário em ``next(rng, weights=...)``. Retry curto-circuita o
        scheduler reemitindo exatamente a última questão errada.
        """
        while self._remaining > 0 or self._pending_retry is not None:
            if self._pending_retry is not None:
                problem = self._pending_retry
                self._pending_retry = None
            else:
                self._remaining -= 1
                self._position += 1
                problem = self._generator.next(
                    self._rng,
                    weights=weights_from_cards(self._cards),
                )
            yield problem

    def record(
        self,
        problem: Problem,
        user_answer: str,
        elapsed_ms: int,
    ) -> Attempt:
        """Avalia a resposta, persiste e devolve a tentativa.

        Em caso de resposta incorreta, ``problem`` é reenfileirado para a
        próxima iteração (retry-on-wrong) e nenhum update de ``Card`` é
        feito — o ciclo ainda não fechou. Ao concluir com resposta
        correta, computa a quality SM-2 (com teto em 2 se houve erro em
        qualquer ponto do ciclo) e atualiza o ``Card``.

        Args:
            problem: o problema apresentado (vindo da iteração).
            user_answer: entrada bruta do usuário; o gerador normaliza.
            elapsed_ms: latência medida pela UI em milissegundos.

        Returns:
            A :class:`Attempt` criada, já adicionada a :attr:`attempts`.

        Raises:
            ValueError: se ``elapsed_ms`` é negativo.
        """
        if elapsed_ms < 0:
            raise ValueError(f"elapsed_ms não pode ser negativo, recebeu {elapsed_ms}")
        correct = self._generator.check(problem, user_answer)
        attempt = Attempt(
            problem=problem,
            user_answer=user_answer,
            elapsed_ms=elapsed_ms,
            correct=correct,
        )
        self._attempts.append(attempt)
        if self._attempt_repo is not None:
            self._attempt_repo.record(attempt)
        if correct:
            self._pending_retry = None
            quality = quality_from_attempt(correct=True, elapsed_ms=elapsed_ms)
            if self._cycle_had_error:
                # Recall falhou no ciclo, mesmo que tenha fechado com acerto.
                quality = min(quality, 2)
            new_card = update_card(self._cards.get(problem.key, Card()), quality)
            self._cards[problem.key] = new_card
            if self._schedule_repo is not None:
                self._schedule_repo.upsert(problem.module_id, problem.key, new_card)
            self._cycle_had_error = False
        else:
            self._pending_retry = problem
            self._cycle_had_error = True
        return attempt

    def summary(self) -> SessionSummary:
        """Resumo estatístico de todas as tentativas (inclusive retries)."""
        return summarize(self._attempts)

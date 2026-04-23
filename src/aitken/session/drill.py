"""DrillSession — camada de aplicação (use case) do treino.

A sessão orquestra três colaboradores injetados:

- ``generator``: produz problemas e valida respostas (contrato em
  :class:`aitken.core.generators.base.Generator`).
- ``repo``: persiste tentativas. Pode ser ``None`` para sessões efêmeras
  (modo ``--no-persist``).
- ``rng``: fonte de aleatoriedade.

**Desacoplamento da UI**: a sessão não chama ``input()``, ``print()``,
``time.perf_counter()`` ou qualquer API de apresentação. Ela expõe duas
operações:

1. iteração (``for problem in session:``) que gera problemas até o limite;
2. ``record(problem, user_answer, elapsed_ms)`` que avalia, persiste e
   devolve a tentativa resultante.

**Retry-on-wrong**: sempre que ``record`` conclui que a resposta é
incorreta, o mesmo problema é reenfileirado e voltará a ser emitido pelo
iterador na próxima rodada. ``max_problems`` conta *problemas distintos a
dominar*; a mesma questão pode gerar múltiplos ``Attempt`` na lista. Essa é
a política padrão de todas as sessões de drill do projeto.

A UI (seja terminal, Textual ou GUI futura) é quem mede latência, lê
entrada do usuário e renderiza feedback. Trocar a UI é trocar o driver
do loop — a sessão fica idêntica.
"""

from collections.abc import Iterator
from random import Random

from aitken.core.generators.base import Generator
from aitken.core.problem import Attempt, Problem
from aitken.core.stats import SessionSummary, summarize
from aitken.storage.repositories import AttemptRepo


class DrillSession:
    """Uma sessão de treino limitada por contagem de problemas distintos.

    Exemplo de uso (driver genérico, UI-agnóstico):

        session = DrillSession(generator, repo, max_problems=30, rng=Random())
        for problem in session:
            # UI mede latência:
            answer, elapsed_ms = ui.ask(problem)
            attempt = session.record(problem, answer, elapsed_ms)
            ui.show_feedback(attempt)
        summary = session.summary()
        ui.show_summary(summary)

    Cada resposta errada faz o mesmo ``problem`` voltar na próxima iteração.
    Abandonar cedo (``break`` no loop) descarta o restante; o que já foi
    registrado permanece em :attr:`attempts`.
    """

    def __init__(
        self,
        generator: Generator,
        repo: AttemptRepo | None,
        max_problems: int,
        rng: Random,
    ) -> None:
        """Inicializa a sessão.

        Args:
            generator: gerador de problemas e validador de respostas.
            repo: repositório de persistência, ou ``None`` para não gravar.
            max_problems: número de problemas *distintos* a produzir; deve
                ser > 0. Erros disparam retry sem consumir desse contador.
            rng: fonte de aleatoriedade. Injetada para reprodutibilidade.

        Raises:
            ValueError: se ``max_problems <= 0``.
        """
        if max_problems <= 0:
            raise ValueError(f"max_problems deve ser > 0, recebeu {max_problems}")
        self._generator = generator
        self._repo = repo
        self._max_problems = max_problems
        self._rng = rng
        self._attempts: list[Attempt] = []
        self._remaining = max_problems
        self._pending_retry: Problem | None = None
        self._position = 0

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

    def __iter__(self) -> Iterator[Problem]:
        """Itera produzindo problemas até dominar ``max_problems`` distintos.

        Se a última chamada a ``record`` apontou resposta errada, a próxima
        iteração reemite *o mesmo* problema — sem decrementar o contador de
        pendentes nem avançar :attr:`current_position`. O loop só termina
        quando todos os distintos foram respondidos corretamente ou o driver
        aborta com ``break``.
        """
        while self._remaining > 0 or self._pending_retry is not None:
            if self._pending_retry is not None:
                problem = self._pending_retry
                self._pending_retry = None
            else:
                self._remaining -= 1
                self._position += 1
                problem = self._generator.next(self._rng)
            yield problem

    def record(
        self,
        problem: Problem,
        user_answer: str,
        elapsed_ms: int,
    ) -> Attempt:
        """Avalia a resposta, persiste e devolve a tentativa.

        Em caso de resposta incorreta, ``problem`` é reenfileirado para a
        próxima iteração do loop — política *retry-on-wrong* padrão.

        Args:
            problem: o problema apresentado (vindo da iteração).
            user_answer: entrada bruta do usuário; o gerador normaliza.
            elapsed_ms: latência medida pela UI em milissegundos.

        Returns:
            A :class:`Attempt` criada, já adicionada a :attr:`attempts`.
            Se houver repositório, a tentativa é persistida antes do
            retorno.

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
        if self._repo is not None:
            self._repo.record(attempt)
        self._pending_retry = None if correct else problem
        return attempt

    def summary(self) -> SessionSummary:
        """Resumo estatístico de todas as tentativas (inclusive retries)."""
        return summarize(self._attempts)

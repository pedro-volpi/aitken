"""Repintura contínua da linha do cronômetro — a thread que o HUD não tinha.

Historicamente o relógio era repintado apenas a cada prompt: o processo
fica bloqueado dentro de ``input()`` e não há event loop onde um tique
caberia. A pedido explícito do usuário, este módulo introduz a peça que
faltava: uma thread de fundo que, a cada centésimo de segundo, sobrescreve
**somente** a linha do cronômetro, algumas linhas acima do cursor.

O truque que preserva a edição do readline é nunca tocar na linha em que o
usuário digita. Cada repintura é uma única ``write()`` com a sequência
DECSC → sobe N linhas → ``\\r`` + linha nova → DECRC (:func:`overlay`):
o cursor volta exatamente para onde estava e o buffer de edição nunca é
alterado. Como a linha repintada tem sempre a mesma largura (``rjust`` na
largura do HUD), não sobra resíduo de uma pintura anterior.

A thread só pinta enquanto **armada** (:meth:`ClockRefresher.arm`), o que
a UI faz apenas com uma questão na tela e o cronômetro correndo; entre
prompts, durante a pausa e nas escritas de feedback ela fica desarmada, e
o lock garante que uma pintura em andamento termine antes de o desarme
devolver o controle — nenhuma escrita da thread se intercala com as do
loop principal.

O módulo não conhece :class:`~mentat.ui.timer.PracticeTimer` nem formato:
recebe um ``render`` que devolve a linha pronta (já padeada e colorida).
Assim a política de formatação continua inteira em ``plain.py`` e esta
peça fica testável com dublês puros, sem dormir de verdade.
"""

import threading
from collections.abc import Callable
from typing import TextIO

RenderClock = Callable[[], str]
"""Devolve a linha do cronômetro pronta para a tela (padeada e estilizada)."""

REFRESH_INTERVAL = 0.01
"""Período entre repinturas, em segundos — um centésimo, a resolução do ``MM:SS:CC``."""


def overlay(line: str, rows_up: int) -> str:
    """Monta a sequência ANSI que redesenha ``line`` ``rows_up`` linhas acima.

    Uma string única de propósito: emitida em uma só ``write()``, o
    terminal a processa como unidade e o cursor termina onde começou
    (DECSC/DECRC preservam linha, coluna e atributos), sem frame
    intermediário visível.

    Exemplos:
        >>> overlay("00:01:23", rows_up=2) == "\\x1b7\\x1b[2A\\r00:01:23\\x1b8"
        True
    """
    return f"\x1b7\x1b[{rows_up}A\r{line}\x1b8"


class ClockRefresher:
    """Thread de fundo que mantém a linha do cronômetro viva sob ``input()``.

    O ciclo de vida é dirigido pela UI: :meth:`arm` antes de bloquear no
    prompt (informando quantas linhas acima do cursor está o relógio),
    :meth:`disarm` assim que a leitura retorna, :meth:`close` no fim da
    sessão. A thread nasce no primeiro ``arm`` — sessão sem terminal
    interativo nunca chega a criá-la.

    É daemon por segurança (não segura o intérprete se ``close`` não
    rodar), mas ``close`` ainda faz ``join``: o loop acorda a cada
    :data:`REFRESH_INTERVAL`, então o encerramento é limitado por um tique.
    """

    def __init__(
        self, out: TextIO, render: RenderClock, *, interval: float = REFRESH_INTERVAL
    ) -> None:
        """
        Args:
            out: stream onde as repinturas são escritas — o mesmo ``out``
                do ``plain.run``, para que tela e overlay nunca divirjam.
            render: produtor da linha pronta; chamado a cada tique, é ele
                que lê o cronômetro.
            interval: período entre repinturas; injetável para que os
                testes de integração não dependam do valor de produção.
        """
        self._out = out
        self._render = render
        self._interval = interval
        self._lock = threading.Lock()
        self._rows_up: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def arm(self, rows_up: int) -> None:
        """Liga a repintura, com o relógio ``rows_up`` linhas acima do cursor."""
        with self._lock:
            self._rows_up = rows_up
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="clock-refresher", daemon=True)
            self._thread.start()

    def disarm(self) -> None:
        """Desliga a repintura. Ao retornar, nenhuma pintura está em curso."""
        with self._lock:
            self._rows_up = None

    def close(self) -> None:
        """Encerra a thread (se nasceu). Idempotente."""
        self.disarm()
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def paint(self) -> None:
        """Uma repintura, se armado; senão, nada. Público para teste direto."""
        with self._lock:
            if self._rows_up is None:
                return
            self._out.write(overlay(self._render(), self._rows_up))
            self._out.flush()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.paint()

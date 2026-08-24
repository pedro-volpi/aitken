"""Cronômetro de tempo *ativo* de prática — pausável e monotônico.

Antes deste módulo a cronometragem era duas chamadas soltas de
``time.perf_counter()`` dentro de :mod:`mentat.ui.plain`: não havia objeto
que soubesse se a sessão estava correndo nem quanto tempo já havia sido
praticado. :class:`PracticeTimer` é essa peça faltante, e é a **fonte
única de verdade** para as duas perguntas.

O que ele mede não é tempo de parede: é tempo de prática. Um intervalo
pausado simplesmente não existe para o cronômetro, então nem infla a
latência da questão em curso nem contamina a mediana/p90 da sessão ou a
*quality* do SM-2 (:func:`mentat.core.scheduler.quality_from_attempt`).

O relógio é :func:`time.monotonic` — imune a ajuste de fuso, NTP e horário
de verão, que um relógio de calendário sofreria no meio da sessão. Ele é
injetável (parâmetro ``clock``) pelo mesmo motivo que ``rng`` é injetável
em :class:`~mentat.session.drill.DrillSession`: sem isso não há como testar
pausa de forma determinística a não ser dormindo de verdade.

Mora em ``ui/`` porque é lá que o projeto permite importar ``time`` —
``core/`` e ``session/`` são deliberadamente livres de relógio.
"""

import time
from collections.abc import Callable

Clock = Callable[[], float]
"""Fonte de tempo em segundos, monotônica. Só a diferença entre duas leituras importa."""


class PracticeTimer:
    """Acumula tempo ativo de prática, com pausa e retomada.

    Nasce **rodando**: uma sessão começa a contar no instante em que é
    montada, então um método ``start()`` seria só mais um estado a
    sincronizar.

    O estado é mínimo de propósito — ``_accumulated`` (tempo já fechado) e
    ``_started_at`` (início do trecho corrente, ou ``None`` se pausado).
    Não existe flag ``_paused`` separada: :attr:`running` é derivada de
    ``_started_at``, o que torna impossível os dois discordarem.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        """
        Args:
            clock: fonte de tempo; padrão :func:`time.monotonic`. ``None``
                em vez de default direto para espelhar o idioma de
                :func:`mentat.ui.plain.run`, onde ``None`` significa "use o
                real" e os testes passam um dublê.
        """
        self._clock: Clock = clock if clock is not None else time.monotonic
        self._accumulated = 0.0
        self._started_at: float | None = self._clock()

    @property
    def running(self) -> bool:
        """``True`` enquanto o tempo corre."""
        return self._started_at is not None

    @property
    def elapsed(self) -> float:
        """Segundos de prática ativa desde a criação, descontadas as pausas.

        Único lugar do projeto onde tempo decorrido é calculado — pausado,
        devolve o acumulado congelado; rodando, soma o trecho em aberto.
        Nunca decresce, o que garante que o delta usado como ``elapsed_ms``
        seja não-negativo.
        """
        if self._started_at is None:
            return self._accumulated
        return self._accumulated + (self._clock() - self._started_at)

    def pause(self) -> None:
        """Congela o cronômetro. Idempotente: pausar pausado não faz nada."""
        if self._started_at is None:
            return
        self._accumulated += self._clock() - self._started_at
        self._started_at = None

    def resume(self) -> None:
        """Retoma de onde parou. Idempotente: retomar rodando não faz nada."""
        if self._started_at is None:
            self._started_at = self._clock()

    def toggle(self) -> bool:
        """Alterna pausa/retomada.

        Returns:
            O novo valor de :attr:`running` — ``True`` se voltou a correr.
        """
        if self.running:
            self.pause()
        else:
            self.resume()
        return self.running


def format_elapsed(seconds: float) -> str:
    """Formata uma duração como ``MM:SS:CC`` (``CC`` = centésimos).

    Função livre, não método: formatar é apresentação, e mantê-la fora de
    :class:`PracticeTimer` deixa as duas testáveis em separado.

    Toda a conversão acontece em inteiro, a partir de uma única
    arredondada. Truncar com ``int()`` seria pior que arredondar: em
    binário ``0.29 * 100 == 28.999999999999996``, e ``int`` disso dá ``28``
    — exatamente o artefato de ponto flutuante que não pode vazar para a
    tela. Os ``divmod`` encadeados também garantem que ``CC`` e ``SS``
    nunca cheguem a ``100``/``60``: o transbordo vira minuto.

    Minutos não são truncados em 99 — uma sessão longa mostra ``123:45:67``
    em vez de mentir sobre a duração.

    Exemplos:
        >>> format_elapsed(207.42)
        '03:27:42'
        >>> format_elapsed(59.999)
        '01:00:00'
        >>> format_elapsed(0.29)
        '00:00:29'
    """
    total_centiseconds = round(seconds * 100)
    minutes, rest = divmod(total_centiseconds, 6000)
    secs, centiseconds = divmod(rest, 100)
    return f"{minutes:02d}:{secs:02d}:{centiseconds:02d}"

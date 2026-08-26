"""Adaptador de UI em texto puro (``input()``/``print()``).

Este módulo é um *driver* de :class:`~mentat.session.drill.DrillSession`
que traduz o contrato da sessão em interação de terminal: imprime o
prompt, cronometra a digitação e repassa à sessão.

**Contrato de substituição**: qualquer outra UI (Textual, Qt, web...)
implementa uma função análoga a :func:`run` que consuma a mesma sessão
via iteração + ``record()``. As camadas ``core/``, ``storage/`` e
``session/`` ficam intocadas quando a UI muda.

A cronometragem é delegada inteira a
:class:`~mentat.ui.timer.PracticeTimer`, que mede tempo *ativo* de prática
sobre :func:`time.monotonic`: o que a UI grava em ``elapsed_ms`` é sempre
a diferença entre duas leituras do mesmo cronômetro, então um intervalo
pausado desaparece da latência sem que o caminho de gravação precise saber
que a pausa existe. A resolução do relógio é de microssegundos, mas a
latência efetiva é dominada pelo tempo de digitação e pelo newline do
terminal, da ordem de 50–100 ms. Para drills cuja latência alvo é ≥ 1 s
(toda a tabuada), essa margem é irrelevante.

**Pausa**: em terminal interativo a leitura da resposta não passa mais
pelo ``input()``/readline, e sim pelo leitor cbreak de
:mod:`mentat.ui.reader` — é ele que torna o Ctrl+P
(:data:`~mentat.ui.hotkeys.PAUSE`) uma tecla de verdade, levantando
:class:`~mentat.ui.reader.PauseRequested` no meio da digitação. Fora de
um terminal (testes, pipe), o ``ask`` continua sendo ``input_fn``/
``input()`` e a pausa cai no fallback de linha-sentinela (``p``/``pause``
+ Enter, os ``aliases`` do mesmo :class:`~mentat.ui.hotkeys.Hotkey`).

**Apresentação**: o driver não desenha o problema — pede a um
:class:`~mentat.ui.presenter.Presenter` (``present(problem)``, uma vez
por apresentação, retry incluído) e compõe as linhas devolvidas no
prompt. Trocar tela por voz ou flash anzan é trocar o presenter no ponto
de composição (:mod:`mentat.cli`), sem tocar neste loop.

**Relógio vivo**: o cronômetro do HUD corre continuamente — a cada
centésimo, a :class:`~mentat.ui.refresh.ClockRefresher` sobrescreve
apenas a linha do relógio, acima do cursor, sem tocar na linha de edição
do readline (ver o docstring de ``refresh.py`` para o truque DECSC/DECRC
e as garantias de não-interferência). Ela só existe em terminal
interativo (``styled``): com ``output``/``input_fn`` de teste nada de
thread é criado e o contrato ``input_fn`` segue determinístico.
"""

import builtins
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from mentat.core.problem import Attempt
from mentat.core.stats import SessionSummary
from mentat.session.drill import DrillSession
from mentat.ui import welcome
from mentat.ui.hotkeys import PAUSE
from mentat.ui.presenter import Presenter, VisualPresenter
from mentat.ui.reader import PauseRequested, tty_reader
from mentat.ui.refresh import ClockRefresher
from mentat.ui.style import faint, supports_ansi, terminal_width
from mentat.ui.timer import Clock, PracticeTimer, format_elapsed

InputFn = Callable[[str], str]

_PAUSE_HINT = f"{PAUSE.keys} para retomar: "
"""Linha do cursor enquanto pausado — o prompt em si documenta a saída."""


def run(
    session: DrillSession,
    *,
    output: TextIO | None = None,
    input_fn: InputFn | None = None,
    presenter: Presenter | None = None,
    clock: Clock | None = None,
) -> SessionSummary:
    """Executa uma sessão inteira com I/O em texto e devolve o resumo.

    Args:
        session: sessão a ser executada (já configurada).
        output: stream de saída; padrão ``sys.stdout``. Aceita qualquer
            objeto com ``write`` — útil em testes para capturar output.
        input_fn: callable ``(prompt) -> str`` para leitura; padrão
            ``None``, que resolve para o leitor cbreak de
            :mod:`mentat.ui.reader` quando saída **e** stdin são um
            terminal (é ele que dá o Ctrl+P), e para
            :func:`builtins.input` caso contrário (resolvido em tempo de
            chamada — necessário para que ``patch("builtins.input", ...)``
            em testes tenha efeito).
        presenter: apresentação do problema (ver
            :mod:`mentat.ui.presenter`); padrão ``None`` resolve para
            :class:`~mentat.ui.presenter.VisualPresenter` com o layout
            default (conta armada).
        clock: fonte de tempo do cronômetro; padrão :func:`time.monotonic`.
            Injetável para que o teste de pausa seja determinístico sem
            dormir de verdade — e para que as asserções de prompt exato não
            fiquem à mercê do relógio.

    Returns:
        :class:`SessionSummary` da sessão (mesmo em caso de abandono via
        ``Ctrl-C``/``Ctrl-D`` no meio — o resumo cobre apenas o que foi
        efetivamente respondido).
    """
    out = output if output is not None else sys.stdout
    if presenter is None:
        presenter = VisualPresenter()
    interactive = getattr(out, "isatty", lambda: False)() and sys.stdin.isatty()
    if input_fn is not None:
        ask: InputFn = input_fn
    elif interactive:
        ask = tty_reader(out)
    else:
        ask = builtins.input

    def _print(line: str = "") -> None:
        out.write(line + "\n")
        out.flush()

    # Uma coluna de folga: escrever na última coluna arma o wrap adiado dos
    # terminais com auto-margin, e a margem também evita o contador colado
    # na borda. Largura lida uma vez — redimensionar vale da próxima sessão.
    styled = supports_ansi(out)
    hud_width = max(terminal_width() - 1, 0) if styled else 0
    timer = PracticeTimer(clock)
    refresher = (
        ClockRefresher(
            out,
            lambda: _format_clock(timer.elapsed, running=True, width=hud_width, styled=True),
        )
        if styled
        else None
    )

    total = session.total_problems
    welcome.print_welcome(out)
    _print(f"\nSessão: {total} problemas. Digite o resultado e Enter.")
    _print("Respostas erradas são reapresentadas até serem acertadas.\n")

    try:
        for problem in session:
            pos = session.current_position
            lines = presenter.present(problem)
            started = timer.elapsed
            answer = _ask_active(
                ask,
                timer,
                lines,
                pos,
                total,
                hud_width=hud_width,
                styled=styled,
                refresher=refresher,
            )
            if answer is None:
                _print("\nSessão interrompida.")
                break
            elapsed_ms = int((timer.elapsed - started) * 1000)

            attempt = session.record(problem, answer, elapsed_ms)
            _print(_format_feedback(attempt))
    finally:
        if refresher is not None:
            refresher.close()

    summary = session.summary()
    _print("")
    for line in _format_summary(summary):
        _print(line)
    return summary


def _ask_active(
    ask: InputFn,
    timer: PracticeTimer,
    lines: Sequence[str],
    position: int,
    total: int,
    *,
    hud_width: int,
    styled: bool,
    refresher: ClockRefresher | None = None,
) -> str | None:
    """Lê até vir uma resposta com o cronômetro rodando.

    Concentra aqui o protocolo de pausa para que o laço de :func:`run`
    continue plano e o caminho de gravação siga sem condicional de pausa.
    Cada volta repinta o prompt inteiro — é assim que a troca de estado
    (pausa, retomada, retry) aparece na tela; entre um prompt e outro, a
    ``refresher`` mantém só a linha do relógio viva. As ``lines`` chegam
    prontas do presenter e são **reusadas** nos redesenhos: pausar e
    retomar não re-apresenta o problema (um presenter de voz não deve
    repetir a fala num toggle).

    O arme acontece imediatamente antes do ``ask`` e só com o cronômetro
    correndo (pausado, o relógio está congelado e a repintura seria
    ruído); o desarme fica em ``finally`` para que nenhuma pintura
    concorra com o feedback, com o resumo ou com o próximo prompt — nem
    sobreviva a um ``Ctrl-C``. O relógio está sempre a
    ``prompt.count("\\n") - 2`` linhas acima do cursor: o prompt abre com
    ``\\n`` e o contador ocupa a linha seguinte, então descontadas essas
    duas quebras restam exatamente as linhas entre o relógio e a linha de
    edição.

    Pausado, só o comando de pausa é aceito: responder com o relógio parado
    inflaria a estatística ao contrário, já que o tempo de raciocínio teria
    ficado de fora da medição.

    A pausa chega por dois caminhos que convergem no mesmo ``toggle``: o
    Ctrl+P do leitor cbreak (:class:`PauseRequested`, terminal interativo)
    e a linha-sentinela dos ``aliases`` de :data:`PAUSE` (fallback de
    ``input()``/testes).

    Returns:
        A linha digitada, ou ``None`` se o usuário abandonou a sessão.
    """
    while True:
        prompt = _format_prompt(
            lines,
            position,
            total,
            timer.elapsed,
            running=timer.running,
            hud_width=hud_width,
            styled=styled,
        )
        if refresher is not None and timer.running:
            refresher.arm(rows_up=prompt.count("\n") - 2)
        try:
            entry = ask(prompt)
        except PauseRequested:
            timer.toggle()
            continue
        except EOFError, KeyboardInterrupt:
            return None
        finally:
            if refresher is not None:
                refresher.disarm()
        if entry.strip().lower() in PAUSE.aliases:
            timer.toggle()
        elif timer.running:
            return entry


def _format_prompt(
    lines: Sequence[str],
    position: int,
    total: int,
    elapsed: float,
    *,
    running: bool = True,
    hud_width: int = 0,
    styled: bool = False,
) -> str:
    """Monta a string que o usuário vê e sob a qual digita a resposta.

    O bloco inteiro vai como argumento único de ``ask()``: :func:`input`
    aceita prompt multilinha, imprime tudo e lê na última linha. Manter isso
    em uma só chamada preserva a cronometragem (um começo, um fim) e o
    contrato de que ``input_fn`` recebe exatamente o que foi apresentado.

    O contador ocupa **sempre** uma linha só sua, nos dois layouts, com o
    cronômetro logo abaixo, e uma linha em branco separa do feedback do
    problema anterior. Conta armada::

        <blank>
                                                      [3/30]
                                                    03:27:42
          17
        × 86
        =

    Desenho de uma linha (``--layout horizontal``, ou termo atômico como
    ``13²`` mesmo no vertical) — o cabeçalho continua acima, a conta segue
    compacta::

        <blank>
                                                      [3/30]
                                                    03:27:42
        17 × 86 =

    Pausado, a conta **some** e sobra o cabeçalho com o tempo congelado::

        <blank>
                                                      [3/30]
                                           03:27:42 [PAUSADO]
        Ctrl+P para retomar:

    Esconder o problema não é enfeite: com ele na tela dava para pausar,
    resolver sem pressão e retomar, produzindo um ``elapsed_ms`` baixo que
    envenenaria a mediana da sessão e a *quality* do SM-2. É a mesma
    política do feedback que nunca revela a resposta certa.

    Ter o cabeçalho fora da linha do cursor não é só estética: tanto o
    fallback ``input()``/readline (que mede a largura do prompt a partir
    do último ``\\n``) quanto o eco manual do leitor cbreak assumem que a
    linha de edição não carrega escape ANSI — os escapes do
    :func:`_format_hud` e do :func:`_format_clock` ficam em linhas
    anteriores e não descontam colunas da edição da resposta. Na conta
    armada isso também evita desalinhar as colunas dos operandos.

    Args:
        lines: resíduo visual do presenter (``present(problem)``), já
            desenhado. Pode ser vazio — apresentação não-visual (voz)
            deixa só o cabeçalho e o ``= `` de resposta.
        elapsed: segundos de prática ativa a exibir. Recebe o número, não o
            cronômetro — a formatação continua pura e testável sozinha.
        running: ``False`` desenha a variante pausada.
        hud_width: largura em que o cabeçalho é alinhado à direita. ``0``
            (default) deixa na margem esquerda, sem padding.
        styled: se o cabeçalho sai apagado (ANSI) ou cru.
    """
    hud = _format_hud(position, total, width=hud_width, styled=styled)
    clock = _format_clock(elapsed, running=running, width=hud_width, styled=styled)
    header = f"\n{hud}\n{clock}"
    if not running:
        return f"{header}\n{_PAUSE_HINT}"
    if not lines:
        return f"{header}\n= "
    if len(lines) == 1:
        return f"{header}\n{lines[0]} = "
    block = "\n".join(lines)
    return f"{header}\n{block}\n= "


def _format_hud(position: int, total: int, *, width: int, styled: bool) -> str:
    """Formata o contador de posição como cromo periférico.

    O ``rjust`` acontece **antes** do :func:`~mentat.ui.style.faint`: os
    escapes ANSI não ocupam coluna nenhuma na tela, mas contam em ``len()``,
    então padear o texto já colorido empurraria o contador para longe da
    borda direita.

    Exemplos:
        >>> _format_hud(3, 30, width=0, styled=False)
        '[3/30]'
        >>> _format_hud(3, 30, width=10, styled=False)
        '    [3/30]'
    """
    hud = f"[{position}/{total}]".rjust(width)
    return faint(hud) if styled else hud


def _format_clock(elapsed: float, *, running: bool, width: int, styled: bool) -> str:
    """Formata a linha do cronômetro, logo abaixo do contador.

    Rodando, é cromo periférico como o contador e sai apagado. Pausado,
    sai em ênfase normal: o contraste com a linha que estava apagada torna
    o estado imediatamente óbvio. Ainda assim nenhuma informação está na
    cor — ``[PAUSADO]`` é literal, e a saída crua não perde nada.

    Mesmo cuidado do :func:`_format_hud`: padear antes de colorir.

    Exemplos:
        >>> _format_clock(207.42, running=True, width=0, styled=False)
        '03:27:42'
        >>> _format_clock(207.42, running=False, width=0, styled=False)
        '03:27:42 [PAUSADO]'
    """
    text = format_elapsed(elapsed)
    if not running:
        text = f"{text} [PAUSADO]"
    padded = text.rjust(width)
    if not styled or not running:
        return padded
    return faint(padded)


def _format_feedback(attempt: Attempt) -> str:
    """Formata uma linha de feedback após uma resposta.

    Em caso de erro, a resposta correta NÃO é revelada — a UI apenas
    confirma o erro e ecoa a entrada do usuário. O próximo ciclo do loop
    reapresenta o mesmo problema (política retry-on-wrong da sessão).
    """
    secs = attempt.elapsed_ms / 1000
    if attempt.correct:
        return f"  ok  ({secs:.2f}s)"
    return f"  x   errado (sua: {attempt.user_answer!r}, {secs:.2f}s)"


def _format_summary(summary: SessionSummary) -> list[str]:
    """Formata o bloco de resumo final."""
    lines = ["-- Resumo --"]
    if summary.total == 0:
        lines.append("Nenhum problema respondido.")
        return lines
    pct = summary.accuracy * 100
    lines.append(f"Acertos:          {summary.correct}/{summary.total} ({pct:.0f}%)")
    lines.append(f"Latência mediana: {summary.median_ms / 1000:.2f}s")
    if summary.p90_ms is not None:
        lines.append(f"Latência p90:     {summary.p90_ms / 1000:.2f}s")
    if summary.slowest is not None:
        prompt, ms = summary.slowest
        lines.append(f"Mais lento:       {prompt} em {ms / 1000:.2f}s")
    return lines

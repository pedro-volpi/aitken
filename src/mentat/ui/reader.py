"""Leitor de linha em modo cbreak — o Ctrl+P que o readline não dava.

O ``input()`` clássico deixa o terminal em modo canônico e entrega a linha
inteira ao readline, que engole cada tecla até o Enter: não existe tecla
solta para um atalho de pausa. Sob GNU readline daria para trapacear com
uma macro; o Python deste projeto usa **libedit**, cujas macros ``bind -s``
inserem texto mas não disparam o accept-line — testado sob pty com
``\\n``, ``\\r``, ``^J`` e ``^M``, nenhum fecha a linha. A pedido explícito
do usuário (2026-08-26), este módulo substitui o readline na leitura da
resposta em terminal interativo por um leitor próprio, tecla a tecla.

O modo é **cbreak**, não raw: ``tty.setcbreak`` desliga só ``ICANON`` e
``ECHO``, mantendo ``ISIG`` — Ctrl+C continua virando ``SIGINT`` (e
portanto ``KeyboardInterrupt``) sem tratamento nenhum aqui. O estado do
terminal é salvo antes e restaurado em ``finally``, inclusive quando a
leitura termina por exceção.

A máquina de teclas (:func:`read_line`) é separada do acesso ao terminal
(:func:`tty_reader`) exatamente como ``PracticeTimer`` separa contagem de
relógio: os testes exercitam a máquina com um stream de teclas fake, sem
pty, e o termios fica confinado a um embrulho fino. Edição além de
backspace não existe de propósito — as respostas são números curtos, e
setas/histórico eram peso morto do readline aqui.
"""

import contextlib
import sys
import termios
import tty
from collections.abc import Callable, Iterator
from typing import TextIO

from mentat.ui.hotkeys import PAUSE

ReadKey = Callable[[], str]
"""Devolve a próxima tecla como string de um caractere; ``""`` no fim do stream."""

_ENTER = frozenset({"\r", "\n"})
_BACKSPACE = frozenset({"\x7f", "\x08"})
_CTRL_D = "\x04"
_ESC = "\x1b"


class PauseRequested(Exception):
    """O usuário pediu pausa no meio da leitura; o buffer digitado foi descartado."""


def read_line(out: TextIO, read_key: ReadKey, *, pause_char: str | None = None) -> str:
    """Lê uma linha tecla a tecla, com eco manual e o atalho de pausa vivo.

    Pressupõe o terminal já em cbreak (eco desligado) — quem garante isso é
    :func:`tty_reader`; nos testes, o stream fake torna o pressuposto
    irrelevante.

    Args:
        out: destino do eco (mesmo stream do prompt).
        read_key: fonte de teclas, uma por chamada.
        pause_char: caractere que dispara a pausa; default
            :data:`~mentat.ui.hotkeys.PAUSE` (``\\x10``, Ctrl+P).

    Returns:
        A linha digitada, sem o Enter.

    Raises:
        PauseRequested: ao receber ``pause_char``. O que já tinha sido
            digitado é descartado — o prompt será redesenhado inteiro na
            retomada, então manter meio buffer só confundiria.
        EOFError: Ctrl+D em linha vazia, ou fim do stream de teclas.
    """
    pause = pause_char if pause_char is not None else PAUSE.char
    buffer: list[str] = []
    while True:
        key = read_key()
        if key == "":
            raise EOFError
        if key in _ENTER:
            out.write("\n")
            out.flush()
            return "".join(buffer)
        if key == pause:
            out.write("\n")
            out.flush()
            raise PauseRequested
        if key == _CTRL_D:
            if not buffer:
                raise EOFError
        elif key in _BACKSPACE:
            if buffer:
                buffer.pop()
                out.write("\b \b")
                out.flush()
        elif key == _ESC:
            _swallow_escape(read_key)
        elif key.isprintable():
            buffer.append(key)
            out.write(key)
            out.flush()


def _swallow_escape(read_key: ReadKey) -> None:
    """Consome uma sequência de escape (seta, F-key) sem ecoar nada.

    CSI (``ESC [``) e SS3 (``ESC O``) são lidas até o byte final (faixa
    ``@``–``~``); qualquer outro ``ESC`` + tecla é descartado como par.
    Deixar a sequência vazar para o buffer ecoaria lixo no meio da resposta.
    """
    key = read_key()
    if key not in {"[", "O"}:
        return
    while True:
        key = read_key()
        if key == "" or "@" <= key <= "~":
            return


@contextlib.contextmanager
def _cbreak(fd: int) -> Iterator[None]:
    """Coloca ``fd`` em cbreak e restaura o estado original ao sair, sempre."""
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def tty_reader(out: TextIO) -> Callable[[str], str]:
    """Cria o substituto de ``input()`` para terminal interativo.

    O callable devolvido tem o mesmo contrato do ``ask`` de
    :func:`mentat.ui.plain.run` — recebe o prompt inteiro, devolve a linha —
    mas entra em cbreak só durante a leitura e reconhece o Ctrl+P.
    """
    stdin = sys.stdin
    fd = stdin.fileno()

    def ask(prompt: str) -> str:
        out.write(prompt)
        out.flush()
        with _cbreak(fd):
            return read_line(out, lambda: stdin.read(1))

    return ask

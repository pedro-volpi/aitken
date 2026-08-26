"""Testes do leitor cbreak (``ui/reader.py``).

A máquina de teclas é exercitada com um stream fake, sem pty nem termios:
``read_line`` recebe ``read_key`` injetado e o eco vai para um
``StringIO``. O acesso real ao terminal fica confinado a ``tty_reader`` e
``_cbreak``, embrulhos finos sem lógica própria.
"""

import io

import pytest

from mentat.ui.reader import PauseRequested, read_line


def _keys(sequence: str) -> tuple[io.StringIO, list[str]]:
    """Monta o par (eco, fila de teclas) para um cenário."""
    return io.StringIO(), list(sequence)


def _pop(queue: list[str]) -> str:
    return queue.pop(0) if queue else ""


def test_types_and_enter_returns_the_line() -> None:
    echo, queue = _keys("42\r")
    assert read_line(echo, lambda: _pop(queue)) == "42"
    assert echo.getvalue() == "42\n"


def test_newline_also_accepts_the_line() -> None:
    echo, queue = _keys("7\n")
    assert read_line(echo, lambda: _pop(queue)) == "7"


def test_backspace_erases_from_buffer_and_screen() -> None:
    echo, queue = _keys("49\x7f\x7f36\r")
    assert read_line(echo, lambda: _pop(queue)) == "36"
    assert echo.getvalue() == "49\b \b\b \b36\n"


def test_backspace_on_empty_buffer_does_nothing() -> None:
    echo, queue = _keys("\x7f5\r")
    assert read_line(echo, lambda: _pop(queue)) == "5"
    assert echo.getvalue() == "5\n"


def test_ctrl_p_raises_pause_and_discards_the_buffer() -> None:
    """O que já foi digitado morre com a pausa — o prompt volta inteiro."""
    echo, queue = _keys("12\x10")
    with pytest.raises(PauseRequested):
        read_line(echo, lambda: _pop(queue))
    assert echo.getvalue().endswith("\n")


def test_ctrl_d_on_empty_line_is_eof() -> None:
    echo, queue = _keys("\x04")
    with pytest.raises(EOFError):
        read_line(echo, lambda: _pop(queue))


def test_ctrl_d_mid_line_is_ignored() -> None:
    """Como no shell: EOF só vale em linha vazia."""
    echo, queue = _keys("8\x04\r")
    assert read_line(echo, lambda: _pop(queue)) == "8"


def test_exhausted_stream_is_eof() -> None:
    echo, queue = _keys("")
    with pytest.raises(EOFError):
        read_line(echo, lambda: _pop(queue))


def test_arrow_keys_are_swallowed_without_echo() -> None:
    """CSI (``ESC [ A``) some inteira: nem buffer nem eco."""
    echo, queue = _keys("\x1b[A\x1b[3~9\r")
    assert read_line(echo, lambda: _pop(queue)) == "9"
    assert echo.getvalue() == "9\n"


def test_lone_escape_pair_is_discarded() -> None:
    """``ESC`` + tecla comum é descartado como par (meta-x de terminal)."""
    echo, queue = _keys("\x1bx3\r")
    assert read_line(echo, lambda: _pop(queue)) == "3"


def test_custom_pause_char_is_honored() -> None:
    echo, queue = _keys("\x14")
    with pytest.raises(PauseRequested):
        read_line(echo, lambda: _pop(queue), pause_char="\x14")


def test_other_control_chars_are_ignored() -> None:
    echo, queue = _keys("\x016\r")
    assert read_line(echo, lambda: _pop(queue)) == "6"
    assert echo.getvalue() == "6\n"

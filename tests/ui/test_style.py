"""Testes do único módulo que emite ANSI.

As três funções são puras o bastante para serem testadas sem terminal:
:func:`faint` não decide nada (só envolve), e :func:`supports_ansi` recebe
o stream como argumento em vez de olhar ``sys.stdout``.
"""

import io
from typing import TextIO, cast

import pytest

from mentat.ui.style import FAINT, RESET, faint, supports_ansi, terminal_width


class _FakeTty(io.StringIO):
    """Buffer que se declara terminal interativo."""

    def isatty(self) -> bool:
        return True


class _NoIsatty:
    """Dublê mínimo de stream: tem ``write``, não tem ``isatty``.

    A UI aceita qualquer objeto com ``write``, então ``supports_ansi`` não
    pode assumir que o método existe.
    """

    def write(self, text: str) -> int:
        return len(text)


def test_faint_wraps_without_asking_anything() -> None:
    assert faint("[3/30]") == f"{FAINT}[3/30]{RESET}"


def test_supports_ansi_is_false_for_a_plain_buffer() -> None:
    assert supports_ansi(io.StringIO()) is False


def test_supports_ansi_is_true_for_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert supports_ansi(_FakeTty()) is True


def test_no_color_wins_over_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_ansi(_FakeTty()) is False


def test_supports_ansi_tolerates_a_stream_without_isatty() -> None:
    assert supports_ansi(cast(TextIO, _NoIsatty())) is False


def test_terminal_width_falls_back_when_there_is_no_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``COLUMNS`` tem prioridade em ``get_terminal_size``; sem ele, o fallback."""
    monkeypatch.setenv("COLUMNS", "123")
    assert terminal_width() == 123

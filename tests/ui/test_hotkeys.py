"""Testes da fonte única de atalhos (``ui/hotkeys.py``)."""

import dataclasses

import pytest

from mentat.ui.hotkeys import ABANDON, HOTKEYS, PAUSE


def test_pause_binds_ctrl_p_and_sentinel_aliases() -> None:
    """As duas encarnações da pausa saem do mesmo registro."""
    assert PAUSE.char == "\x10"
    assert PAUSE.aliases == frozenset({"p", "pause"})
    assert PAUSE.keys == "Ctrl+P"


def test_abandon_has_no_capture_char() -> None:
    """Ctrl+C/Ctrl+D chegam por sinal/EOF, não pelo dicionário de captura."""
    assert ABANDON.char is None
    assert ABANDON.aliases == frozenset()


def test_hotkeys_lists_pause_and_abandon() -> None:
    assert HOTKEYS == (PAUSE, ABANDON)


def test_hotkey_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        PAUSE.keys = "Ctrl+Q"  # type: ignore[misc]

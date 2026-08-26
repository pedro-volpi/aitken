"""Testes da saudação (``ui/welcome.py``).

O banner figlet é cromo condicional (só tty) e não é testado aqui; o
contrato testável é a lista de atalhos: sempre presente, e derivada da
lista canônica em vez de literais duplicados.
"""

import io

from mentat.ui.hotkeys import HOTKEYS
from mentat.ui.welcome import hotkey_lines, print_welcome


def test_hotkey_lines_cover_every_canonical_hotkey() -> None:
    """Dirigido pelos dados: cada Hotkey aparece com keys e description."""
    lines = hotkey_lines()
    assert len(lines) == len(HOTKEYS)
    for hotkey, line in zip(HOTKEYS, lines, strict=True):
        assert hotkey.keys in line
        assert hotkey.description in line


def test_hotkey_lines_align_the_description_column() -> None:
    starts = {
        line.index(hotkey.description) for hotkey, line in zip(HOTKEYS, hotkey_lines(), strict=True)
    }
    assert len(starts) == 1


def test_print_welcome_without_tty_prints_only_the_plain_list() -> None:
    """Sem terminal: nada de figlet nem ANSI, mas a lista sai inteira."""
    buf = io.StringIO()
    print_welcome(buf)
    output = buf.getvalue()
    assert "\x1b" not in output
    for hotkey in HOTKEYS:
        assert hotkey.keys in output
        assert hotkey.description in output

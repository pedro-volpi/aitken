"""Saudação da sessão — o nome do programa em ASCII art e a interface.

Módulo autocontido de propósito: não conhece sessão, timer nem driver. A
única coisa que ele puxa de fora é a lista canônica de atalhos
(:data:`~mentat.ui.hotkeys.HOTKEYS`) — a saudação *representa* os
bindings, nunca os define, então o que aparece na tela e o que o leitor de
teclas captura não têm como divergir.

O banner segue a receita (e a cadeia de degradação) do ``mac-awake`` dos
dotfiles do usuário: ``figlet`` pelo desenho, ``lolcat -f`` pela cor —
``-f`` porque a saída é capturada, e sem ele o lolcat detecta o pipe e
despe os escapes. Sem figlet, ou fora de um terminal interativo, o desenho
simplesmente não sai: ele é puro cromo e pode falhar em silêncio. A lista
de atalhos em texto puro, ao contrário, sai **sempre** — ela é a fonte
canônica (e testada) da interface. lolcat só entra sob
:func:`~mentat.ui.style.supports_ansi`; em particular, ``NO_COLOR`` mantém
o desenho e descarta a cor, como manda a convenção.
"""

import contextlib
import shutil
import subprocess
from typing import TextIO

from mentat.ui.hotkeys import HOTKEYS
from mentat.ui.style import supports_ansi, terminal_width

_BANNER_TEXT = "MENTAT"
"""O que o figlet desenha: o nome do programa, não um atalho."""


def print_welcome(out: TextIO) -> None:
    """Estampa o banner MENTAT (quando possível) e a lista de atalhos (sempre)."""
    _print_banner(out)
    for line in hotkey_lines():
        out.write(line + "\n")
    out.flush()


def hotkey_lines() -> list[str]:
    """Formata :data:`HOTKEYS` como tabela de duas colunas alinhadas.

    Função separada (e pura) para que o teste prove a fonte única: cada
    atalho da lista canônica aparece com ``keys`` e ``description``, sem
    nenhum literal duplicado aqui.

    Exemplos:
        >>> any("Ctrl+P" in line for line in hotkey_lines())
        True
    """
    width = max(len(hotkey.keys) for hotkey in HOTKEYS)
    return [f"  {hotkey.keys.ljust(width)}   {hotkey.description}" for hotkey in HOTKEYS]


def _print_banner(out: TextIO) -> None:
    """Desenha ``MENTAT`` via figlet + lolcat, falhando em silêncio."""
    if not getattr(out, "isatty", lambda: False)():
        return
    figlet = shutil.which("figlet")
    if figlet is None:
        return
    try:
        art = subprocess.run(
            [figlet, "-w", str(terminal_width()), _BANNER_TEXT],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return
    lolcat = shutil.which("lolcat") if supports_ansi(out) else None
    if lolcat is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            art = subprocess.run(
                [lolcat, "-f"],
                input=art,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
    out.write(art)
    out.flush()

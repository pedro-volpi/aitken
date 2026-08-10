"""Estilo de terminal — o único lugar do projeto que emite ANSI.

Escopo deliberadamente mínimo: o projeto não usa cor para *informar* nada,
apenas para tirar ênfase do cromo periférico (hoje, o contador de posição
do drill). Por isso não há paleta, nem tema, nem dependência de ``rich`` —
duas constantes e três funções puras bastam.

A escolha do SGR *faint* (``2``) em vez de bright black (``90``) é
proposital: ``faint`` não fixa uma cor, então funciona igual em tema claro
e escuro, e terminais que não o implementam mostram texto normal em vez de
um cinza que pode sumir no fundo.

Emitir escapes é decidido por :func:`supports_ansi`, nunca assumido: saída
redirecionada para arquivo ou pipe recebe texto cru, e ``NO_COLOR`` no
ambiente desliga tudo (convenção de https://no-color.org).
"""

import os
import shutil
from typing import TextIO

FAINT = "\x1b[2m"
"""Início de trecho apagado (SGR 2)."""

RESET = "\x1b[0m"
"""Fim de trecho apagado (SGR 0 — reseta todos os atributos)."""


def faint(text: str) -> str:
    """Envolve ``text`` nos escapes de baixa ênfase.

    Não checa nada: quem decide *se* deve haver cor é o chamador, via
    :func:`supports_ansi`. Manter as duas responsabilidades separadas é o
    que permite testar a formatação sem simular um terminal.

    Exemplos:
        >>> faint("[3/30]") == "\\x1b[2m[3/30]\\x1b[0m"
        True
    """
    return f"{FAINT}{text}{RESET}"


def supports_ansi(stream: TextIO) -> bool:
    """Diz se vale emitir escapes ANSI em ``stream``.

    Args:
        stream: destino da escrita. ``getattr`` em vez de ``stream.isatty()``
            direto porque a UI aceita qualquer objeto com ``write`` — um
            ``StringIO`` de teste tem ``isatty``, mas um dublê mínimo pode
            não ter.

    Returns:
        ``True`` só quando o destino é um terminal interativo e ``NO_COLOR``
        não está no ambiente.
    """
    if os.environ.get("NO_COLOR"):
        return False
    return getattr(stream, "isatty", lambda: False)()


def terminal_width(fallback: int = 80) -> int:
    """Largura do terminal em colunas, com fallback para saída não-tty."""
    return shutil.get_terminal_size(fallback=(fallback, 24)).columns

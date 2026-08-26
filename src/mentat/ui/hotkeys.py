"""Fonte única dos atalhos de teclado da UI.

Cada binding do projeto mora aqui uma vez, como dado puro: o leitor de
teclas (:mod:`mentat.ui.reader`) consome ``char`` e ``aliases`` para
reconhecer o atalho, e a saudação (:mod:`mentat.ui.welcome`) consome
``keys`` e ``description`` para apresentá-lo. Nenhum dos dois hardcoda o
binding — mudar um atalho é editar uma linha deste módulo, e captura e
documentação mudam juntas, sem chance de divergir.

:class:`Hotkey` é deliberadamente burro: sem método de render, sem I/O.
Representar a lista é decisão de apresentação e pertence a quem apresenta;
aqui ficam só os fatos.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Hotkey:
    """Um atalho da interface, nas suas duas encarnações: captura e ajuda."""

    keys: str
    """Forma exibida ao usuário (``"Ctrl+P"``, ``"Ctrl+C / Ctrl+D"``)."""

    description: str
    """O que o atalho faz, em uma frase curta sem ponto final."""

    char: str | None = None
    """Caractere de controle que o leitor cbreak captura (``"\\x10"``), ou
    ``None`` para atalhos que o terminal entrega por outra via (sinais)."""

    aliases: frozenset[str] = frozenset()
    """Linhas-sentinela aceitas como fallback quando não há leitor cbreak
    (saída não interativa, ``input_fn`` de teste). Vazio = sem fallback."""


PAUSE = Hotkey(
    keys="Ctrl+P",
    description="pausa e retoma o cronômetro",
    char="\x10",
    aliases=frozenset({"p", "pause"}),
)
"""Alterna a pausa. ``\\x10`` é o byte que o terminal emite para Ctrl+P."""

ABANDON = Hotkey(
    keys="Ctrl+C / Ctrl+D",
    description="abandona a sessão",
)
"""Encerra a sessão. Sem ``char``: Ctrl+C chega como ``SIGINT`` (ISIG fica
ligado no cbreak) e Ctrl+D é tratado pelo leitor como EOF — nenhum dos
dois passa pelo dicionário de captura."""

HOTKEYS: tuple[Hotkey, ...] = (PAUSE, ABANDON)
"""Todos os atalhos da interface, na ordem em que a saudação os lista."""

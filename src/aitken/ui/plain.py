"""Adaptador de UI em texto puro (``input()``/``print()``).

Este módulo é um *driver* de :class:`~aitken.session.drill.DrillSession`
que traduz o contrato da sessão em interação de terminal: imprime o
prompt, cronometra a digitação e repassa à sessão.

**Contrato de substituição**: qualquer outra UI (Textual, Qt, web...)
implementa uma função análoga a :func:`run` que consuma a mesma sessão
via iteração + ``record()``. As camadas ``core/``, ``storage/`` e
``session/`` ficam intocadas quando a UI muda.

A cronometragem usa :func:`time.perf_counter` (monotônico, alta
resolução) — precisão de microssegundos no relógio, mas a latência
efetiva é dominada pelo tempo de digitação e pelo newline do terminal,
da ordem de 50–100 ms. Para drills cuja latência alvo é ≥ 1 s (toda a
tabuada), essa margem é irrelevante.
"""

import builtins
import sys
import time
from collections.abc import Callable
from typing import TextIO

from aitken.core.problem import Attempt
from aitken.core.stats import SessionSummary
from aitken.session.drill import DrillSession

InputFn = Callable[[str], str]


def run(
    session: DrillSession,
    *,
    output: TextIO | None = None,
    input_fn: InputFn | None = None,
) -> SessionSummary:
    """Executa uma sessão inteira com I/O em texto e devolve o resumo.

    Args:
        session: sessão a ser executada (já configurada).
        output: stream de saída; padrão ``sys.stdout``. Aceita qualquer
            objeto com ``write`` — útil em testes para capturar output.
        input_fn: callable ``(prompt) -> str`` para leitura; padrão
            ``None`` (resolve para :func:`builtins.input` em tempo de
            chamada — necessário para que ``patch("builtins.input", ...)``
            em testes tenha efeito).

    Returns:
        :class:`SessionSummary` da sessão (mesmo em caso de abandono via
        ``Ctrl-C``/``Ctrl-D`` no meio — o resumo cobre apenas o que foi
        efetivamente respondido).
    """
    out = output if output is not None else sys.stdout
    ask: InputFn = input_fn if input_fn is not None else builtins.input

    def _print(line: str = "") -> None:
        out.write(line + "\n")
        out.flush()

    total = session.total_problems
    _print(f"\nSessão: {total} problemas. Digite o resultado e Enter.")
    _print("Ctrl-C ou Ctrl-D para abandonar.\n")

    for i, problem in enumerate(session, start=1):
        prompt = f"[{i}/{total}]  {problem.prompt} = "
        start = time.perf_counter()
        try:
            answer = ask(prompt)
        except EOFError, KeyboardInterrupt:
            _print("\nSessão interrompida.")
            break
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        attempt = session.record(problem, answer, elapsed_ms)
        _print(_format_feedback(attempt))

    summary = session.summary()
    _print("")
    for line in _format_summary(summary):
        _print(line)
    return summary


def _format_feedback(attempt: Attempt) -> str:
    """Formata uma linha de feedback após uma resposta."""
    secs = attempt.elapsed_ms / 1000
    if attempt.correct:
        return f"  ok  ({secs:.2f}s)"
    return (
        f"  x   correta: {attempt.problem.expected_answer}  "
        f"(sua: {attempt.user_answer!r}, {secs:.2f}s)"
    )


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

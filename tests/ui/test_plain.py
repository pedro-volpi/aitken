"""Teste de integração do adaptador de UI em texto puro.

Injeta um ``input_fn`` fake para simular o usuário digitando respostas e
um buffer ``io.StringIO`` como ``output`` para capturar o que seria
impresso. Isso valida o contrato ``ui.plain.run`` ↔ ``DrillSession`` sem
precisar de terminal.
"""

import io
from pathlib import Path
from random import Random

from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo
from aitken.ui.plain import run


class _FakeInput:
    """Callable que devolve respostas pré-programadas, em ordem.

    Respostas podem ser strings ou uma ``Exception`` a ser levantada
    (para simular EOF/KeyboardInterrupt).
    """

    def __init__(self, answers: list[str | Exception]) -> None:
        self._answers = list(answers)
        self._prompts_received: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self._prompts_received.append(prompt)
        if not self._answers:
            raise EOFError
        value = self._answers.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    @property
    def prompts(self) -> list[str]:
        return self._prompts_received


def test_run_all_correct(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "ui.db")
    try:
        repo = AttemptRepo(conn)
        session = DrillSession(
            generator=TablesGenerator(TablesParams()),
            repo=repo,
            max_problems=3,
            rng=Random(0),
        )
        # Resolvemos os problemas sem executar ainda: geramos uma sessão
        # paralela com a mesma seed para saber as respostas esperadas.
        preview = DrillSession(
            generator=TablesGenerator(TablesParams()),
            repo=None,
            max_problems=3,
            rng=Random(0),
        )
        correct_answers = [p.expected_answer for p in preview]

        fake = _FakeInput(list(correct_answers))
        buf = io.StringIO()
        summary = run(session, output=buf, input_fn=fake)

        assert summary.total == 3
        assert summary.correct == 3
        assert repo.count() == 3
        # Output contém bloco de resumo.
        text = buf.getvalue()
        assert "Resumo" in text
        assert "3/3" in text
    finally:
        conn.close()


def test_run_mixed_results() -> None:
    preview = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=3,
        rng=Random(1),
    )
    correct_answers = [p.expected_answer for p in preview]
    # Erra o segundo de propósito; depois acerta (retry), depois segue em frente.
    answers: list[str | Exception] = [
        correct_answers[0],
        "999",
        correct_answers[1],
        correct_answers[2],
    ]

    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=3,
        rng=Random(1),
    )
    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=_FakeInput(answers))

    # 4 tentativas registradas (1 errada + 3 corretas), 3 distintos dominados.
    assert summary.total == 4
    assert summary.correct == 3
    assert summary.wrong == 1
    text = buf.getvalue()
    assert "errado" in text  # feedback de erro (sem revelar a resposta)
    assert "correta:" not in text  # a resposta certa nunca é exibida no erro
    assert "ok" in text  # feedback de acerto


def test_run_repeats_problem_until_correct() -> None:
    """A mesma prompt aparece em ciclos sucessivos até a resposta ser aceita."""
    preview = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=1,
        rng=Random(3),
    )
    (only,) = list(preview)

    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=1,
        rng=Random(3),
    )
    fake = _FakeInput(["1", "2", only.expected_answer])
    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=fake)

    # Três tentativas registradas para o mesmo problema.
    assert summary.total == 3
    assert summary.correct == 1
    assert summary.wrong == 2
    # A UI recebeu o mesmo prompt nas três vezes.
    problem_prompts = [p for p in fake.prompts if only.prompt in p]
    assert len(problem_prompts) == 3


def test_run_handles_abort() -> None:
    """EOF no meio da sessão encerra sem exceção e retorna resumo parcial."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=5,
        rng=Random(2),
    )
    # Primeira resposta OK, segunda simula Ctrl-D.
    preview = DrillSession(
        generator=TablesGenerator(TablesParams()),
        repo=None,
        max_problems=5,
        rng=Random(2),
    )
    first = next(iter(preview)).expected_answer
    answers: list[str | Exception] = [first, EOFError()]

    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=_FakeInput(answers))

    # Apenas 1 tentativa registrada (a que veio antes do EOF).
    assert summary.total == 1
    assert summary.correct == 1
    assert "interrompida" in buf.getvalue()

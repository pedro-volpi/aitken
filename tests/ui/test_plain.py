"""Teste de integração do adaptador de UI em texto puro.

Injeta um ``input_fn`` fake para simular o usuário digitando respostas e
um buffer ``io.StringIO`` como ``output`` para capturar o que seria
impresso. Isso valida o contrato ``ui.plain.run`` ↔ ``DrillSession`` sem
precisar de terminal.
"""

import io
import re
from pathlib import Path
from random import Random

from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo
from aitken.ui.plain import run

_PROMPT_RE = re.compile(r"(\d+)\s*×\s*(\d+)")


def _answer_from_prompt(prompt: str) -> str:
    match = _PROMPT_RE.search(prompt)
    assert match is not None, f"não achei 'a × b' em {prompt!r}"
    return str(int(match.group(1)) * int(match.group(2)))


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


class _AutoCorrect:
    """Callable que deriva a resposta correta diretamente da prompt.

    Útil quando SM-2 torna a ordem dos problemas não-previsível a partir
    de uma sessão paralela com a mesma seed.
    """

    def __init__(self) -> None:
        self._prompts_received: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self._prompts_received.append(prompt)
        return _answer_from_prompt(prompt)

    @property
    def prompts(self) -> list[str]:
        return self._prompts_received


def test_run_all_correct(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "ui.db")
    try:
        repo = AttemptRepo(conn)
        session = DrillSession(
            generator=TablesGenerator(TablesParams()),
            attempt_repo=repo,
            schedule_repo=None,
            max_problems=3,
            rng=Random(0),
        )
        buf = io.StringIO()
        summary = run(session, output=buf, input_fn=_AutoCorrect())

        assert summary.total == 3
        assert summary.correct == 3
        assert repo.count() == 3
        text = buf.getvalue()
        assert "Resumo" in text
        assert "3/3" in text
    finally:
        conn.close()


def test_run_mixed_results() -> None:
    """Erra uma vez e depois acerta tudo — usando auto-correct + injeção de erro."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=3,
        rng=Random(1),
    )

    wrong_injected = [False]

    def answer(prompt: str = "") -> str:
        if not wrong_injected[0]:
            wrong_injected[0] = True
            return "999"
        return _answer_from_prompt(prompt)

    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=answer)

    # 4 tentativas (1 errada + 3 corretas), 3 distintos dominados.
    assert summary.total == 4
    assert summary.correct == 3
    assert summary.wrong == 1
    text = buf.getvalue()
    assert "errado" in text  # feedback de erro (sem revelar a resposta)
    assert "correta:" not in text  # a resposta certa nunca é exibida no erro
    assert "ok" in text


def test_run_repeats_problem_until_correct() -> None:
    """A mesma prompt aparece em ciclos sucessivos até a resposta ser aceita."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(3),
    )

    seen_prompt: list[str] = []

    def fake(prompt: str = "") -> str:
        seen_prompt.append(prompt)
        # Duas erradas, depois correta.
        if len(seen_prompt) < 3:
            return "-1"
        return _answer_from_prompt(prompt)

    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=fake)

    assert summary.total == 3
    assert summary.correct == 1
    assert summary.wrong == 2
    # A UI recebeu o mesmo prompt nas três vezes.
    assert len(set(seen_prompt)) == 1


def test_run_handles_abort() -> None:
    """EOF no meio da sessão encerra sem exceção e retorna resumo parcial."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams()),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=5,
        rng=Random(2),
    )

    called = [0]

    def answer(prompt: str = "") -> str:
        called[0] += 1
        if called[0] == 1:
            return _answer_from_prompt(prompt)
        raise EOFError

    buf = io.StringIO()
    summary = run(session, output=buf, input_fn=answer)

    # Apenas 1 tentativa registrada (a que veio antes do EOF).
    assert summary.total == 1
    assert summary.correct == 1
    assert "interrompida" in buf.getvalue()

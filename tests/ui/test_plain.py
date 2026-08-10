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

from aitken.core.expression import BinaryOp, Term
from aitken.core.generators.squares import SquaresGenerator, SquaresParams
from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.core.problem import Problem
from aitken.session.drill import DrillSession
from aitken.storage.db import open_db
from aitken.storage.repositories import AttemptRepo
from aitken.ui.layout import Layout
from aitken.ui.plain import _format_hud, _format_prompt, run
from aitken.ui.style import FAINT, RESET

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


def test_vertical_layout_is_the_default_block() -> None:
    """Sem ``layout=``, a UI arma a conta: contador, operandos alinhados, ``= ``."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )
    fake = _AutoCorrect()
    run(session, output=io.StringIO(), input_fn=fake)

    assert fake.prompts == ["\n[1/1]\n  7\n× 7\n= "]


def test_horizontal_layout_keeps_the_operation_on_one_line() -> None:
    """A conta fica compacta; só o contador ocupa a linha de cima."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )
    fake = _AutoCorrect()
    run(session, output=io.StringIO(), input_fn=fake, layout=Layout.HORIZONTAL)

    assert fake.prompts == ["\n[1/1]\n7 × 7 = "]


def test_vertical_layout_aligns_operands_of_different_widths() -> None:
    """O bloco entregue ao usuário preserva o alinhamento das casas."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=9, max_factor=12)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=6,
        rng=Random(0),
    )
    fake = _AutoCorrect()
    run(session, output=io.StringIO(), input_fn=fake)

    for prompt in fake.prompts:
        left, right = prompt.splitlines()[-3:-1]
        assert len(left) == len(right)
        assert right.startswith("× ")


def test_unary_module_stays_on_one_line_even_in_vertical() -> None:
    """N² não tem forma armada — o bloco degrada para a linha compacta."""
    session = DrillSession(
        generator=SquaresGenerator(SquaresParams(min_base=13, max_base=13)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )
    fake = _FakeInput(["169"])
    run(session, output=io.StringIO(), input_fn=fake, layout=Layout.VERTICAL)

    assert fake.prompts == ["\n[1/1]\n13² = "]


def test_retry_reshows_the_same_block() -> None:
    """Errar reapresenta o bloco idêntico — layout não interfere no retry."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )
    fake = _FakeInput(["1", "49"])
    run(session, output=io.StringIO(), input_fn=fake)

    assert fake.prompts == ["\n[1/1]\n  7\n× 7\n= "] * 2


def test_hud_is_plain_and_flush_left_without_width() -> None:
    """``width=0`` é o caminho não-tty: nenhum padding, nenhum escape."""
    assert _format_hud(3, 30, width=0, styled=False) == "[3/30]"


def test_hud_is_right_aligned_to_the_given_width() -> None:
    assert _format_hud(3, 30, width=20, styled=False) == " " * 14 + "[3/30]"


def test_hud_pads_before_coloring() -> None:
    """Os escapes ficam por fora do padding — largura visível == ``width``.

    Padear a string já colorida contaria os escapes como colunas e jogaria
    o contador para dentro da tela, longe da borda direita.
    """
    hud = _format_hud(3, 30, width=20, styled=True)

    assert hud.startswith(FAINT)
    assert hud.endswith(RESET)
    assert len(hud.removeprefix(FAINT).removesuffix(RESET)) == 20


def test_prompt_keeps_the_operands_flush_left_while_the_hud_goes_right() -> None:
    """Alinhar o contador não pode empurrar a conta armada."""
    problem = Problem("tables", "7x7", BinaryOp("17", "×", "86"), "1462")

    prompt = _format_prompt(problem, 3, 30, Layout.VERTICAL, hud_width=40, styled=False)

    blank, hud, left, right, tail = prompt.splitlines()
    assert blank == ""
    assert hud == "[3/30]".rjust(40)
    assert (left, right, tail) == ("  17", "× 86", "= ")


def test_unary_prompt_also_gets_the_hud_on_its_own_line() -> None:
    problem = Problem("squares", "13", Term("13²"), "169")

    prompt = _format_prompt(problem, 3, 30, Layout.VERTICAL, hud_width=40, styled=False)

    assert prompt == "\n" + "[3/30]".rjust(40) + "\n13² = "


def test_ansi_never_lands_on_the_line_the_user_types_in() -> None:
    """Escape na última linha descontaria colunas do readline na edição."""
    problem = Problem("tables", "7x7", BinaryOp("17", "×", "86"), "1462")

    for layout in Layout:
        prompt = _format_prompt(problem, 3, 30, layout, hud_width=40, styled=True)
        assert "\x1b" not in prompt.splitlines()[-1]


def test_run_writes_no_escapes_when_output_is_not_a_terminal() -> None:
    """``StringIO`` não é tty — a sessão inteira sai crua e sem padding."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )
    fake = _AutoCorrect()
    buf = io.StringIO()
    run(session, output=buf, input_fn=fake)

    assert "\x1b" not in buf.getvalue()
    assert fake.prompts == ["\n[1/1]\n  7\n× 7\n= "]


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

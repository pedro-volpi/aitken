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

from mentat.core.expression import BinaryOp, Term
from mentat.core.generators.squares import SquaresGenerator, SquaresParams
from mentat.core.generators.tables import TablesGenerator, TablesParams
from mentat.core.problem import Problem
from mentat.session.drill import DrillSession
from mentat.storage.db import open_db
from mentat.storage.repositories import AttemptRepo
from mentat.ui.hotkeys import PAUSE
from mentat.ui.layout import Layout, render
from mentat.ui.plain import _format_clock, _format_hud, _format_prompt, run
from mentat.ui.presenter import VisualPresenter
from mentat.ui.reader import PauseRequested
from mentat.ui.style import FAINT, RESET

_PROMPT_RE = re.compile(r"(\d+)\s*×\s*(\d+)")


def _frozen_clock() -> float:
    """Relógio parado — mantém determinística toda asserção de prompt exato.

    Sem isso o cronômetro no cabeçalho faria cada repinte sair diferente e
    os testes de "o retry reapresenta o bloco idêntico" ficariam flaky.
    """
    return 0.0


class _FakeClock:
    """Relógio monotônico que só anda quando o teste manda."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
    summary = run(session, output=buf, input_fn=fake, clock=_frozen_clock)

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
    run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert fake.prompts == ["\n[1/1]\n00:00:00\n  7\n× 7\n= "]


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
    run(
        session,
        output=io.StringIO(),
        input_fn=fake,
        presenter=VisualPresenter(Layout.HORIZONTAL),
        clock=_frozen_clock,
    )

    assert fake.prompts == ["\n[1/1]\n00:00:00\n7 × 7 = "]


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
    run(
        session,
        output=io.StringIO(),
        input_fn=fake,
        presenter=VisualPresenter(Layout.VERTICAL),
        clock=_frozen_clock,
    )

    assert fake.prompts == ["\n[1/1]\n00:00:00\n13² = "]


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
    run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert fake.prompts == ["\n[1/1]\n00:00:00\n  7\n× 7\n= "] * 2


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

    prompt = _format_prompt(
        render(problem.expression, Layout.VERTICAL), 3, 30, 207.42, hud_width=40, styled=False
    )

    blank, hud, clock, left, right, tail = prompt.splitlines()
    assert blank == ""
    assert hud == "[3/30]".rjust(40)
    assert clock == "03:27:42".rjust(40)
    assert (left, right, tail) == ("  17", "× 86", "= ")


def test_unary_prompt_also_gets_the_hud_on_its_own_line() -> None:
    problem = Problem("squares", "13", Term("13²"), "169")

    prompt = _format_prompt(
        render(problem.expression, Layout.VERTICAL), 3, 30, 207.42, hud_width=40, styled=False
    )

    expected_header = "\n" + "[3/30]".rjust(40) + "\n" + "03:27:42".rjust(40)
    assert prompt == expected_header + "\n13² = "


def test_ansi_never_lands_on_the_line_the_user_types_in() -> None:
    """Escape na última linha descontaria colunas do readline na edição."""
    problem = Problem("tables", "7x7", BinaryOp("17", "×", "86"), "1462")

    for layout in Layout:
        for running in (True, False):
            prompt = _format_prompt(
                render(problem.expression, layout),
                3,
                30,
                207.42,
                running=running,
                hud_width=40,
                styled=True,
            )
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
    run(session, output=buf, input_fn=fake, clock=_frozen_clock)

    assert "\x1b" not in buf.getvalue()
    assert fake.prompts == ["\n[1/1]\n00:00:00\n  7\n× 7\n= "]


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


def _single_problem_session() -> DrillSession:
    """Sessão de um problema só, com resposta previsível: ``7 × 7 = 49``."""
    return DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=1,
        rng=Random(0),
    )


def test_greeting_documents_the_pause_binding() -> None:
    """O binding só existe para o usuário se a saudação o anunciar.

    A asserção é dirigida pelo registro canônico (:data:`PAUSE`), não por
    literal: se o atalho mudar em ``hotkeys.py``, a saudação acompanha e o
    teste continua provando a fonte única.
    """
    buf = io.StringIO()
    run(_single_problem_session(), output=buf, input_fn=_FakeInput(["49"]), clock=_frozen_clock)

    greeting = buf.getvalue()
    assert PAUSE.keys in greeting
    assert PAUSE.description in greeting


class _RecordingPresenter:
    """Presenter dublê: linhas fixas, contando quantas vezes apresentou."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.presented: list[str] = []

    def present(self, problem: Problem) -> list[str]:
        self.presented.append(problem.key)
        return self.lines


def test_injected_presenter_lines_reach_the_prompt() -> None:
    """O driver compõe o que o presenter devolver — a costura é plugável."""
    presenter = _RecordingPresenter(["<<sete vezes sete>>"])
    fake = _FakeInput(["49"])
    run(
        _single_problem_session(),
        output=io.StringIO(),
        input_fn=fake,
        presenter=presenter,
        clock=_frozen_clock,
    )

    assert fake.prompts == ["\n[1/1]\n00:00:00\n<<sete vezes sete>> = "]


def test_empty_presenter_lines_leave_header_and_answer_marker_only() -> None:
    """Apresentação não-visual (voz): o prompt é só cabeçalho + ``= ``."""
    presenter = _RecordingPresenter([])
    fake = _FakeInput(["49"])
    run(
        _single_problem_session(),
        output=io.StringIO(),
        input_fn=fake,
        presenter=presenter,
        clock=_frozen_clock,
    )

    assert fake.prompts == ["\n[1/1]\n00:00:00\n= "]


def test_presenter_presents_once_per_showing_including_retry() -> None:
    """Retry re-apresenta (a questão volta); toggle de pausa não re-apresenta."""
    presenter = _RecordingPresenter(["7 × 7"])
    fake = _FakeInput(["1", "p", "p", "49"])
    run(
        _single_problem_session(),
        output=io.StringIO(),
        input_fn=fake,
        presenter=presenter,
        clock=_frozen_clock,
    )

    # Duas apresentações: a original e o retry. As duas voltas de pausa
    # repintaram o prompt sem pedir nova apresentação.
    assert len(presenter.presented) == 2
    assert len(fake.prompts) == 4


def test_pause_requested_from_the_reader_toggles_the_timer() -> None:
    """O Ctrl+P do leitor cbreak converge no mesmo toggle da linha-sentinela."""
    session = _single_problem_session()
    fake = _FakeInput([PauseRequested(), PauseRequested(), "49"])

    summary = run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert summary.total == 1
    assert summary.correct == 1
    # 1º prompt rodando, 2º pausado (a conta some), 3º rodando de novo.
    running, paused, resumed = fake.prompts
    assert "[PAUSADO]" in paused
    assert "7" not in paused.replace("00:00:00", "")
    assert resumed == running


def test_pause_command_is_not_recorded_as_an_attempt() -> None:
    """``p`` alterna o cronômetro; não conta como resposta errada."""
    session = _single_problem_session()
    fake = _FakeInput(["p", "p", "49"])

    summary = run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert summary.total == 1
    assert summary.correct == 1
    assert len(fake.prompts) == 3


def test_pause_command_accepts_the_full_word_and_ignores_case() -> None:
    session = _single_problem_session()
    fake = _FakeInput(["  Pause  ", "P", "49"])

    summary = run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert summary.total == 1
    assert summary.correct == 1


def test_paused_prompt_hides_the_problem_and_marks_the_state() -> None:
    """Pausado sobra o cabeçalho com o tempo congelado — a conta some.

    Deixar o problema na tela permitiria pausar, resolver sem pressão e
    retomar, produzindo um ``elapsed_ms`` que mentiria para a mediana e
    para o SM-2.
    """
    fake = _FakeInput(["p", "p", "49"])
    run(_single_problem_session(), output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    running_before, paused, running_after = fake.prompts
    assert running_before == "\n[1/1]\n00:00:00\n  7\n× 7\n= "
    assert paused == "\n[1/1]\n00:00:00 [PAUSADO]\nCtrl+P para retomar: "
    assert running_after == running_before


def test_answer_typed_while_paused_is_ignored() -> None:
    """Com o relógio parado, só o comando de pausa é aceito."""
    session = _single_problem_session()
    fake = _FakeInput(["p", "49", "p", "49"])

    summary = run(session, output=io.StringIO(), input_fn=fake, clock=_frozen_clock)

    assert summary.total == 1
    assert summary.correct == 1
    assert fake.prompts[1] == fake.prompts[2]  # a resposta ignorada só repintou o prompt


def test_paused_interval_is_excluded_from_the_recorded_latency() -> None:
    """O intervalo pausado não entra no ``elapsed_ms`` gravado.

    Dois segundos pensando, dez minutos longe do terminal, mais um segundo
    para responder: a latência é de três segundos, não de dez minutos.
    """
    session = _single_problem_session()
    clock = _FakeClock()
    entries = ["p", "p", "49"]
    advances = [2.0, 600.0, 1.0]
    calls = [0]

    def answer(prompt: str = "") -> str:
        index = calls[0]
        calls[0] += 1
        clock.advance(advances[index])
        return entries[index]

    run(session, output=io.StringIO(), input_fn=answer, clock=clock)

    assert [a.elapsed_ms for a in session.attempts] == [3000]


def test_elapsed_shown_in_the_hud_skips_the_paused_interval() -> None:
    """O cronômetro do cabeçalho retoma de onde parou, não do relógio de parede."""
    session = DrillSession(
        generator=TablesGenerator(TablesParams(min_factor=7, max_factor=7)),
        attempt_repo=None,
        schedule_repo=None,
        max_problems=2,
        rng=Random(0),
    )
    clock = _FakeClock()
    entries = ["p", "p", "49", "49"]
    advances = [2.0, 600.0, 1.0, 1.0]
    calls = [0]

    def answer(prompt: str = "") -> str:
        index = calls[0]
        calls[0] += 1
        clock.advance(advances[index])
        return entries[index]

    fake_prompts: list[str] = []

    def recording(prompt: str = "") -> str:
        fake_prompts.append(prompt)
        return answer(prompt)

    run(session, output=io.StringIO(), input_fn=recording, clock=clock)

    # Cabeçalho do 2º problema: 3 s de prática ativa, apesar dos 603 s de relógio.
    assert fake_prompts[3].startswith("\n[2/2]\n00:03:00\n")


def test_abort_while_paused_still_ends_the_session() -> None:
    """Ctrl-D pausado abandona como em qualquer outro momento."""
    session = _single_problem_session()
    buf = io.StringIO()

    summary = run(session, output=buf, input_fn=_FakeInput(["p", EOFError()]), clock=_frozen_clock)

    assert summary.total == 0
    assert "interrompida" in buf.getvalue()


def test_clock_is_faint_while_running() -> None:
    """Rodando, o cronômetro é cromo periférico como o contador."""
    clock = _format_clock(207.42, running=True, width=20, styled=True)

    assert clock.startswith(FAINT)
    assert clock.endswith(RESET)
    assert len(clock.removeprefix(FAINT).removesuffix(RESET)) == 20


def test_paused_clock_drops_the_faint_so_the_state_stands_out() -> None:
    """O contraste com a linha apagada torna a pausa óbvia sem codificar cor."""
    clock = _format_clock(207.42, running=False, width=20, styled=True)

    assert "\x1b" not in clock
    assert clock == "03:27:42 [PAUSADO]".rjust(20)


def test_clock_is_plain_and_flush_left_without_width() -> None:
    assert _format_clock(207.42, running=True, width=0, styled=False) == "03:27:42"


def test_non_tty_run_never_engages_the_refresher() -> None:
    """Sem terminal interativo não há thread de repintura nem banner.

    É o que mantém o contrato ``input_fn`` determinístico nos testes: a
    saída capturada não pode conter overlay (DECSC/DECRC) nem ASCII art.
    """
    buf = io.StringIO()
    run(_single_problem_session(), output=buf, input_fn=_FakeInput(["49"]), clock=_frozen_clock)

    assert "\x1b7" not in buf.getvalue()
    assert "\x1b8" not in buf.getvalue()

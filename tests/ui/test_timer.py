"""Testes do cronômetro de tempo ativo de prática.

Nenhum ``sleep``: o relógio é injetado como dublê e avançado à mão, então
os testes de pausa são determinísticos e instantâneos. É exatamente para
isso que :class:`~mentat.ui.timer.PracticeTimer` aceita ``clock``.
"""

from mentat.ui.timer import PracticeTimer, format_elapsed


class _FakeClock:
    """Relógio monotônico controlado pelo teste.

    Avança só quando ``advance`` é chamado — nunca sozinho.
    """

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_timer_starts_running() -> None:
    """A sessão começa a contar assim que o cronômetro é montado."""
    timer = PracticeTimer(_FakeClock())

    assert timer.running is True
    assert timer.elapsed == 0.0


def test_elapsed_grows_while_running() -> None:
    clock = _FakeClock()
    timer = PracticeTimer(clock)

    clock.advance(2.5)

    assert timer.elapsed == 2.5


def test_elapsed_is_frozen_while_paused() -> None:
    """O relógio anda, o tempo de prática não."""
    clock = _FakeClock()
    timer = PracticeTimer(clock)
    clock.advance(3.0)

    timer.pause()
    clock.advance(60.0)

    assert timer.running is False
    assert timer.elapsed == 3.0


def test_resume_does_not_count_the_paused_interval() -> None:
    clock = _FakeClock()
    timer = PracticeTimer(clock)
    clock.advance(3.0)
    timer.pause()
    clock.advance(60.0)  # usuário longe do terminal

    timer.resume()
    clock.advance(1.5)

    assert timer.running is True
    assert timer.elapsed == 4.5


def test_repeated_pause_resume_cycles_accumulate_only_active_time() -> None:
    """Três ciclos: só os trechos ativos entram na soma."""
    clock = _FakeClock()
    timer = PracticeTimer(clock)

    for active, idle in ((1.0, 10.0), (2.0, 20.0), (0.5, 30.0)):
        clock.advance(active)
        timer.pause()
        clock.advance(idle)
        timer.resume()

    assert timer.elapsed == 3.5


def test_pause_is_idempotent() -> None:
    """Pausar pausado não descarta nem duplica o trecho já fechado."""
    clock = _FakeClock()
    timer = PracticeTimer(clock)
    clock.advance(4.0)

    timer.pause()
    clock.advance(5.0)
    timer.pause()

    assert timer.elapsed == 4.0


def test_resume_is_idempotent() -> None:
    """Retomar rodando não reinicia o trecho em aberto."""
    clock = _FakeClock()
    timer = PracticeTimer(clock)
    clock.advance(4.0)

    timer.resume()

    assert timer.running is True
    assert timer.elapsed == 4.0


def test_toggle_alternates_and_reports_the_new_state() -> None:
    timer = PracticeTimer(_FakeClock())

    assert timer.toggle() is False
    assert timer.running is False
    assert timer.toggle() is True
    assert timer.running is True


def test_elapsed_never_decreases_across_a_pause_cycle() -> None:
    """Invariante que sustenta ``elapsed_ms`` não-negativo em ``record()``."""
    clock = _FakeClock()
    timer = PracticeTimer(clock)
    readings = []

    for _ in range(3):
        clock.advance(1.0)
        readings.append(timer.elapsed)
        timer.pause()
        clock.advance(5.0)
        readings.append(timer.elapsed)
        timer.resume()
        readings.append(timer.elapsed)

    assert readings == sorted(readings)


def test_default_clock_is_monotonic() -> None:
    """Sem ``clock``, o cronômetro usa o relógio monotônico real."""
    timer = PracticeTimer()

    assert timer.running is True
    assert timer.elapsed >= 0.0


def test_format_elapsed_zero() -> None:
    assert format_elapsed(0.0) == "00:00:00"


def test_format_elapsed_shows_centiseconds() -> None:
    assert format_elapsed(1.23) == "00:01:23"


def test_format_elapsed_example_from_the_spec() -> None:
    """3 min, 27 s e 42 centésimos."""
    assert format_elapsed(207.42) == "03:27:42"


def test_format_elapsed_rolls_over_to_the_next_second() -> None:
    assert format_elapsed(0.99) == "00:00:99"
    assert format_elapsed(1.0) == "00:01:00"


def test_format_elapsed_rolls_over_to_the_next_minute() -> None:
    assert format_elapsed(59.99) == "00:59:99"
    assert format_elapsed(60.0) == "01:00:00"


def test_format_elapsed_rounds_up_into_the_next_minute() -> None:
    """``59.999`` não pode virar ``00:59:100`` nem ``00:60:00``."""
    assert format_elapsed(59.999) == "01:00:00"


def test_format_elapsed_does_not_leak_binary_float_artifacts() -> None:
    """``0.29 * 100`` é ``28.999999999999996`` — truncar mostraria ``28``."""
    assert format_elapsed(0.29) == "00:00:29"
    assert format_elapsed(0.07) == "00:00:07"
    assert format_elapsed(2.675) == "00:02:68"


def test_format_elapsed_keeps_minutes_past_ninety_nine() -> None:
    """Sessão longa alarga o campo em vez de mentir sobre a duração."""
    assert format_elapsed(6000.0) == "100:00:00"


def test_format_elapsed_pads_every_field_to_two_digits() -> None:
    assert format_elapsed(65.05) == "01:05:05"

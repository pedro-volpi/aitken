"""Testes da repintura contínua do cronômetro (``ui/refresh.py``).

A peça foi desenhada para ser testável sem dormir: ``paint()`` é público e
o teste o chama diretamente com um ``render`` dublê, sem thread nenhuma. A
thread real entra em um único teste de integração, com margens largas.
"""

import io
import time

from mentat.ui.refresh import ClockRefresher, overlay


def test_overlay_saves_moves_paints_and_restores() -> None:
    """A sequência inteira em uma string: DECSC, sobe N, CR, linha, DECRC."""
    assert overlay("00:01:23", rows_up=2) == "\x1b7\x1b[2A\r00:01:23\x1b8"


def test_paint_before_arm_writes_nothing() -> None:
    buf = io.StringIO()
    refresher = ClockRefresher(buf, lambda: "00:00:00")

    refresher.paint()

    assert buf.getvalue() == ""


def test_paint_when_armed_writes_the_overlay_at_the_given_row() -> None:
    buf = io.StringIO()
    refresher = ClockRefresher(buf, lambda: "00:00:42")

    refresher.arm(rows_up=3)
    refresher.paint()
    refresher.close()

    assert buf.getvalue() == overlay("00:00:42", rows_up=3)


def test_disarm_stops_painting() -> None:
    buf = io.StringIO()
    refresher = ClockRefresher(buf, lambda: "00:00:01")

    refresher.arm(rows_up=1)
    refresher.disarm()
    refresher.paint()
    refresher.close()

    assert buf.getvalue() == ""


def test_render_is_read_at_paint_time_not_at_arm_time() -> None:
    """Cada pintura relê o relógio — é isso que faz o cronômetro andar."""
    buf = io.StringIO()
    ticks = iter(["00:00:01", "00:00:02"])
    refresher = ClockRefresher(buf, lambda: next(ticks))

    refresher.arm(rows_up=1)
    refresher.paint()
    refresher.paint()
    refresher.close()

    assert buf.getvalue() == overlay("00:00:01", rows_up=1) + overlay("00:00:02", rows_up=1)


def test_close_is_idempotent_and_safe_without_thread() -> None:
    refresher = ClockRefresher(io.StringIO(), lambda: "00:00:00")

    refresher.close()
    refresher.close()


def test_background_thread_paints_while_armed() -> None:
    """Integração com a thread real: armado, pinta sozinho; fechado, para.

    O deadline de 2 s existe só para não pendurar a suíte se a thread
    quebrar — o caminho feliz sai no primeiro tique (10 ms).
    """
    buf = io.StringIO()
    refresher = ClockRefresher(buf, lambda: "00:00:99")

    refresher.arm(rows_up=1)
    deadline = time.monotonic() + 2.0
    while not buf.getvalue() and time.monotonic() < deadline:
        time.sleep(0.005)
    refresher.close()

    painted = buf.getvalue()
    assert overlay("00:00:99", rows_up=1) in painted
    time.sleep(0.05)
    assert buf.getvalue() == painted

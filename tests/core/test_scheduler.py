"""Testes do scheduler SM-2 ponderado por latência."""

import pytest

from aitken.core.scheduler import (
    Card,
    quality_from_attempt,
    sampling_weight,
    update_card,
    weights_from_cards,
)


def test_default_card() -> None:
    c = Card()
    assert c.ease_factor == 2.5
    assert c.consecutive_correct == 0


def test_update_quality_5_bumps_ef_and_streak() -> None:
    c = update_card(Card(), quality=5)
    assert c.ease_factor > 2.5
    assert c.consecutive_correct == 1


def test_update_quality_4_keeps_ef_bumps_streak() -> None:
    c = update_card(Card(), quality=4)
    # quality 4 → delta = 0.1 - 1*(0.08 + 0.02) = 0
    assert c.ease_factor == pytest.approx(2.5)
    assert c.consecutive_correct == 1


def test_update_quality_3_drops_ef() -> None:
    c = update_card(Card(), quality=3)
    assert c.ease_factor < 2.5
    assert c.consecutive_correct == 1


def test_update_recall_failure_resets_streak() -> None:
    warm = Card(ease_factor=2.7, consecutive_correct=3)
    c = update_card(warm, quality=1)
    assert c.consecutive_correct == 0
    assert c.ease_factor == pytest.approx(2.5)  # -0.2


def test_ease_factor_floor() -> None:
    bad = Card(ease_factor=1.4, consecutive_correct=0)
    c = update_card(bad, quality=0)
    assert c.ease_factor == pytest.approx(1.3)  # clamped


def test_update_rejects_quality_out_of_range() -> None:
    with pytest.raises(ValueError):
        update_card(Card(), quality=-1)
    with pytest.raises(ValueError):
        update_card(Card(), quality=6)


def test_quality_from_attempt_correct_fast() -> None:
    assert quality_from_attempt(correct=True, elapsed_ms=500) == 5


def test_quality_from_attempt_correct_medium() -> None:
    assert quality_from_attempt(correct=True, elapsed_ms=2500) == 4


def test_quality_from_attempt_correct_slow() -> None:
    assert quality_from_attempt(correct=True, elapsed_ms=5000) == 3


def test_quality_from_attempt_correct_very_slow() -> None:
    assert quality_from_attempt(correct=True, elapsed_ms=9000) == 2


def test_quality_from_attempt_wrong() -> None:
    assert quality_from_attempt(correct=False, elapsed_ms=1000) == 1


def test_quality_from_attempt_wrong_and_very_slow() -> None:
    assert quality_from_attempt(correct=False, elapsed_ms=10000) == 0


def test_quality_from_attempt_rejects_negative_elapsed() -> None:
    with pytest.raises(ValueError):
        quality_from_attempt(correct=True, elapsed_ms=-1)


def test_sampling_weight_unseen_is_highest() -> None:
    default = Card()
    assert sampling_weight(None) > sampling_weight(default)


def test_sampling_weight_monotonic_in_ease_factor() -> None:
    easy = Card(ease_factor=3.0, consecutive_correct=0)
    hard = Card(ease_factor=1.5, consecutive_correct=0)
    assert sampling_weight(hard) > sampling_weight(easy)


def test_sampling_weight_dampened_by_streak() -> None:
    cold = Card(ease_factor=2.5, consecutive_correct=0)
    warm = Card(ease_factor=2.5, consecutive_correct=5)
    assert sampling_weight(cold) > sampling_weight(warm)


def test_weights_from_cards_empty() -> None:
    assert weights_from_cards({}) == {}


def test_weights_from_cards_reflects_each_entry() -> None:
    cards = {"a": Card(), "b": Card(ease_factor=1.5, consecutive_correct=0)}
    w = weights_from_cards(cards)
    assert w.keys() == cards.keys()
    assert w["b"] > w["a"]

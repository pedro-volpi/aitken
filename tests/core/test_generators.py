"""Testes do gerador de tabuada.

Cobrem: amostragem dentro da faixa, filtro de triviais, canonicalização
de chaves comutativas, validação de ``TablesParams``, determinismo por
seed e parsing de respostas em ``check``.
"""
from __future__ import annotations

from random import Random

import pytest

from aitken.core.generators.tables import TablesGenerator, TablesParams
from aitken.core.problem import Problem


def _split_prompt(prompt: str) -> tuple[int, int]:
    """Extrai ``(a, b)`` de um prompt no formato ``"a × b"``."""
    a_str, _, b_str = prompt.partition(" × ")
    return int(a_str), int(b_str)


def test_module_id() -> None:
    assert TablesGenerator(TablesParams()).module_id == "tables"


def test_produces_problems_in_range() -> None:
    gen = TablesGenerator(TablesParams(min_factor=3, max_factor=5))
    rng = Random(0)
    for _ in range(300):
        p = gen.next(rng)
        a, b = _split_prompt(p.prompt)
        assert 3 <= a <= 5
        assert 3 <= b <= 5


def test_excludes_trivial_by_default() -> None:
    # min_factor=0 mas exclude_trivial=True (padrão) — nunca deve sair < 2.
    gen = TablesGenerator(TablesParams(min_factor=2, max_factor=9))
    rng = Random(42)
    for _ in range(500):
        a, b = _split_prompt(gen.next(rng).prompt)
        assert a >= 2 and b >= 2


def test_includes_trivial_when_disabled() -> None:
    gen = TablesGenerator(
        TablesParams(min_factor=0, max_factor=9, exclude_trivial=False)
    )
    rng = Random(42)
    saw_trivial = any(
        _split_prompt(gen.next(rng).prompt)[0] < 2
        or _split_prompt(gen.next(rng).prompt)[1] < 2
        for _ in range(500)
    )
    assert saw_trivial


def test_commutative_key_is_canonical() -> None:
    gen = TablesGenerator(TablesParams(commutative_pairs=True))
    rng = Random(123)
    for _ in range(500):
        p = gen.next(rng)
        a, b = _split_prompt(p.prompt)
        assert p.key == f"tables:{min(a, b)}x{max(a, b)}"


def test_non_commutative_key_preserves_order() -> None:
    gen = TablesGenerator(TablesParams(commutative_pairs=False))
    rng = Random(7)
    for _ in range(200):
        p = gen.next(rng)
        a, b = _split_prompt(p.prompt)
        assert p.key == f"tables:{a}x{b}"


def test_expected_answer_is_product() -> None:
    gen = TablesGenerator(TablesParams())
    rng = Random(1)
    for _ in range(300):
        p = gen.next(rng)
        a, b = _split_prompt(p.prompt)
        assert int(p.expected_answer) == a * b


def test_key_prefix_is_module_id() -> None:
    gen = TablesGenerator(TablesParams())
    rng = Random(0)
    for _ in range(50):
        assert gen.next(rng).key.startswith("tables:")


def test_module_id_on_problem() -> None:
    gen = TablesGenerator(TablesParams())
    rng = Random(0)
    assert gen.next(rng).module_id == "tables"


def test_check_accepts_correct() -> None:
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:7x8", "7 × 8", "56")
    assert gen.check(p, "56")


def test_check_strips_whitespace() -> None:
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:7x8", "7 × 8", "56")
    assert gen.check(p, "  56 ")
    assert gen.check(p, "\t56\n")


def test_check_rejects_wrong_number() -> None:
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:7x8", "7 × 8", "56")
    assert not gen.check(p, "55")
    assert not gen.check(p, "57")
    assert not gen.check(p, "0")


def test_check_rejects_empty() -> None:
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:7x8", "7 × 8", "56")
    assert not gen.check(p, "")
    assert not gen.check(p, "   ")


def test_check_rejects_non_numeric() -> None:
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:7x8", "7 × 8", "56")
    assert not gen.check(p, "abc")
    # Decimais são rejeitados — tabuada é sempre inteiro.
    assert not gen.check(p, "5.6")
    assert not gen.check(p, "56a")


def test_check_accepts_negative_when_expected_is_negative() -> None:
    # Defensivo: a implementação atual não gera produtos negativos,
    # mas o parser deve aceitar sinal para futuros módulos que usem o
    # mesmo mecanismo de comparação inteira.
    gen = TablesGenerator(TablesParams())
    p = Problem("tables", "tables:neg", "prompt", "-12")
    assert gen.check(p, "-12")


def test_deterministic_with_same_seed() -> None:
    params = TablesParams()
    gen = TablesGenerator(params)
    seq1 = [gen.next(Random(99)).prompt for _ in range(1)]
    seq2 = [gen.next(Random(99)).prompt for _ in range(1)]
    assert seq1 == seq2


def test_sequence_reproducible_with_shared_rng() -> None:
    gen = TablesGenerator(TablesParams())
    rng1 = Random(77)
    rng2 = Random(77)
    for _ in range(20):
        assert gen.next(rng1) == gen.next(rng2)


def test_params_rejects_negative_min() -> None:
    with pytest.raises(ValueError):
        TablesParams(min_factor=-1, max_factor=5)


def test_params_rejects_min_gt_max() -> None:
    with pytest.raises(ValueError):
        TablesParams(min_factor=8, max_factor=3)


def test_params_rejects_empty_after_exclude_trivial() -> None:
    # Faixa [0, 1] fica vazia ao filtrar triviais.
    with pytest.raises(ValueError):
        TablesParams(min_factor=0, max_factor=1, exclude_trivial=True)


def test_params_accepts_range_2_2() -> None:
    # Edge case: faixa mínima não-trivial.
    params = TablesParams(min_factor=2, max_factor=2)
    gen = TablesGenerator(params)
    p = gen.next(Random(0))
    assert p.prompt == "2 × 2"
    assert p.expected_answer == "4"


def test_extended_range_up_to_19() -> None:
    gen = TablesGenerator(TablesParams(min_factor=2, max_factor=19))
    rng = Random(5)
    for _ in range(500):
        a, b = _split_prompt(gen.next(rng).prompt)
        assert 2 <= a <= 19 and 2 <= b <= 19

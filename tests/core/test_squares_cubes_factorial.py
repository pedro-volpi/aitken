"""Testes dos geradores ``squares``, ``cubes`` e ``factorial``."""

from random import Random

import pytest

from aitken.core.generators.cubes import CubesGenerator, CubesParams
from aitken.core.generators.factorial import FactorialGenerator
from aitken.core.generators.squares import SquaresGenerator, SquaresParams
from aitken.core.problem import Problem

# ---------- squares ----------


def test_squares_module_id() -> None:
    assert SquaresGenerator(SquaresParams()).module_id == "squares"


def test_squares_default_range_all_keys() -> None:
    gen = SquaresGenerator(SquaresParams())  # 11..25
    keys = list(gen.all_keys())
    assert keys[0] == "squares:11"
    assert keys[-1] == "squares:25"
    assert len(keys) == 15


def test_squares_sample_and_answer() -> None:
    gen = SquaresGenerator(SquaresParams(min_base=3, max_base=5))
    rng = Random(0)
    for _ in range(50):
        p = gen.next(rng)
        base_str = p.prompt.rstrip("²")
        base = int(base_str)
        assert 3 <= base <= 5
        assert p.expected_answer == str(base * base)
        assert p.key == f"squares:{base}"


def test_squares_weighted_respects_highest_weight() -> None:
    gen = SquaresGenerator(SquaresParams())  # 11..25
    weights = {k: 0.01 for k in gen.all_keys()}
    weights["squares:17"] = 100.0
    rng = Random(0)
    counts: dict[str, int] = {}
    for _ in range(200):
        p = gen.next(rng, weights=weights)
        counts[p.key] = counts.get(p.key, 0) + 1
    assert counts["squares:17"] > 150  # dominância esmagadora


def test_squares_check_accepts_correct() -> None:
    gen = SquaresGenerator(SquaresParams())
    p = Problem("squares", "squares:12", "12²", "144")
    assert gen.check(p, "144")
    assert gen.check(p, "  144\n")


def test_squares_check_rejects_wrong() -> None:
    gen = SquaresGenerator(SquaresParams())
    p = Problem("squares", "squares:12", "12²", "144")
    assert not gen.check(p, "143")
    assert not gen.check(p, "")
    assert not gen.check(p, "abc")


def test_squares_params_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        SquaresParams(min_base=5, max_base=3)


def test_squares_params_rejects_negative_min() -> None:
    with pytest.raises(ValueError):
        SquaresParams(min_base=-1, max_base=5)


def test_squares_params_rejects_empty_after_exclude_trivial() -> None:
    with pytest.raises(ValueError):
        SquaresParams(min_base=0, max_base=1, exclude_trivial=True)


def test_squares_include_trivial() -> None:
    gen = SquaresGenerator(SquaresParams(min_base=0, max_base=3, exclude_trivial=False))
    keys = list(gen.all_keys())
    assert keys == ["squares:0", "squares:1", "squares:2", "squares:3"]


# ---------- cubes ----------


def test_cubes_module_id() -> None:
    assert CubesGenerator(CubesParams()).module_id == "cubes"


def test_cubes_default_range_all_keys() -> None:
    gen = CubesGenerator(CubesParams())  # 3..10
    keys = list(gen.all_keys())
    assert keys[0] == "cubes:3"
    assert keys[-1] == "cubes:10"
    assert len(keys) == 8


def test_cubes_sample_and_answer() -> None:
    gen = CubesGenerator(CubesParams(min_base=3, max_base=5))
    rng = Random(0)
    for _ in range(50):
        p = gen.next(rng)
        base = int(p.prompt.rstrip("³"))
        assert 3 <= base <= 5
        assert p.expected_answer == str(base**3)
        assert p.key == f"cubes:{base}"


def test_cubes_expected_answers_spot_check() -> None:
    gen = CubesGenerator(CubesParams(min_base=2, max_base=10))
    rng = Random(0)
    seen: dict[int, str] = {}
    for _ in range(200):
        p = gen.next(rng)
        base = int(p.prompt.rstrip("³"))
        seen[base] = p.expected_answer
    # 7³ = 343, 10³ = 1000
    assert seen.get(7) == "343"
    assert seen.get(10) == "1000"


def test_cubes_check_accepts_correct() -> None:
    gen = CubesGenerator(CubesParams())
    p = Problem("cubes", "cubes:4", "4³", "64")
    assert gen.check(p, "64")


def test_cubes_params_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        CubesParams(min_base=5, max_base=3)


# ---------- factorial ----------


def test_factorial_module_id() -> None:
    assert FactorialGenerator().module_id == "factorial"


def test_factorial_pool_is_0_to_10() -> None:
    gen = FactorialGenerator()
    keys = list(gen.all_keys())
    assert keys == [f"factorial:{n}" for n in range(11)]


def test_factorial_answers_for_each_base() -> None:
    """Checa as 11 respostas com samples exaustivos."""
    gen = FactorialGenerator()
    seen: dict[int, str] = {}
    rng = Random(0)
    # Com seed fixa e amostragem uniforme, coletamos gradualmente os 11.
    for _ in range(2000):
        p = gen.next(rng)
        n = int(p.prompt.rstrip("!"))
        seen[n] = p.expected_answer
        if len(seen) == 11:
            break
    assert seen[0] == "1"
    assert seen[1] == "1"
    assert seen[2] == "2"
    assert seen[3] == "6"
    assert seen[4] == "24"
    assert seen[5] == "120"
    assert seen[6] == "720"
    assert seen[7] == "5040"
    assert seen[8] == "40320"
    assert seen[9] == "362880"
    assert seen[10] == "3628800"


def test_factorial_check_accepts_correct() -> None:
    gen = FactorialGenerator()
    p = Problem("factorial", "factorial:5", "5!", "120")
    assert gen.check(p, "120")


def test_factorial_check_rejects_non_numeric() -> None:
    gen = FactorialGenerator()
    p = Problem("factorial", "factorial:5", "5!", "120")
    assert not gen.check(p, "")
    assert not gen.check(p, "abc")


def test_factorial_weighted_respects_highest_weight() -> None:
    gen = FactorialGenerator()
    weights = {k: 0.01 for k in gen.all_keys()}
    weights["factorial:7"] = 100.0
    rng = Random(0)
    counts: dict[str, int] = {}
    for _ in range(200):
        p = gen.next(rng, weights=weights)
        counts[p.key] = counts.get(p.key, 0) + 1
    assert counts["factorial:7"] > 150

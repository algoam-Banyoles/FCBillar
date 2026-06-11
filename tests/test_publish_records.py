import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "publish_records.py"
SPEC = importlib.util.spec_from_file_location("publish_records", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

valid_record_average = MODULE.valid_record_average


def test_rejects_truncated_three_cushion_draw() -> None:
    assert not valid_record_average(1, 13, 13, 5)


def test_rejects_impossible_three_cushion_average() -> None:
    assert not valid_record_average(1, 35, 6, 10)


def test_accepts_completed_three_cushion_draw() -> None:
    assert valid_record_average(1, 13, 13, 50)


def test_accepts_short_completed_three_cushion_win() -> None:
    assert valid_record_average(1, 40, 29, 15)


def test_accepts_short_games_in_other_modalities() -> None:
    assert valid_record_average(2, 300, 0, 1)

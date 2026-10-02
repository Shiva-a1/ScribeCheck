import pytest

from shared.grading import combine, flag_reasons, match_student

POINTS = {1: 1.0, 2: 1.0, 3: 1.0}


def test_median_per_point_and_total():
    judges = [{1: 1, 2: 1, 3: 0}, {1: 1, 2: 1, 3: 0}, {1: 1, 2: 0, 3: 0}]
    per_point, total, spread = combine(judges, POINTS)
    assert per_point == {1: 1, 2: 1, 3: 0}
    assert total == 2
    assert spread == 1


def test_marks_are_capped_at_point_value_and_zero():
    judges = [{1: 4, 2: -2, 3: 1}, {1: 1, 2: 0, 3: 1}, {1: 1, 2: 0, 3: 1}]
    per_point, total, _ = combine(judges, POINTS)
    assert per_point == {1: 1, 2: 0, 3: 1}
    assert total == 2


def test_missing_point_counts_as_zero():
    _, total, _ = combine([{1: 1}, {1: 1, 2: 1}, {1: 1, 2: 1}], POINTS)
    assert total == 2


def test_two_judges_use_their_average():
    _, total, _ = combine([{1: 1, 2: 1, 3: 1}, {1: 1, 2: 0, 3: 0}], POINTS)
    assert total == pytest.approx(2.0)


def test_one_outlier_cannot_drag_the_grade():
    _, total, spread = combine([{1: 1, 2: 1, 3: 1}, {1: 1, 2: 1, 3: 1}, {1: 0, 2: 0, 3: 0}], POINTS)
    assert total == 3
    assert spread == 3


def test_flag_reasons():
    assert flag_reasons(0, 3) == []
    assert flag_reasons(1.5, 3) == ["judges disagree"]
    assert flag_reasons(0, 2, read_confidence=0.4, contradicts_key=True) == [
        "graded by 2 judges", "hard to read", "web contradicts the key",
    ]


@pytest.mark.parametrize("read, expected", [
    ("12345678", "12345678"),
    ("1234 5678", "12345678"),
    ("ID: 12345678", "12345678"),
    ("12345679", None),
    ("", None),
])
def test_match_student(read, expected):
    assert match_student(read, ["12345678", "23456789"]) == expected

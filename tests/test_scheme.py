from shared.scheme import scheme_problems


def question(max_marks, *marks, number=1):
    return {"number": number, "max_marks": max_marks, "points": [{"description": "idea", "marks": m} for m in marks]}


def test_valid_scheme_has_no_problems():
    assert scheme_problems([question(3, 1, 1, 1), question(2, 1.5, 0.5, number=2)]) == []


def test_points_must_add_up():
    assert scheme_problems([question(3, 1, 1)]) == ["Question 1: points add up to 2, but the question is worth 3."]


def test_missing_marks_and_points():
    assert scheme_problems([question(0)]) == ["Question 1 needs its marks filled in."]
    assert scheme_problems([question(2)]) == ["Question 1 has no rubric points."]


def test_empty_key():
    assert scheme_problems([]) == ["Upload an answer key first."]


def test_blank_description():
    q = question(1, 1)
    q["points"][0]["description"] = "  "
    assert scheme_problems([q]) == ["Question 1 has a rubric point with no description."]

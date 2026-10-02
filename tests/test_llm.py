import pytest
from pydantic import ValidationError

from shared.llm import parse_json
from shared.schemas import Judgment


def test_parses_json_wrapped_in_text_or_fences():
    text = 'Sure:\n```json\n{"points": [{"point_id": 1, "marks": 1, "evidence": "halves"}]}\n```'
    assert parse_json(text, Judgment).points[0].marks == 1


def test_rejects_missing_json_and_wrong_shape():
    with pytest.raises(ValueError):
        parse_json("no json here", Judgment)
    with pytest.raises(ValidationError):
        parse_json('{"points": [{"marks": 1}]}', Judgment)

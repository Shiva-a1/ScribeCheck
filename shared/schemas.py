from pydantic import BaseModel, Field


class RubricPoint(BaseModel):
    description: str
    marks: float


class KeyQuestion(BaseModel):
    number: int
    text: str = ""
    reference_answer: str
    max_marks: float
    points: list[RubricPoint]


class AnswerKey(BaseModel):
    questions: list[KeyQuestion]


class Scheme(BaseModel):
    points: list[RubricPoint]


class ReadAnswer(BaseModel):
    number: int
    text: str
    confidence: float = Field(ge=0, le=1)


class ReadSheet(BaseModel):
    student_id: str
    answers: list[ReadAnswer]


class Coverage(BaseModel):
    uncovered_claims: list[str]


class WebVerdict(BaseModel):
    contradicts_key: bool
    summary: str


class PointJudgment(BaseModel):
    point_id: int
    marks: float
    evidence: str = ""


class Judgment(BaseModel):
    points: list[PointJudgment]

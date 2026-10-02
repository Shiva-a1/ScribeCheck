from collections import defaultdict
from contextlib import contextmanager

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import User, require_student
from shared import db, storage

router = APIRouter(prefix="/api/student")


class RegradeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@contextmanager
def as_student(user):
    with db.connection() as conn:
        conn.execute("SELECT set_config('app.student_id', %s, true)", (user.student_id,))
        conn.execute("SET LOCAL ROLE student_api")
        yield conn


@router.get("/exams")
def list_exams(user: User = Depends(require_student)):
    with as_student(user) as conn:
        return conn.execute(
            "SELECT e.exam_id, e.title, e.released_at, "
            "sum(coalesce(g.override_marks, g.final_marks)) AS total, sum(g.max_marks) AS max "
            "FROM exams e JOIN submissions s USING (exam_id) JOIN answers a USING (submission_id) "
            "JOIN grades g USING (answer_id) GROUP BY e.exam_id ORDER BY e.released_at DESC"
        ).fetchall()


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, user: User = Depends(require_student)):
    with as_student(user) as conn:
        exam = conn.execute("SELECT exam_id, title, released_at FROM exams WHERE exam_id = %s", (exam_id,)).fetchone()
        sheet = conn.execute(
            "SELECT submission_id, s3_key, content_type FROM submissions WHERE exam_id = %s", (exam_id,)
        ).fetchone()
        if exam is None or sheet is None:
            raise HTTPException(404, "Exam not found.")
        questions = conn.execute(
            "SELECT a.answer_id, q.number, q.text, a.text AS answer, "
            "coalesce(g.override_marks, g.final_marks) AS marks, g.max_marks, g.override_marks IS NOT NULL AS adjusted, "
            "f.text AS feedback, r.status AS regrade_status, r.reason AS regrade_reason "
            "FROM answers a JOIN questions q USING (question_id) LEFT JOIN grades g USING (answer_id) "
            "LEFT JOIN feedback f USING (answer_id) LEFT JOIN regrade_requests r USING (answer_id) "
            "WHERE a.submission_id = %s ORDER BY q.number",
            (sheet["submission_id"],),
        ).fetchall()
        points = defaultdict(list)
        for p in conn.execute(
            "SELECT pr.answer_id, rp.description, rp.marks AS max, pr.marks "
            "FROM point_results pr JOIN rubric_points rp USING (point_id) JOIN answers a USING (answer_id) "
            "WHERE a.submission_id = %s ORDER BY rp.position",
            (sheet["submission_id"],),
        ):
            points[p["answer_id"]].append(p)
    graded = [q for q in questions if q["marks"] is not None]
    return {
        **exam,
        "total": sum(q["marks"] for q in graded),
        "max": sum(q["max_marks"] for q in graded),
        "scan_url": storage.url(sheet["s3_key"]),
        "scan_type": sheet["content_type"],
        "questions": [{**q, "points": points[q["answer_id"]]} for q in questions],
    }


@router.post("/answers/{answer_id}/regrade")
def request_regrade(answer_id: int, body: RegradeIn, user: User = Depends(require_student)):
    try:
        with as_student(user) as conn:
            conn.execute(
                "INSERT INTO regrade_requests (answer_id, student_id, reason) VALUES (%s, %s, %s)",
                (answer_id, user.student_id, body.reason.strip()),
            )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "You've already asked for this answer to be regraded.")
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(404, "Answer not found.")
    return {"ok": True}

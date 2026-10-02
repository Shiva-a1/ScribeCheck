import os

import psycopg
import pytest
from psycopg.rows import dict_row

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="needs TEST_DATABASE_URL pointing at a database with db/schema.sql loaded")


@pytest.fixture
def conn():
    with psycopg.connect(URL, row_factory=dict_row) as conn:
        yield conn
        conn.rollback()


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


@pytest.fixture
def school(conn):
    teacher = one(conn, "INSERT INTO users (email, role) VALUES ('t@ufl.edu', 'teacher') RETURNING user_id")["user_id"]
    exam = one(conn, "INSERT INTO exams (owner_id, title, status, released_at) VALUES (%s, 'Quiz', 'released', now()) RETURNING exam_id", teacher)["exam_id"]
    question = one(conn, "INSERT INTO questions (exam_id, number, reference_answer, max_marks) VALUES (%s, 1, 'key', 2) RETURNING question_id", exam)["question_id"]
    answers = {}
    for sid, email in (("111", "a@ufl.edu"), ("222", "b@ufl.edu")):
        user = one(conn, "INSERT INTO users (email, role) VALUES (%s, 'student') RETURNING user_id", email)["user_id"]
        conn.execute("INSERT INTO students (student_id, user_id, name, email) VALUES (%s, %s, %s, %s)", (sid, user, sid, email))
        conn.execute("INSERT INTO exam_students VALUES (%s, %s)", (exam, sid))
        sub = one(conn, "INSERT INTO submissions (exam_id, student_id, s3_key, content_type, status) VALUES (%s, %s, 'k', 'image/png', 'graded') RETURNING submission_id", exam, sid)["submission_id"]
        answer = one(conn, "INSERT INTO answers (submission_id, question_id, text, status) VALUES (%s, %s, 'x', 'graded') RETURNING answer_id", sub, question)["answer_id"]
        conn.execute("INSERT INTO grades (answer_id, final_marks, max_marks, judges, flagged) VALUES (%s, 1, 2, 3, false)", (answer,))
        answers[sid] = answer
    return {"exam": exam, "answers": answers}


def become(conn, student_id):
    conn.execute("SELECT set_config('app.student_id', %s, true)", (student_id,))
    conn.execute("SET LOCAL ROLE student_api")


def test_student_sees_only_their_own_grades(conn, school):
    become(conn, "111")
    seen = {r["answer_id"] for r in conn.execute("SELECT answer_id FROM grades")}
    assert seen == {school["answers"]["111"]}
    assert conn.execute("SELECT count(*) AS n FROM submissions").fetchone()["n"] == 1


def test_unreleased_exam_is_invisible(conn, school):
    conn.execute("UPDATE exams SET released_at = NULL WHERE exam_id = %s", (school["exam"],))
    become(conn, "111")
    assert conn.execute("SELECT count(*) AS n FROM grades").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM exams").fetchone()["n"] == 0


def test_student_cannot_request_regrade_for_someone_else(conn, school):
    become(conn, "111")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO regrade_requests (answer_id, student_id, reason) VALUES (%s, '111', 'mine?')", (school["answers"]["222"],))


def test_student_cannot_change_grades(conn, school):
    become(conn, "111")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE grades SET final_marks = 2")

import os
import random
import re
from collections import deque

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shared import config, db, kafka, llm, storage
from shared.schemas import AnswerKey, Coverage, Judgment, KeyQuestion, PointJudgment, ReadAnswer, ReadSheet, RubricPoint
from workers import aggregator, evidence, feedback, judge, reader

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="needs TEST_DATABASE_URL pointing at a database with db/schema.sql loaded")


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", URL)
    monkeypatch.setenv("CLAUDE_MODEL", "test")
    monkeypatch.setenv("CLAUDE_VISION_MODEL", "test")
    monkeypatch.setattr(db, "_pool", None)
    files, queue = {}, deque()
    monkeypatch.setattr(storage, "put", lambda key, data, content_type: files.__setitem__(key, data))
    monkeypatch.setattr(storage, "get", lambda key: files[key])
    monkeypatch.setattr(storage, "url", lambda key, expires=600: f"https://scans.test/{key}")
    monkeypatch.setattr(kafka, "publish", lambda topic, key, value: queue.append((topic, value)))
    monkeypatch.setattr(llm, "embed", lambda texts: [np.ones(1536, dtype=np.float32) for _ in texts])
    monkeypatch.setattr(llm, "ask_claude_text", lambda system, prompt, max_tokens=600: "You explained the halving step well; review what happens in an unbalanced tree.")
    student_id = str(random.randint(10_000_000, 99_999_999))

    def ask_claude(system, content, schema, model=None, max_tokens=4000):
        if schema is AnswerKey:
            return AnswerKey(questions=[
                KeyQuestion(number=1, text="Why is BST lookup O(log n)?", reference_answer="Halves each step; O(n) if unbalanced.",
                            max_marks=3, points=[RubricPoint(description=d, marks=1) for d in ("says O(log n)", "halves each step", "O(n) unbalanced")]),
                KeyQuestion(number=2, text="Stack vs queue?", reference_answer="LIFO vs FIFO.", max_marks=2,
                            points=[RubricPoint(description="stack is LIFO", marks=1), RubricPoint(description="queue is FIFO", marks=1)]),
            ])
        if schema is ReadSheet:
            return ReadSheet(student_id=f"ID {student_id}", answers=[
                ReadAnswer(number=1, text="Each step cuts the tree in half so it is log n.", confidence=0.9),
                ReadAnswer(number=2, text="Stack is last in first out, queue is first in first out.", confidence=0.95),
            ])
        if schema is Coverage:
            return Coverage(uncovered_claims=[])
        raise AssertionError(schema)

    def ask_judge(provider, system, prompt, schema):
        ids = [int(i) for i in re.findall(r"point_id (\d+)", prompt)]
        generous = provider != "gemini"
        marks = [1, 1, 0] if len(ids) == 3 else [1, 1]
        if len(ids) == 3 and not generous:
            marks = [1, 0, 0]
        return Judgment(points=[PointJudgment(point_id=i, marks=m, evidence="quote") for i, m in zip(ids, marks)])

    monkeypatch.setattr(llm, "ask_claude", ask_claude)
    monkeypatch.setattr(llm, "ask_judge", ask_judge)

    def drain():
        handlers = {
            "sheets": [reader.handle],
            "answers": [evidence.handle],
            "evidence": [lambda m, j=j: judge.handle(m, j) for j in ("claude", "openai", "gemini")],
            "judgments": [aggregator.handle],
            "graded": [feedback.handle],
        }
        while queue:
            topic, value = queue.popleft()
            for handle in handlers[topic]:
                handle(value)

    from api.main import app
    suffix = random.randint(0, 10**9)
    teacher_email, student_email = f"teacher{suffix}@ufl.edu", f"student{suffix}@ufl.edu"
    with db.connection() as conn:
        conn.execute("INSERT INTO users (email, name, role) VALUES (%s, 'Dr Rao', 'teacher')", (teacher_email,))
    client = TestClient(app)

    def login(email):
        token = client.post("/api/dev/login", json={"email": email}).json()["token"]
        client.headers["Authorization"] = f"Bearer {token}"

    return {"client": client, "drain": drain, "login": login, "teacher": teacher_email,
            "student": student_email, "student_id": student_id, "queue": queue}


def test_exam_flows_from_upload_to_student_results(world):
    client, drain = world["client"], world["drain"]
    world["login"](world["teacher"])

    exam = client.post("/api/exams", json={"title": "Quiz 3"}).json()
    exam_id = exam["exam_id"]
    exam = client.post(f"/api/exams/{exam_id}/key", files={"file": ("key.txt", b"Q1 (3 marks)...", "text/plain")}).json()
    assert [q["max_marks"] for q in exam["questions"]] == [3, 2]

    early = client.post(f"/api/exams/{exam_id}/sheets", files=[("files", ("a.png", b"img", "image/png"))])
    assert early.status_code == 409

    first = exam["questions"][0]
    broken = {"questions": [{"question_id": first["question_id"], "max_marks": 3, "points": [{"description": "only one", "marks": 1}]}]}
    client.put(f"/api/exams/{exam_id}/scheme", json=broken)
    refused = client.post(f"/api/exams/{exam_id}/confirm")
    assert refused.status_code == 422
    assert "points add up to 1" in refused.json()["detail"]["problems"][0]

    fixed = {"questions": [{"question_id": first["question_id"], "max_marks": 3,
                            "points": [{"description": d, "marks": 1} for d in ("says O(log n)", "halves each step", "O(n) unbalanced")]}]}
    client.put(f"/api/exams/{exam_id}/scheme", json=fixed)
    assert client.post(f"/api/exams/{exam_id}/confirm").json()["status"] == "ready"

    client.post(f"/api/exams/{exam_id}/notes", files={"file": ("notes.txt", b"Binary search trees halve the search space. " * 50, "text/plain")})
    roster = f"student_id,name,email\n{world['student_id']},Ben Lee,{world['student']}\n".encode()
    assert client.post(f"/api/exams/{exam_id}/roster", files={"file": ("roster.csv", roster, "text/csv")}).json()["roster_size"] == 1

    assert client.post(f"/api/exams/{exam_id}/sheets", files=[("files", ("ben.png", b"img", "image/png"))]).json() == {"queued": 1}
    drain()

    results = client.get(f"/api/exams/{exam_id}/results").json()
    row = results["rows"][0]
    assert row["student_id"] == world["student_id"] and row["status"] == "graded"
    assert row["cells"]["1"]["marks"] == 2 and not row["cells"]["1"]["flagged"]
    assert row["cells"]["2"]["marks"] == 2
    assert row["total"] == 4 and row["max"] == 5

    detail = client.get(f"/api/answers/{row['cells']['1']['answer_id']}").json()
    assert {tuple(sorted(p["judges"])) for p in detail["points"]} == {("claude", "gemini", "openai")}
    assert detail["feedback"].startswith("You explained")
    assert detail["points"][1]["judges"]["gemini"] == 0 and detail["points"][1]["final"] == 1

    world["login"](world["student"])
    assert client.get("/api/student/exams").json() == []

    world["login"](world["teacher"])
    assert client.post(f"/api/exams/{exam_id}/release").json() == {"ok": True}

    world["login"](world["student"])
    [mine] = client.get("/api/student/exams").json()
    assert mine["total"] == 4
    view = client.get(f"/api/student/exams/{exam_id}").json()
    assert [q["marks"] for q in view["questions"]] == [2, 2]
    assert "judges" not in view["questions"][0]
    answer_id = view["questions"][0]["answer_id"]
    assert client.post(f"/api/student/answers/{answer_id}/regrade", json={"reason": "I did explain the unbalanced case."}).json() == {"ok": True}
    assert client.post(f"/api/student/answers/{answer_id}/regrade", json={"reason": "Asking again for the same one."}).status_code == 409
    assert client.get("/api/exams").status_code == 403

    world["login"](world["teacher"])
    [request] = client.get(f"/api/exams/{exam_id}/regrades").json()
    client.post(f"/api/regrades/{request['request_id']}/resolve", json={"marks": 3})
    assert client.get(f"/api/exams/{exam_id}/results").json()["rows"][0]["total"] == 5
    assert "Ben Lee" in client.get(f"/api/exams/{exam_id}/export").text


def test_aggregator_waits_for_all_three_judges_then_grades_after_timeout(world):
    world["login"](world["teacher"])
    client = world["client"]
    exam_id = client.post("/api/exams", json={"title": "Partial"}).json()["exam_id"]
    client.post(f"/api/exams/{exam_id}/key", files={"file": ("key.txt", b"key", "text/plain")})
    client.post(f"/api/exams/{exam_id}/confirm")
    client.post(f"/api/exams/{exam_id}/sheets", files=[("files", ("x.png", b"img", "image/png"))])

    queue = world["queue"]
    while queue:
        topic, value = queue.popleft()
        if topic == "sheets":
            reader.handle(value)
        elif topic == "answers":
            evidence.handle(value)
        elif topic == "evidence":
            for name in ("claude", "openai"):
                judge.handle(value, name)
        elif topic == "judgments":
            aggregator.handle(value)

    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM grades g JOIN answers a USING (answer_id) JOIN submissions s USING (submission_id) WHERE s.exam_id = %s", (exam_id,)).fetchone()["n"] == 0
        conn.execute("UPDATE answers SET dispatched_at = now() - interval '10 minutes' WHERE submission_id IN (SELECT submission_id FROM submissions WHERE exam_id = %s)", (exam_id,))
    aggregator.sweep()

    cells = client.get(f"/api/exams/{exam_id}/results").json()["rows"][0]["cells"]
    assert all(c["status"] == "graded" and c["flagged"] for c in cells.values())
    answer = client.get(f"/api/answers/{cells['1']['answer_id']}").json()
    assert "graded by 2 judges" in answer["grade"]["flag_reasons"]


def test_sheets_uploaded_before_the_roster_match_once_it_arrives(world):
    world["login"](world["teacher"])
    client = world["client"]
    exam_id = client.post("/api/exams", json={"title": "Roster later"}).json()["exam_id"]
    client.post(f"/api/exams/{exam_id}/key", files={"file": ("key.txt", b"key", "text/plain")})
    client.post(f"/api/exams/{exam_id}/confirm")
    client.post(f"/api/exams/{exam_id}/sheets", files=[("files", ("x.png", b"img", "image/png"))])
    world["drain"]()
    assert client.get(f"/api/exams/{exam_id}/results").json()["rows"][0]["student_id"] is None
    refused = client.post(f"/api/exams/{exam_id}/release")
    assert refused.json()["detail"] == "Can't release yet: 1 without a student assigned."

    roster = f"student_id,name,email\n{world['student_id']},Ben Lee,{world['student']}\n".encode()
    client.post(f"/api/exams/{exam_id}/roster", files={"file": ("roster.csv", roster, "text/csv")})
    assert client.get(f"/api/exams/{exam_id}/results").json()["rows"][0]["student_id"] == world["student_id"]
    assert client.post(f"/api/exams/{exam_id}/release").json() == {"ok": True}

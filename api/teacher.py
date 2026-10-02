import csv
import io
import json
import uuid
from collections import defaultdict
from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import User, invite, require_teacher, user_from_token
from shared import config, db, kafka, llm, prompts, storage, text
from shared.roster import parse_roster
from shared.scheme import scheme_problems
from shared.schemas import AnswerKey
from workers.aggregator import mark_graded

router = APIRouter(prefix="/api")
SHEET_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
FILE_TYPES = SHEET_TYPES | {"text/plain"}
REMATCH = """
    UPDATE submissions s SET student_id = m.student_id
    FROM (
        SELECT DISTINCT ON (es.student_id) u.submission_id, es.student_id
        FROM submissions u
        JOIN exam_students es ON es.exam_id = u.exam_id
            AND regexp_replace(coalesce(u.read_student_id, ''), '\\D', '', 'g') = regexp_replace(es.student_id, '\\D', '', 'g')
        WHERE u.exam_id = %(id)s AND u.student_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM submissions t WHERE t.exam_id = u.exam_id AND t.student_id = es.student_id)
        ORDER BY es.student_id, u.submission_id
    ) m
    WHERE s.submission_id = m.submission_id
"""


class NewExam(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class PointIn(BaseModel):
    description: str
    marks: float = Field(gt=0)


class QuestionScheme(BaseModel):
    question_id: int
    max_marks: float = Field(ge=0)
    points: list[PointIn]


class SchemeIn(BaseModel):
    questions: list[QuestionScheme]


class MarksIn(BaseModel):
    marks: float | None = Field(default=None, ge=0)


class AssignIn(BaseModel):
    student_id: str


def own_exam(conn, exam_id, user):
    exam = conn.execute(
        "SELECT * FROM exams WHERE exam_id = %s AND owner_id = %s", (exam_id, user.user_id)
    ).fetchone()
    if exam is None:
        raise HTTPException(404, "Exam not found.")
    return exam


def own_answer(conn, answer_id, user):
    answer = conn.execute(
        "SELECT a.*, s.exam_id, s.s3_key, s.content_type, s.student_id, e.status AS exam_status "
        "FROM answers a JOIN submissions s USING (submission_id) JOIN exams e ON e.exam_id = s.exam_id "
        "WHERE a.answer_id = %s AND e.owner_id = %s",
        (answer_id, user.user_id),
    ).fetchone()
    if answer is None:
        raise HTTPException(404, "Answer not found.")
    return answer


def require_status(exam, *allowed, message):
    if exam["status"] not in allowed:
        raise HTTPException(409, message)


def read_upload(file, allowed):
    if file.content_type not in allowed:
        raise HTTPException(422, f"{file.filename} isn't a supported file type.")
    return file.file.read()


def scheme(conn, exam_id):
    questions = conn.execute(
        "SELECT question_id, number, text, reference_answer, max_marks FROM questions WHERE exam_id = %s ORDER BY number",
        (exam_id,),
    ).fetchall()
    points = defaultdict(list)
    for p in conn.execute(
        "SELECT p.point_id, p.question_id, p.description, p.marks FROM rubric_points p "
        "JOIN questions q USING (question_id) WHERE q.exam_id = %s ORDER BY p.position",
        (exam_id,),
    ):
        points[p["question_id"]].append(p)
    return [{**q, "points": points[q["question_id"]]} for q in questions]


def exam_detail(conn, exam):
    counts = conn.execute(
        "SELECT (SELECT count(*) FROM note_chunks WHERE exam_id = %(id)s) AS notes_chunks, "
        "(SELECT count(*) FROM exam_students WHERE exam_id = %(id)s) AS roster_size, "
        "(SELECT count(*) FROM submissions WHERE exam_id = %(id)s) AS sheets",
        {"id": exam["exam_id"]},
    ).fetchone()
    return {**exam, **counts, "questions": scheme(conn, exam["exam_id"])}


@router.get("/exams")
def list_exams(user: User = Depends(require_teacher)):
    with db.connection() as conn:
        return conn.execute(
            "SELECT e.exam_id, e.title, e.status, e.created_at, count(s.*) AS sheets, "
            "count(s.*) FILTER (WHERE s.status = 'graded') AS graded "
            "FROM exams e LEFT JOIN submissions s USING (exam_id) WHERE e.owner_id = %s "
            "GROUP BY e.exam_id ORDER BY e.created_at DESC",
            (user.user_id,),
        ).fetchall()


@router.post("/exams")
def create_exam(body: NewExam, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        exam = conn.execute(
            "INSERT INTO exams (owner_id, title) VALUES (%s, %s) RETURNING *", (user.user_id, body.title.strip())
        ).fetchone()
        return exam_detail(conn, exam)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        return exam_detail(conn, own_exam(conn, exam_id, user))


@router.post("/exams/{exam_id}/key")
def upload_key(exam_id: int, file: UploadFile = File(...), user: User = Depends(require_teacher)):
    with db.connection() as conn:
        require_status(own_exam(conn, exam_id, user), "draft", message="The marking scheme is already confirmed.")
    data = read_upload(file, FILE_TYPES)
    content = (
        [{"type": "text", "text": data.decode("utf-8", errors="replace")}]
        if file.content_type == "text/plain"
        else [llm.file_block(data, file.content_type)]
    )
    key = llm.ask_claude(
        prompts.KEY_SYSTEM,
        content + [{"type": "text", "text": "Build the marking scheme for this answer key."}],
        AnswerKey,
        model=config.required("CLAUDE_VISION_MODEL"),
        max_tokens=8000,
    )
    seen = set()
    with db.connection() as conn:
        conn.execute("DELETE FROM questions WHERE exam_id = %s", (exam_id,))
        for q in key.questions:
            if q.number in seen:
                continue
            seen.add(q.number)
            question_id = conn.execute(
                "INSERT INTO questions (exam_id, number, text, reference_answer, max_marks) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING question_id",
                (exam_id, q.number, q.text, q.reference_answer, max(q.max_marks, 0)),
            ).fetchone()["question_id"]
            for position, point in enumerate(p for p in q.points if p.marks > 0):
                conn.execute(
                    "INSERT INTO rubric_points (question_id, description, marks, position) VALUES (%s, %s, %s, %s)",
                    (question_id, point.description, point.marks, position),
                )
        return exam_detail(conn, own_exam(conn, exam_id, user))


@router.put("/exams/{exam_id}/scheme")
def save_scheme(exam_id: int, body: SchemeIn, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        require_status(own_exam(conn, exam_id, user), "draft", message="The marking scheme is already confirmed.")
        ids = {r["question_id"] for r in conn.execute("SELECT question_id FROM questions WHERE exam_id = %s", (exam_id,))}
        for q in body.questions:
            if q.question_id not in ids:
                raise HTTPException(422, "That question isn't part of this exam.")
            conn.execute("UPDATE questions SET max_marks = %s WHERE question_id = %s", (q.max_marks, q.question_id))
            conn.execute("DELETE FROM rubric_points WHERE question_id = %s", (q.question_id,))
            for position, point in enumerate(q.points):
                conn.execute(
                    "INSERT INTO rubric_points (question_id, description, marks, position) VALUES (%s, %s, %s, %s)",
                    (q.question_id, point.description.strip(), point.marks, position),
                )
        return exam_detail(conn, own_exam(conn, exam_id, user))


@router.post("/exams/{exam_id}/confirm")
def confirm_scheme(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        exam = own_exam(conn, exam_id, user)
        require_status(exam, "draft", message="The marking scheme is already confirmed.")
        problems = scheme_problems(scheme(conn, exam_id))
        if problems:
            raise HTTPException(422, {"message": "Fix the marking scheme first.", "problems": problems})
        exam = conn.execute(
            "UPDATE exams SET status = 'ready', scheme_confirmed_at = now() WHERE exam_id = %s RETURNING *", (exam_id,)
        ).fetchone()
        return exam_detail(conn, exam)


@router.post("/exams/{exam_id}/notes")
def upload_notes(exam_id: int, file: UploadFile = File(...), user: User = Depends(require_teacher)):
    with db.connection() as conn:
        own_exam(conn, exam_id, user)
    data = read_upload(file, {"application/pdf", "text/plain"})
    raw = text.pdf_text(data) if file.content_type == "application/pdf" else data.decode("utf-8", errors="replace")
    chunks = text.chunk_text(raw)
    if not chunks:
        raise HTTPException(422, "No text was found in that file. Scanned PDFs need to be converted to text first.")
    vectors = [v for i in range(0, len(chunks), 100) for v in llm.embed(chunks[i:i + 100])]
    with db.connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO note_chunks (exam_id, content, embedding) VALUES (%s, %s, %s)",
                [(exam_id, c, v) for c, v in zip(chunks, vectors)],
            )
        conn.execute("UPDATE questions SET notes_pack = NULL WHERE exam_id = %s", (exam_id,))
        return exam_detail(conn, own_exam(conn, exam_id, user))


@router.post("/exams/{exam_id}/roster")
def upload_roster(exam_id: int, file: UploadFile = File(...), user: User = Depends(require_teacher)):
    with db.connection() as conn:
        own_exam(conn, exam_id, user)
    try:
        students = parse_roster(file.file.read().decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(422, str(error))
    skipped = []
    with db.connection() as conn:
        for s in students:
            account = conn.execute(
                "INSERT INTO users (email, name, role) VALUES (%s, %s, 'student') "
                "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING user_id, role",
                (s["email"], s["name"]),
            ).fetchone()
            if account["role"] != "student":
                skipped.append(s["email"])
                continue
            conn.execute(
                "INSERT INTO students (student_id, user_id, name, email) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (student_id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email, user_id = EXCLUDED.user_id",
                (s["student_id"], account["user_id"], s["name"], s["email"]),
            )
            conn.execute(
                "INSERT INTO exam_students (exam_id, student_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (exam_id, s["student_id"]),
            )
    with db.connection() as conn:
        conn.execute(REMATCH, {"id": exam_id})
    for s in students:
        if s["email"] not in skipped:
            invite(s["email"])
    with db.connection() as conn:
        return {**exam_detail(conn, own_exam(conn, exam_id, user)), "skipped": skipped}


@router.post("/exams/{exam_id}/sheets")
def upload_sheets(exam_id: int, files: list[UploadFile] = File(...), user: User = Depends(require_teacher)):
    with db.connection() as conn:
        exam = own_exam(conn, exam_id, user)
    require_status(exam, "ready", message="Confirm the marking scheme before uploading sheets." if exam["status"] == "draft"
                   else "Results are already released.")
    for f in files:
        if f.content_type not in SHEET_TYPES:
            raise HTTPException(422, f"{f.filename} isn't a PDF or image.")
    for f in files:
        key = f"exams/{exam_id}/{uuid.uuid4().hex}{Path(f.filename or '').suffix.lower()}"
        storage.put(key, f.file.read(), f.content_type)
        with db.connection() as conn:
            submission_id = conn.execute(
                "INSERT INTO submissions (exam_id, s3_key, content_type) VALUES (%s, %s, %s) RETURNING submission_id",
                (exam_id, key, f.content_type),
            ).fetchone()["submission_id"]
        kafka.publish("sheets", submission_id, {"submission_id": submission_id})
    return {"queued": len(files)}


RESULTS = """
    SELECT s.submission_id, s.student_id, st.name, s.read_student_id, s.status,
           q.number, a.answer_id, a.status AS answer_status,
           coalesce(g.override_marks, g.final_marks) AS marks, g.max_marks, g.flagged,
           g.override_marks IS NOT NULL AS overridden
    FROM submissions s
    LEFT JOIN students st USING (student_id)
    LEFT JOIN answers a ON a.submission_id = s.submission_id
    LEFT JOIN questions q ON q.question_id = a.question_id
    LEFT JOIN grades g ON g.answer_id = a.answer_id
    WHERE s.exam_id = %s
    ORDER BY st.name NULLS LAST, s.submission_id, q.number
"""


def results(conn, exam_id):
    questions = conn.execute(
        "SELECT question_id, number, max_marks FROM questions WHERE exam_id = %s ORDER BY number", (exam_id,)
    ).fetchall()
    rows = {}
    for r in conn.execute(RESULTS, (exam_id,)):
        row = rows.setdefault(r["submission_id"], {
            "submission_id": r["submission_id"], "student_id": r["student_id"], "name": r["name"],
            "read_student_id": r["read_student_id"], "status": r["status"], "cells": {},
        })
        if r["answer_id"]:
            row["cells"][r["number"]] = {
                "answer_id": r["answer_id"], "status": r["answer_status"], "marks": r["marks"],
                "max_marks": r["max_marks"], "flagged": r["flagged"], "overridden": r["overridden"],
            }
    for row in rows.values():
        complete = row["status"] == "graded"
        row["total"] = sum(c["marks"] for c in row["cells"].values()) if complete else None
        row["max"] = sum(q["max_marks"] for q in questions)
    cells = [c for row in rows.values() for c in row["cells"].values()]
    totals = [row["total"] for row in rows.values() if row["total"] is not None]
    roster = conn.execute(
        "SELECT st.student_id, st.name FROM exam_students es JOIN students st USING (student_id) "
        "WHERE es.exam_id = %s AND NOT EXISTS (SELECT 1 FROM submissions s WHERE s.exam_id = es.exam_id AND s.student_id = st.student_id) "
        "ORDER BY st.name",
        (exam_id,),
    ).fetchall()
    return {
        "questions": questions,
        "rows": list(rows.values()),
        "unassigned_students": roster,
        "summary": {
            "sheets": len(rows),
            "graded": sum(row["status"] == "graded" for row in rows.values()),
            "unmatched": sum(row["student_id"] is None and row["status"] in ("grading", "graded") for row in rows.values()),
            "flagged": sum(bool(c["flagged"]) for c in cells),
            "failed": sum(c["status"] == "failed" for c in cells),
            "average": sum(totals) / len(totals) if totals else None,
        },
    }


@router.get("/exams/{exam_id}/results")
def get_results(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        own_exam(conn, exam_id, user)
        return results(conn, exam_id)


@router.get("/answers/{answer_id}")
def get_answer(answer_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        answer = own_answer(conn, answer_id, user)
        question = conn.execute(
            "SELECT number, text, reference_answer, max_marks FROM questions WHERE question_id = %s", (answer["question_id"],)
        ).fetchone()
        student = conn.execute(
            "SELECT student_id, name FROM students WHERE student_id = %s", (answer["student_id"],)
        ).fetchone()
        grade = conn.execute("SELECT * FROM grades WHERE answer_id = %s", (answer_id,)).fetchone()
        feedback = conn.execute("SELECT text FROM feedback WHERE answer_id = %s", (answer_id,)).fetchone()
        judges = defaultdict(dict)
        for j in conn.execute("SELECT point_id, model, marks FROM judgments WHERE answer_id = %s", (answer_id,)):
            judges[j["point_id"]][j["model"]] = j["marks"]
        points = conn.execute(
            "SELECT rp.point_id, rp.description, rp.marks, pr.marks AS final, pr.evidence "
            "FROM rubric_points rp LEFT JOIN point_results pr ON pr.point_id = rp.point_id AND pr.answer_id = %s "
            "WHERE rp.question_id = %s ORDER BY rp.position",
            (answer_id, answer["question_id"]),
        ).fetchall()
    return {
        "answer_id": answer_id,
        "status": answer["status"],
        "text": answer["text"],
        "read_confidence": answer["read_confidence"],
        "scan_url": storage.url(answer["s3_key"]),
        "scan_type": answer["content_type"],
        "exam_status": answer["exam_status"],
        "student": student,
        "question": question,
        "grade": grade,
        "points": [{**p, "judges": judges[p["point_id"]]} for p in points],
        "web_evidence": answer["web_evidence"],
        "feedback": feedback["text"] if feedback else None,
    }


@router.put("/answers/{answer_id}/grade")
def override_grade(answer_id: int, body: MarksIn, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        answer = own_answer(conn, answer_id, user)
        set_override(conn, answer, body.marks)
    return {"ok": True}


def set_override(conn, answer, marks):
    maximum = conn.execute("SELECT max_marks FROM questions WHERE question_id = %s", (answer["question_id"],)).fetchone()["max_marks"]
    if marks is not None and marks > maximum:
        raise HTTPException(422, f"This question is worth {maximum:g} marks at most.")
    if marks is None:
        conn.execute("UPDATE grades SET override_marks = NULL WHERE answer_id = %s", (answer["answer_id"],))
    else:
        conn.execute(
            "INSERT INTO grades (answer_id, final_marks, max_marks, judges, flagged, flag_reasons, override_marks) "
            "VALUES (%s, 0, %s, 0, true, ARRAY['graded by teacher'], %s) "
            "ON CONFLICT (answer_id) DO UPDATE SET override_marks = EXCLUDED.override_marks",
            (answer["answer_id"], maximum, marks),
        )
    if answer["status"] != "graded":
        mark_graded(conn, answer["answer_id"], answer["submission_id"], answer["exam_id"])
    else:
        conn.execute("SELECT pg_notify('grades', %s)", (f"{answer['exam_id']}:{answer['answer_id']}",))


@router.put("/submissions/{submission_id}/student")
def assign_student(submission_id: int, body: AssignIn, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        submission = conn.execute(
            "SELECT s.exam_id FROM submissions s JOIN exams e USING (exam_id) WHERE s.submission_id = %s AND e.owner_id = %s",
            (submission_id, user.user_id),
        ).fetchone()
        if submission is None:
            raise HTTPException(404, "Sheet not found.")
        on_roster = conn.execute(
            "SELECT 1 FROM exam_students WHERE exam_id = %s AND student_id = %s", (submission["exam_id"], body.student_id)
        ).fetchone()
        if not on_roster:
            raise HTTPException(422, "That student isn't on this exam's roster.")
        try:
            conn.execute("UPDATE submissions SET student_id = %s WHERE submission_id = %s", (body.student_id, submission_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "That student already has a sheet for this exam.")
        conn.execute("SELECT pg_notify('grades', %s)", (f"{submission['exam_id']}:0",))
    return {"ok": True}


@router.post("/exams/{exam_id}/release")
def release(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        require_status(own_exam(conn, exam_id, user), "ready", message="This exam can't be released yet.")
        waiting = conn.execute(
            "SELECT count(*) FILTER (WHERE status <> 'graded') AS grading, count(*) FILTER (WHERE student_id IS NULL) AS unmatched "
            "FROM submissions WHERE exam_id = %s",
            (exam_id,),
        ).fetchone()
        if waiting["grading"] or waiting["unmatched"]:
            reasons = [f"{waiting['grading']} still grading"] if waiting["grading"] else []
            reasons += [f"{waiting['unmatched']} without a student assigned"] if waiting["unmatched"] else []
            raise HTTPException(409, f"Can't release yet: {' and '.join(reasons)}.")
        conn.execute("UPDATE exams SET status = 'released', released_at = now() WHERE exam_id = %s", (exam_id,))
    return {"ok": True}


@router.get("/exams/{exam_id}/regrades")
def list_regrades(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        own_exam(conn, exam_id, user)
        return conn.execute(
            "SELECT r.request_id, r.answer_id, r.reason, r.status, r.created_at, st.name, q.number "
            "FROM regrade_requests r JOIN answers a USING (answer_id) JOIN submissions s USING (submission_id) "
            "JOIN students st ON st.student_id = r.student_id JOIN questions q ON q.question_id = a.question_id "
            "WHERE s.exam_id = %s ORDER BY r.status, r.created_at",
            (exam_id,),
        ).fetchall()


@router.post("/regrades/{request_id}/resolve")
def resolve_regrade(request_id: int, body: MarksIn, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        request = conn.execute("SELECT answer_id FROM regrade_requests WHERE request_id = %s", (request_id,)).fetchone()
        if request is None:
            raise HTTPException(404, "Request not found.")
        answer = own_answer(conn, request["answer_id"], user)
        if body.marks is not None:
            set_override(conn, answer, body.marks)
        conn.execute("UPDATE regrade_requests SET status = 'resolved', resolved_at = now() WHERE request_id = %s", (request_id,))
    return {"ok": True}


@router.get("/exams/{exam_id}/stats")
def get_stats(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        own_exam(conn, exam_id, user)
        return {
            "questions": conn.execute("SELECT * FROM question_stats WHERE exam_id = %s ORDER BY number", (exam_id,)).fetchall(),
            "judges": conn.execute("SELECT * FROM judge_stats WHERE exam_id = %s ORDER BY model", (exam_id,)).fetchall(),
        }


@router.get("/exams/{exam_id}/export")
def export_csv(exam_id: int, user: User = Depends(require_teacher)):
    with db.connection() as conn:
        exam = own_exam(conn, exam_id, user)
        data = results(conn, exam_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["student_id", "name", *[f"Q{q['number']}" for q in data["questions"]], "total"])
    for row in data["rows"]:
        cells = [row["cells"].get(q["number"], {}).get("marks") for q in data["questions"]]
        writer.writerow([row["student_id"] or "", row["name"] or "", *cells, row["total"]])
    filename = f"{exam['title']}.csv".replace('"', "")
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/exams/{exam_id}/events")
async def events(exam_id: int, token: str):
    user = await run_in_threadpool(user_from_token, token)
    if user.role not in ("teacher", "admin"):
        raise HTTPException(403, "Only teachers can do this.")

    def check():
        with db.connection() as conn:
            own_exam(conn, exam_id, user)

    await run_in_threadpool(check)

    async def stream():
        async with await psycopg.AsyncConnection.connect(config.DATABASE_URL, autocommit=True) as conn:
            await conn.execute("LISTEN grades")
            yield "retry: 3000\n\n"
            while True:
                async for note in conn.notifies(timeout=15):
                    exam, answer = note.payload.split(":")
                    if exam == str(exam_id):
                        yield f"event: grade\ndata: {json.dumps({'answer_id': int(answer)})}\n\n"
                yield ": still here\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

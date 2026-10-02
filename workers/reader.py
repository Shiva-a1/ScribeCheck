from shared import config, db, grading, kafka, llm, prompts, storage
from shared.schemas import ReadSheet


def handle(message):
    submission_id = message["submission_id"]
    with db.connection() as conn:
        sheet = conn.execute(
            "UPDATE submissions SET status = 'reading' WHERE submission_id = %s AND status IN ('queued', 'reading') "
            "RETURNING exam_id, s3_key, content_type",
            (submission_id,),
        ).fetchone()
        if sheet is None:
            return
        questions = conn.execute(
            "SELECT question_id, number, text FROM questions WHERE exam_id = %s ORDER BY number", (sheet["exam_id"],)
        ).fetchall()
        roster = [r["student_id"] for r in conn.execute(
            "SELECT student_id FROM exam_students WHERE exam_id = %s", (sheet["exam_id"],)
        )]

    listing = "\n".join(f"Question {q['number']}: {q['text'] or '(text not given)'}" for q in questions)
    read = llm.ask_claude(
        prompts.READER_SYSTEM,
        [llm.file_block(storage.get(sheet["s3_key"]), sheet["content_type"]),
         {"type": "text", "text": f"Questions on this exam:\n{listing}"}],
        ReadSheet,
        model=config.required("CLAUDE_VISION_MODEL"),
    )
    by_number = {a.number: a for a in read.answers}

    with db.connection() as conn:
        student_id = grading.match_student(read.student_id, roster)
        taken = student_id and conn.execute(
            "SELECT 1 FROM submissions WHERE exam_id = %s AND student_id = %s AND submission_id <> %s",
            (sheet["exam_id"], student_id, submission_id),
        ).fetchone()
        conn.execute(
            "UPDATE submissions SET read_student_id = %s, student_id = %s, status = 'grading' WHERE submission_id = %s",
            (read.student_id, None if taken else student_id, submission_id),
        )
        answer_ids = []
        for q in questions:
            found = by_number.get(q["number"])
            row = conn.execute(
                "INSERT INTO answers (submission_id, question_id, text, read_confidence) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (submission_id, question_id) DO UPDATE SET text = EXCLUDED.text RETURNING answer_id",
                (submission_id, q["question_id"], found.text if found else "", found.confidence if found else 1.0),
            ).fetchone()
            answer_ids.append(row["answer_id"])

    for answer_id in answer_ids:
        kafka.publish("answers", answer_id, {"answer_id": answer_id})


if __name__ == "__main__":
    kafka.run("sheets", "reader", handle)

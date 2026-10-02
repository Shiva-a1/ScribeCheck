from collections import defaultdict

from shared import db, grading, kafka

MAX_RETRIES = 2


def finalize(conn, answer_id, allow_partial=False):
    answer = conn.execute(
        "SELECT a.status, a.read_confidence, a.web_evidence, a.question_id, a.submission_id, s.exam_id "
        "FROM answers a JOIN submissions s USING (submission_id) WHERE a.answer_id = %s FOR UPDATE OF a",
        (answer_id,),
    ).fetchone()
    if answer is None or answer["status"] == "graded":
        return False

    rows = conn.execute("SELECT model, point_id, marks, evidence FROM judgments WHERE answer_id = %s", (answer_id,)).fetchall()
    by_model, quotes = defaultdict(dict), defaultdict(list)
    for r in rows:
        by_model[r["model"]][r["point_id"]] = float(r["marks"])
        if r["evidence"] and r["marks"] > 0:
            quotes[r["point_id"]].append(r["evidence"])
    needed = 2 if allow_partial else len(grading.JUDGES)
    if len(by_model) < needed:
        return False

    points = {r["point_id"]: float(r["marks"]) for r in conn.execute(
        "SELECT point_id, marks FROM rubric_points WHERE question_id = %s", (answer["question_id"],)
    )}
    per_point, total, spread = grading.combine(list(by_model.values()), points)
    web = answer["web_evidence"] or {}
    reasons = grading.flag_reasons(spread, len(by_model), answer["read_confidence"], web.get("contradicts_key", False))

    for point_id, marks in per_point.items():
        conn.execute(
            "INSERT INTO point_results (answer_id, point_id, marks, evidence) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (answer_id, point_id) DO UPDATE SET marks = EXCLUDED.marks, evidence = EXCLUDED.evidence",
            (answer_id, point_id, marks, quotes[point_id][0] if marks > 0 and quotes[point_id] else ""),
        )
    conn.execute(
        "INSERT INTO grades (answer_id, final_marks, max_marks, judges, flagged, flag_reasons) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (answer_id) DO UPDATE SET final_marks = EXCLUDED.final_marks, "
        "max_marks = EXCLUDED.max_marks, judges = EXCLUDED.judges, flagged = EXCLUDED.flagged, "
        "flag_reasons = EXCLUDED.flag_reasons, graded_at = now()",
        (answer_id, total, sum(points.values()), len(by_model), bool(reasons), reasons),
    )
    mark_graded(conn, answer_id, answer["submission_id"], answer["exam_id"])
    return True


def mark_graded(conn, answer_id, submission_id, exam_id):
    conn.execute("UPDATE answers SET status = 'graded' WHERE answer_id = %s", (answer_id,))
    conn.execute(
        "UPDATE submissions SET status = 'graded' WHERE submission_id = %s "
        "AND NOT EXISTS (SELECT 1 FROM answers WHERE submission_id = %s AND status <> 'graded')",
        (submission_id, submission_id),
    )
    conn.execute("SELECT pg_notify('grades', %s)", (f"{exam_id}:{answer_id}",))


def handle(message):
    with db.connection() as conn:
        done = finalize(conn, message["answer_id"])
    if done:
        kafka.publish("graded", message["answer_id"], {"answer_id": message["answer_id"]})


def sweep():
    with db.connection() as conn:
        stuck = conn.execute(
            "SELECT answer_id, retries FROM answers WHERE status = 'judging' AND dispatched_at < now() - interval '5 minutes'"
        ).fetchall()
    for row in stuck:
        with db.connection() as conn:
            if finalize(conn, row["answer_id"], allow_partial=True):
                graded, retry = True, False
            elif row["retries"] < MAX_RETRIES:
                conn.execute(
                    "UPDATE answers SET retries = retries + 1, dispatched_at = now() WHERE answer_id = %s", (row["answer_id"],)
                )
                graded, retry = False, True
            else:
                conn.execute("UPDATE answers SET status = 'failed' WHERE answer_id = %s", (row["answer_id"],))
                graded, retry = False, False
        if graded:
            kafka.publish("graded", row["answer_id"], {"answer_id": row["answer_id"]})
        if retry:
            kafka.publish("evidence", row["answer_id"], {"answer_id": row["answer_id"]})


if __name__ == "__main__":
    kafka.run("judgments", "aggregator", handle, every=60, on_tick=sweep)

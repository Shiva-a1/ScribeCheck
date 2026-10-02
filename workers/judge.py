from shared import config, db, kafka, llm, prompts
from shared.schemas import Judgment

ANSWER = """
    SELECT a.answer_id, a.text, a.web_evidence, a.question_id, q.text AS question, q.reference_answer, q.notes_pack
    FROM answers a JOIN questions q USING (question_id)
    WHERE a.answer_id = %s
"""


def handle(message, judge):
    answer_id = message["answer_id"]
    with db.connection() as conn:
        done = conn.execute(
            "SELECT 1 FROM judgments WHERE answer_id = %s AND model = %s LIMIT 1", (answer_id, judge)
        ).fetchone()
        row = None if done else conn.execute(ANSWER, (answer_id,)).fetchone()
        points = [] if done or row is None else conn.execute(
            "SELECT point_id, description, marks FROM rubric_points WHERE question_id = %s ORDER BY position",
            (row["question_id"],),
        ).fetchall()

    if row is not None and not done:
        verdicts = {}
        if row["text"].strip():
            prompt = prompts.judge_prompt(
                row["question"], row["reference_answer"], points, row["text"], row["notes_pack"], row["web_evidence"]
            )
            result = llm.ask_judge(judge, prompts.JUDGE_SYSTEM, prompt, Judgment)
            verdicts = {p.point_id: p for p in result.points}
        with db.connection() as conn:
            for point in points:
                verdict = verdicts.get(point["point_id"])
                conn.execute(
                    "INSERT INTO judgments (answer_id, model, point_id, marks, evidence) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (answer_id, judge, point["point_id"], verdict.marks if verdict else 0, verdict.evidence if verdict else ""),
                )

    kafka.publish("judgments", answer_id, {"answer_id": answer_id, "model": judge})


if __name__ == "__main__":
    judge = config.required("JUDGE")
    kafka.run("evidence", f"judge-{judge}", lambda message: handle(message, judge))

from shared import db, kafka, llm, prompts

ANSWER = """
    SELECT a.answer_id, a.text, q.text AS question, q.notes_pack, g.final_marks, g.max_marks
    FROM answers a JOIN questions q USING (question_id) JOIN grades g USING (answer_id)
    WHERE a.answer_id = %s
"""
RESULTS = """
    SELECT rp.description, rp.marks AS max, pr.marks
    FROM point_results pr JOIN rubric_points rp USING (point_id)
    WHERE pr.answer_id = %s ORDER BY rp.position
"""


def write_feedback(row, results):
    if not row["text"].strip():
        return "No answer was found for this question on your sheet. Review this topic in the notes and practise writing out the key points."
    if row["final_marks"] >= row["max_marks"]:
        return "Full marks. You covered every point this question asked for."
    return llm.ask_claude_text(
        prompts.FEEDBACK_SYSTEM, prompts.feedback_prompt(row["question"], row["text"], row["notes_pack"], results)
    )


def handle(message):
    answer_id = message["answer_id"]
    with db.connection() as conn:
        if conn.execute("SELECT 1 FROM feedback WHERE answer_id = %s", (answer_id,)).fetchone():
            return
        row = conn.execute(ANSWER, (answer_id,)).fetchone()
        if row is None:
            return
        results = conn.execute(RESULTS, (answer_id,)).fetchall()
    text = write_feedback(row, results)
    with db.connection() as conn:
        conn.execute("INSERT INTO feedback (answer_id, text) VALUES (%s, %s) ON CONFLICT DO NOTHING", (answer_id, text))


if __name__ == "__main__":
    kafka.run("graded", "feedback", handle)

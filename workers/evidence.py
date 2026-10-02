from psycopg.types.json import Jsonb

from shared import db, kafka, llm, prompts
from shared.schemas import Coverage, WebVerdict

ANSWER = """
    SELECT a.answer_id, a.text, a.web_evidence, q.question_id, q.exam_id, q.text AS question,
           q.reference_answer, q.notes_pack
    FROM answers a JOIN questions q USING (question_id)
    WHERE a.answer_id = %s
"""


def notes_pack(conn, row):
    if row["notes_pack"] is not None:
        return row["notes_pack"]
    has_notes = conn.execute("SELECT 1 FROM note_chunks WHERE exam_id = %s LIMIT 1", (row["exam_id"],)).fetchone()
    pack = ""
    if has_notes:
        [vector] = llm.embed([f"{row['question']}\n{row['reference_answer']}"])
        chunks = conn.execute(
            "SELECT content FROM note_chunks WHERE exam_id = %s ORDER BY embedding <=> %s LIMIT 4",
            (row["exam_id"], vector),
        ).fetchall()
        pack = "\n\n".join(c["content"] for c in chunks)
    conn.execute("UPDATE questions SET notes_pack = %s WHERE question_id = %s", (pack, row["question_id"]))
    return pack


def gather(row, pack):
    evidence = {"claims": [], "summary": "", "sources": [], "contradicts_key": False}
    if not row["text"].strip():
        return evidence
    coverage = llm.ask_claude(
        prompts.COVERAGE_SYSTEM,
        prompts.coverage_prompt(row["question"], row["reference_answer"], pack, row["text"]),
        Coverage,
    )
    if not coverage.uncovered_claims:
        return evidence
    research, sources = llm.web_search(prompts.web_prompt(row["question"], row["reference_answer"], coverage.uncovered_claims))
    verdict = llm.ask_claude(prompts.VERDICT_SYSTEM, prompts.verdict_prompt(row["reference_answer"], research), WebVerdict)
    return {
        "claims": coverage.uncovered_claims,
        "summary": verdict.summary,
        "sources": sources,
        "contradicts_key": verdict.contradicts_key,
    }


def handle(message):
    answer_id = message["answer_id"]
    with db.connection() as conn:
        row = conn.execute(ANSWER, (answer_id,)).fetchone()
        if row is None:
            return
        pack = notes_pack(conn, row)
    evidence = row["web_evidence"] if row["web_evidence"] is not None else gather(row, pack)
    with db.connection() as conn:
        conn.execute(
            "UPDATE answers SET web_evidence = %s, status = 'judging', dispatched_at = now() "
            "WHERE answer_id = %s AND status IN ('pending', 'judging')",
            (Jsonb(evidence), answer_id),
        )
    kafka.publish("evidence", answer_id, {"answer_id": answer_id})


if __name__ == "__main__":
    kafka.run("answers", "evidence", handle)

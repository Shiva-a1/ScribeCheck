import os
import sys

import psycopg

CHECKS = {
    "grades outside 0 and the question's marks":
        "SELECT count(*) FROM grades g JOIN answers a USING (answer_id) JOIN questions q USING (question_id) "
        "WHERE coalesce(g.override_marks, g.final_marks) NOT BETWEEN 0 AND q.max_marks",
    "rubric point results above the point's value":
        "SELECT count(*) FROM point_results pr JOIN rubric_points rp USING (point_id) WHERE pr.marks > rp.marks",
    "machine grades from fewer than 2 judges":
        "SELECT count(*) FROM grades WHERE judges = 1",
    "answers stuck judging for over an hour":
        "SELECT count(*) FROM answers WHERE status = 'judging' AND dispatched_at < now() - interval '1 hour'",
    "graded answers with no feedback after an hour":
        "SELECT count(*) FROM grades g LEFT JOIN feedback f USING (answer_id) WHERE f.answer_id IS NULL "
        "AND g.graded_at < now() - interval '1 hour'",
}

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    failures = {name: conn.execute(sql).fetchone()[0] for name, sql in CHECKS.items()}

for name, count in failures.items():
    print(f"{'FAIL' if count else 'ok  '} {name}: {count}")
sys.exit(1 if any(failures.values()) else 0)

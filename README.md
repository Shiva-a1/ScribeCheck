# Scribe-Check

Grades scanned short-answer exam sheets by meaning, not wording. A teacher uploads the answer key, notes, roster and scans; Claude reads each sheet, three independent judges (Claude, GPT, Gemini) grade every rubric point, and the median mark stands. Disagreements are flagged, students get feedback, and they see results once the teacher releases them.

```
sheets ─▶ reader ─▶ answers ─▶ evidence ─▶ evidence ─┬▶ judge (claude) ─┐
(topic)   worker    (topic)    worker      (topic)   ├▶ judge (openai) ─┼▶ judgments ─▶ aggregator ─▶ graded ─▶ feedback
                                                     └▶ judge (gemini) ─┘   (topic)                  (topic)    writer
```

Every worker reads one Kafka topic, does one job, writes to Postgres and publishes the next message. Messages carry only IDs; Postgres holds the state.

## Run it locally

You need Docker and API keys for Anthropic, OpenAI and Google Gemini.

```bash
cp .env.example .env              # fill in the three API keys and OPENAI_MODEL / GEMINI_MODEL
docker compose up --build
docker compose exec api python -m scripts.add_teacher you@ufl.edu "Your Name"
```

Open http://localhost:8000 and sign in with that email. `samples/` has an answer key, notes and a roster to try. Students on the roster can sign in with their own email to see released results.

The nightly report (Airflow + PySpark) is optional: `docker compose --profile analytics up airflow`, then open http://localhost:8080 and trigger `scribe_nightly`.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                                    # unit tests
TEST_DATABASE_URL=postgresql://scribe:scribe@localhost:5432/scribe pytest   # adds database tests
```

The database tests need a Postgres with `db/schema.sql` loaded (the compose database works). They check row-level security and run one exam through the API and all five workers, with stand-ins for the AI APIs, S3 and Kafka. CI runs everything on each push.

## Measure grading quality

Download the Mohler short-answer dataset as a CSV (columns `question, desired_answer, student_answer, score_me, score_other, score_avg`; pass `--help` to rename them) into `data/`.

```bash
python -m eval.mohler_eval data/mohler.csv --split dev                  # tune prompts on this
python -m eval.mohler_eval data/mohler.csv --split test                 # run once, at the end
python -m eval.attacks data/mohler.csv                                  # paraphrase, keyword stuffing, prompt injection
python -m eval.mohler_eval data/mohler.csv --split dev --export-golden 50
python -m eval.golden                                                   # fails if MAE rises above 0.6
python -m eval.iam_eval data/iam/lines data/iam/labels.tsv --trocr      # Claude vs TrOCR reading
```

Every number comes with a 95% bootstrap confidence interval, and "human vs human" is the bar to beat. API calls are cached in `eval/cache/`, so reruns are free.

## Deploy

1. Create an S3 bucket (default encryption on), a Cognito user pool with a hosted domain and an app client with callback URL `https://your-domain/`, and an EC2 instance with at least 8 GB of RAM.
2. In `.env`, set `AUTH_MODE=cognito`, the four `COGNITO_` values, a long random `DEV_SECRET`, and clear `S3_ENDPOINT` and `S3_PUBLIC_ENDPOINT`. Give the instance an IAM role for S3 and Cognito instead of access keys.
3. Get a certificate with certbot, set your domain in `deploy/nginx.conf`, then `docker compose --profile prod up -d`.

## Reading the code

Read it in this order; each step builds on the last.

1. `db/schema.sql`: every table, and the row-level security policies at the bottom.
2. `shared/grading.py` and `tests/test_grading.py`: the median, capping and flag rules.
3. `shared/prompts.py`: what each model is asked, and how student text is kept from acting as instructions.
4. `shared/llm.py`: one function per kind of model call, and how the three providers differ.
5. `shared/kafka.py`: the consume, retry, dead-letter, commit loop every worker uses.
6. `workers/` in pipeline order: reader, evidence, judge, aggregator, feedback.
7. `api/auth.py`, then `api/teacher.py` and `api/student.py` (note `as_student`).
8. `frontend/app.js`, then `teacher.js` and `student.js`.
9. `eval/metrics.py`, then the eval scripts.
10. `tests/test_pipeline.py`: the whole system in one test.

## Status

Tested here: all unit tests, the schema and row-level security on Postgres 16 with pgvector, the full API-to-workers flow with stand-in model calls, live updates from Postgres to the browser over Server-Sent Events, and every screen in a headless browser.

Not yet run: real calls to the three model APIs, Kafka, MinIO and the Docker images, the Airflow DAG and PySpark job, Cognito sign-in, and the evaluation scripts on real data. Expect small fixes the first time each of these runs.

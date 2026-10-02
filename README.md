# Scribe-Check

**A multi-LLM grading pipeline for handwritten exams.** A teacher uploads an answer key, course notes, a class roster and scanned answer sheets. Claude reads each sheet, three independent judges (Claude, GPT and Gemini) grade every answer against the key, and the median mark stands. Answers the judges disagree on are flagged for review, and students sign in to see their marks and feedback once the teacher releases them.

![Teacher dashboard](images/teacher_dashboard.png)

## How it works

```
sheets ─▶ reader ─▶ answers ─▶ evidence ─▶ evidence ─┬▶ judge (claude) ─┐
(topic)   worker    (topic)    worker      (topic)   ├▶ judge (openai) ─┼▶ judgments ─▶ aggregator ─▶ graded ─▶ feedback
                                                     └▶ judge (gemini) ─┘   (topic)                  (topic)    writer
```

1. **Read.** Claude vision transcribes each sheet and reads the student ID, which is matched against the roster.
2. **Gather evidence.** The relevant sections of the teacher's notes are retrieved with pgvector, once per question. If neither the key nor the notes cover a claim, Claude checks it with web search.
3. **Judge.** Three models grade each rubric point independently. They grade by meaning, not wording, and the answer key always takes priority.
4. **Combine.** Marks are capped at each point's value and the median is taken per point. An answer is flagged if the judges differ by more than one mark, the handwriting was hard to read, or the web contradicts the key.
5. **Feedback.** Claude writes improvement notes from the points the student missed.

Each worker reads one Kafka topic, does one job and writes its result to PostgreSQL. Messages carry only IDs, and the database holds the state.

## Features

- **Marking scheme from any answer key.** Claude turns a PDF, photo or text key into rubric points, and the teacher confirms them once per exam. Code checks that the points add up to each question's marks.
- **Three-judge grading with fallback.** If a provider fails or hits its quota, the answer is graded by the remaining two after a timeout and flagged, so grading never stalls.
- **Reliable processing.** Retries, a dead-letter topic, duplicate-safe writes, and Kafka offsets committed only after the database write succeeds.
- **Teacher dashboard.** Grades appear live over Server-Sent Events, with per-judge marks and evidence for every answer, mark overrides, unmatched-sheet assignment, regrade requests and CSV export.
- **Student portal.** Students see their marks, what earned them, what they missed and the feedback, and can request a regrade.
- **Data isolation.** PostgreSQL row-level security means a student can only ever read their own results, even if an API query forgets a filter.
- **Prompt-injection safeguards.** Student text is treated as untrusted data and kept from closing its own prompt tags.

## Tech stack

Python, FastAPI, PostgreSQL with pgvector, Kafka, Docker Compose, Claude, OpenAI and Gemini APIs, HTML/CSS/JavaScript, Airflow and PySpark (nightly class report), GitHub Actions.

## Running it locally

You need Docker Desktop (with at least 6 GB of memory) and API keys for Anthropic, OpenAI and Google Gemini.

```bash
cp .env.example .env              # add your three API keys and model names
docker compose up --build
docker compose exec api python -m scripts.add_teacher you@ufl.edu "Your Name"
```

Open http://localhost:8000 and sign in with that email. To try it out, create an exam and upload the files in `samples/` in this order: answer key, confirm the scheme, roster, notes, then answer sheets.

## API keys and costs

| Provider | Used for | Model setting |
| --- | --- | --- |
| Anthropic | Reading sheets, rubric building, evidence checks, one judge, feedback | `CLAUDE_MODEL`, `CLAUDE_VISION_MODEL` |
| OpenAI | One judge, embeddings for the teacher's notes | `OPENAI_MODEL` (e.g. `gpt-5-mini`) |
| Google Gemini | One judge | `GEMINI_MODEL` (e.g. `gemini-3.5-flash`) |

Keys live only in `.env`, which is excluded from Git. Grading a sheet costs a few cents across the three providers (estimated; measured figures to follow). Gemini's free tier allows about 20 grading requests a day per model, after which answers fall back to two judges.

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
TEST_DATABASE_URL=postgresql://scribe:scribe@localhost:5432/scribe pytest
```

The second run adds the database tests. They verify row-level security and push exams through the API and all five workers, with stand-ins for the AI providers, S3 and Kafka. CI runs the full suite on every push.

## Evaluation (in progress)

Grading is evaluated against human scores on the Mohler short-answer dataset (2,273 answers to 79 computer-science questions, each graded by two people), using quadratic weighted kappa, mean absolute error and bootstrap 95% confidence intervals. The bar to beat is the human graders themselves: on a 100-answer sample, they agree at a QWK of 0.47 (95% CI 0.35–0.62).

## Lessons from the first live run

Running the system end to end against live services surfaced problems that unit tests couldn't:

- **A dependency disappeared upstream.** MinIO removed its free image from Docker Hub, which broke local S3 storage. The compose file now uses `bitnamilegacy/minio`.
- **SDK and model changes.** The current Anthropic SDK no longer accepts a `temperature` argument, and newer Claude models reject forced tool calls. Structured output now asks for the tool without forcing it, and falls back to parsing JSON from text.
- **Quota limits.** Gemini's free-tier daily limit was hit mid-run. The two-judge timeout handled it as designed, and every affected answer was flagged.
- **Ordering of uploads.** Sheets uploaded before the roster stayed unmatched. Adding a roster now re-matches them automatically by the ID read from each sheet.

## Project structure

```
api/          FastAPI app: auth, teacher routes, student routes
workers/      reader, evidence, judge, aggregator, feedback
shared/       config, database, Kafka, storage, LLM clients, prompts, grading logic
db/           schema.sql, including row-level security policies
frontend/     teacher dashboard, student portal, sign-in
pipelines/    Airflow DAG, data-quality checks, PySpark stats
eval/         metrics, Mohler evaluation, robustness tests, golden-set gate
tests/        unit, security and end-to-end tests
deploy/       nginx configuration for HTTPS
```

## Roadmap

- Complete the Mohler evaluation on the held-out test split.
- Add Prometheus metrics, OpenTelemetry tracing and Grafana dashboards.
- Deploy on Kubernetes with Helm.
- Measure throughput and cost per sheet with one worker versus three.

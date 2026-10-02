CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE,
    name text NOT NULL DEFAULT '',
    role text NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE students (
    student_id text PRIMARY KEY,
    user_id bigint UNIQUE REFERENCES users,
    name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE exams (
    exam_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL REFERENCES users,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready', 'released')),
    scheme_confirmed_at timestamptz,
    released_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE exam_students (
    exam_id bigint REFERENCES exams ON DELETE CASCADE,
    student_id text REFERENCES students,
    PRIMARY KEY (exam_id, student_id)
);

CREATE TABLE questions (
    question_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id bigint NOT NULL REFERENCES exams ON DELETE CASCADE,
    number int NOT NULL,
    text text NOT NULL DEFAULT '',
    reference_answer text NOT NULL,
    max_marks numeric NOT NULL CHECK (max_marks >= 0),
    notes_pack text,
    UNIQUE (exam_id, number)
);

CREATE TABLE rubric_points (
    point_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES questions ON DELETE CASCADE,
    description text NOT NULL,
    marks numeric NOT NULL CHECK (marks > 0),
    position int NOT NULL
);

CREATE TABLE note_chunks (
    chunk_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id bigint NOT NULL REFERENCES exams ON DELETE CASCADE,
    content text NOT NULL,
    embedding vector(1536) NOT NULL
);
CREATE INDEX note_chunks_embedding ON note_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE submissions (
    submission_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id bigint NOT NULL REFERENCES exams ON DELETE CASCADE,
    student_id text REFERENCES students,
    read_student_id text,
    s3_key text NOT NULL,
    content_type text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'reading', 'grading', 'graded', 'failed')),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (exam_id, student_id)
);
CREATE INDEX submissions_exam ON submissions (exam_id);

CREATE TABLE answers (
    answer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    submission_id bigint NOT NULL REFERENCES submissions ON DELETE CASCADE,
    question_id bigint NOT NULL REFERENCES questions ON DELETE CASCADE,
    text text NOT NULL DEFAULT '',
    read_confidence real,
    web_evidence jsonb,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'judging', 'graded', 'failed')),
    dispatched_at timestamptz,
    retries int NOT NULL DEFAULT 0,
    UNIQUE (submission_id, question_id)
);
CREATE INDEX answers_waiting ON answers (status, dispatched_at);

CREATE TABLE judgments (
    answer_id bigint REFERENCES answers ON DELETE CASCADE,
    model text,
    point_id bigint REFERENCES rubric_points ON DELETE CASCADE,
    marks numeric NOT NULL,
    evidence text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (answer_id, model, point_id)
);

CREATE TABLE point_results (
    answer_id bigint REFERENCES answers ON DELETE CASCADE,
    point_id bigint REFERENCES rubric_points ON DELETE CASCADE,
    marks numeric NOT NULL,
    evidence text NOT NULL DEFAULT '',
    PRIMARY KEY (answer_id, point_id)
);

CREATE TABLE grades (
    answer_id bigint PRIMARY KEY REFERENCES answers ON DELETE CASCADE,
    final_marks numeric NOT NULL,
    max_marks numeric NOT NULL,
    judges int NOT NULL,
    flagged boolean NOT NULL,
    flag_reasons text[] NOT NULL DEFAULT '{}',
    override_marks numeric,
    graded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    answer_id bigint PRIMARY KEY REFERENCES answers ON DELETE CASCADE,
    text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE regrade_requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    answer_id bigint NOT NULL UNIQUE REFERENCES answers ON DELETE CASCADE,
    student_id text NOT NULL REFERENCES students,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

-- Written by the nightly PySpark job.
CREATE TABLE question_stats (
    exam_id bigint,
    question_id bigint,
    number int,
    answers bigint,
    mean_score double precision,
    stddev double precision,
    flag_rate double precision,
    computed_at timestamptz
);

CREATE TABLE judge_stats (
    exam_id bigint,
    model text,
    answers bigint,
    mean_gap double precision,
    within_one double precision,
    computed_at timestamptz
);

-- Students reach the database only through this role, so these policies
-- decide what they can see even if an API query forgets a filter.
DO $$ BEGIN
    CREATE ROLE student_api NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
GRANT student_api TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO student_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO student_api;
GRANT SELECT ON exams, exam_students, questions, rubric_points, submissions,
    answers, point_results, grades, feedback, regrade_requests TO student_api;
GRANT INSERT ON regrade_requests TO student_api;

ALTER TABLE exam_students ENABLE ROW LEVEL SECURITY;
ALTER TABLE exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rubric_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE point_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE grades ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE regrade_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY own_enrolment ON exam_students FOR SELECT TO student_api
    USING (student_id = current_setting('app.student_id', true));
CREATE POLICY released_exams ON exams FOR SELECT TO student_api
    USING (released_at IS NOT NULL AND exam_id IN (SELECT exam_id FROM exam_students));
CREATE POLICY visible_questions ON questions FOR SELECT TO student_api
    USING (exam_id IN (SELECT exam_id FROM exams));
CREATE POLICY visible_points ON rubric_points FOR SELECT TO student_api
    USING (question_id IN (SELECT question_id FROM questions));
CREATE POLICY own_submissions ON submissions FOR SELECT TO student_api
    USING (student_id = current_setting('app.student_id', true) AND exam_id IN (SELECT exam_id FROM exams));
CREATE POLICY own_answers ON answers FOR SELECT TO student_api
    USING (submission_id IN (SELECT submission_id FROM submissions));
CREATE POLICY own_point_results ON point_results FOR SELECT TO student_api
    USING (answer_id IN (SELECT answer_id FROM answers));
CREATE POLICY own_grades ON grades FOR SELECT TO student_api
    USING (answer_id IN (SELECT answer_id FROM answers));
CREATE POLICY own_feedback ON feedback FOR SELECT TO student_api
    USING (answer_id IN (SELECT answer_id FROM answers));
CREATE POLICY own_regrades ON regrade_requests FOR SELECT TO student_api
    USING (student_id = current_setting('app.student_id', true));
CREATE POLICY request_own_regrades ON regrade_requests FOR INSERT TO student_api
    WITH CHECK (student_id = current_setting('app.student_id', true) AND answer_id IN (SELECT answer_id FROM answers));

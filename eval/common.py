import csv
import hashlib
import json
import random
import shelve
import threading
from pathlib import Path

import numpy as np

from shared import grading, llm, prompts
from shared.schemas import Judgment, Scheme
from shared.text import chunk_text, pdf_text

CACHE = Path(__file__).parent / "cache"
_lock = threading.Lock()


def cached(kind, payload, compute):
    CACHE.mkdir(exist_ok=True)
    key = hashlib.sha256(json.dumps([kind, payload], sort_keys=True).encode()).hexdigest()
    with _lock, shelve.open(str(CACHE / "calls")) as store:
        if key in store:
            return store[key]
    value = compute()
    with _lock, shelve.open(str(CACHE / "calls")) as store:
        store[key] = value
    return value


def load_mohler(path, question="question", reference="desired_answer", answer="student_answer",
                grader_a="score_me", grader_b="score_other", average="score_avg"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [{
        "id": i,
        "question": r[question].strip(),
        "reference": r[reference].strip(),
        "answer": r[answer].strip(),
        "grader_a": float(r[grader_a]),
        "grader_b": float(r[grader_b]),
        "human": float(r[average]),
    } for i, r in enumerate(rows)]


def split(rows, part, dev_share=0.3, seed=13):
    questions = sorted({r["question"] for r in rows})
    random.Random(seed).shuffle(questions)
    dev = set(questions[:round(len(questions) * dev_share)])
    return [r for r in rows if (r["question"] in dev) == (part == "dev")]


def rubric(question, reference, total=5.0):
    def compute():
        result = llm.ask_claude(prompts.SCHEME_SYSTEM, prompts.scheme_prompt(question, reference, total), Scheme)
        return [p.model_dump() for p in result.points]
    points = cached("scheme", [question, reference, total], compute)
    return [{"point_id": i + 1, **p} for i, p in enumerate(points)]


def judge(provider, question, reference, points, answer, notes=""):
    prompt = prompts.judge_prompt(question, reference, points, answer, notes)

    def compute():
        result = llm.ask_judge(provider, prompts.JUDGE_SYSTEM, prompt, Judgment)
        return {p.point_id: p.marks for p in result.points}
    return cached("judge", [provider, prompt], compute)


def grade(row, judges=grading.JUDGES, notes=""):
    points = rubric(row["question"], row["reference"])
    limits = {p["point_id"]: p["marks"] for p in points}
    if not row["answer"].strip():
        return {"median": 0.0, **{j: 0.0 for j in judges}}
    marks = {j: judge(j, row["question"], row["reference"], points, row["answer"], notes) for j in judges}
    singles = {j: sum(grading.cap(m.get(p, 0), limits[p]) for p in limits) for j, m in marks.items()}
    _, total, _ = grading.combine(list(marks.values()), limits)
    return {"median": total, **singles}


def embed(texts):
    return np.array(cached("embed", texts, lambda: [v.tolist() for v in llm.embed(texts)]))


class Notes:
    def __init__(self, path, k=4):
        data = Path(path).read_bytes()
        text = pdf_text(data) if path.endswith(".pdf") else data.decode()
        self.chunks = chunk_text(text)
        self.vectors = embed(self.chunks)
        self.vectors /= np.linalg.norm(self.vectors, axis=1, keepdims=True)
        self.k = k

    def pack(self, question, reference):
        query = embed([f"{question}\n{reference}"])[0]
        best = np.argsort(self.vectors @ (query / np.linalg.norm(query)))[::-1][: self.k]
        return "\n\n".join(self.chunks[i] for i in best)

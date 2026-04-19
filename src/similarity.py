"""
similarity.py — Hybrid text similarity scoring.
Levenshtein + BLEU + Cosine (sentence embeddings).
"""

import numpy as np


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            curr_row.append(min(prev_row[j + 1] + 1, curr_row[j] + 1, prev_row[j] + (c1 != c2)))
        prev_row = curr_row
    return prev_row[-1]


def levenshtein_similarity(prediction, reference):
    if not prediction and not reference:
        return 1.0
    max_len = max(len(prediction), len(reference))
    if max_len == 0:
        return 1.0
    return 1.0 - (levenshtein_distance(prediction, reference) / max_len)


def compute_bleu(prediction, reference):
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    if not prediction.strip() or not reference.strip():
        return 0.0
    smoothie = SmoothingFunction().method1
    try:
        return sentence_bleu([reference.lower().split()], prediction.lower().split(), smoothing_function=smoothie)
    except (ValueError, ZeroDivisionError):
        return 0.0


_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Loaded sentence-transformers: all-MiniLM-L6-v2")
    return _embedding_model


def cosine_similarity_score(prediction, reference):
    if not prediction.strip() or not reference.strip():
        return 0.0
    model = _get_embedding_model()
    embeddings = model.encode([prediction, reference])
    dot = np.dot(embeddings[0], embeddings[1])
    norm = np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
    return float(max(0.0, dot / norm)) if norm > 0 else 0.0


DEFAULT_WEIGHTS = {"levenshtein": 0.35, "bleu": 0.30, "cosine": 0.35}


def compute_hybrid_score(prediction, reference, weights=None, return_breakdown=False):
    if weights is None:
        weights = DEFAULT_WEIGHTS
    lev = levenshtein_similarity(prediction, reference)
    bleu = compute_bleu(prediction, reference)
    cos = cosine_similarity_score(prediction, reference)
    combined = weights["levenshtein"] * lev + weights["bleu"] * bleu + weights["cosine"] * cos
    result = {"combined_score": round(combined, 4)}
    if return_breakdown:
        result["levenshtein"] = round(lev, 4)
        result["bleu"] = round(bleu, 4)
        result["cosine"] = round(cos, 4)
    return result

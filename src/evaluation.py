"""
evaluation.py — CER, WER, batch evaluation, and cascade failure analysis.
"""

from jiwer import wer, cer


def compute_cer(prediction, reference):
    if not reference.strip():
        return 0.0 if not prediction.strip() else 1.0
    return cer(reference, prediction)


def compute_wer(prediction, reference):
    if not reference.strip():
        return 0.0 if not prediction.strip() else 1.0
    return wer(reference, prediction)


def evaluate_ocr_batch(predictions, references):
    assert len(predictions) == len(references)
    results = []
    for pred, ref in zip(predictions, references):
        results.append({
            "prediction": pred, "reference": ref,
            "cer": round(compute_cer(pred, ref), 4),
            "wer": round(compute_wer(pred, ref), 4),
        })
    mean_cer = sum(r["cer"] for r in results) / len(results)
    mean_wer = sum(r["wer"] for r in results) / len(results)
    return {"mean_cer": round(mean_cer, 4), "mean_wer": round(mean_wer, 4),
            "num_samples": len(results), "per_sample": results}


def cascade_analysis(predictions, references, cer_threshold=0.1):
    from src.similarity import compute_hybrid_score
    good_ocr, poor_ocr = [], []
    for pred, ref in zip(predictions, references):
        sample_cer = compute_cer(pred, ref)
        similarity = compute_hybrid_score(pred, ref, return_breakdown=True)
        entry = {"prediction": pred, "reference": ref, "cer": round(sample_cer, 4), **similarity}
        (good_ocr if sample_cer <= cer_threshold else poor_ocr).append(entry)

    def _summarize(group):
        if not group:
            return {"count": 0, "mean_combined": None, "mean_cer": None}
        return {
            "count": len(group),
            "mean_combined": round(sum(g["combined_score"] for g in group) / len(group), 4),
            "mean_cer": round(sum(g["cer"] for g in group) / len(group), 4),
            "mean_levenshtein": round(sum(g["levenshtein"] for g in group) / len(group), 4),
            "mean_bleu": round(sum(g["bleu"] for g in group) / len(group), 4),
            "mean_cosine": round(sum(g["cosine"] for g in group) / len(group), 4),
        }

    return {"cer_threshold": cer_threshold, "good_ocr": _summarize(good_ocr),
            "poor_ocr": _summarize(poor_ocr),
            "good_ocr_samples": good_ocr, "poor_ocr_samples": poor_ocr}

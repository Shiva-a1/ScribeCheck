import numpy as np
from sklearn.metrics import cohen_kappa_score


def qwk(truth, pred, scale=2):
    a = np.rint(np.asarray(truth, float) * scale).astype(int)
    b = np.rint(np.asarray(pred, float) * scale).astype(int)
    if len(set(a) | set(b)) < 2:
        return float("nan")
    return cohen_kappa_score(a, b, weights="quadratic")


def mae(truth, pred):
    return float(np.mean(np.abs(np.asarray(pred, float) - np.asarray(truth, float))))


def bias(truth, pred):
    return float(np.mean(np.asarray(pred, float) - np.asarray(truth, float)))


def exact(truth, pred):
    return float(np.mean(np.abs(np.asarray(pred, float) - np.asarray(truth, float)) < 0.25))


def within_one(truth, pred):
    return float(np.mean(np.abs(np.asarray(pred, float) - np.asarray(truth, float)) <= 1))


METRICS = {"qwk": qwk, "mae": mae, "exact": exact, "within_1": within_one, "bias": bias}


def resamples(groups, n, seed):
    groups = np.asarray(groups)
    ids = np.unique(groups)
    members = {g: np.flatnonzero(groups == g) for g in ids}
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield np.concatenate([members[g] for g in rng.choice(ids, len(ids))])


def bootstrap_ci(truth, pred, metric, groups=None, n=2000, seed=0):
    truth, pred = np.asarray(truth, float), np.asarray(pred, float)
    groups = np.arange(len(truth)) if groups is None else groups
    scores = [metric(truth[i], pred[i]) for i in resamples(groups, n, seed)]
    low, high = np.nanpercentile(scores, [2.5, 97.5])
    return metric(truth, pred), float(low), float(high)


def paired_diff_ci(truth, pred_a, pred_b, metric, groups=None, n=2000, seed=0):
    truth, pred_a, pred_b = (np.asarray(x, float) for x in (truth, pred_a, pred_b))
    groups = np.arange(len(truth)) if groups is None else groups
    diffs = [metric(truth[i], pred_a[i]) - metric(truth[i], pred_b[i]) for i in resamples(groups, n, seed)]
    low, high = np.nanpercentile(diffs, [2.5, 97.5])
    return metric(truth, pred_a) - metric(truth, pred_b), float(low), float(high)


def rate_ci(outcomes, n=2000, seed=0):
    outcomes = np.asarray(outcomes, float)
    rng = np.random.default_rng(seed)
    rates = [outcomes[rng.integers(0, len(outcomes), len(outcomes))].mean() for _ in range(n)]
    low, high = np.percentile(rates, [2.5, 97.5])
    return float(outcomes.mean()), float(low), float(high)


def report(truth, systems, groups=None):
    rows = {}
    for name, pred in systems.items():
        rows[name] = {m: bootstrap_ci(truth, pred, f, groups) for m, f in METRICS.items()}
    return rows


def print_report(rows):
    names = list(METRICS)
    print(f"{'system':<18}" + "".join(f"{m:>24}" for m in names))
    for system, values in rows.items():
        cells = "".join(f"{v[0]:>8.3f} [{v[1]:.3f}, {v[2]:.3f}]" for v in (values[m] for m in names))
        print(f"{system:<18}{cells}")

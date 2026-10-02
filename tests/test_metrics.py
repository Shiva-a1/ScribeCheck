import numpy as np

from eval.metrics import bootstrap_ci, exact, mae, paired_diff_ci, qwk, rate_ci, within_one


def test_perfect_agreement():
    truth = [0, 1, 2, 3, 4, 5]
    assert qwk(truth, truth) == 1
    assert mae(truth, truth) == 0
    assert exact(truth, truth) == within_one(truth, truth) == 1


def test_interval_contains_the_estimate_and_narrows_with_more_data():
    rng = np.random.default_rng(1)
    truth = rng.integers(0, 6, 400)
    pred = np.clip(truth + rng.integers(-1, 2, 400), 0, 5)
    value, low, high = bootstrap_ci(truth, pred, mae)
    assert low <= value <= high
    _, small_low, small_high = bootstrap_ci(truth[:50], pred[:50], mae)
    assert (high - low) < (small_high - small_low)


def test_grouped_bootstrap_keeps_groups_together():
    truth = np.repeat([0, 5], 50)
    pred = np.repeat([0, 0], 50)
    groups = np.repeat([0, 1], 50)
    value, low, high = bootstrap_ci(truth, pred, mae, groups=groups, n=500)
    assert value == 2.5
    assert {low, high} <= {0.0, 2.5, 5.0}


def test_paired_difference_detects_a_better_system():
    rng = np.random.default_rng(2)
    truth = rng.integers(0, 6, 300)
    good = truth.copy()
    bad = np.clip(truth + rng.choice([-2, 2], 300), 0, 5)
    diff, low, high = paired_diff_ci(truth, good, bad, mae)
    assert diff < 0 and high < 0


def test_rate_interval():
    rate, low, high = rate_ci([1] * 90 + [0] * 10)
    assert rate == 0.9 and low < 0.9 < high

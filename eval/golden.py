import argparse
import json
import sys

from eval import common, metrics

parser = argparse.ArgumentParser(description="Fail if grading quality drops on the golden set.")
parser.add_argument("path", nargs="?", default="eval/golden.jsonl")
parser.add_argument("--max-mae", type=float, default=0.6)
args = parser.parse_args()

rows = [json.loads(line) for line in open(args.path)]
pred = [common.grade(r)["median"] for r in rows]
score, low, high = metrics.bootstrap_ci([r["human"] for r in rows], pred, metrics.mae)
print(f"Golden set MAE {score:.3f} [{low:.3f}, {high:.3f}] on {len(rows)} answers (limit {args.max_mae})")
sys.exit(1 if score > args.max_mae else 0)

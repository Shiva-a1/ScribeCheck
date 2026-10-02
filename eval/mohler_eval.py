import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval import common, metrics
from shared import grading

parser = argparse.ArgumentParser(description="Compare Scribe-Check's grades with human grades on the Mohler dataset.")
parser.add_argument("csv")
parser.add_argument("--split", choices=["dev", "test"], default="dev")
parser.add_argument("--limit", type=int)
parser.add_argument("--notes", help="Course notes (PDF or text) to use as the notes pack.")
parser.add_argument("--workers", type=int, default=8)
parser.add_argument("--export-golden", type=int, metavar="N", help="Write N dev answers to eval/golden.jsonl.")
args = parser.parse_args()

rows = common.split(common.load_mohler(args.csv), args.split)[: args.limit]
notes = common.Notes(args.notes) if args.notes else None


def run(row):
    pack = notes.pack(row["question"], row["reference"]) if notes else ""
    return common.grade(row, notes=pack)


with ThreadPoolExecutor(args.workers) as pool:
    graded = list(pool.map(run, rows))

human = [r["human"] for r in rows]
systems = {name: [g[name] for g in graded] for name in (*grading.JUDGES, "median")}
table = metrics.report([r["grader_b"] for r in rows], {"human vs human": [r["grader_a"] for r in rows]})
table.update(metrics.report(human, systems))
print(f"\n{len(rows)} answers from the {args.split} split ({len({r['question'] for r in rows})} questions)\n")
metrics.print_report(table)

best_single = min(grading.JUDGES, key=lambda j: metrics.mae(human, systems[j]))
diff = metrics.paired_diff_ci(human, systems["median"], systems[best_single], metrics.mae)
print(f"\nMAE of median minus {best_single} alone: {diff[0]:+.3f} [{diff[1]:+.3f}, {diff[2]:+.3f}]")
print("An interval entirely below zero means the three-judge median is reliably better.")

out = Path(__file__).parent / "results"
out.mkdir(exist_ok=True)
(out / f"mohler_{args.split}.json").write_text(json.dumps({"n": len(rows), "metrics": table}, indent=2))

if args.export_golden:
    if args.split != "dev":
        raise SystemExit("Export the golden set from the dev split only.")
    with open(Path(__file__).parent / "golden.jsonl", "w") as f:
        for r in rows[: args.export_golden]:
            f.write(json.dumps({k: r[k] for k in ("question", "reference", "answer", "human")}) + "\n")

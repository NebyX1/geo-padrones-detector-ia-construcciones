"""Evaluate independent local labels; does not substitute automatic or QA confirmations for truth."""

import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict

parser = argparse.ArgumentParser(
    description="CSV: parcel_id,true_building,predicted_building,true_footprint_m2,predicted_footprint_m2,stratum"
)
parser.add_argument("labels")
parser.add_argument("--output", default="artifacts/local-validation.json")
args = parser.parse_args()


def metrics(rows):
    tp = tn = fp = fn = 0
    absolute = []
    percent = []
    for row in rows:
        if row["true_building"] not in {"0", "1"} or row["predicted_building"] not in {"0", "1"}:
            raise ValueError("Las clases deben ser 0/1 y excluir indeterminados explícitamente.")
        truth, prediction = row["true_building"] == "1", row["predicted_building"] == "1"
        tp += truth and prediction
        tn += not truth and not prediction
        fp += not truth and prediction
        fn += truth and not prediction
        if row.get("true_footprint_m2") and row.get("predicted_footprint_m2"):
            truth_area, predicted_area = float(row["true_footprint_m2"]), float(row["predicted_footprint_m2"])
            absolute.append(abs(predicted_area - truth_area))
            if truth_area > 0:
                percent.append(abs(predicted_area - truth_area) / truth_area * 100)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return dict(
        n=len(rows),
        precision=precision,
        recall=recall,
        f1=2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None,
        confusion_matrix={"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        mae_m2=sum(absolute) / len(absolute) if absolute else None,
        mape_pct=sum(percent) / len(percent) if percent else None,
        area_samples=len(absolute),
        percentage_samples=len(percent),
    )


rows = list(csv.DictReader(Path(args.labels).open(encoding="utf-8-sig")))
if len({r["parcel_id"] for r in rows}) != len(rows):
    raise SystemExit("Existen parcelas repetidas en la evaluación.")
groups = defaultdict(list)
for row in rows:
    groups[row.get("stratum", "unspecified")].append(row)
report = {
    "overall": metrics(rows),
    "by_stratum": {k: metrics(v) for k, v in groups.items()},
    "minimum_200_met": len(rows) >= 200,
    "notice": "La independencia y calidad de las etiquetas debe ser comprobada por los responsables técnicos.",
}
target = Path(args.output)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

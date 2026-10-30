#!/usr/bin/env python3
"""Aggregate district metrics and gate A1-A7. Fail workflow if criteria missed."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics-dir", default="metrics")
    ap.add_argument("--fail-on-criteria", action="store_true")
    args = ap.parse_args()
    files = sorted(Path(args.metrics_dir).glob("d*.json"))
    if not files:
        report = {"status": "INCOMPLETE", "criteria": {k: "UNVERIFIED" for k in "A1 A2 A3 A4 A5 A6 A7".split()}}
        Path("report.md").write_text("# Validation\n\nNo metrics files.\n")
        json.dump(report, open("metrics.json", "w"), indent=2)
        print("NO METRICS")
        sys.exit(0 if not args.fail_on_criteria else 1)

    districts = [json.loads(f.read_text()) for f in files]

    def avg_key(noise, key):
        vals = [d["by_noise"][str(noise)][key] for d in districts if str(noise) in d.get("by_noise", {})]
        return round(sum(vals) / len(vals), 2) if vals else None

    a1_national = avg_key(20, "all_top1")
    a1_min_district = min((d["by_noise"].get("20", {}).get("all_top1", 0) for d in districts), default=0)
    a1_interior = avg_key(20, "interior_top1")
    a1_border = avg_key(20, "border_top1")
    a2 = avg_key(100, "all_top3")
    a3_vals = []
    for d in districts:
        for r in [0, 20, 100, 500, 2000, 5000]:
            a3_vals.append(d.get("chosen_correct_pct", {}).get(str(r), 0))
    a3 = round(sum(a3_vals) / len(a3_vals), 2) if a3_vals else 0
    a3_20km_chosen = sum(d.get("chosen_correct_pct", {}).get("20000", 0) for d in districts) / max(1, len(districts))
    eces = [d.get("ece_approx", 1) for d in districts]
    a4 = max(eces) if eces else 1

    criteria = {
        "A1": "PASS" if (a1_national or 0) >= 98 and a1_min_district >= 95 else "FAIL",
        "A2": "PASS" if (a2 or 0) >= 98 else "FAIL",
        "A3": "PASS" if a3 >= 90 else "FAIL",
        "A4": "PASS" if a4 <= 0.05 else "FAIL",
        "A5": "UNVERIFIED",
        "A6": "UNVERIFIED",
        "A7": "UNVERIFIED",
    }
    status = "PASS" if all(v == "PASS" for k, v in criteria.items() if k in ("A1", "A2", "A3", "A4")) else "FAIL"

    lines = [
        "# Validation report",
        f"Districts: {len(districts)}",
        f"Status: {status}",
        "",
        "## A1 r=20m village top1",
        f"- national all: {a1_national}% (need >=98)",
        f"- min district: {a1_min_district}% (need >=95)",
        f"- national interior: {a1_interior}%",
        f"- national border: {a1_border}%",
        f"- result: {criteria['A1']}",
        "",
        "## A2 r=100m village top3",
        f"- national: {a2}% (need >=98) -> {criteria['A2']}",
        "",
        "## A3 chosen-level correctness",
        f"- mean over r<=5km: {a3}% (need >=90) -> {criteria['A3']}",
        f"- r=20km chosen: {round(a3_20km_chosen,2)}%",
        "",
        "## A4 ECE",
        f"- max district ECE: {a4} (need <=0.05) -> {criteria['A4']}",
        "",
        "## Criteria",
    ]
    for k, v in criteria.items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Per-district A1 (r=20m top1)")
    lines.append("| district | all | interior | border |")
    lines.append("|----------|----:|---------:|-------:|")
    for d in sorted(districts, key=lambda x: x["district_id"]):
        bn = d.get("by_noise", {}).get("20", {})
        lines.append(f"| {d['district_id']} | {bn.get('all_top1','?')} | {bn.get('interior_top1','?')} | {bn.get('border_top1','?')} |")

    Path("report.md").write_text("\n".join(lines) + "\n")
    report = {
        "status": status,
        "criteria": criteria,
        "a1_national": a1_national,
        "a1_min_district": a1_min_district,
        "a1_interior": a1_interior,
        "a1_border": a1_border,
        "a2": a2,
        "a3": a3,
        "a4_max_ece": a4,
        "districts": len(districts),
        "seeds": {"tune": 424242, "test": 20261030},
    }
    json.dump(report, open("metrics.json", "w"), indent=2)
    print(json.dumps(report, indent=2))
    if args.fail_on_criteria and status != "PASS":
        sys.exit(1)

if __name__ == "__main__":
    main()

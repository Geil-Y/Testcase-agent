"""Apply sanitize to an existing generated_cases.json and save a copy."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testcase_agent.parser.html_parser import GeneratedCase, Step
from testcase_agent.pipeline.post_process import sanitize_numeric_values


def apply_sanitize(src_dir: str, dest_dir: str) -> None:
    src = Path(src_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    # Copy metadata files (excluding the original cases)
    for f in src.glob("*.json"):
        if f.name == "generated_cases.json":
            continue
        shutil.copy2(f, dest / f.name)

    prompts_src = src / "prompts"
    prompts_dest = dest / "prompts"
    if prompts_src.exists():
        prompts_dest.mkdir(parents=True, exist_ok=True)
        for f in prompts_src.iterdir():
            shutil.copy2(f, prompts_dest / f.name)

    with open(src / "generated_cases.json", encoding="utf-8") as f:
        data = json.load(f)

    total_replacements = 0
    affected_cases = 0

    for req in data:
        signals = req["analysis"]["signals"]
        thresholds = req["analysis"]["thresholds"]
        timing = [t for t in req["analysis"].get("timing", [])
                  if t.strip().lower() != "none found"]

        for case in req["cases"]:
            c = GeneratedCase(
                title=case.get("title", ""),
                objective=case.get("objective", ""),
                precondition=case.get("precondition", ""),
                postcondition=case.get("postcondition", ""),
                related_requirement=case.get("related_requirement", ""),
                steps=[Step(order=s["order"], action=s["action"], expected=s.get("expected"))
                       for s in case["steps"]],
            )

            sc, reps = sanitize_numeric_values(
                c,
                requirement_description=req.get("description", ""),
                supplementary_info=req.get("supplementary_info", ""),
                extracted_signals=signals,
                extracted_thresholds=thresholds,
                extracted_timing=timing,
                accepted_test_basis=req.get("accepted_test_basis", ""),
            )

            if reps:
                total_replacements += len(reps)
                affected_cases += 1
                for i, s in enumerate(sc.steps):
                    case["steps"][i]["action"] = s.action
                    case["steps"][i]["expected"] = s.expected

    dest_path = dest / "generated_cases.json"
    dest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Sanitize applied: {total_replacements} replacements across {affected_cases} cases")
    print(f"Output: {dest_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python apply_sanitize.py <src_generated_cases_dir> <dest_dir>")
        sys.exit(1)
    apply_sanitize(sys.argv[1], sys.argv[2])

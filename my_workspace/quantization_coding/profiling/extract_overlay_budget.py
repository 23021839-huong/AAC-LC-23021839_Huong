#!/usr/bin/env python3
"""Extract post-route Vivado utilization and calculate remaining XC7Z020 budget."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RESOURCE_ROWS = {
    "lut": ("CLB LUTs", "Slice LUTs"),
    "ff": ("CLB Registers", "Slice Registers"),
    "bram36": ("Block RAM Tile",),
    "dsp": ("DSPs", "DSP Blocks", "DSP48E1 only"),
}


def parse_number(value: str) -> float:
    return float(value.replace(",", "").strip())


def find_resource(text: str, labels: tuple[str, ...]) -> dict[str, float | str] | None:
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not any(cells[0].lower() == label.lower() for label in labels):
            continue
        numbers = [
            cell
            for cell in cells[1:]
            if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", cell)
        ]
        if not numbers:
            continue
        # Vivado utilization tables place Used before Available.  Capacity is
        # optional here because scope_v1.json remains the locked device source.
        return {
            "label": cells[0],
            "used": parse_number(numbers[0]),
            # Vivado commonly emits Used, Fixed, Available, Util%.  Taking the
            # largest later numeric cell avoids mistaking Fixed for Available.
            "report_available": max(map(parse_number, numbers[1:])) if len(numbers) > 1 else 0,
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("utilization_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--scope", type=Path, default=Path(__file__).with_name("scope_v1.json")
    )
    args = parser.parse_args()

    report_text = args.utilization_report.read_text(encoding="utf-8", errors="replace")
    scope = json.loads(args.scope.read_text(encoding="utf-8"))
    capacity = {key: int(value) for key, value in scope["xc7z020_capacity"].items()}
    target = {
        key: int(value) for key, value in scope["qc_initial_incremental_budget"].items()
    }

    resources: dict[str, dict[str, float | int | str | None]] = {}
    missing: list[str] = []
    capacity_mismatches: list[str] = []
    fits = True
    for key, labels in RESOURCE_ROWS.items():
        parsed = find_resource(report_text, labels)
        if parsed is None:
            missing.append(key)
            resources[key] = {
                "label": None,
                "used": None,
                "capacity": capacity[key],
                "remaining": None,
                "qc_target": target.get(key, 0),
                "remaining_after_qc_target": None,
            }
            fits = False
            continue
        used = float(parsed["used"])
        report_available = float(parsed["report_available"])
        if report_available and abs(report_available - capacity[key]) > 0.01:
            capacity_mismatches.append(
                f"{key}: report={report_available:g}, scope={capacity[key]:g}"
            )
        remaining = capacity[key] - used
        qc_target = target.get(key, 0)
        remaining_after = remaining - qc_target
        fits = fits and remaining_after >= 0
        resources[key] = {
            **parsed,
            "capacity": capacity[key],
            "remaining": remaining,
            "qc_target": qc_target,
            "remaining_after_qc_target": remaining_after,
        }

    status = (
        "PENDING"
        if missing
        else ("PASS" if fits and not capacity_mismatches else "FAIL")
    )
    payload = {
        "schema_version": 1,
        "scope_id": scope["scope_id"],
        "status": status,
        "source_report": str(args.utilization_report.resolve()),
        "source_report_kind": "Vivado implementation utilization",
        "resources": resources,
        "missing_resources": missing,
        "capacity_mismatches": capacity_mismatches,
        "qc_target_fits": bool(not missing and not capacity_mismatches and fits),
        "note": "Used values come from the report; capacity and QC target come from scope_v1.json.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

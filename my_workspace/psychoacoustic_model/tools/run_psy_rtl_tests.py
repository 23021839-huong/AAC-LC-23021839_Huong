#!/usr/bin/env python3
"""Build a native FDK helper oracle and run isolated VHDL-2008 Psy regressions.

This verifies the SFB frontend and the separate post-TNS masking engine. It does
not report full Psy, ARM equivalence, synthesis, timing, or board acceptance.
Only Python's standard library, GCC/MinGW g++, and GHDL are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RTL = ("psy_pkg", "psy_log2", "psy_sfb_frontend", "psy_masking")
BENCHES = ("tb_psy_math", "tb_psy_sfb_frontend", "tb_psy_masking")
NATIVE = (
    "libAACenc/src/psy_model/band_nrg.cpp",
    "libAACenc/src/psy_model/spreading.cpp",
    "libAACenc/src/psy_model/pre_echo_control.cpp",
    "libAACenc/src/common/aacEnc_rom.cpp",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghdl", default="ghdl")
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build" / "rtl_native")
    args = parser.parse_args()
    compiler, simulator = shutil.which(args.cxx), shutil.which(args.ghdl)
    if not compiler or not simulator:
        parser.error("GCC/MinGW g++ and GHDL must be on PATH or supplied explicitly")
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    vector_dir = build / "vectors"
    vector_dir.mkdir(exist_ok=True)
    # Never leave an earlier success report looking like this run's outcome.
    report = {"status": "RUNNING", "scope": "native-helper isolated-stage regression",
              "arm_verified": False, "full_psy": False, "checks": []}
    report_path = build / "report.json"

    def save() -> None:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(command: list[str], name: str, marker: str | None = None) -> str:
        try:
            result = subprocess.run(command, cwd=build, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            (build / (name + ".log")).write_text(str(exc), encoding="utf-8")
            raise RuntimeError(f"{name} failed: {exc}") from exc
        (build / (name + ".log")).write_text(result.stdout, encoding="utf-8")
        report["checks"].append({"name": name, "command": command,
                                  "exit_code": result.returncode})
        save()
        if result.returncode or (marker and marker not in result.stdout):
            print(result.stdout[-6000:])
            raise RuntimeError(f"{name} failed; see {build / (name + '.log')}")
        return result.stdout

    save()
    try:
        oracle = build / ("fdk_psy_rtl_oracle.exe" if sys.platform == "win32" else "fdk_psy_rtl_oracle")
        include_dirs = [REPO / "libAACenc" / "src"]
        include_dirs += sorted(REPO.glob("lib*/include"))
        sources = [ROOT / "tests" / "rtl" / "fdk_psy_rtl_oracle.cpp"]
        sources += [REPO / p for p in NATIVE]
        command = [compiler, "-std=c++17", "-O2", "-fwrapv", "-fno-strict-overflow",
                   "-ffunction-sections", "-fdata-sections"]
        command += ["-I" + str(p) for p in include_dirs]
        command += [str(p) for p in sources]
        command += ["-Wl,--gc-sections", "-o", str(oracle)]
        run(command, "oracle_compile")
        print(run([str(oracle), str(vector_dir)], "oracle_vectors", "PASS:" ).strip())
        tracked = list(sources)
        tracked += list((REPO / "libFDK" / "include").rglob("*.h"))
        tracked += list((REPO / "libSYS" / "include").rglob("*.h"))
        tracked += list((REPO / "libAACenc" / "src").glob("*.h"))
        rtl_files = [ROOT / "rtl" / (n + ".vhd") for n in RTL]
        tb_files = [ROOT / "tb" / (n + ".vhd") for n in BENCHES]
        tracked += rtl_files + tb_files + [Path(__file__).resolve()]
        report["source_sha256"] = {
            str(p.relative_to(REPO)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(tracked))
        }
        report["vector_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(vector_dir.glob("*.txt"))
        }
        report["compiler"] = run([compiler, "--version"], "compiler_version").splitlines()[0]
        report["simulator"] = run([simulator, "--version"], "simulator_version").splitlines()[0]
        run([simulator, "-a", "--std=08", *map(str, rtl_files + tb_files)], "vhdl_analyze")
        summaries = []
        for bench in BENCHES:
            output = run([simulator, "-r", "--std=08", bench,
                          "-gVECTOR_DIR=" + vector_dir.as_posix(), "--assert-level=error"],
                         bench, "PASS: " + bench[3:])
            summary = next(line for line in output.splitlines() if "PASS:" in line)
            summaries.append(summary)
            print(summary)
        report["summaries"] = summaries
        report["status"] = "PASS"
        save()
        print(f"PASS: isolated Psy RTL stages; report: {report_path}")
        return 0
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        save()
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
Run the full profiling workflow for CBP-NG branch predictors.

The suite executes the pairwise parameter sweeps for similar predictors,
the fixed-budget structured study, and the comparison plot generators.
It also writes a compact markdown summary that can be regenerated from
the cached CSV outputs with --skip-sim.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = REPO_ROOT / "profiling"
DEFAULT_OUT_DIR = PROFILE_DIR / "outputs"
DEFAULT_TRACE = REPO_ROOT / "gcc_test_trace.gz"


SWEEP_SCRIPTS = [
    "gag_vs_gap_sweep.py",
    "gagL_vs_gapL_sweep.py",
    "pag_vs_pap_sweep.py",
    "pagL_vs_papL_sweep.py",
    "bimode_sweep.py",
    "bimodeL_sweep.py",
    "lxor_sweep.py",
    "structured_profiling.py",
]


SUMMARY_PLOTS = [
    "best_four_comparison.py",
    "best_five_comparisonL.py",
]


SCRIPT_OUTPUTS = {
    "gag_vs_gap_sweep.py": "gag_vs_gap_results.csv",
    "gagL_vs_gapL_sweep.py": "gagL_vs_gapL_results.csv",
    "pag_vs_pap_sweep.py": "pag_vs_pap_results.csv",
    "pagL_vs_papL_sweep.py": "pagL_vs_papL_results.csv",
    "bimode_sweep.py": "bimode_sweep_results.csv",
    "bimodeL_sweep.py": "bimodeL_sweep_results.csv",
    "lxor_sweep.py": "lxor_sweep_results.csv",
    "structured_profiling.py": "structured_profiling_results.csv",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="") as handle:
        return list(csv.DictReader(handle))


def best_row(rows: list[dict[str, str]], predicate=None) -> dict[str, str] | None:
    filtered = [row for row in rows if predicate is None or predicate(row)]
    if not filtered:
        return None
    return max(filtered, key=lambda row: float(row["vfs"]))


def run_script(script_name: str, args: list[str]) -> None:
    script_path = PROFILE_DIR / script_name
    proc = subprocess.run([sys.executable, str(script_path), *args], cwd=REPO_ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"{script_name} failed with exit code {proc.returncode}")


def format_metric(value: str, precision: int = 3) -> str:
    return f"{float(value):.{precision}f}"


def write_summary(out_dir: Path) -> Path:
    lines: list[str] = []
    lines.append("# CBP-NG Profiling Summary")
    lines.append("")
    lines.append("This summary is generated from the CSV files in profiling/outputs.")
    lines.append("")

    sweep_specs = [
        ("gag_vs_gap_results.csv", "GAG vs GAP"),
        ("gagL_vs_gapL_results.csv", "gagL vs gapL"),
        ("pag_vs_pap_results.csv", "PAG vs PAP"),
        ("pagL_vs_papL_results.csv", "pagL vs papL"),
        ("bimode_sweep_results.csv", "Bi-Mode"),
        ("bimodeL_sweep_results.csv", "Bi-Mode_L"),
        ("lxor_sweep_results.csv", "LXOR"),
    ]

    lines.append("## Sweep Winners")
    lines.append("")
    lines.append("| Study | Best Configuration | IPC | MPKI | EPI (fJ) | VFS |")
    lines.append("| :---- | :----------------- | :-- | :--- | :------- | :-- |")

    for csv_name, study_name in sweep_specs:
        csv_path = out_dir / csv_name
        if not csv_path.exists():
            continue
        rows = read_csv_rows(csv_path)
        if not rows:
            continue
        if "type" in rows[0]:
            types = sorted({row["type"] for row in rows})
            for predictor_type in types:
                row = best_row(
                    rows, lambda candidate: candidate.get("type") == predictor_type
                )
                if row is None:
                    continue
                lines.append(
                    f"| {study_name} | {row['expr']} | {format_metric(row['ipc'])} | {format_metric(row['mpki'])} | {format_metric(row['epi'], 1)} | {format_metric(row['vfs'], 4)} |"
                )
        else:
            row = best_row(rows)
            if row is None:
                continue
            lines.append(
                f"| {study_name} | {row['expr']} | {format_metric(row['ipc'])} | {format_metric(row['mpki'])} | {format_metric(row['epi'], 1)} | {format_metric(row['vfs'], 4)} |"
            )

    structured_csv = out_dir / "structured_profiling_results.csv"
    if structured_csv.exists():
        rows = read_csv_rows(structured_csv)
        if rows:
            lines.append("")
            lines.append("## Fixed Budget Winners")
            lines.append("")
            lines.append(
                "| Budget | Best Overall | Best Block Predictor | Best Scalar Predictor |"
            )
            lines.append(
                "| :----- | :----------- | :------------------- | :-------------------- |"
            )

            for budget in ["8KB", "16KB"]:
                budget_rows = [row for row in rows if row["budget"] == budget]
                block_row = best_row(
                    budget_rows, lambda candidate: candidate["type"] == "Block"
                )
                scalar_row = best_row(
                    budget_rows, lambda candidate: candidate["type"] == "Scalar"
                )
                overall_row = best_row(budget_rows)

                def describe(row: dict[str, str] | None) -> str:
                    if row is None:
                        return "n/a"
                    return f"{row['name']} ({row['expr']}, VFS {format_metric(row['vfs'], 4)})"

                lines.append(
                    f"| {budget} | {describe(overall_row)} | {describe(block_row)} | {describe(scalar_row)} |"
                )

    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(
        "- [structured_profiling_results.csv](outputs/structured_profiling_results.csv)"
    )
    lines.append("- [structured_profiling.png](outputs/structured_profiling.png)")
    lines.append("- [profiling_suite_summary.md](outputs/profiling_suite_summary.md)")

    summary_path = out_dir / "profiling_suite_summary.md"
    summary_path.write_text("\n".join(lines) + "\n")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full CBP-NG profiling suite")
    parser.add_argument("--warmup", type=int, default=1_000_000)
    parser.add_argument("--measure", type=int, default=10_000_000)
    parser.add_argument("--trace", default=str(DEFAULT_TRACE))
    parser.add_argument("--outdir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--skip-sim", action="store_true")
    parser.add_argument("--skip-summary-plots", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    common_args = ["--outdir", str(out_dir), "--trace", str(Path(args.trace).resolve())]
    if not args.skip_sim:
        common_args.extend(
            ["--warmup", str(args.warmup), "--measure", str(args.measure)]
        )
    else:
        common_args.append("--skip-sim")

    for script_name in SWEEP_SCRIPTS:
        if args.skip_sim:
            output_name = SCRIPT_OUTPUTS.get(script_name)
            if output_name is not None and not (out_dir / output_name).exists():
                print(f"Skipping {script_name} because {output_name} is missing")
                continue
        run_script(script_name, common_args)

    if not args.skip_summary_plots:
        for script_name in SUMMARY_PLOTS:
            run_script(script_name, [])

    summary_path = write_summary(out_dir)
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()

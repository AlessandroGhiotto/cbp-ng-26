#!/usr/bin/env python3

"""Benchmark several CBP-NG predictors and compare their results.

The script compiles and runs a set of predictor configurations, then summarizes
the resulting .out files with predictor_metrics.py and prints a comparison
table.

Examples:

  ./benchmark_predictors.py ./gcc_test_trace.gz
  ./benchmark_predictors.py ./traces --warmup 1000000 --measure 40000000
"""

from __future__ import annotations

import argparse
import csv
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent


DEFAULT_CONFIGS: list[tuple[str, str]] = [
    ("lxor_8_6", "lxor<8,6>"),
    ("lxor_10_8", "lxor<>"),
    ("lxor_12_10", "lxor<12,10>"),
    ("tage", "tage<>"),
    ("gshare", "gshare<>"),
    ("bimodal", "bimodal<>"),
    ("perceptron", "perceptron<>"),
]

OUR_CONFIGS: list[tuple[str, str]] = [
    ("bimode", "bimode<>"),
    ("bimodeL", "bimodeL<8,12,10,2,4>"),
    ("gag", "gag<>"),
    ("gagL", "gagL<>"),
    ("gap", "gap<>"),
    ("gapL", "gapL<>"),
    ("gshare_simple", "gshare_simple<>"),
    ("lxor", "lxor<>"),
    ("pag", "pag<>"),
    ("pagL", "pagL<>"),
    ("pap", "pap<>"),
    ("papL", "papL<>"),
]



def run_command(command: Iterable[str], *, cwd: Path, stdout=None) -> None:
    command_list = list(command)
    printable = " ".join(shlex.quote(part) for part in command_list)
    print(f"+ {printable}")
    subprocess.run(command_list, cwd=cwd, check=True, stdout=stdout)


def compile_predictor(predictor_expr: str) -> None:
    shell_command = f'./compile cbp -DPREDICTOR="{predictor_expr}"'
    run_command(["bash", "-lc", shell_command], cwd=REPO_ROOT)


def trace_name(path: Path) -> str:
    name = path.name
    if name.endswith(".gz"):
        name = name[:-3]
    if name.endswith("_trace"):
        name = name[:-6]
    return name


def collect_traces(trace_path: Path) -> list[Path]:
    if trace_path.is_file():
        return [trace_path]

    if trace_path.is_dir():
        traces = sorted(trace_path.glob("*_trace.gz"))
        if traces:
            return traces

    raise FileNotFoundError(f"No trace files found at {trace_path}")


def run_benchmark(
    predictor_label: str,
    predictor_expr: str,
    traces: list[Path],
    out_root: Path,
    warmup: int,
    measure: int,
) -> Path:
    compile_predictor(predictor_expr)

    result_dir = out_root / predictor_label
    result_dir.mkdir(parents=True, exist_ok=True)

    for trace in traces:
        out_file = result_dir / f"{trace_name(trace)}.out"
        with out_file.open("w") as stream:
            run_command(
                ["./cbp", str(trace), trace_name(trace), str(warmup), str(measure)],
                cwd=REPO_ROOT,
                stdout=stream,
            )

    return result_dir


def summarize_result_dir(result_dir: Path) -> list[str]:
    metrics_script = Path(__file__).resolve().parent / "predictor_metrics.py"
    output = subprocess.check_output(
        [sys.executable, str(metrics_script), str(result_dir)],
        cwd=REPO_ROOT,
        text=True,
    )
    line = output.strip().splitlines()[-1]
    return next(csv.reader([line]))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark CBP-NG predictors and compare their metrics."
    )
    parser.add_argument(
        "trace_path",
        nargs="?",
        default="./gcc_test_trace.gz",
        help="Trace file or directory of *_trace.gz files",
    )
    parser.add_argument(
        "--outdir",
        default="benchmark_results",
        help="Directory to store benchmark outputs",
    )
    parser.add_argument(
        "--warmup", type=int, default=0, help="Warmup instructions per trace"
    )
    parser.add_argument(
        "--measure", type=int, default=1000, help="Measurement instructions per trace"
    )
    parser.add_argument(
        "--mode",
        choices=["default", "our", "all"],
        default="default",
        help="Which set of predictors to run ('default', 'our' (custom predictors), or 'all')",
    )
    parser.add_argument(
        "--predictors",
        help="Comma-separated list of predictor labels/names to run (e.g., gag,gap)",
    )
    args = parser.parse_args()

    trace_path = (
        (REPO_ROOT / args.trace_path).resolve()
        if not Path(args.trace_path).is_absolute()
        else Path(args.trace_path)
    )
    traces = collect_traces(trace_path)
    out_root = (
        (REPO_ROOT / args.outdir).resolve()
        if not Path(args.outdir).is_absolute()
        else Path(args.outdir)
    )
    out_root.mkdir(parents=True, exist_ok=True)

    if args.mode == "default":
        configs = DEFAULT_CONFIGS
    elif args.mode == "our":
        configs = OUR_CONFIGS
    else:
        configs = DEFAULT_CONFIGS + OUR_CONFIGS

    if args.predictors:
        selected = [p.strip() for p in args.predictors.split(",")]
        configs = [c for c in configs if any(s == c[0] or s == c[1] for s in selected)]

    print(f"Traces: {len(traces)}")
    print(f"Warmup: {args.warmup}")
    print(f"Measure: {args.measure}")
    print(f"Mode: {args.mode}")
    if args.predictors:
        print(f"Selected predictors: {args.predictors}")

    summaries: list[dict[str, str]] = []
    for label, predictor_expr in configs:
        print(f"\n=== {label} ({predictor_expr}) ===")
        result_dir = run_benchmark(
            label, predictor_expr, traces, out_root, args.warmup, args.measure
        )
        ipc, cpi, epi, mpi, dpi, ppi, throughput, p1_lat, p2_lat = summarize_result_dir(result_dir)
        summaries.append(
            {
                "config": label,
                "predictor": predictor_expr,
                "ipc": ipc,
                "cpi": cpi,
                "epi": epi,
                "mpi": mpi,
                "dpi": dpi,
                "ppi": ppi,
                "throughput": throughput,
                "p1_latency": p1_lat,
                "p2_latency": p2_lat,
            }
        )

    summaries.sort(key=lambda row: float(row["ipc"]), reverse=True)

    print("\nComparison (sorted by IPC):")
    header = [
        "config",
        "predictor",
        "IPC",
        "CPI",
        "EPI",
        "MPI",
        "DPI",
        "PPI",
        "Throughput",
        "P1 lat",
        "P2 lat",
    ]
    print(" | ".join(header))
    print(" | ".join(["---"] * len(header)))
    for row in summaries:
        print(
            " | ".join(
                [
                    row["config"],
                    row["predictor"],
                    row["ipc"],
                    row["cpi"],
                    row["epi"],
                    row["mpi"],
                    row["dpi"],
                    row["ppi"],
                    row["throughput"],
                    row["p1_latency"],
                    row["p2_latency"],
                ]
            )
        )

    comparison_file = out_root / "comparison.csv"
    with comparison_file.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "config",
                "predictor",
                "ipc",
                "cpi",
                "epi",
                "mpi",
                "dpi",
                "ppi",
                "throughput",
                "p1_latency",
                "p2_latency",
            ],
        )
        writer.writeheader()
        writer.writerows(summaries)

    print(f"\nSaved comparison to {comparison_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

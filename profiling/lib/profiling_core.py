import math
import subprocess
import shutil
import sys
import os
import csv
import concurrent.futures
from pathlib import Path

APPTAINER_SIF = "/home/ghi/Documents/HPC-PoliMi/1-AMSC/amsc_mk_2025.sif"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

def run_cmd(cmd: str) -> str:
    use_apptainer = shutil.which("apptainer") is not None and os.path.exists(APPTAINER_SIF)
    if "APPTAINER_CONTAINER" in os.environ or "SINGULARITY_CONTAINER" in os.environ:
        use_apptainer = False
    
    if use_apptainer:
        full_cmd = [
            "apptainer",
            "exec",
            APPTAINER_SIF,
            "bash",
            "-lc",
            f"source /u/sw/etc/bash.bashrc && {cmd}"
        ]
    else:
        full_cmd = ["bash", "-lc", cmd]

    proc = subprocess.run(full_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {cmd}\nStderr: {proc.stderr}\nStdout: {proc.stdout}"
        )
    return proc.stdout

def compile_predictor(expr: str) -> None:
    cmd = f'./compile cbp -DPREDICTOR="{expr}"'
    run_cmd(cmd)

def calculate_vfs_score(ipc: float, cpi: float, epi: float) -> float:
    IPCcbp0 = 8.0
    CPIcbp0 = 0.0315
    EPIcbp0 = 1000.0
    ALPHA = 1.625
    BETA = 4.0 * ALPHA / (ALPHA - 1.0) ** 2
    GAMMA = 2.0 / (ALPHA - 1.0)
    cbp_energy_ratio = 0.05
    WPI0 = IPCcbp0 * CPIcbp0
    WPI = ipc * cpi
    speedup = (ipc / IPCcbp0) * (1.0 + WPI0) / (1.0 + WPI)
    LAMBDA = 1.0 / (1.0 + WPI0 / 2.0) - cbp_energy_ratio
    normalizedEPI = ((epi / EPIcbp0) * cbp_energy_ratio + LAMBDA * speedup**GAMMA) * (
        1.0 + WPI / 2.0
    )

    vfs_arg = 1.0 + BETA / (speedup * normalizedEPI)
    if vfs_arg <= 0:
        return 0.0

    vfs = speedup * ALPHA * (1.0 - 2.0 / (1.0 + math.sqrt(vfs_arg)))
    return vfs

def parse_simulator_output(stdout: str, expr: str) -> dict:
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    csv_line = lines[-1]
    parts = csv_line.split(",")
    
    trace_name = parts[0]
    instr = float(parts[1])
    branches = float(parts[2])
    cond_branches = float(parts[3])
    npred = float(parts[4])
    extra = float(parts[5])
    diverge = float(parts[6])
    diverge_at_end = float(parts[7])
    misp = float(parts[8])
    p1_lat = math.ceil(float(parts[9]))
    p2_lat = math.ceil(float(parts[10]))
    epi = float(parts[11])

    MPI = misp / instr
    MPKI = MPI * 1000.0

    if p2_lat <= p1_lat:
        cycles = npred * max(1, p2_lat)
    else:
        cycles = npred * max(1, p1_lat) + diverge * p2_lat - diverge_at_end * max(1, p1_lat)
    cycles += extra

    IPC = instr / cycles
    p2_to_exec_stages = 9.0
    CPI = MPI * (p2_to_exec_stages + p2_lat - max(1, min(p1_lat, p2_lat)))
    vfs = calculate_vfs_score(IPC, CPI, epi)

    return {
        "trace": trace_name,
        "instructions": instr,
        "branches": branches,
        "cond_branches": cond_branches,
        "npred": npred,
        "extra_cycles": extra,
        "diverge": diverge,
        "diverge_at_end": diverge_at_end,
        "mispredictions": misp,
        "p1_lat": p1_lat,
        "p2_lat": p2_lat,
        "epi": epi,
        "mpki": MPKI,
        "ipc": IPC,
        "cpi": CPI,
        "vfs": vfs
    }

def run_predictor_on_multiple_traces(expr: str, traces: list[Path], warmup: int = 1000000, measure: int = 40000000, jobs: int = 8) -> dict[str, dict]:
    compile_predictor(expr)
    results = {}
    
    def run_one(trace_path):
        trace_name = trace_path.stem
        if trace_name.endswith(".gz"):
            trace_name = Path(trace_name).stem
        if trace_name.endswith("_trace"):
            trace_name = trace_name[:-6]
            
        cmd = f"./cbp {trace_path} {trace_name} {warmup} {measure}"
        try:
            stdout = run_cmd(cmd)
            metrics = parse_simulator_output(stdout, expr)
            return trace_name, metrics
        except Exception as e:
            print(f"Error running {expr} on {trace_path}: {e}")
            return trace_name, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(run_one, t): t for t in traces}
        for future in concurrent.futures.as_completed(futures):
            t_name, metrics = future.result()
            if metrics:
                results[t_name] = metrics
                
    return results

def get_predictor_size_bits(expr: str) -> int:
    expr = expr.strip()
    if "<" not in expr:
        if expr == "tage" or expr == "tage<>":
            return 286720
        elif expr == "reference":
            return 0
        raise ValueError(f"Cannot determine size of default template expression: {expr}")
        
    name, params_str = expr.split("<", 1)
    params_str = params_str.rsplit(">", 1)[0]
    
    if not params_str.strip():
        if name == "tage":
            return 286720
        return 0
        
    params = []
    for p in params_str.split(","):
        p = p.strip()
        if p.isdigit():
            params.append(int(p))
        else:
            # Handle float or expression (e.g. THRESHOLD)
            try:
                params.append(float(p))
            except ValueError:
                params.append(p)
    
    if name == "gag":
        return (1 << params[0]) * params[1]
    elif name == "gagL":
        return (1 << params[0]) * params[1] * (1 << params[2])
    elif name == "gap":
        return (1 << (params[0] + params[1])) * params[2]
    elif name == "gapL":
        return (1 << (params[0] + params[1])) * params[2] * (1 << params[3])
    elif name == "gshare_simple" or name == "gshare":
        return (1 << max(params[0], params[1])) * params[2]
    elif name == "gshare_simpleL" or name == "gshareL":
        return (1 << max(params[0], params[1])) * params[2] * (1 << params[3])
    elif name == "pag":
        return (1 << params[0]) * params[2] + (1 << params[1]) * params[0]
    elif name == "pagL":
        return (1 << params[0]) * params[2] * (1 << params[3]) + (1 << params[1]) * params[0]
    elif name == "pap":
        return (1 << (params[0] + params[2])) * params[3] + (1 << params[1]) * params[0]
    elif name == "papL":
        return (1 << (params[0] + params[2])) * params[3] * (1 << params[4]) + (1 << params[1]) * params[0]
    elif name == "bimode":
        return ((1 << params[0]) + 2 * (1 << params[2])) * params[3]
    elif name == "bimodeL":
        return ((1 << params[0]) + 2 * (1 << params[2])) * params[3] * (1 << params[4])
    elif name == "bimode_singleram":
        return ((1 << params[0]) + (1 << (params[2] + 1))) * params[3]
    elif name == "lxor" or name == "lxor_general":
        if len(params) == 2:
            pc_b, bhr_b = params
            comp_b = bhr_b
            ctr_b = 2
        else:
            pc_b, bhr_b, comp_b, ctr_b = params
        return (1 << (bhr_b + comp_b)) * ctr_b + (1 << pc_b) * bhr_b
    elif name == "lxorL" or name == "lxor_generalL":
        if len(params) == 3:
            pc_b, bhr_b, line_b = params
            comp_b = bhr_b
            ctr_b = 2
        else:
            pc_b, bhr_b, comp_b, ctr_b, line_b = params
        return (1 << (bhr_b + comp_b)) * ctr_b * (1 << line_b) + (1 << pc_b) * bhr_b
    elif name == "tage_simple":
        pc_b, tag_b = params[0], params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        return (1 << pc_b) * (4 * ctr_b + 3 * tag_b)
    elif name == "tage_simpleL" or name == "tage_simple_satL" or name == "tage_simple_satNL":
        pc_b, tag_b = params[0], params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        line_b = params[7] if len(params) > 7 else 4
        li = 1 << line_b
        return (1 << pc_b) * (4 * ctr_b * li + 3 * tag_b)
    elif name == "tage_simple_u":
        pc_b, tag_b = params[0], params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        return (1 << pc_b) * (4 * ctr_b + 3 * tag_b + 3)
    elif name == "tage_simple_uL":
        pc_b, tag_b = params[0], params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        line_b = params[7] if len(params) > 7 else 4
        li = 1 << line_b
        return (1 << pc_b) * (4 * ctr_b * li + 3 * tag_b + 3)
    elif name == "perceptron_simple":
        pc_b, bhr_b, ctr_b = params[0], params[1], params[2]
        return (1 << pc_b) * (bhr_b + 1) * ctr_b
    elif name == "perceptron_simpleL":
        pc_b, bhr_b, ctr_b, _, line_b = params
        li = 1 << line_b
        return (1 << pc_b) * (bhr_b + 1) * li * ctr_b
    elif name == "tage_biasL":
        pc_b = params[0]
        tag_b = params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        line_b = params[7] if len(params) > 7 else 4
        bias_b = params[8] if len(params) > 8 else 6
        li = 1 << line_b
        return (1 << pc_b) * (4 * ctr_b * li + 3 * tag_b) + (1 << bias_b) * 2 * li
    elif name == "tage_bimodeL":
        pc_b = params[0]
        tag_b = params[1]
        ctr_b = params[6] if len(params) > 6 else 3
        line_b = params[7] if len(params) > 7 else 4
        bias_b = params[8] if len(params) > 8 else 6
        choice_b = params[10] if len(params) > 10 else 10
        pht_b = params[11] if len(params) > 11 else 10
        use_bias = params[13] if len(params) > 13 else True
        if isinstance(use_bias, str):
            use_bias = use_bias.lower() == "true"
        li = 1 << line_b
        
        choice_size = (1 << choice_b) * ctr_b * li
        pht_size = 2 * (1 << pht_b) * ctr_b * li
        tage_size = 3 * (1 << pc_b) * ((ctr_b * li) + tag_b)
        bias_size = ((1 << bias_b) * 2 * li) if use_bias else 0
        return choice_size + pht_size + tage_size + bias_size
    else:
        raise ValueError(f"Unknown predictor name: {name}")

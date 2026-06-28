import subprocess
import sys

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Error running command: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result.stdout

def main():
    pht_size = 10
    print(f"Starting experiment: fixed PHT index size = {pht_size} bits (1024 rows)")
    print("Varying history length (HIST_B) from 1 to 16 bits...")
    print("-" * 60)
    print(f"{'History Bits':<15} | {'Cond Branches':<15} | {'Mispredictions':<15} | {'Accuracy (%)':<15}")
    print("-" * 60)

    results = []

    for hist_b in range(1, 17):
        # 1. Compile
        compile_cmd = f'./compile cbp -DPREDICTOR="gag_exp<{pht_size},{hist_b},2>"'
        run_cmd(compile_cmd)

        # 2. Run simulation
        sim_cmd = f"./cbp ./gcc_test_trace.gz gcc_test_trace 0 1000000"
        output = run_cmd(sim_cmd)

        # 3. Parse output as CSV
        # The output should have a line with comma-separated values
        # e.g., gcc_test_trace,1000000,197807,158767,1000000,18014,0,0,10785,0.423333,0.436667,54
        cond_branches = None
        mispredictions = None

        for line in output.splitlines():
            parts = line.strip().split(",")
            if len(parts) >= 9 and parts[1].isdigit():
                try:
                    cond_branches = int(parts[3])
                    mispredictions = int(parts[8])
                    break
                except ValueError:
                    continue

        if cond_branches is not None and mispredictions is not None:
            accuracy = 100.0 * (1.0 - mispredictions / cond_branches)
            print(f"{hist_b:<15} | {cond_branches:<15} | {mispredictions:<15} | {accuracy:.3f}%")
            results.append((hist_b, cond_branches, mispredictions, accuracy))
        else:
            print(f"Failed to parse output for HIST_B = {hist_b}")
            print(f"Simulation output was: {output}")

    # Write results to a markdown file
    md_file_path = "gag_experiment_results.md"
    with open(md_file_path, "w") as f:
        f.write(f"# GAG Predictor History Length Experiment\n\n")
        f.write(f"This experiment fixes the PHT size to **{1 << pht_size} entries** (index size = {pht_size} bits, counter size = 2 bits).\n")
        f.write(f"We vary the history length (`HIST_B`) from 1 to 16 bits and measure the predictor's accuracy on 1,000,000 instructions of `gcc_test_trace`.\n\n")
        f.write(f"## Configuration\n")
        f.write(f"- **PHT Index size**: {pht_size} bits\n")
        f.write(f"- **Counter size**: 2 bits\n")
        f.write(f"- **Trace**: `gcc_test_trace` (1,000,000 instructions)\n\n")
        f.write(f"## Results\n\n")
        f.write(f"| History Size (bits) | Conditional Branches | Mispredictions | Accuracy (%) |\n")
        f.write(f"| :---: | :---: | :---: | :---: |\n")
        for hist_b, cb, misp, acc in results:
            f.write(f"| {hist_b} | {cb} | {misp} | **{acc:.3f}%** |\n")

    print("-" * 60)
    print(f"Experiment complete. Results saved to {md_file_path}")

if __name__ == "__main__":
    main()

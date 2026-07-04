#include <iostream>
#include <iomanip>
#include <string>
#include <vector>
#include <unordered_set>
#include <algorithm>
#include "trace_reader.hpp"

int main(int argc, char* argv[]) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0] << " <trace_path> <trace_name> <warmup_instructions> <measurement_instructions>" << std::endl;
        return 1;
    }

    std::string trace_path = argv[1];
    std::string trace_name = argv[2];
    uint64_t warmup_instructions = std::stoull(argv[3]);
    uint64_t measurement_instructions = std::stoull(argv[4]);

    trace_reader reader(trace_path, trace_name);

    uint64_t ninstr = 0;
    uint64_t nbranch = 0;
    uint64_t ncondbr = 0;
    uint64_t ncondbr_taken = 0;
    uint64_t ncondbr_backwards = 0;
    uint64_t ncondbr_backwards_taken = 0;
    uint64_t nuncond_direct = 0;
    uint64_t nuncond_indirect = 0;
    uint64_t ncalls = 0;
    uint64_t nreturns = 0;

    std::unordered_set<uint64_t> cond_pcs;
    std::unordered_set<uint64_t> branch_pcs;

    bool warmed_up = (warmup_instructions == 0);

    auto clear_stats = [&]() {
        ninstr = 0;
        nbranch = 0;
        ncondbr = 0;
        ncondbr_taken = 0;
        ncondbr_backwards = 0;
        ncondbr_backwards_taken = 0;
        nuncond_direct = 0;
        nuncond_indirect = 0;
        ncalls = 0;
        nreturns = 0;
        cond_pcs.clear();
        branch_pcs.clear();
    };

    try {
        instruction instr;
        instruction next_instr = reader.next_instruction();
        
        while (!warmed_up || ninstr < measurement_instructions) {
            instr = next_instr;
            next_instr = reader.next_instruction();
            ninstr++;

            instr.taken_branch = (next_instr.pc != instr.pc + 4);
            if (!instr.branch && instr.taken_branch) {
                // discontinuity; make it look like an indirect jump
                instr.branch = true;
                instr.inst_class = INST_CLASS::BR_UNCOND_INDIRECT;
            }

            instr.next_pc = next_instr.pc;

            // Only collect stats if warmed up
            if (warmed_up) {
                if (instr.branch) {
                    nbranch++;
                    branch_pcs.insert(instr.pc);

                    bool is_cond = (instr.inst_class == INST_CLASS::BR_COND);
                    if (is_cond) {
                        ncondbr++;
                        cond_pcs.insert(instr.pc);
                        if (instr.taken_branch) {
                            ncondbr_taken++;
                        }
                        bool is_backward = (instr.next_pc < instr.pc);
                        if (is_backward) {
                            ncondbr_backwards++;
                            if (instr.taken_branch) {
                                ncondbr_backwards_taken++;
                            }
                        }
                    } else {
                        // Unconditional branch
                        bool is_indirect = (instr.inst_class == INST_CLASS::BR_UNCOND_INDIRECT) || 
                                           (instr.inst_class == INST_CLASS::BR_CALL_INDIRECT) ||
                                           (instr.inst_class == INST_CLASS::BR_RETURN);
                        if (is_indirect) {
                            nuncond_indirect++;
                        } else {
                            nuncond_direct++;
                        }

                        bool is_call = (instr.inst_class == INST_CLASS::BR_CALL_DIRECT) || 
                                       (instr.inst_class == INST_CLASS::BR_CALL_INDIRECT);
                        if (is_call) {
                            ncalls++;
                        }

                        if (instr.inst_class == INST_CLASS::BR_RETURN) {
                            nreturns++;
                        }
                    }
                }
            }

            if (!warmed_up && ninstr > warmup_instructions) {
                warmed_up = true;
                clear_stats();
            }
        }
    } catch (const out_of_instructions &e) {
        // reached end of trace before reaching measurement limit
    }

    std::cout << trace_name << ","
              << ninstr << ","
              << nbranch << ","
              << ncondbr << ","
              << ncondbr_taken << ","
              << ncondbr_backwards << ","
              << ncondbr_backwards_taken << ","
              << nuncond_direct << ","
              << nuncond_indirect << ","
              << ncalls << ","
              << nreturns << ","
              << cond_pcs.size() << ","
              << branch_pcs.size() << std::endl;

    return 0;
}

#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"

using namespace hcm;

/*
 * bimodeL (Bi-Mode Line) branch predictor - Pipelined Version.
 *
 * This predictor performs line-wide (cacheline) prediction of 2^LINE_B instructions.
 *
 * Pipelining:
 * - Level 1 (predict1): Performs choice-table lookup (fast, <1 cycle latency)
 *   and predicts direction directly based on the bias from the choice table.
 * - Level 2 (predict2): Performs Taken/Not-Taken PHT table lookup (higher latency)
 *   and overrides the Level 1 prediction if they disagree.
 *
 * This achieves high IPC (P1 lat = 1, P2 lat = 2) while maintaining Bi-Mode accuracy.
 */

template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2, u64 LINE_B = 4>
struct bimodeL : predictor
{
    static constexpr u64 CHOICE_ENTRIES = 1 << CHOICE_B;
    static constexpr u64 PHT_ENTRIES = 1 << PHT_B;
    static constexpr u64 LI = 1 << LINE_B; // Number of instructions per line
    static constexpr u64 MAX_CTR = (1 << CTR_B) - 1;

    // Line-wide choice table and PHTs
    ram<arr<val<CTR_B>, LI>, CHOICE_ENTRIES> choice_table;
    ram<arr<val<CTR_B>, LI>, PHT_ENTRIES> taken_pht;
    ram<arr<val<CTR_B>, LI>, PHT_ENTRIES> not_taken_pht;

    // Registers to save prediction state for update
    reg<CHOICE_B> choice_idx;
    arr<reg<CTR_B>, LI> choice_ctr_line;
    reg<LI> choice_val_line;

    reg<PHT_B> pht_idx;
    arr<reg<CTR_B>, LI> pht_ctr_line;
    arr<reg<CTR_B>, LI> reg_taken_line;
    arr<reg<CTR_B>, LI> reg_not_taken_line;

    // BHR (Branch History Register)
    reg<BHR_B> bhr;

    // Simulation artifacts to track branches in the block
    u64 num_branches = 0;
    arr<reg<LINE_B>, LI> branch_offset;
    arr<reg<1>, LI> branch_taken;

    val<1> predict1(val<64> inst_pc)
    {
        num_branches = 0;

        inst_pc.fanout(hard<2> {});

        // 1. Index Choice Table using line address (PC >> 2 + LINE_B)
        val<CHOICE_B> choice_row_idx = val<CHOICE_B> { inst_pc >> 2 + LINE_B };
        choice_row_idx.fanout(hard<2> {});
        choice_idx = choice_row_idx;

        arr<val<CTR_B>, LI> choice_line = choice_table.read(choice_row_idx);
        choice_line.fanout(hard<2> {});
        choice_ctr_line = choice_line;

        // Determine choice direction for each instruction in the line
        arr<val<1>, LI> choice_preds = [&](u64 i) {
            return choice_line[i] >> (CTR_B - 1);
        };
        choice_preds.fanout(hard<2> {});
        choice_val_line = choice_preds.concat();

        // Level 1 prediction based purely on Choice Table
        val<LINE_B> offset = inst_pc >> 2;
        return choice_preds.select(offset.fo1());
    }

    val<1> reuse_predict1(val<64> inst_pc)
    {
        val<LINE_B> offset = inst_pc >> 2;
        arr<val<1>, LI> choice_preds = choice_val_line.make_array(val<1> {});
        return choice_preds.fo1().select(offset.fo1());
    }

    val<1> predict2(val<64> inst_pc)
    {
        inst_pc.fanout(hard<2> {});

        val<PHT_B> pht_row_idx = val<PHT_B> { inst_pc >> 2 + LINE_B } ^ val<PHT_B> { bhr };
        pht_row_idx.fanout(hard<3> {});
        pht_idx = pht_row_idx;

        // 2. Read both Taken and Not-Taken PHT lines at Level 2
        arr<val<CTR_B>, LI> t_line = taken_pht.read(pht_row_idx);
        arr<val<CTR_B>, LI> nt_line = not_taken_pht.read(pht_row_idx);
        t_line.fanout(hard<2> {});
        nt_line.fanout(hard<2> {});
        reg_taken_line = t_line;
        reg_not_taken_line = nt_line;

        arr<val<1>, LI> choice_preds = choice_val_line.make_array(val<1> {});

        // Select the counter line based on choice table predictions
        arr<val<CTR_B>, LI> selected_line = [&](u64 i) {
            return select(choice_preds.fo1()[i], t_line[i], nt_line[i]);
        };
        selected_line.fanout(hard<2> {});
        pht_ctr_line = selected_line;

        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<2> {});
        reuse_prediction(offset != hard<LI - 1> {});

        // Level 2 prediction
        arr<val<1>, LI> pred_taken = [&](u64 i) {
            return selected_line[i] >> (CTR_B - 1);
        };
        return pred_taken.fo1().select(offset);
    }

    val<1> reuse_predict2(val<64> inst_pc)
    {
        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<2> {});
        reuse_prediction(offset != hard<LI - 1> {});

        arr<val<1>, LI> pred_taken = [&](u64 i) {
            return pht_ctr_line[i] >> (CTR_B - 1);
        };
        return pred_taken.fo1().select(offset);
    }

    inline val<CTR_B> update_counter(val<CTR_B> ctr, val<1> incr)
    {
        ctr.fanout(hard<6> {});
        val<CTR_B> increased = select(ctr == hard<ctr.maxval> {}, ctr, val<CTR_B> { ctr + 1 });
        val<CTR_B> decreased = select(ctr == hard<ctr.minval> {}, ctr, val<CTR_B> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    void update_condbr(val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        branch_offset[num_branches] = branch_pc.fo1() >> 2;
        branch_taken[num_branches] = taken.fo1();
        num_branches++;
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
        // val<1>& mispredict = block_end_info.is_mispredict.fo1();

        if (num_branches == 0)
        {
            return;
        }

        // Update BHR
        val<LI> new_history = branch_taken.concat().reverse() >> (LI - num_branches);
        bhr = (bhr << num_branches) + new_history.fo1();

        // Build branch mask and taken mask for the cacheline
        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            return valid_mask & branch_offset[i].decode().concat();
        };
        branch_onehot.fanout(hard<2> {});
        val<LI> branch_mask = branch_onehot.fold_or();
        branch_mask.fanout(hard<4> {});

        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fo1().fold_or();
        taken_mask.fanout(hard<2> {});

        // Compute new Choice and PHT lines
        arr<val<CTR_B>, LI> new_choice_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            val<CTR_B> updated_ctr = update_counter(choice_ctr_line[i], is_taken.fo1());
            return select(is_exec.fo1(), updated_ctr.fo1(), choice_ctr_line[i]);
        };
        new_choice_line.fanout(hard<2> {});

        arr<val<CTR_B>, LI> new_pht_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            val<CTR_B> updated_ctr = update_counter(pht_ctr_line[i], is_taken.fo1());
            return select(is_exec.fo1(), updated_ctr.fo1(), pht_ctr_line[i]);
        };
        new_pht_line.fanout(hard<3> {});

        // Update Taken PHT line conditionally
        arr<val<CTR_B>, LI> new_taken_line = [&](u64 i) {
            val<1> is_chosen = val<1> { choice_val_line >> i };
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> update_taken = is_exec.fo1() & is_chosen.fo1();
            return select(update_taken.fo1(), new_pht_line[i], reg_taken_line[i]);
        };
        new_taken_line.fanout(hard<2> {});

        // Update Not-Taken PHT line conditionally
        arr<val<CTR_B>, LI> new_not_taken_line = [&](u64 i) {
            val<1> is_chosen = val<1> { choice_val_line >> i };
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> update_not_taken = is_exec.fo1() & ~is_chosen.fo1();
            return select(update_not_taken.fo1(), new_pht_line[i], reg_not_taken_line[i]);
        };
        new_not_taken_line.fanout(hard<2> {});

        // Determine which updates are actually performed
        val<1> performing_choice_update = (new_choice_line.concat() != choice_ctr_line.concat());
        val<1> performing_taken_update = (new_taken_line.concat() != reg_taken_line.concat());
        val<1> performing_not_taken_update = (new_not_taken_line.concat() != reg_not_taken_line.concat());

        performing_choice_update.fanout(hard<2> {});
        performing_taken_update.fanout(hard<2> {});
        performing_not_taken_update.fanout(hard<2> {});

        need_extra_cycle(performing_choice_update | performing_taken_update | performing_not_taken_update);

        execute_if(performing_choice_update, [&]() {
            choice_table.write(choice_idx, new_choice_line);
        });

        execute_if(performing_taken_update, [&]() {
            taken_pht.write(pht_idx, new_taken_line);
        });

        execute_if(performing_not_taken_update, [&]() {
            not_taken_pht.write(pht_idx, new_not_taken_line);
        });

        num_branches = 0;
    }
};

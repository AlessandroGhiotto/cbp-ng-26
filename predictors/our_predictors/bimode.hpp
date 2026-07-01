#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"

using namespace hcm;

/*
 * Bi-Mode branch predictor. (reducing destructive aliasing)
 *
 * This predictor uses:
 * 1. A Choice Table (2-bit saturating counters) indexed by the branch PC.
 *    It predicts whether the branch is likely taken (bias = 1) or not-taken (bias = 0).
 * 2. Two PHT tables (each 2-bit counters):
 *    - Taken PHT: indexed by PC XOR BHR.
 *    - Not-Taken PHT: indexed by PC XOR BHR.
 *
 * To save energy, only the PHT selected by the choice table is read and updated.
 *
 * This implementation makes a 1-cycle prediction at level 1 and reuse at level 2.
 */

template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2>
struct bimode : predictor
{
    static constexpr u64 CHOICE_ENTRIES = 1 << CHOICE_B;
    static constexpr u64 PHT_ENTRIES = 1 << PHT_B;

    // Choice table and two directional PHTs
    ram<val<CTR_B>, CHOICE_ENTRIES> choice_table;
    ram<val<CTR_B>, PHT_ENTRIES> taken_pht;
    ram<val<CTR_B>, PHT_ENTRIES> not_taken_pht;

    // Registers to save prediction state for update
    reg<CHOICE_B> choice_idx;
    reg<CTR_B> choice_ctr;
    reg<1> choice_val;

    reg<PHT_B> pht_idx;
    reg<CTR_B> pht_ctr;

    // Branch History Register (BHR)
    reg<BHR_B> bhr;

    val<1> predict1(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<2> {});

        // 1. Index Choice Table using low PC bits
        val<CHOICE_B> c_idx = val<CHOICE_B> { inst_pc >> 2 };
        c_idx.fanout(hard<2> {});
        choice_idx = c_idx;

        val<CTR_B> c_ctr = choice_table.read(c_idx);
        c_ctr.fanout(hard<2> {});
        choice_ctr = c_ctr;

        // Determine if choice predictor is biased towards taken
        val<1> c_val = c_ctr >> (CTR_B - 1);
        c_val.fanout(hard<4> {});
        choice_val = c_val;

        // 2. Index PHTs using PC XOR BHR
        val<PHT_B> p_idx = val<PHT_B> { inst_pc >> 2 } ^ val<PHT_B> { bhr };
        p_idx.fanout(hard<3> {});
        pht_idx = p_idx;

        // 3. Conditionally read only the chosen PHT table to save read energy
        val<CTR_B> t_ctr = execute_if(c_val, [&]() { return taken_pht.read(p_idx); });
        val<CTR_B> nt_ctr = execute_if(~c_val, [&]() { return not_taken_pht.read(p_idx); });

        val<CTR_B> p_ctr = select(c_val, t_ctr.fo1(), nt_ctr.fo1());
        p_ctr.fanout(hard<2> {});
        pht_ctr = p_ctr;

        // 4. Return the direction prediction (MSB of selected counter)
        return p_ctr >> (CTR_B - 1);
    }

    val<1> predict2([[maybe_unused]] val<64> inst_pc) override
    {
        return pht_ctr >> (CTR_B - 1);
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        taken.fanout(hard<3> {});

        // 1. Calculate new choice counter value (always update choice table based on actual direction)
        val<CTR_B> new_choice_ctr = update_ctr(choice_ctr, taken);
        new_choice_ctr.fanout(hard<2> {});

        val<1> update_choice = val<1> { new_choice_ctr != choice_ctr };
        update_choice.fanout(hard<2> {});

        // 2. Calculate new PHT counter value
        val<CTR_B> new_pht_ctr = update_ctr(pht_ctr, taken);
        new_pht_ctr.fanout(hard<3> {});

        val<1> update_pht = val<1> { new_pht_ctr != pht_ctr };
        update_pht.fanout(hard<3> {});

        // Request extra cycle if updates are actually performed (SRAM write cycles)
        need_extra_cycle(update_choice | update_pht);

        // 3. Write updated counters to choice table
        execute_if(update_choice, [&]() {
            choice_table.write(choice_idx, new_choice_ctr);
        });

        // 4. Write updated counters to the selected PHT only
        val<1> update_taken_pht = update_pht & choice_val;
        val<1> update_not_taken_pht = update_pht & ~choice_val;

        execute_if(update_taken_pht.fo1(), [&]() {
            taken_pht.write(pht_idx, new_pht_ctr);
        });

        execute_if(update_not_taken_pht.fo1(), [&]() {
            not_taken_pht.write(pht_idx, new_pht_ctr);
        });

        // 5. Update Branch History Register (BHR)
        bhr = (bhr << 1) + taken;
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info) override
    {
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc) override
    {
        return hard<0> {};
    }

    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc) override
    {
        return hard<0> {};
    }
};

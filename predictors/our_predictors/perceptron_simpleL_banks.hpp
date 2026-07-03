#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include <bit>

using namespace hcm;

/*
 * perceptron_simple implements a very simple perceptron predictor
 * - take the PC and index in the table of weights
 * - take the BHR
 * - compute the weighted sum
 * - see if it greater than 0
 * - (train)
 *
 * PREDICT A LINE: instead of having a bigram with "(BHR_B + 1) * LI" bits per line
 *  we have "LI" banks of bits "(BHR_B + 1)""
 */

template <
    u64 PC_B = 8,
    u64 BHR_B = 32,
    u64 CTR_B = 8,
    u64 THRESHOLD = 83,
    u64 LINE_B = 2>
struct perceptron_simpleL_banks : predictor
{
    static constexpr u64 LI = 1 << LINE_B;
    static constexpr u64 PHT_ROWS = 1 << PC_B;
    static constexpr u64 RBITS = CTR_B + std::bit_width(BHR_B);

    // Banked weight tables: one table per cacheline instruction slot
    struct Bank
    {
        ram<arr<val<CTR_B, i64>, BHR_B + 1>, PHT_ROWS> weights;
        arr<reg<CTR_B, i64>, BHR_B + 1> reg_weights;
    } site[LI];

    // Registers to store state between prediction and update
    reg<PC_B> reg_index;
    arr<reg<RBITS, i64>, LI> reg_y;
    arr<reg<1>, LI> pred_taken;
    reg<PC_B> block_pc;

    // Global History Register (BHR)
    reg<BHR_B> bhr;

    // Record values from per-branch updates to be used in per-cacheline update logic
    u64 num_branches = 0;
    arr<reg<LINE_B>, LI> branch_offset;
    arr<reg<1>, LI> branch_taken;

    val<1> predict1(val<64> inst_pc)
    {
        // Reset branch counter
        num_branches = 0;

        inst_pc.fanout(hard<3> {});

        // Save line PC
        block_pc = inst_pc >> (2 + LINE_B);

        // Hash the PC to get the table index using fold_xor
        val<PC_B> index = (inst_pc >> 2).make_array(val<PC_B> {}).fold_xor();
        index.fanout(hard<LI + 1> {});
        reg_index = index;

        // Read the weight vector from each bank in parallel
        for (u64 i = 0; i < LI; i++)
        {
            if (i == LI - 1)
            {
                site[i].reg_weights = site[i].weights.read(index.fo1());
            }
            else
            {
                site[i].reg_weights = site[i].weights.read(index);
            }
        }

        // Compute dot products for all slots in the block
        arr<val<RBITS, i64>, LI> y_block = [&](u64 i) {
            arr<val<CTR_B, i64>, BHR_B + 1> terms = [&](u64 j) -> val<CTR_B, i64> {
                if (j == 0)
                {
                    return site[i].reg_weights[0];
                }
                else
                {
                    val<1> bhr_bit = val<1> { bhr >> (j - 1) };
                    val<CTR_B, i64> weight = site[i].reg_weights[j];
                    return select(bhr_bit, weight, -weight);
                }
            };
            return terms.fo1().fold_add();
        };
        y_block.fanout(hard<2> {});
        reg_y = y_block;

        // Compute predictions (taken if y >= 0)
        arr<val<1>, LI> preds = [&](u64 i) {
            return ~(y_block[i] >> hard<RBITS - 1> {});
        };
        pred_taken = preds;

        return predict(inst_pc);
    }

    val<1> predict(val<64> inst_pc)
    {
        val<LINE_B> offset = val<LINE_B> { inst_pc.fo1() >> 2 };
        offset.fanout(hard<2> {});
        reuse_prediction(offset != hard<LI - 1> {});
        return pred_taken.select(offset);
    }

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc.fo1());
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc.fo1());
    }

    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc.fo1());
    }

    void update_condbr(val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        branch_offset[num_branches] = branch_pc >> 2;
        branch_taken[num_branches] = taken;
        num_branches++;
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
        // Calculate cacheline row masks
        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            return valid_mask.fo1() & branch_offset[i].decode().concat();
        };
        branch_onehot.fanout(hard<2> {});
        val<LI> branch_mask = branch_onehot.fold_or();

        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fo1().fold_or();
        taken_mask.fanout(hard<2> {});

        // Compute which slots need an update
        arr<val<1>, LI> update_slots = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<1> pred = pred_taken[i];
            val<1> mispredicted = pred ^ taken_bit;

            val<RBITS, i64> y = reg_y[i];
            val<1> is_positive = ~(y >> hard<RBITS - 1> {});
            is_positive.fanout(hard<2> {});
            val<RBITS, i64> abs_y = select(is_positive, y, -y);
            val<1> below_threshold = (abs_y <= static_cast<i64>(THRESHOLD));

            return has_branch & (mispredicted | below_threshold);
        };

        val<LI> update_mask = update_slots.concat();
        update_mask.fanout(hard<2> {});

        val<1> performing_update = (update_mask != hard<0> {});

        need_extra_cycle(performing_update.fo1());

        // Convert masks to bit arrays
        arr<val<1>, LI> update_bits = update_mask.fo1().make_array(val<1> {});
        arr<val<1>, LI> taken_bits = taken_mask.fo1().make_array(val<1> {});

        for (u64 i = 0; i < LI; i++)
        {
            val<1> do_update = update_bits[i];
            do_update.fanout(hard<2> {});

            val<1> taken_bit = taken_bits[i];
            taken_bit.fanout(hard<BHR_B + 1> {});

            execute_if(do_update.fo1(), [&]() {
                arr<val<CTR_B, i64>, BHR_B + 1> new_weights = [&](u64 j) -> val<CTR_B, i64> {
                    val<CTR_B, i64> w_j = site[i].reg_weights[j];
                    w_j.fanout(hard<2> {});
                    val<CTR_B, i64> incr = select(w_j == hard<w_j.maxval> {}, w_j, val<CTR_B, i64> { w_j + 1 });
                    val<CTR_B, i64> decr = select(w_j == hard<w_j.minval> {}, w_j, val<CTR_B, i64> { w_j - 1 });

                    val<1> tk = (j == BHR_B) ? taken_bit.fo1() : taken_bit;

                    if (j == 0)
                    {
                        return select(tk, incr, decr);
                    }
                    else
                    {
                        val<1> bhr_bit = val<1> { bhr >> (j - 1) };
                        val<1> same_direction = ~(tk ^ bhr_bit);
                        return select(same_direction, incr, decr);
                    }
                };
                site[i].weights.write(reg_index, new_weights.fo1());
            });
        }

        // Update BHR at the very end
        val<LI> new_history = branch_taken.concat().reverse() >> (LI - num_branches);
        bhr = (bhr << num_branches) + new_history.fo1();
    }
};

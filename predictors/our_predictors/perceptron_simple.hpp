#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include <bit>

using namespace hcm;

template <
    u64 PC_B = 8,
    u64 BHR_B = 36,
    u64 CTR_B = 8,
    u64 THRESHOLD = 83>
struct perceptron_simple : predictor
{
    static constexpr u64 PHT_ROWS = 1 << PC_B;
    static constexpr u64 RBITS = CTR_B + std::bit_width(BHR_B);

    // Table of weight vectors (each entry has BHR_B + 1 weights)
    ram<arr<val<CTR_B, i64>, BHR_B + 1>, PHT_ROWS> weights;

    // Registers to store state between prediction and update
    reg<PC_B> reg_index;
    arr<reg<CTR_B, i64>, BHR_B + 1> reg_weights;
    reg<RBITS, i64> reg_y;
    reg<1> reg_pred;

    // Global History Register (BHR)
    reg<BHR_B> bhr;

    val<1> predict1(val<64> inst_pc)
    {
        // Hash the PC to get the table index
        val<PC_B> index = val<PC_B> { inst_pc >> 2 };
        reg_index = index;

        // Read the weight vector from RAM
        // +1 is for the bias
        arr<val<CTR_B, i64>, BHR_B + 1> w = weights.read(index);
        w.fanout(hard<2> {});
        reg_weights = w;

        // Compute the dot product y
        arr<val<CTR_B, i64>, BHR_B + 1> terms = [&](u64 j) -> val<CTR_B, i64> {
            if (j == 0)
            {
                return w[0]; // bias
            }
            else
            {
                val<1> bhr_bit = val<1> { bhr >> (j - 1) };
                val<CTR_B, i64> weight = w[j];
                return select(bhr_bit, weight, -weight); // w[j] ^ bhr[j]
            }
        };

        val<RBITS, i64> y = terms.fo1().fold_add();
        y.fanout(hard<2> {});
        reg_y = y;

        // Sign bit determines the prediction (taken if y >= 0)
        val<1> pred = ~(y.fo1() >> hard<RBITS - 1> {});
        reg_pred = pred;

        return pred;
    }

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        return reg_pred;
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        taken.fanout(hard<3> {});

        // mispredicted if prediction != actual outcome
        val<1> mispredicted = reg_pred ^ taken;

        // Compute absolute value of y
        val<1> is_positive = ~(reg_y >> hard<RBITS - 1> {});
        is_positive.fanout(hard<2> {});
        val<RBITS, i64> abs_y = select(is_positive, reg_y, -reg_y);
        val<1> below_threshold = (abs_y <= static_cast<i64>(THRESHOLD));

        // Train if prediction was wrong, or if dot product magnitude is below threshold
        val<1> perform_update = mispredicted | below_threshold;
        perform_update.fanout(hard<2> {});

        need_extra_cycle(perform_update);

        execute_if(perform_update.fo1(), [&]() {
            arr<val<CTR_B, i64>, BHR_B + 1> new_weights = [&](u64 j) -> val<CTR_B, i64> {
                val<CTR_B, i64> w_j = reg_weights[j];
                w_j.fanout(hard<2> {});
                val<CTR_B, i64> incr = select(w_j == hard<w_j.maxval> {}, w_j, val<CTR_B, i64> { w_j + 1 });
                val<CTR_B, i64> decr = select(w_j == hard<w_j.minval> {}, w_j, val<CTR_B, i64> { w_j - 1 });

                if (j == 0)
                {
                    return select(taken, incr, decr);
                }
                else
                {
                    val<1> bhr_bit = val<1> { bhr >> (j - 1) };
                    val<1> same_direction = ~(taken ^ bhr_bit);
                    return select(same_direction, incr, decr);
                }
            };
            weights.write(reg_index, new_weights.fo1());
        });

        // Update global history
        bhr = (bhr << 1) + taken.fo1();
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info) {}
    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc) { return val<1> { 0 }; }
    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc) { return val<1> { 0 }; }
};

#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

template <u64 BHR_B = 8, u64 CTR_B = 2, u64 LINE_B = 4>
struct gagL : predictor
{
    /*
     * Predict 2^LINE_B instruction per cycle using an SRAM array of simple CTR_B-bit (2-bit)
     * counters indexed by the BHR (BHR_B bits).
     */

    static constexpr u64 MAX_CTR = (1 << CTR_B) - 1;

    // LI = LI (instructions in a line)
    // LI = 2^LINE_B = #instructions predicted per cycle
    static constexpr u64 LI = 1 << LINE_B;
    static constexpr u64 PHT_ROWS = 1 << BHR_B;
    // each row contains an arry of LI saturating counters
    ram<arr<val<CTR_B>, LI>, PHT_ROWS> counters;
    // reg<CTR_B> counter;
    reg<BHR_B> bhr;

    // values to be used for update time [ONE PER INSTRUCTION]
    arr<reg<CTR_B>, LI> counter;
    arr<reg<1>, LI> saturated;
    arr<reg<1>, LI> pred_taken;

    // Record values from per-branch updates to be used in per-cacheline
    // update logic
    u64 num_branches = 0;               // counter for the branch
    arr<reg<LINE_B>, LI> branch_offset; // offset within the line
    arr<reg<1>, LI> branch_taken;       // T/NT

    // Full table lookup
    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        // reset branches ctr
        num_branches = 0;

        // get counter (a whole line!)

        counter = counters.read(bhr);

        // FOR EACH OFFSET
        for (u64 i = 0; i < LI; i++)
        {
            // check if ctr is saturated (is 0 or is full)
            saturated[i] = (counter[i] == hard<0> {}) | (counter[i] == hard<MAX_CTR> {});
            // get prediction (leftmost bit)
            pred_taken[i] = counter[i] >> (counter[i].size - 1);
        }

        return predict(inst_pc);
    };

    val<1> predict(val<64> inst_pc)
    {
        // select the prediction for the current offset

        // offset = pc/4  (since the pc increments by 4 per instructtion)
        // only low LINE_B bits matter!!
        // we have 16 branches, so 16 offsets (4 bits)
        val<LINE_B> offset = inst_pc >> 2;
        // if offset == #INSTR - 1
        // then we call reuse_prediction(0)
        // (last offset in the line => we will go to the next prediction block)
        reuse_prediction(offset != hard<LI - 1> {});
        // select the predictor (T/NT) for this instruction
        return pred_taken.select(offset);
    };

    // for reusepredict() method we just look at the pred_taken registers!
    // we do the full table lookup only at predict1()
    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc);
    };
    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc);
    }

    // No second level predictor
    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        return predict(inst_pc);
    }

    inline val<CTR_B> update_counter(val<CTR_B> ctr, val<1> incr)
    {
        ctr.fanout(hard<6> {});
        val<CTR_B> increased = select(ctr == hard<ctr.maxval> {}, ctr, val<CTR_B> { ctr + 1 });
        val<CTR_B> decreased = select(ctr == hard<ctr.minval> {}, ctr, val<CTR_B> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, [[maybe_unused]] val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        branch_offset[num_branches] = branch_pc >> 2; // STORE OFFSET
        branch_taken[num_branches] = taken;           // STORE TRUE OUTCOME
        num_branches++;
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
        // UPDATE BHR
        val<BHR_B> old_bhr = bhr;
        // branches are stored in reverse order
        // and we need to take only the last "num_branches" results
        val<LI> new_history = branch_taken.concat().reverse() >> (LI - num_branches);
        bhr = (bhr << num_branches) + new_history.fo1();

        // In order to perform updates for the current cacheline, we want a
        // mask with one bit corresponding to one instruction offset in the
        // line, but to start we have an array indexed by branch number.
        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            // `valid_mask` will have all bits set if this instricution was executed in
            // this prediction block
            // i.e if i < num_branches
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            // `decode` sets a bit corresponding to the value it is called on.
            // So, if `branch_offset[1]` holds a value of 5, this statement
            // will return 0b10000, assuming `i < num_branches`.
            // decode() => ONE-HOT VECTOR
            // concat() => make it a full line

            // the VALID_MASK is just used to make the AND with the one_hot vector.
            // for this reason we need a full val<LI> of ones.
            // we do a bit-wise AND
            // 0100.decode() -> (4) -> ..001000
            return valid_mask & branch_offset[i].decode().concat();
        };
        // Fold that array of 16-bit vals into a single 16-bit val with
        // bitwise-OR
        val<LI> branch_mask = branch_onehot.fold_or();

        // Similar to `branch_mask` above, but this time we only want the bits
        // in the mask set if this were a *taken* branch
        // SAME MECHANISM
        // replicate if it was taken or not and do bit-wise or with the BRANCH_ONEHOT
        // we get like branch_onehot but only for taken branches
        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fold_or();

        // Determine which offsets we want to update. We update the counter
        // of any offset which was a branch and that branch's counter was
        // either incorrect or NOT saturated.
        val<LI> incorrect = taken_mask ^ pred_taken.concat(); // not correct if Pred != trueRes
        val<LI> update_mask = branch_mask & (~saturated.concat() | incorrect);

        // Determine whether to perform an update - when the updated counter is
        // different than the read counter
        val<1> performing_update = (update_mask != hard<0> {});

        arr<val<CTR_B>, LI> new_counters = [&](u64 i) {
            return select(val<1> { update_mask >> i },
                          update_counter(counter[i], val<1> { taken_mask >> i }),
                          counter[i]);
        };

        // If we are doing an update, inform the simulator we need an extra
        // cycle to write the array (note this must be called *before* the
        // array write below, or it will fail at runtime with a message like
        // "single RAM access per cycle")
        need_extra_cycle(performing_update);

        // Finally, write back to the array (only if needed)
        execute_if(performing_update, [&]() {
            // ! HERE THE INDEX IS THE BHR (change it if needed)
            counters.write(old_bhr.fo1(), new_counters);
        });
    }
};

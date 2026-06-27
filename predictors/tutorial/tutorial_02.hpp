#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

struct tutorial_02 : predictor
{
    /*
     * Predict one instruction per cycle using an SRAM array of simple two-bit
     * counters indexed by a hashed PC.
     */

    // we have 64 val<2>. a val<2> is used as a 2-bit BHT 
    // 64 of them -> indexed with 6 bits adresses (each cell)
    ram<val<2>, 64> counters;
    reg<2> counter; // register to hold the counter value read from the SRAM array

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        // Hash the instruction PC to a 6-bit index by first chunking it into
        // an array of 6-bit values, then folding that array onto itself using
        // XOR. In order to reduce collisions
        val<6> index = inst_pc.make_array(val<6> {}).fold_xor(); 

        // Index into the array of 2-bit counters, saving the counter value to
        // a register
        counter = counters.read(index);

        // Use the top (LEFTMOST) bit of the counter to predict the branch's direction
        // 00 >> 1 -> 00 (0)
        // 01 >> 1 -> 00 (0)
        // 10 >> 1 -> 01 (1)
        // 11 >> 1 -> 01 (1)
        return counter >> 1;
    };

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        // re-use the same prediction for the second-level predictor
        return counter >> 1;
    }

    // Note: common.hpp contains a more generic version of a saturating counter
    // update, this is reproduced here for learning purposes.
    inline val<2> update_counter(val<2> counter, val<1> taken)
    {
        // Saturating counter means that:
        // - max_value + 1 |-> max_value
        //   x = x if x == max_value else x + 1
        // - min_value - 1 |-> min_value
        //   x = x if x == min_value else x - 1
        val<2> increased = select(counter == 3, counter, val<2> { counter + 1 });
        val<2> decreased = select(counter == 0, counter, val<2> { counter - 1 });
        // this is HW
        // we compute both options (increased and decreased) and select with a mux
        return select(taken, increased, decreased);
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, [[maybe_unused]] val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        // Calculate the new saturating counter value based on its previous
        // value and the executed direction of the branch
        val<2> newcounter = update_counter(counter, taken);

        // Determine whether to perform an update - when the updated counter is
        // different than the read counter
        val<1> performing_update = val<1> { newcounter != counter };

        // If we are doing an update, inform the simulator we need an extra
        // cycle to write the array (note this must be called *before* the
        // array write below, or it will fail at runtime with a message like
        // "single RAM access per cycle")
        need_extra_cycle(performing_update);

        // Update the SRAM array conditionally
        execute_if(performing_update, [&]() {
            val<6> index = branch_pc.make_array(val<6> {}).fold_xor();
            counters.write(index, newcounter);
        });
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
    }

    // reuse_predict1 and reuse_predict2 will never be called because this
    // predictor never calls reuse_prediction()
    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    };
    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    }
};

#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

template <u64 BHR_B = 8, u64 PC_B = 10, u64 CTR_B = 2>
struct pag : predictor
{

    /*
     * Predict one instruction per cycle using an SRAM array of simple CTR_B-bit (2-bit)
     * counters indexed by a BHR, which is chosen across 2^PC_B BHRs,
     * which are indexed with the PB_B lsb of the PC.
     */

    // we have 2^BHR_B counters of val<CTR_B>
    static constexpr u64 PHT_ROWS = 1 << BHR_B;
    static constexpr u64 BHR_ROWS = 1 << PC_B;
    ram<val<CTR_B>, PHT_ROWS> counters; // PATTERN HISTORY TABLE
    ram<val<BHR_B>, BHR_ROWS> bhrs;     // GLOBAL HISTORY TABLE
    reg<CTR_B> counter;
    reg<BHR_B> bhr;
    reg<PC_B> index;

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        // get BHR corresponding to the PB_B lsb of the PC
        // ! >>2 since we are counting istructions (last 2 bits are always 00)
        index = val<PC_B> { inst_pc >> 2 };
        bhr = bhrs.read(index);

        // Index into the array of counters, saving the counter value to
        // a register
        counter = counters.read(bhr);

        // Use the top (LEFTMOST) bit of the counter to predict the branch's direction
        return counter >> (counter.size - 1);
    };

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        // re-use the same prediction for the second-level predictor
        return counter >> (counter.size - 1);
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
        // Declare fanouts for variables used multiple times in this function
        // branch_pc.fanout(hard<1> {});
        bhr.fanout(hard<3> {});
        counter.fanout(hard<2> {});

        // get newcounter and see if we need to update
        val<CTR_B> newcounter = update_counter(counter, taken);
        val<1> performing_update_counter = val<1> { newcounter != counter };

        // same for bhr
        // (we could assume that it always change and don't check if it changes or not
        // but this is more efficient if the bhr is very small for example)
        val<BHR_B> newbhr = (bhr << 1) + taken;
        val<1> performing_update_bhr = val<1> { newbhr != bhr };

        need_extra_cycle(performing_update_counter | performing_update_bhr);

        // Update the SRAM arrays conditionally
        execute_if(performing_update_counter, [&]() {
            // we write in counter[bhr] (that is the cell we have selected also for reading)
            counters.write(bhr, newcounter);
        });

        execute_if(performing_update_bhr, [&]() {
            // the bhrs index instead is the k lsb bits of the PC
            // index = val<PC_B> { inst_pc >> 2 };
            bhrs.write(index, newbhr);
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

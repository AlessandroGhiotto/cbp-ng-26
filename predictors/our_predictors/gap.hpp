#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

template <u64 BHR_B = 4, u64 PC_B = 4, u64 CTR_B = 2>
struct gap : predictor
{
    /*
     * Predict one instruction per cycle using an SRAM array of simple CTR_B-bit (2-bit)
     * counters indexed by the PC_B lsb of the PC concatenated with a BHR (BHR_B bits).
     */

    // we have 2^BHR_B counters of val<CTR_B>
    static constexpr u64 B = BHR_B + PC_B;
    static constexpr u64 PHT_ROWS = 1 << B;
    ram<val<CTR_B>, PHT_ROWS> counters;
    reg<CTR_B> counter;
    reg<BHR_B> bhr;

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        val<B> index = concat(val<PC_B> { inst_pc.fo1() }, bhr);

        // Index into the array of counters, saving the counter value to
        // a register
        counter = counters.read(index.fo1());
        counter.fanout(hard<2> {});

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
        taken.fanout(hard<2> {});

        // update the BHR
        val<BHR_B> old_bhr = bhr;
        bhr = (bhr << 1) + taken;

        // Calculate the new saturating counter value based on its previous
        // value and the executed direction of the branch
        val<CTR_B> newcounter = update_counter(counter, taken);
        newcounter.fanout(hard<2> {});

        // Determine whether to perform an update - when the updated counter is
        // different than the read counter
        val<1> performing_update = val<1> { newcounter != counter };
        performing_update.fanout(hard<2> {});

        // If we are doing an update, inform the simulator we need an extra
        // cycle to write the array (note this must be called *before* the
        // array write below, or it will fail at runtime with a message like
        // "single RAM access per cycle")
        need_extra_cycle(performing_update);

        // Update the SRAM array conditionally
        execute_if(performing_update, [&]() {
            val<B> index = concat(val<PC_B> { branch_pc.fo1() }, old_bhr.fo1());
            counters.write(index.fo1(), newcounter);
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

#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

template <u64 BHR_B = 8, u64 PC_B = 10, u64 CTR_B = 2>
struct gshare_simple : predictor
{
    /*
     * Predict one instruction per cycle using an SRAM array of simple CTR_B-bit (2-bit)
     * counters indexed by the PC_B lsb of the PC XORed with a BHR (BHR_B bits).
     */

    // we have 2^BHR_B counters of val<CTR_B>
    static constexpr u64 B = std::max(BHR_B, PC_B);
    static constexpr u64 PHT_ROWS = 1 << B;
    ram<val<CTR_B>, PHT_ROWS> counters;
    reg<CTR_B> counter;
    reg<BHR_B> bhr;

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        // compute index
        // ! REMEMBER TO SHIFT BY 2 THE PC
        val<B> index = val<B> { inst_pc.fo1() >> 2 } ^ val<B> { bhr };

        // get ctr
        counter = counters.read(index.fo1());

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

        // Calculate the new saturating counter
        val<CTR_B> newcounter = update_counter(counter, taken);
        newcounter.fanout(hard<2> {});
        val<1> performing_update = val<1> { newcounter != counter };
        performing_update.fanout(hard<2> {});

        need_extra_cycle(performing_update);

        // Update the SRAM array conditionally
        execute_if(performing_update, [&]() {
            val<B> index = val<B> { branch_pc.fo1() >> 2 } ^ val<B> { old_bhr.fo1() };
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

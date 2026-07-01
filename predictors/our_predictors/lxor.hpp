#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

// lxor_general allows to have complement bitstring which is shorter than the bhr
// and a saturating counter of any bit length
template <u64 PC_B = 10, u64 BHR_B = 8, u64 COMPLEMENT_B = 8, u64 CTR_B = 2>
struct lxor_general : predictor
{

    /*
     * LXOR (Local eXclusive-OR) branch predictor.
     *
     * The predictor keeps a local history table indexed by static branch PC bits.
     * The selected local history is then concatenated with its bitwise complement
     * to index a single pattern history table of 2-bit saturating counters.
     */

    static_assert(BHR_B >= COMPLEMENT_B);
    static_assert(COMPLEMENT_B > 0);
    static_assert(PC_B > 0);
    static_assert(CTR_B > 0);

    // the BHR index a specific NHT (Next Hystory Table) in the PHT
    // the complement index the counters inside each NHT
    static constexpr u64 PHT_ROWS = 1 << (BHR_B + COMPLEMENT_B);
    // static constexpr u64 NHT_ROWS = 1 << COMPLEMENT_B;
    static constexpr u64 BHR_ROWS = 1 << PC_B;
    ram<val<CTR_B>, PHT_ROWS> counters; // PATTERN HISTORY TABLE
    ram<val<BHR_B>, BHR_ROWS> bhrs;     // GLOBAL HISTORY TABLE
    reg<CTR_B> counter;
    reg<BHR_B> bhr;
    // reg<COMPLEMENT_B> complement;
    // reg<PC_B> index;

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        // get BHR corresponding to the PB_B lsb of the PC
        // ! >>2 since we are counting istructions (last 2 bits are always 00)
        val<PC_B> index = val<PC_B> { inst_pc.fo1() >> 2 };
        bhr = bhrs.read(index.fo1());

        // get complement
        // val<PC_B> allones = val<1> { 1 }.replicate(hard<PC_B> {}).concat();
        // val<COMPLEMENT_B> complement = val<COMPLEMENT_B> { index ^ allones.fo1() };

        // get first the NHT (counters[index]) than the counter (read())
        val<COMPLEMENT_B> complement = val<COMPLEMENT_B> { ~bhr };
        counter = counters.read(concat(bhr, complement.fo1()));

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

        // get newcounter and see if we need to update
        val<CTR_B> newcounter = update_counter(counter, taken);
        newcounter.fanout(hard<2> {});
        val<1> performing_update_counter = val<1> { newcounter != counter };
        performing_update_counter.fanout(hard<2> {});

        // same for bhr
        // (we could assume that it always change and don't check if it changes or not
        // but this is more efficient if the bhr is very small for example)
        val<BHR_B> newbhr = (bhr << 1) + taken;
        newbhr.fanout(hard<2> {});
        val<1> performing_update_bhr = val<1> { newbhr != bhr };
        performing_update_bhr.fanout(hard<2> {});

        need_extra_cycle(performing_update_counter | performing_update_bhr);

        // Update the SRAM arrays conditionally
        execute_if(performing_update_counter, [&]() {
            // we write in counter[bhr] (that is the cell we have selected also for reading)
            val<COMPLEMENT_B> complement = val<COMPLEMENT_B> { ~bhr };
            counters.write(concat(bhr, complement.fo1()), newcounter);
        });

        execute_if(performing_update_bhr, [&]() {
            // the bhrs index instead is the k lsb bits of the PC
            val<PC_B> index = val<PC_B> { branch_pc.fo1() >> 2 };
            bhrs.write(index.fo1(), newbhr);
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

// fix the complement bitstring to be long as the original bhr
// fix the saturating counter to use 2 bits
template <u64 PC_B = 10, u64 BHR_B = 8>
struct lxor : lxor_general<PC_B, BHR_B, BHR_B, 2>
{
    // Inherit the constructor from the parent class
    using lxor_general<PC_B, BHR_B, BHR_B, 2>::lxor_general;
};

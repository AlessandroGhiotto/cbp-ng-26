#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"

using namespace hcm;

/*
 * LXOR (Local eXclusive-OR) branch predictor.
 *
 * The predictor keeps a local history table indexed by static branch PC bits.
 * The selected local history is then concatenated with its bitwise complement
 * to index a single pattern history table of 2-bit saturating counters.
 *
 * This implementation keeps level 1 simple and zero-latency by always
 * predicting not taken there, while level 2 performs the LXOR lookup.
 */

template <u64 LOG_GHT = 10, u64 HIST_BITS = 8>
struct lxor_vibe : predictor
{
    static_assert(LOG_GHT > 0);
    static_assert(HIST_BITS > 0);

    static constexpr u64 GHT_ENTRIES = 1 << LOG_GHT;
    static constexpr u64 PHT_BITS = 2 * HIST_BITS;
    static constexpr u64 PHT_ENTRIES = 1 << PHT_BITS;

    ram<val<HIST_BITS>, GHT_ENTRIES> ght;
    ram<val<2>, PHT_ENTRIES> pht;

    reg<LOG_GHT> ght_index;
    reg<HIST_BITS> local_history;
    reg<HIST_BITS> nht_index;
    reg<HIST_BITS> ctr_index;
    reg<PHT_BITS> pht_index;
    reg<2> counter;

    reg<1> branch_pending;
    reg<1> branch_taken;

    static val<LOG_GHT> pc_index(val<64> inst_pc)
    {
        // Use the low PC bits directly, as shown in the diagram.
        return val<LOG_GHT> { inst_pc >> 2 };
    }

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    }

    val<1> predict2(val<64> inst_pc)
    {
        ght_index = pc_index(inst_pc);
        local_history = ght.read(ght_index);
        local_history.fanout(hard<2> {});

        // The selected NHT is indexed by the local history bits.
        nht_index = local_history;
        ctr_index = ~local_history;
        pht_index = concat(nht_index, ctr_index);

        counter = pht.read(pht_index);
        counter.fanout(hard<2> {});

        return counter >> 1;
    }

    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc)
    {
        return counter >> 1;
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        branch_pending = hard<1> {};
        branch_taken = taken.fo1();

        // The predictor updates both the local history table and the PHT in
        // update_cycle(), so reserve a cycle before those writes happen.
        need_extra_cycle(hard<1> {});
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
        execute_if(branch_pending, [&]() {
            val<2> increased = select(counter == 3, counter, val<2> { counter + 1 });
            val<2> decreased = select(counter == 0, counter, val<2> { counter - 1 });
            val<2> new_counter = select(branch_taken, increased, decreased);
            val<HIST_BITS> new_history = val<HIST_BITS> { (local_history.fo1() << 1) ^ val<HIST_BITS> { branch_taken } };

            pht.write(pht_index, new_counter);
            ght.write(ght_index, new_history);

            branch_pending = hard<0> {};
        });
    }
};
